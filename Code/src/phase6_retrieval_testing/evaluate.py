"""Phase 6: measure retrieval on the golden set (architecture phase 6). Never calls Mistral.

Golden set: Data/eval/golden_set.jsonl. Each in-scope item names the section it should route
to and a tag rule for what counts as relevant (`relevant_if`: field -> list of labels, or "any"
for any stated label; an excerpt is relevant if its record matches any field). This set is
AI-drafted from the PRD's questions and uses the engine's own tags as the relevance check, so a
person should review it; until then the hit rate is reported as provisional.

Metrics (architecture phase 6):
  top-3 hit rate        a relevant excerpt in the top 3 (PRD target 80% or more)
  out-of-scope refusals advice, returns and off-topic items come back out_of_scope (target 100%)
  routing accuracy      the bundle's section matches expected_section (reported, no target)
  personal data         personal data detectable in stored excerpts (target 0)
"""
from __future__ import annotations

from src.phase1_data_loading.pii import strip_pii
from src.tagging.taxonomy import FIELDS

PII_KINDS = ("EMAIL", "PHONE", "PAN", "AADHAAR", "ACCOUNT", "OTP")


def relevant(tags: dict | None, rule: dict) -> bool:
    if not tags or not tags.get("about_sip"):
        return False
    for field, wanted in rule.items():
        value = tags.get(field)
        unknown = FIELDS[field]["unknown"] if field in FIELDS else None
        if wanted == "any" and value not in (None, unknown):
            return True
        if isinstance(wanted, list) and value in wanted:
            return True
    return False


def evaluate(golden: list[dict], retrieve, tags: dict[str, dict], excerpts: list[dict]) -> dict:
    items, misses = [], []
    for g in golden:
        bundle = retrieve(g["question"])
        route = (bundle.get("route") or {}).get("section")
        top3 = bundle.get("excerpts", [])[:3]
        row = {"id": g["id"], "question": g["question"], "status": bundle["status"], "reason": bundle.get("reason"),
               "route": route, "expected_section": g.get("expected_section")}
        if g["out_of_scope"]:
            row["refused"] = bundle["status"] == "out_of_scope"
            if not row["refused"]:
                misses.append({**row, "problem": "should have been refused"})
        else:
            row["hit"] = any(relevant(tags.get(e["record_id"]), g["relevant_if"]) for e in top3)
            row["routed_ok"] = route == g.get("expected_section") if route else None
            row["top3"] = [{"record_id": e["record_id"], "score": e["score"], "text": e["text"][:120]} for e in top3]
            if not row["hit"]:
                misses.append({**row, "problem": "no relevant excerpt in the top 3"})
        items.append(row)

    in_scope = [r for r in items if "hit" in r]
    refusals = [r for r in items if "refused" in r]
    routed = [r for r in in_scope if r["routed_ok"] is not None]
    pii = sum(1 for e in excerpts if any(strip_pii(e["text"])[1].get(k) for k in PII_KINDS))
    hits = sum(r["hit"] for r in in_scope)
    return {
        "golden_set": "AI-drafted (16 discovery questions + 4 refusals); relevance judged by the engine's tags; "
                      "needs human review",
        "top3_hit_rate": round(hits / len(in_scope), 3) if in_scope else None,
        "top3_hits": hits, "in_scope_items": len(in_scope), "target": 0.80,
        "meets_target": bool(in_scope) and hits / len(in_scope) >= 0.80,
        "refusal_rate": round(sum(r["refused"] for r in refusals) / len(refusals), 3) if refusals else None,
        "refusals_ok": sum(r["refused"] for r in refusals), "refusal_items": len(refusals),
        "routing_accuracy": round(sum(r["routed_ok"] for r in routed) / len(routed), 3) if routed else None,
        "routed_items": len(routed),
        "personal_data_in_excerpts": pii,
        "items": items, "misses": misses,
    }
