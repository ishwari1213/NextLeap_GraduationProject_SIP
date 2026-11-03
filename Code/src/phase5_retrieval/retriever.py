"""Phase 5 orchestration: question -> evidence bundle (architecture phase 5, steps 1 to 7).

    retriever = Retriever()
    bundle = retriever.retrieve("What leads investors to pause, reduce or stop a SIP?", app="Groww")

The model and the Chroma collections load once, on first use (or `warm_up()`), and are reused
for every question. Filters (`app`, `source`, `doc_type`) narrow the search, e.g. to Groww only.
"""
from __future__ import annotations

import logging
import time

import numpy as np

from src import config
from src.phase3_embedding.embedder import Embedder
from src.phase4_vector_store import store
from src.phase5_retrieval import scope
from src.phase5_retrieval.bundle import make_bundle
from src.phase5_retrieval.router import Router
from src.phase5_retrieval.search import INFO_PAGE, boost, build_where, search, supporting_count

log = logging.getLogger(__name__)

NO_SECTIONS_NOTE = ("Routing skipped: the sections collection is empty until the FR-7 page-data export "
                    "writes Data/site/sections_index.json, so the bundle has no route or section data.")


class Retriever:
    def __init__(self, embedder=None, excerpts=None, sections=None):
        self._embedder = embedder
        self._excerpts = excerpts
        self._sections = sections
        self._router = None
        self._last_updated = None
        self._tagged = False
        self._about: dict = {}

    def warm_up(self) -> "Retriever":
        if self._excerpts is None:
            if not config.VECTOR_DB_DIR.exists():
                raise RuntimeError(f"{config.VECTOR_DB_DIR} not found: run phase 4 first")
            db = store.client()
            self._excerpts = store.open_collection(db, config.EXCERPTS_COLLECTION)
            try:
                self._sections = store.open_collection(db, config.SECTIONS_COLLECTION)
            except Exception:  # an old store without the collection
                self._sections = None
        if self._embedder is None:
            self._embedder = Embedder()
        self._embedder.embed(["warm up"])  # load the model now, not on the first question
        self._router = Router(self._sections)
        about = {sid: e.get("about", "") for sid, e in self._router.entries.items() if e.get("about")}
        vectors = self._embedder.embed(list(about.values())) if about else []
        self._about = dict(zip(about, vectors))
        info = store.build_info(self._excerpts)
        self._last_updated = info.get("last_updated_from_sources")
        self._tagged = bool(info.get("tagged"))
        return self

    def info(self) -> dict:
        if self._router is None:
            self.warm_up()
        return {
            "excerpts": self._excerpts.count(),
            "sections": self._sections.count() if self._sections is not None else 0,
            "last_updated_from_sources": self._last_updated,
            "model": config.EMBEDDING_MODEL,
        }

    def retrieve(self, question: str, *, app: str | None = None, source: str | None = None,
                 doc_type: str | None = None) -> dict:
        if self._router is None:
            self.warm_up()
        started = time.monotonic()
        question = " ".join(question.split())
        filters = {k: v for k, v in (("app", app), ("source", source), ("doc_type", doc_type)) if v}
        common = {"last_updated": self._last_updated, "filters": filters}

        def elapsed() -> int:
            return int((time.monotonic() - started) * 1000)

        # 1-2. refuse before searching
        checked = scope.check_input(question)
        if checked.allowed:
            checked = scope.check_scope(question)
        if not checked.allowed:
            return make_bundle(checked.question, "out_of_scope", reason=checked.reason, detail=checked.detail,
                               timing_ms=elapsed(), **common)

        # 3. embed with the phase 3 model
        vector = self._embedder.embed([question])[0]

        # 4. route to a section
        notes: list[str] = []
        route, section_data = self._router.route(vector)
        if not self._router.available:
            notes.append(NO_SECTIONS_NOTE)
        elif route and route["score"] < config.ROUTE_MIN_SIMILARITY:
            return make_bundle(question, "out_of_scope", reason="off_topic", route=route, timing_ms=elapsed(),
                               detail=f"nearest section scored {route['score']} < {config.ROUTE_MIN_SIMILARITY}",
                               **common)

        # 5. search investor evidence, and information pages separately as context. The search vector
        #    blends in the routed section's `about` text, so abstract questions find concrete posts.
        search_vector = vector
        about_vec = self._about.get((route or {}).get("section"))
        if about_vec is not None and config.QUERY_SECTION_BLEND:
            blended = vector + config.QUERY_SECTION_BLEND * about_vec
            search_vector = blended / np.linalg.norm(blended)
        evidence_where = build_where(app, source, doc_type, exclude_doc_type=INFO_PAGE,
                                     sip_only=self._tagged and config.RETRIEVAL_SIP_ONLY)
        candidates = search(self._excerpts, search_vector, config.RETRIEVAL_CANDIDATES, evidence_where)
        candidates = boost(candidates, (route or {}).get("section"), config.SECTION_TAG_BOOST)
        context = [] if doc_type else search(self._excerpts, vector, config.RETRIEVAL_CONTEXT_EXCERPTS,
                                              build_where(app, source, INFO_PAGE))
        if route is None:  # no sections to judge relevance: use the best excerpt over the whole corpus
            best = search(self._excerpts, vector, 1, None) if filters else (candidates + context)
            best_score = max((c["score"] for c in best), default=0.0)
            if best_score < config.OFF_TOPIC_MAX_SIMILARITY:
                return make_bundle(question, "out_of_scope", reason="off_topic", timing_ms=elapsed(),
                                   detail=f"best excerpt scored {best_score} < {config.OFF_TOPIC_MAX_SIMILARITY}",
                                   notes=notes, **common)
        evidence = [c for c in candidates if c["score"] >= config.RETRIEVAL_MIN_SIMILARITY]
        context = [c for c in context if c["score"] >= config.RETRIEVAL_MIN_SIMILARITY]

        # 6. count supporting records
        supporting = supporting_count(evidence)
        status = "evidence" if supporting >= config.INSUFFICIENT_EVIDENCE_BELOW else "insufficient_evidence"
        detail = None if status == "evidence" else \
            f"{supporting} supporting records above {config.RETRIEVAL_MIN_SIMILARITY}; {config.INSUFFICIENT_EVIDENCE_BELOW} needed"

        # 7. bundle
        return make_bundle(question, status, detail=detail, route=route, section_data=section_data,
                           candidates=evidence, context=context, supporting_items=supporting, notes=notes,
                           timing_ms=elapsed(), **common)
