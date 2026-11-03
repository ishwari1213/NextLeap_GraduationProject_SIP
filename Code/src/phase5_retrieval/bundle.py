"""Step 7: the evidence bundle handed to the answer step (architecture phase 5).

status   evidence               enough supporting records; answer from `excerpts` + `section_data`
         insufficient_evidence  fewer than 15 supporting records (FR-12); say what data would help
         out_of_scope           refused before or after search; `reason` says why:
                                personal_data | investment_advice | returns_or_projection |
                                individual | off_topic
"""
from __future__ import annotations

from src import config

DECLINE_WITH_LINKS = {"investment_advice", "returns_or_projection"}


def make_bundle(question: str, status: str, *, reason: str | None = None, detail: str | None = None,
                route: dict | None = None, section_data: dict | None = None, candidates: list[dict] | None = None,
                context: list[dict] | None = None, supporting_items: int = 0, last_updated: str | None = None,
                filters: dict | None = None, notes: list[str] | None = None, timing_ms: int | None = None) -> dict:
    candidates = candidates or []
    return {
        "question": question,
        "status": status,
        "reason": reason,
        "detail": detail,
        "route": route,
        "page_link": f"{route['page']} → {route['title']}" if route and route.get("page") else None,
        "section_data": section_data,
        "supporting_items": supporting_items,
        "evidence_needed": config.INSUFFICIENT_EVIDENCE_BELOW,
        "candidates_above_cutoff": len(candidates),
        "excerpts": candidates[:config.RETRIEVAL_PROMPT_EXCERPTS],  # investor evidence, best first
        "context": context or [],  # information-page passages: definitions only, never evidence
        "decline_links": config.OFFICIAL_LINKS if reason in DECLINE_WITH_LINKS else [],
        "filters": filters or {},
        "last_updated": last_updated,
        "notes": notes or [],
        "timing_ms": timing_ms,
    }
