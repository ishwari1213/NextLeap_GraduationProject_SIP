"""Phase 4 entry point: Data/chunks/ + Data/embeddings/ -> Data/vector_db/chroma/.

Run from the Code/ folder:
    python -m src.phase4_vector_store.run

Collections
  excerpts  id = chunk_id; the phase 3 vector; the excerpt text; metadata record_id, source,
            app, url, date, doc_type, tags, token_count (+ row_hash, used to skip unchanged rows)
  sections  id = section_id; for routing in phase 5 (empty until the FR-7 export exists)

Each collection carries its build information, including `last_updated_from_sources`, the
date answers show as "Last updated from sources" (PRD FR-10).

Checks the architecture's "done when" conditions and exits with code 1 if any fails:
  * collection counts match phase 2 (excerpts) and phase 3 (sections)
  * a sample query returns excerpts with every metadata field filled
"""
from __future__ import annotations

import json
import logging
import sys
import time

from src import config
from src.jsonl import read_jsonl
from src.phase1_data_loading.loaders.common import now_iso
from src.phase3_embedding.cache import VectorCache, text_key
from src.phase3_embedding.run import load_sections
from src.phase4_vector_store import store

log = logging.getLogger("phase4")

REQUIRED_FILLED = ("record_id", "source", "url", "date", "doc_type")  # may never be empty
SAMPLE_QUERIES = 5


def sources_fetched_at() -> str | None:
    """When phase 1 last fetched the sources (Data/cleaned/load_report.json)."""
    try:
        return json.loads(config.LOAD_REPORT_FILE.read_text(encoding="utf-8")).get("run_at")
    except (OSError, ValueError):
        return None


def sample_query_check(collection, chunks: list[dict], vectors) -> dict:
    """Query with a few excerpts' own vectors: each must come back first, with full metadata."""
    if not chunks:
        return {"sample_queries": 0, "sample_not_found": 0, "sample_missing_metadata": 0}
    picks = sorted({round(i * (len(chunks) - 1) / max(SAMPLE_QUERIES - 1, 1)) for i in range(SAMPLE_QUERIES)})
    result = collection.query(query_embeddings=vectors[picks], n_results=3,
                              include=["metadatas", "distances", "documents"])
    not_found = missing = 0
    for row, i in enumerate(picks):
        ids, dists, metas = result["ids"][row], result["distances"][row], result["metadatas"][row]
        # an identical text elsewhere has the same vector, so accept any distance-0 hit
        if not (chunks[i]["chunk_id"] in ids and dists[0] < 1e-4):
            not_found += 1
        for meta in metas:
            meta = meta or {}
            if any(f not in meta for f in store.EXCERPT_FIELDS) or any(not meta.get(f) for f in REQUIRED_FILLED):
                missing += 1
    return {"sample_queries": len(picks), "sample_not_found": not_found, "sample_missing_metadata": missing}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    for noisy in ("chromadb", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    started = time.monotonic()

    # --- inputs: phase 2 excerpts and phase 3 vectors ----------------------------------------
    if not config.CHUNKS_FILE.exists():
        log.error("%s not found: run phase 2 first", config.CHUNKS_FILE)
        return 1
    chunks = list(read_jsonl(config.CHUNKS_FILE))
    cache = VectorCache.load(config.EMBEDDING_VECTORS_FILE, config.EMBEDDING_KEYS_FILE,
                             config.EMBEDDING_MODEL, config.EMBEDDING_DIM)
    keys = [text_key(c["text"]) for c in chunks]
    sections, sections_note = load_sections()
    section_keys = [text_key(s["text"]) for s in sections]
    missing = sum(1 for k in keys + section_keys if k not in cache)
    if missing:
        log.error("%d excerpts or sections have no vector: run phase 3 first (python -m src.phase3_embedding.run)",
                  missing)
        return 1
    if sections_note:
        log.warning("Sections collection left empty: %s", sections_note)

    fetched = sources_fetched_at()
    built = now_iso()
    # FR-5 tags, when tagging has run: each excerpt carries its record's tags as metadata
    tags = {t["record_id"]: t for t in read_jsonl(config.TAGS_FILE)} if config.TAGS_FILE.exists() else {}
    tagged = bool(tags) and all(c["record_id"] in tags for c in chunks if c["doc_type"] != "info_page")

    info = {
        "built_at": built,
        "sources_fetched_at": fetched or "",
        "last_updated_from_sources": (fetched or built)[:10],
        "model": config.EMBEDDING_MODEL,
        "dim": config.EMBEDDING_DIM,
        "tagged": tagged,
    }
    if tags and not tagged:
        log.warning("Some excerpts have no tags yet: run tagging (python -m src.tagging.run); tags left out")

    # --- write ---------------------------------------------------------------------------------
    db = store.client()
    excerpts_col = store.get_or_create(db, config.EXCERPTS_COLLECTION)
    excerpt_vectors = cache.get(keys)
    excerpt_result = store.sync(
        excerpts_col,
        ids=[c["chunk_id"] for c in chunks],
        vectors=excerpt_vectors,
        documents=[c["text"] for c in chunks],
        metadatas=[store.excerpt_metadata(c, tags.get(c["record_id"]) if tagged else None) for c in chunks],
    )
    excerpts_col.modify(metadata={**info, "rows": len(chunks)})

    sections_col = store.get_or_create(db, config.SECTIONS_COLLECTION)
    section_result = store.sync(
        sections_col,
        ids=[s["section_id"] for s in sections],
        vectors=cache.get(section_keys) if sections else excerpt_vectors[:0],
        documents=[s["text"] for s in sections],
        metadatas=[store.section_metadata(s) for s in sections],
    )
    sections_col.modify(metadata={**info, "rows": len(sections)})

    # --- checks --------------------------------------------------------------------------------
    space = (excerpts_col.configuration_json.get("hnsw") or {}).get("space") \
        if hasattr(excerpts_col, "configuration_json") else "cosine"
    checks = {
        "excerpt_count_mismatch": abs(excerpts_col.count() - len(chunks)),
        "section_count_mismatch": abs(sections_col.count() - len(sections)),
        "not_cosine": 0 if space == "cosine" else 1,
    }
    sample = sample_query_check(excerpts_col, chunks, excerpt_vectors)
    checks.update({k: v for k, v in sample.items() if k != "sample_queries"})

    report = {
        "run_at": built,
        "path": config.VECTOR_DB_DIR.relative_to(config.PROJECT_DIR).as_posix(),
        "build_info": info,
        "excerpts": {"rows": excerpts_col.count(), **excerpt_result},
        "sections": {"rows": sections_col.count(), **section_result, "note": sections_note},
        "sample_queries": sample["sample_queries"],
        "seconds": round(time.monotonic() - started, 1),
        "checks": checks,
    }
    config.VECTOR_STORE_REPORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.VECTOR_STORE_REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nPhase 4 summary")
    for name in ("excerpts", "sections"):
        r = report[name]
        print(f"{name:<9} rows {r['rows']:>6} | added {r['added']}, updated {r['updated']}, "
              f"unchanged {r['unchanged']}, deleted {r['deleted']}")
    print(f"Last updated from sources: {info['last_updated_from_sources']} | {report['seconds']}s")
    print("Checks: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in checks.items()))
    if sections_note:
        print(f"Note: sections collection is empty: {sections_note}")
    print(f"Vector DB -> {report['path']}")

    failed = {k: v for k, v in checks.items() if v}
    if failed:
        log.error("Phase 4 checks failed: %s", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
