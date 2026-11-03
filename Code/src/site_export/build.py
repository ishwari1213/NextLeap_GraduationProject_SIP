"""FR-7 page data: records + tags + phase reports -> one JSON file per page + sections_index.json.

Every value carries its count `n`, a `sample` tag (ok, or low under 10 posts) and a `status`
(computed, or not_computed with its reason and missing step), as the UI spec's data contract
asks. The site reads only these files and the phase reports, so no number is typed into a page.

Evidence = every tagged record except information pages. SIP posts = evidence tagged
about_sip. Problem posts = SIP posts with a failure mode. "Groww only" = Groww's store reviews
plus forum and Reddit posts that name Groww (the competitor-review question is still open, so
the Overview shows both scopes).
"""
from __future__ import annotations

from collections import Counter

from src import config
from src.site_export import scoring
from src.site_export.survey import build_survey
from src.tagging.taxonomy import FIELDS, SEGMENT_FIELDS

LOW = config.LOW_SAMPLE_BELOW
SURVEY = "loading the investor survey (python -m src.survey.load) from Docs/SIP Investor Behavior Survey.csv"
HUMAN = "a person labels a sample of posts (Data/eval/human_labels.csv) so the engine's tags can be compared"
GOLDEN = "the phase 6 golden-set run (python -m src.phase6_retrieval_testing.run)"

PRETTY = {
    "before_starting": "Before starting", "first_instalment": "First instalment", "months_2_6": "Months 2–6",
    "months_7_12": "Months 7–12", "after_year_1": "After year 1", "considering_stopping": "Considering stopping",
    "returns_or_pnl": "Returns or P&L", "nav_or_units": "NAV or units", "sip_dates": "SIP dates",
    "under_25": "Under 25", "25_to_44": "25 to 44", "45_plus": "45 or older", "nri": "NRI",
    "youtube": "YouTube", "youtube_or_finfluencer": "YouTube or finfluencer", "other_apps_or_amc": "Other apps or AMC",
    "debited_after_cancel_or_twice": "Debited after cancel or twice", "cannot_pause_or_change_amount":
    "Cannot pause or change amount", "confusing_returns_or_progress": "Confusing returns or progress",
    "losses_shake_confidence": "Losses shake confidence", "support_not_resolving": "Support not resolving",
    "charges_and_tax": "Charges and tax", "cash_flow_or_life": "Cash flow or life event",
    "money_source": "Source of money", "help_seeking": "Help outside the app",
}
SOURCE_LABELS = {"play_store": "Google Play", "app_store": "App Store", "forums": "Forums", "reddit": "Reddit",
                 "team_bhp": "Team-BHP", "youtube": "YouTube"}


def pretty(key: str) -> str:
    return PRETTY.get(key, key.replace("_", " ").capitalize())


def sample(n: int) -> str:
    return "low" if n < LOW else "ok"


def stat(n: int, base: int | None = None) -> dict:
    return {"status": "computed", "n": n, "base": base,
            "share": round(n / base, 3) if base else None, "sample": sample(n)}


def not_computed(reason: str, missing_step: str) -> dict:
    return {"status": "not_computed", "reason": reason, "missing_step": missing_step}


def dist(posts: list[dict], field: str, *, with_problem: bool = False) -> dict:
    unknown = FIELDS[field]["unknown"]
    counts = Counter(p[field] for p in posts if p[field] != unknown)
    rows = []
    for key, n in counts.most_common():
        row = {"key": key, "label": pretty(key), "n": n, "sample": sample(n)}
        if with_problem:
            row["with_problem"] = sum(1 for p in posts if p[field] == key and p["failure_mode"] != "none")
        rows.append(row)
    return {"status": "computed", "rows": rows, "stated": sum(counts.values()), "base": len(posts)}


def month(iso: str | None) -> str:
    from datetime import date
    try:
        return date.fromisoformat((iso or "")[:10]).strftime("%b %Y")
    except ValueError:
        return ""


