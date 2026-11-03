"""Survey findings for the site pages (the PRD's primary research: 21 SIP investors, 23 responses).

Everything is counted from Data/survey/responses.jsonl (de-identified). Shares are of the SIP
investors who answered (Q2 = Yes). The survey is a small convenience sample, so every figure is
"n of 21", never a population percentage.

Investor patterns (UI spec, Segments page):
  The Watcher        checks weekly or more often (Q15)
  The Quiet Checker  checks monthly, rarely or only when the SIP is debited (Q15)
  The Cash-Squeezed  has considered stopping (Q17) for a cash or life reason (Q18)
Groups overlap.

Engine vs survey reading (Validation page), per theme:
  Supported           the engine finds the theme in at least 10 posts and at least 30% of investors report it
  Engine under-counts at least 30% of investors report it but it is under 5% of the engine's problem posts
  Not supported       the engine finds it but under 10% of investors report it
  Untested            the survey did not ask about it
"""
from __future__ import annotations

from collections import Counter

CHECK_ORDER = ["Multiple Times Per Day", "Daily", "Weekly", "Monthly", "Only When SIP Gets Debited", "Rarely"]
WEEKLY_OR_MORE = {"Multiple Times Per Day", "Daily", "Weekly"}
QUIET = {"Monthly", "Rarely", "Only When SIP Gets Debited"}
CASH_REASONS = {"Financial Emergency", "Job Loss", "Irregular Income", "Family Expenses", "Travel"}
MARKET_REASONS = {"Poor Returns", "Market Fall", "Fear of Losing Money", "Lack of Confidence",
                  "Better Investment Alternatives"}
FUTURE_CASH = {"Job Loss", "Income Reduction", "Financial Emergency", "Family Responsibilities"}
FUTURE_MARKET = {"Poor Returns", "Market Crash", "Lack of Confidence"}
PAUSED_STATEMENT = "I have paused/reduced SIPs due to uncertainty."
WORRY_STATEMENTS = {"I worry often but continue investing.", "I frequently reconsider my investment decisions."}


def _rows(counter: Counter, base: int, order: list[str] | None = None) -> list[dict]:
    keys = [k for k in order if k in counter] if order else [k for k, _ in counter.most_common()]
    return [{"key": k, "label": k, "n": counter[k], "base": base} for k in keys]


def _count(sip: list[dict], key: str, multi: bool = False) -> Counter:
    c = Counter()
    for r in sip:
        value = r.get(key)
        if multi:
            c.update(value or [])
        elif value not in (None, ""):
            c[value] += 1
    return c


def _verdict(engine_n: int | None, engine_share: float | None, survey_share: float | None) -> str:
    if survey_share is None:
        return "Untested"
    if engine_share is not None and survey_share >= 0.30 and engine_share < 0.05:
        return "Engine under-counts"
    if engine_n is not None and engine_n >= 10 and survey_share >= 0.30:
        return "Supported"
    if engine_n is not None and engine_n >= 10 and survey_share < 0.10:
        return "Not supported"
    return "Partly supported"


