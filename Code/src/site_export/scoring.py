"""FR-6 opportunity scoring.

    Score = 100 x (0.40 x reach + 0.30 x severity + 0.15 x stage fit + 0.15 x segment fit)   (PRD)

The PRD names the four parts; their definitions here are the prototype's, shown on the Method page:
  reach        the opportunity's problem posts / the largest opportunity's problem posts
  severity     share of its posts stating an event that report stopping, pausing, reducing or
               considering stopping
  stage fit    share of its posts stating a stage that sit in the first 12 months (onboarding to
               months 7-12), the window the business metric covers
  segment fit  share of its posts stating experience that come from first-time investors
A part stated by fewer than 5 posts is left out and the other weights are rescaled (PRD).
An opportunity with fewer than 5 problem posts is not scored.
"""
from __future__ import annotations

from src import config

OPPORTUNITIES = [
    {"id": "reliable_instalments", "name": "Reliable instalments", "driver": "B",
     "failure_modes": ["instalment_failed", "debited_after_cancel_or_twice"]},
    {"id": "clear_returns", "name": "Clear returns and progress", "driver": "C",
     "failure_modes": ["confusing_returns_or_progress"]},
    {"id": "confidence_losses", "name": "Confidence through early losses", "driver": "C",
     "failure_modes": ["losses_shake_confidence"]},
    {"id": "flexible_controls", "name": "Flexible SIP controls", "driver": "D",
     "failure_modes": ["cannot_pause_or_change_amount", "amount_too_high"]},
    {"id": "easy_return", "name": "Easy return after a pause", "driver": "D", "failure_modes": [],
     "note": "No tag captures restarting after a pause, so this opportunity cannot be scored yet."},
]
CONTEXT_ONLY = ["app_bug", "withdrawal_problem", "support_not_resolving"]  # real problems, outside the SIP score
EARLY_STAGES = {"onboarding", "first_instalment", "months_2_6", "months_7_12"}
DROP_EVENTS = {"stopped", "paused", "reduced", "considering_stopping"}


def _part(posts: list[dict], field: str, unknown: str, hit) -> dict:
    stated = [p for p in posts if p[field] != unknown]
    n = len(stated)
    value = sum(1 for p in stated if hit(p[field])) / n if n else None
    return {"value": round(value, 3) if value is not None else None, "n": n,
            "kept": n >= config.MIN_POSTS_PER_PART}


def score(problem_posts: list[dict]) -> list[dict]:
    """One row per opportunity, best first; unscored ones last."""
    groups = {o["id"]: [p for p in problem_posts if p["failure_mode"] in o["failure_modes"]] for o in OPPORTUNITIES}
    largest = max((len(v) for v in groups.values()), default=0)
    rows = []
    for opp in OPPORTUNITIES:
        posts = groups[opp["id"]]
        n = len(posts)
        parts = {
            "reach": {"value": round(n / largest, 3) if largest else None, "n": n, "kept": n >= config.MIN_POSTS_PER_PART},
            "severity": _part(posts, "event", "not_stated", lambda v: v in DROP_EVENTS),
            "stage_fit": _part(posts, "stage", "not_stated", lambda v: v in EARLY_STAGES),
            "segment_fit": _part(posts, "experience", "not_stated", lambda v: v == "first_time"),
        }
        kept = {k: p for k, p in parts.items() if p["kept"] and p["value"] is not None}
        weight = sum(config.SCORE_WEIGHTS[k] for k in kept)
        value = round(100 * sum(config.SCORE_WEIGHTS[k] * p["value"] for k, p in kept.items()) / weight) \
            if n >= config.MIN_POSTS_PER_PART and weight else None
        if not opp["failure_modes"]:
            tag = "Not scored"
        elif value is None:
            tag = "Not scored"
        else:
            tag = "Scored" if n >= config.LOW_SAMPLE_BELOW else "Small sample"
        rows.append({
            "id": opp["id"], "name": opp["name"], "driver": opp["driver"], "failure_modes": opp["failure_modes"],
            "posts": n, "share_of_problem_posts": round(n / len(problem_posts), 3) if problem_posts else None,
            "parts": parts, "left_out": [k for k, p in parts.items() if not p["kept"]], "score": value, "tag": tag,
            "note": opp.get("note") or (f"Fewer than {config.MIN_POSTS_PER_PART} posts, so not scored."
                                        if value is None and opp["failure_modes"] else ""),
        })
    return sorted(rows, key=lambda r: (r["score"] is None, -(r["score"] or 0), -r["posts"]))