def quotes(posts: list[dict], failure_mode: str, k: int = 3) -> list[dict]:
    """De-identified quotes of at most 25 words, labelled with source and month only (UI spec rule 4)."""
    pool = [p for p in posts if p["failure_mode"] == failure_mode and 8 <= len(p["text"].split()) <= 60]
    pool.sort(key=lambda p: p.get("date") or "", reverse=True)
    out, seen = [], set()
    for p in pool:
        words = " ".join(p["text"].split()).split()
        text = " ".join(words[:25]) + ("…" if len(words) > 25 else "")
        if text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append({"text": text, "source": SOURCE_LABELS.get(p["source"], p["source"]), "month": month(p.get("date"))})
        if len(out) == k:
            break
    return out


def _label_numbers(section_id: str, nums: dict, opportunities: list[dict]) -> dict:
    """Key numbers whose labels say what each number is, so the answer step cannot mistake a
    score for a post count."""
    if section_id == "opportunities":
        out = {}
        for o in opportunities:
            if o["score"] is not None:
                out[f"{o['name']}: opportunity score (0-100)"] = o["score"]
            out[f"{o['name']}: problem posts"] = o["posts"]
        return out
    return {f"{label}: posts": value for label, value in nums.items()}


def is_groww(p: dict) -> bool:
    return p.get("app") == "Groww" or (not p.get("app") and "groww" in p["text"].lower())


