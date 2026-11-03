"""Steps 5 and 6: search the `excerpts` collection and count supporting records.

Scores are cosine similarities (1 - Chroma's cosine distance): 1 is identical, 0 unrelated.
Investor evidence (reviews, posts, comments) and information pages are searched separately:
information pages are context for definitions, never evidence (PRD), and their textbook
wording would otherwise crowd investor posts out of the top results. Supporting items are
distinct records, so two excerpts of one long post count once.
"""
from __future__ import annotations

import numpy as np

INFO_PAGE = "info_page"


SECTION_FIELDS = {  # the tag each routed section is about, for the optional rank boost
    "expectations": ["expectation"], "stages": ["stage"], "checking": ["checking"], "confusion": ["confusion"],
    "outside-the-app": ["help_seeking"], "failure-modes": ["failure_mode"], "triggers": ["trigger"],
    "continuers": ["event"], "first-time": ["experience"], "opportunities": ["failure_mode"],
    "segments": ["income", "age", "money_source", "influence", "residency", "experience"],
}


def build_where(app: str | None = None, source: str | None = None, doc_type: str | None = None, *,
                exclude_doc_type: str | None = None, sip_only: bool = False) -> dict | None:
    conditions = [{field: value} for field, value in (("app", app), ("source", source), ("doc_type", doc_type))
                  if value]
    if exclude_doc_type and not doc_type:
        conditions.append({"doc_type": {"$ne": exclude_doc_type}})
    if sip_only:
        conditions.append({"about_sip": True})
    if not conditions:
        return None
    return conditions[0] if len(conditions) == 1 else {"$and": conditions}


def search(collection, vector: np.ndarray, k: int, where: dict | None = None) -> list[dict]:
    """The k nearest excerpts, best first, each with its score and metadata."""
    result = collection.query(query_embeddings=vector[None, :], n_results=k, where=where,
                              include=["documents", "metadatas", "distances"])
    candidates = []
    for chunk_id, text, meta, distance in zip(result["ids"][0], result["documents"][0],
                                              result["metadatas"][0], result["distances"][0]):
        meta = meta or {}
        candidates.append({
            "chunk_id": chunk_id,
            "record_id": meta.get("record_id", ""),
            "score": round(1.0 - float(distance), 4),
            "source": meta.get("source", ""),
            "app": meta.get("app") or None,
            "doc_type": meta.get("doc_type", ""),
            "date": meta.get("date") or None,
            "url": meta.get("url", ""),
            "tags": meta.get("tags", ""),
            "text": text,
        })
    return candidates


def boost(candidates: list[dict], section: str | None, amount: float) -> list[dict]:
    """Reorder candidates, favouring those tagged for the routed section; scores stay as they are."""
    fields = SECTION_FIELDS.get(section or "", [])
    if not amount or not fields:
        return candidates

    def rank(c: dict) -> float:
        stated = any(f"{field}:" in c.get("tags", "") for field in fields)
        return c["score"] + (amount if stated else 0.0)
    return sorted(candidates, key=rank, reverse=True)


def supporting_count(candidates: list[dict]) -> int:
    return len({c["record_id"] for c in candidates if c["doc_type"] != INFO_PAGE})