def build_survey(responses: list[dict], engine: dict) -> dict:
    """Survey sections for each page. `engine` holds the engine's counts for the comparison."""
    sip = [r for r in responses if r.get("q2") == "Yes"]
    n = len(sip)
    if not n:
        return {}
    considered = [r for r in sip if r.get("q17") == "Yes"]

    def reasons(r: dict) -> set[str]:
        return set(r.get("q18") or [])
    cash_only = sum(1 for r in considered if reasons(r) & CASH_REASONS and not reasons(r) & MARKET_REASONS)
    market_only = sum(1 for r in considered if reasons(r) & MARKET_REASONS and not reasons(r) & CASH_REASONS)
    both = sum(1 for r in considered if reasons(r) & MARKET_REASONS and reasons(r) & CASH_REASONS)
    future_cash = sum(1 for r in sip if set(r.get("q27") or []) & FUTURE_CASH)
    future_market = sum(1 for r in sip if set(r.get("q27") or []) & FUTURE_MARKET)
    active = sum(1 for r in sip if r.get("q25") == "Yes")
    checks = _count(sip, "q15")
    weekly = [r for r in sip if r.get("q15") in WEEKLY_OR_MORE]
    quiet = [r for r in sip if r.get("q15") in QUIET]
    squeezed = [r for r in considered if reasons(r) & CASH_REASONS]
    first_look = _count(sip, "q16")
    help_c = _count(sip, "q19", multi=True)
    fear = sum(1 for r in sip if "Fear of Losing Money" in (r.get("q23") or []))
    market_moves = sum(1 for r in sip if "Understanding Market Movements" in (r.get("q23") or []))
    returns_first = first_look["Profit/Loss"] + first_look["Return %"]
    ages, jobs = _count(sip, "q1"), _count(sip, "q4")
    top_age, top_job = (ages.most_common(1) or [("", 0)])[0][0], (jobs.most_common(1) or [("", 0)])[0][0]
    new_investors = sum(1 for r in sip if r.get("q13") in ("Less than 6 Months", "6-12 Months"))
    sample = {"n": n, "responses": len(responses), "top_age": top_age, "top_occupation": top_job,
              "under_a_year": new_investors,
              "note": f"Survey of {n} SIP investors ({len(responses)} responses), mostly aged {top_age} and "
                      f"{top_job.lower().replace(' employee', '')}; {new_investors} are under a year into their SIP. "
                      "A small convenience "
                      "sample: figures are 'n of " + str(n) + "', not population percentages."}

    def share(x: int) -> float:
        return round(x / n, 3)

    problems = engine.get("problem_posts") or 0
    comparison = [
        {"theme": "Failed instalments", "engine": f"{engine['instalments']} problem posts",
         "survey": "Not asked", "reading": "Untested"},
        {"theme": "Understanding returns and progress",
         "engine": f"{engine['returns_confusion']} SIP posts confused by returns or P&L",
         "survey": f"{returns_first} of {n} look at profit/loss or return % first; {market_moves} find market "
                   "movements hard to understand",
         "reading": _verdict(engine["returns_confusion"], None, share(returns_first))},
        {"theme": "Fear of losses", "engine": f"{engine['losses']} problem posts ({engine['losses'] / problems:.0%})"
         if problems else "0", "survey": f"{fear} of {n} name fear of losing money as a challenge",
         "reading": _verdict(engine["losses"], engine["losses"] / problems if problems else None, share(fear))},
        {"theme": "Cash-flow fit", "engine": f"{engine['cash']} SIP posts (amount too high or a cash-flow trigger)",
         "survey": f"{future_cash} of {n} say job loss, income cuts, emergencies or family duties would make them stop",
         "reading": _verdict(engine["cash"], engine["cash"] / problems if problems else None, share(future_cash))},
        {"theme": "Adjusting instead of quitting", "engine": f"{engine['controls']} problem posts on pausing or "
         "changing the amount", "survey": f"{len(considered)} of {n} have considered stopping, pausing or reducing",
         "reading": _verdict(engine["controls"], None, share(len(considered)))},
        {"theme": "Help outside the app", "engine": f"{engine['help']} SIP posts seeking help outside the app",
         "survey": f"{help_c['Investment App']} of {n} ask their investment app; {help_c['Google Search']} use Google, "
                   f"{help_c['Friends / Family']} friends or family, {help_c['YouTube']} YouTube",
         "reading": "Supported" if engine["help"] >= 10 and help_c["Investment App"] / n < 0.25 else "Partly supported"},
    ]

    return {
        "status": "computed",
        "sample": sample,
        "overview": {
            "surveyed": {"n": n, "responses": len(responses)},
            "considered_stopping": {"n": len(considered), "base": n},
            "future_cash": {"n": future_cash, "base": n},
            "active": {"n": active, "base": n},
            "insight": f"In the survey, {len(considered)} of {n} SIP investors have considered stopping, pausing or "
                       f"reducing; looking ahead, {future_cash} name job loss, income cuts, emergencies or family "
                       f"duties as what would make them stop, against {future_market} for poor returns, a crash or low "
                       "confidence.",
        },
        "journey": {
            "checking": _rows(checks, n, CHECK_ORDER), "weekly_or_more": len(weekly),
            "first_look": _rows(first_look, n), "expectation": _rows(_count(sip, "q12"), n),
            "returns_horizon": _rows(_count(sip, "q11"), n), "influence": _rows(_count(sip, "q7", multi=True), n),
            "help": _rows(help_c, n), "profile": _rows(_count(sip, "q29"), n),
        },
        "dropoffs": {
            "considered": len(considered), "active": active, "inactive": n - active,
            "why_considered": [{"key": "market", "label": "Returns or market worries only", "n": market_only, "base": len(considered)},
                               {"key": "cash", "label": "Cash flow or life events only", "n": cash_only, "base": len(considered)},
                               {"key": "both", "label": "Both", "n": both, "base": len(considered)}],
            "reasons": _rows(_count(considered, "q18", multi=True), len(considered)),
            "future": _rows(_count(sip, "q27", multi=True), n),
            "future_cash": future_cash, "future_market": future_market,
            "likelihood": [{"key": str(k), "label": f"{k} of 5", "n": _count(sip, "q28")[k], "base": n}
                           for k in (5, 4, 3, 2, 1)],
            "keep_going": _rows(_count(sip, "q26", multi=True), n),
        },
        "segments": {
            "patterns": [
                {"name": "The Watcher", "definition": "checks weekly or more often", "n": len(weekly),
                 "detail": f"{sum(1 for r in weekly if r.get('q17') == 'Yes')} have considered stopping"},
                {"name": "The Quiet Checker", "definition": "checks monthly, rarely or on debit day", "n": len(quiet),
                 "detail": f"{sum(1 for r in quiet if r.get('q17') == 'Yes')} have considered stopping; "
                           f"{sum(1 for r in quiet if r.get('q29') == PAUSED_STATEMENT)} say they paused or reduced"},
                {"name": "The Cash-Squeezed", "definition": "considered stopping over job loss, an emergency or family costs",
                 "n": len(squeezed),
                 "detail": f"{sum(1 for r in squeezed if r.get('q25') == 'Yes')} still active; "
                           f"{sum(1 for r in squeezed if (r.get('q28') or 0) >= 4)} rate continuing 4 or 5 of 5"},
            ],
            "profile": {
                "Age now": _rows(ages, n), "Age at first SIP": _rows(_count(sip, "q3"), n),
                "Occupation": _rows(jobs, n), "Source of money": _rows(_count(sip, "q5"), n),
                "Income regularity": _rows(_count(sip, "q6"), n), "Time investing": _rows(_count(sip, "q13"), n),
                "Platform": _rows(_count(sip, "q14"), n),
            },
        },
        "validation": {"comparison": comparison},
    }