def build(records: list[dict], tags: dict[str, dict], reports: dict) -> dict[str, dict]:
    posts = [{**r, **tags[r["id"]]} for r in records if r["source"] != "info_pages" and r["id"] in tags]
    sip = [p for p in posts if p["about_sip"]]
    problems = [p for p in sip if p["failure_mode"] != "none"]
    scopes = {"all": problems, "groww": [p for p in problems if is_groww(p)]}
    common = {"generated_at": reports.get("generated_at"), "last_updated": reports.get("last_updated")}

    # ---- overview ---------------------------------------------------------------------------
    opportunities = {name: scoring.score(scope) for name, scope in scopes.items()}
    fm_rows = {name: dist(scope, "failure_mode") for name, scope in scopes.items()}
    for rows in fm_rows.values():
        for row in rows["rows"]:
            row["context_only"] = row["key"] in scoring.CONTEXT_ONLY
    tree = [
        ("A", "Set-up works", [p for p in problems if p["stage"] in ("before_starting", "onboarding")]),
        ("B", "Instalments keep succeeding",
         [p for p in problems if p["failure_mode"] in ("instalment_failed", "debited_after_cancel_or_twice")]),
        ("C", "Understands progress and keeps confidence",
         [p for p in problems if p["failure_mode"] in ("confusing_returns_or_progress", "losses_shake_confidence")]),
        ("D", "Can adjust instead of quitting",
         [p for p in problems if p["failure_mode"] in ("cannot_pause_or_change_amount", "amount_too_high")]),
        ("E", "Gets help when stuck",
         [p for p in sip if p["failure_mode"] == "support_not_resolving" or p["help_seeking"] != "none"]),
    ]
    top = next((o for o in opportunities["all"] if o["score"] is not None), None)
    context_n = sum(1 for p in problems if p["failure_mode"] in scoring.CONTEXT_ONLY)
    expect = Counter(p["expectation"] for p in sip)
    later = sum(1 for p in sip if p["stage"] in ("months_2_6", "months_7_12"))
    first_time = [p for p in sip if p["experience"] == "first_time"]
    insights = []
    if top:
        insights.append(f"{top['name']} scores highest ({top['score']}): {top['posts']} of {len(problems)} problem "
                        f"posts ({top['posts'] / len(problems):.0%}).")
    if problems:
        insights.append(f"{context_n} problem posts ({context_n / len(problems):.0%}) are app bugs, withdrawals or "
                        "support issues; they are real but sit outside the SIP opportunity score.")
    insights.append(f"Expectation is mostly long term: {expect['long_term_growth']} SIP posts expect long-term growth, "
                    f"{expect['quick_gains']} expect quick gains.")
    insights.append(f"Evidence is thin where the metric lives: {later} SIP posts sit in months 2 to 12, and "
                    f"{len(first_time)} come from first-time investors "
                    f"({sum(1 for p in first_time if p['failure_mode'] != 'none')} of them state a problem).")

    # ---- the investor survey (primary research), beside the engine's counts -----------------
    survey = build_survey(reports.get("survey_rows") or [], {
        "problem_posts": len(problems),
        "instalments": sum(1 for p in problems if p["failure_mode"] in ("instalment_failed", "debited_after_cancel_or_twice")),
        "returns_confusion": sum(1 for p in sip if p["confusion"] == "returns_or_pnl"
                                 or p["failure_mode"] == "confusing_returns_or_progress"),
        "losses": sum(1 for p in problems if p["failure_mode"] == "losses_shake_confidence"),
        "cash": sum(1 for p in sip if p["failure_mode"] == "amount_too_high" or p["trigger"] == "cash_flow_or_life"),
        "controls": sum(1 for p in problems if p["failure_mode"] == "cannot_pause_or_change_amount"),
        "help": sum(1 for p in sip if p["help_seeking"] != "none"),
    })

    def survey_part(page: str, reason: str) -> dict:
        if not survey:
            return not_computed(reason, SURVEY)
        return {"status": "computed", "sample": survey["sample"], **survey[page]}

    if survey:
        insights.append(survey["overview"]["insight"])
    overview = {
        **common,
        "tiles": {"posts": stat(len(posts)), "sip_posts": stat(len(sip), len(posts)),
                  "problem_posts": stat(len(problems), len(sip)),
                  "sources": {"status": "computed", "n": len({p["source"] for p in sip})}},
        "opportunities": opportunities,
        "scope_sizes": {name: len(scope) for name, scope in scopes.items()},
        "failure_modes": fm_rows,
        "metric_tree": [{"id": i, "label": label, **stat(len(group))} for i, label, group in tree],
        "insights": insights,
        "survey": survey_part("overview", "Survey findings sit beside these counts in the PRD."),
    }

    # ---- journey ----------------------------------------------------------------------------
    conf, helpd = dist(sip, "confusion"), dist(sip, "help_seeking")
    journey = {
        **common,
        "tiles": {"long_term": stat(expect["long_term_growth"], len(sip)), "quick_gains": stat(expect["quick_gains"]),
                  "checking_stated": stat(sum(1 for p in sip if p["checking"] != "not_stated"), len(sip)),
                  "top_confusion": conf["rows"][0] if conf["rows"] else None,
                  "top_help": helpd["rows"][0] if helpd["rows"] else None},
        "stages": dist(sip, "stage", with_problem=True),
        "expectations": dist(sip, "expectation"),
        "checking": dist(sip, "checking"),
        "confusion": conf,
        "help_seeking": helpd,
        "survey": survey_part("journey", "Survey answers on checking, feelings and help-seeking."),
    }

    # ---- drop-offs --------------------------------------------------------------------------
    events = dist(sip, "event")
    ev = Counter(p["event"] for p in sip)
    drop = [p for p in sip if p["event"] in scoring.DROP_EVENTS]
    cont = [p for p in sip if p["event"] == "continued"]

    def profile(group: list[dict]) -> dict:
        return {"n": len(group), "sample": sample(len(group)),
                "failure_modes": dist(group, "failure_mode")["rows"][:3],
                "triggers": dist(group, "trigger")["rows"][:3]}

    instal = sum(1 for p in problems if p["failure_mode"] in ("instalment_failed", "debited_after_cancel_or_twice"))
    losses = sum(1 for p in problems if p["failure_mode"] == "losses_shake_confidence")
    dropoffs = {
        **common,
        "tiles": {"event_stated": stat(events["stated"], len(sip)), "stopped": stat(ev["stopped"]),
                  "considering": stat(ev["considering_stopping"]), "paused_reduced": stat(ev["paused"] + ev["reduced"])},
        "events": events,
        "failure_modes": fm_rows["all"],
        "triggers": dist(sip, "trigger"),
        "market_or_not": {"status": "computed", "losses": stat(losses, len(problems)),
                          "instalments": stat(instal, len(problems)), "base": len(problems)},
        "quotes": {fm: quotes(sip, fm) for fm in ("instalment_failed", "confusing_returns_or_progress",
                                                    "losses_shake_confidence")},
        "continuers_vs_dropoffs": {"status": "computed", "continued": profile(cont), "dropped": profile(drop)},
        "survey": survey_part("dropoffs", "Survey answers on why people considered stopping."),
    }

    # ---- segments ---------------------------------------------------------------------------
    seg_rows = []
    for field in SEGMENT_FIELDS:
        for row in dist(sip, field)["rows"]:
            group = [p for p in sip if p[field] == row["key"]]
            seg_rows.append({"segment": pretty(field), "group": row["label"], "n": row["n"], "sample": row["sample"],
                             "with_problem": sum(1 for p in group if p["failure_mode"] != "none"),
                             "top_failure_modes": [r["label"] for r in dist(group, "failure_mode")["rows"][:2]]})
    any_segment = sum(1 for p in sip if any(p[f] != FIELDS[f]["unknown"] for f in SEGMENT_FIELDS))
    segments = {
        **common,
        "tiles": {"stated": stat(any_segment, len(sip)), "first_time": stat(len(first_time)),
                  "first_time_problem": stat(sum(1 for p in first_time if p["failure_mode"] != "none"))},
        "table": {"status": "computed", "rows": seg_rows},
        "first_time": {"status": "computed", **stat(len(first_time)),
                       "no_problem": sum(1 for p in first_time if p["failure_mode"] == "none"),
                       "failure_modes": dist(first_time, "failure_mode")["rows"][:3],
                       "expectations": dist(first_time, "expectation")["rows"][:3]},
        "survey": survey_part("segments", "Survey-based patterns (The Watcher, The Quiet Checker, The Cash-Squeezed)."),
    }

    # ---- validation and method (tagging, scoring, retrieval evaluation) ----------------------
    tag_report = reports.get("tags") or {}
    evaluation = reports.get("evaluation")
    validation = {
        **common,
        "tagging": {"status": "computed", "model": tag_report.get("model"),
                    "prompt_version": tag_report.get("prompt_version"),
                    "tagged_by_model": tag_report.get("tagged_by_model"), "tagged_by_rule": tag_report.get("routes", {}).get("rule"),
                    "invalid_labels_dropped": tag_report.get("invalid_labels_dropped"),
                    "still_untagged": tag_report.get("still_untagged")},
        "retrieval": ({"status": "computed", **evaluation} if evaluation else
                      not_computed("Top-3 hit rate on the golden set (PRD target 80%).", GOLDEN)),
        "agreement": ({"status": "computed", **reports["agreement"]} if reports.get("agreement") else
                      not_computed("Agreement between the engine's tags and a person's labels on the same posts.",
                                   HUMAN)),
        "survey": survey_part("validation", "Engine findings checked against the investor survey."),
    }
    method = {
        **common,
        "formula": "Score = 100 × (0.40 × reach + 0.30 × severity + 0.15 × stage fit + 0.15 × segment fit)",
        "weights": config.SCORE_WEIGHTS, "min_posts_per_part": config.MIN_POSTS_PER_PART,
        "definitions": {
            "reach": "the opportunity's problem posts divided by the largest opportunity's",
            "severity": "share of its posts stating an event that report stopping, pausing, reducing or considering stopping",
            "stage_fit": "share of its posts stating a stage that sit in the first 12 months (onboarding to months 7–12)",
            "segment_fit": "share of its posts stating experience that come from first-time investors",
        },
        "opportunity_failure_modes": {o["name"]: [pretty(f) for f in o["failure_modes"]] for o in scoring.OPPORTUNITIES},
        "context_only": [pretty(f) for f in scoring.CONTEXT_ONLY],
        "tagging": validation["tagging"],
        "evidence_counts": {"posts": len(posts), "sip_posts": len(sip), "problem_posts": len(problems)},
    }

    # ---- sections for routing (phase 5) --------------------------------------------------------
    scored = [o for o in opportunities["all"] if o["score"] is not None]
    sections = [
        ("Overview", "opportunities", "Opportunities",
         "Which opportunity should we solve first, and why? What unmet needs emerge consistently across "
         "conversations? Ranked SIP problems and opportunity scores.",
         {o["name"]: o["score"] for o in scored}),
        ("Journey", "expectations", "Why people start and what they expect",
         "Why do people start a SIP, and what do they expect to happen? Goals, motivation and expectations.",
         {r["label"]: r["n"] for r in journey["expectations"]["rows"][:5]}),
        ("Journey", "stages", "What changes after starting",
         "What changes in investor behaviour in the months after starting a SIP? Onboarding, first instalment, "
         "months 2 to 6, months 7 to 12, after the first year.",
         {r["label"]: r["n"] for r in journey["stages"]["rows"]}),
        ("Journey", "checking", "What investors check and how often",
         "What do investors check, and how often, once they have started a SIP? Checking frequency.",
         {r["label"]: r["n"] for r in journey["checking"]["rows"]}),
        ("Journey", "confusion", "In-app confusion",
         "What confuses or worries investors inside the app? Returns, payment status, NAV, units, SIP dates.",
         {r["label"]: r["n"] for r in conf["rows"][:6]}),
        ("Journey", "outside-the-app", "Outside the app",
         "What do investors do outside the app when they feel unsure? Where do they go for help: forums, "
         "support, YouTube, friends, advisors.", {r["label"]: r["n"] for r in helpd["rows"][:6]}),
        ("Drop-offs", "failure-modes", "Failure modes",
         "What leads investors to pause, reduce or stop a SIP? Which problems make SIPs fail: failed instalments, "
         "autopay and mandate failures, money debited twice, cannot pause or change the amount, confusing returns.",
         {r["label"]: r["n"] for r in fm_rows["all"]["rows"][:8]}),
        ("Drop-offs", "triggers", "Triggers",
         "Market or not: do market falls and losses make investors stop their SIPs, or other triggers such as "
         "switching platform, charges, a cash-flow shock or app bugs?",
         {r["label"]: r["n"] for r in dropoffs["triggers"]["rows"][:8]}),
        ("Drop-offs", "continuers", "Continuers vs drop-offs",
         "What separates investors who continue from those who quietly drop off?",
         {"continued": len(cont), "dropped": len(drop)}),
        ("Segments", "segments", "Patterns by segment",
         "How do patterns differ across user segments: income stability, age, source of money, who influenced "
         "them, residency, NRI, students, salaried?", {"posts stating a segment": any_segment}),
        ("Segments", "first-time", "First-time investors",
         "What is specific to first-time investors? How do first-time investors differ from experienced ones?",
         {"first-time posts": len(first_time)}),
        ("Validation", "quality", "How quality was checked",
         "How was the quality of the insights validated? Where did the engine fail?", {}),
        ("Method", "pipeline", "How it was built",
         "How was the engine built? How does it gather and analyse data, identify themes and generate insights?",
         method["evidence_counts"]),
    ]
    # `text` (the questions a section answers) is what routing matches; `about` (what its posts say,
    # in investors' words) is blended into the search vector so abstract questions find concrete posts.
    about = {
        "opportunities": "My SIP instalment or autopay failed, money was debited but the SIP was not processed, I "
                         "cannot pause or change my SIP amount, the returns are confusing, losses worry me.",
        "expectations": "I started a SIP for long-term wealth, retirement, a goal, a saving habit or tax saving, and "
                        "I expect it to grow steadily over the years.",
        "stages": "I just set up my SIP mandate; my first instalment went through; a few months into my SIP; I have "
                  "been doing SIPs for years.",
        "checking": "I check my SIP portfolio every day, every week, once a month on the debit day, or rarely.",
        "confusion": "I don't understand the returns or P&L shown in the app, whether my instalment went through, "
                     "which NAV I got or how many units were allotted.",
        "outside-the-app": "I asked on a forum or Reddit, contacted customer support, checked the AMC website, watched "
                           "YouTube, or asked friends, family or an advisor.",
        "failure-modes": "My SIP instalment failed, the autopay mandate was rejected, money was debited twice, I could "
                         "not pause or modify my SIP.",
        "triggers": "I stopped my SIP because the market fell and I saw losses, I switched to another platform or a "
                    "direct plan, the charges, or I lost my job.",
        "continuers": "I kept my SIP going despite the problems, while others stopped, paused or are thinking of "
                      "stopping their SIP.",
        "segments": "I am a student, salaried, self-employed, an NRI, in my twenties; I started after watching "
                    "YouTube or on a friend's advice.",
        "first-time": "I am a first-time investor, new to mutual funds, I just started my first SIP; I have been "
                      "investing for many years.",
    }
    index = [{"page": page, "section_id": sid, "title": title, "text": text, "about": about.get(sid, ""),
              "key_numbers": _label_numbers(sid, nums, opportunities["all"])} for page, sid, title, text, nums in sections]

    return {"overview": overview, "journey": journey, "dropoffs": dropoffs, "segments": segments,
            "validation": validation, "method": method, "sections_index": index}
