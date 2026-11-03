"""Page 5: Validation. How the data, the tags and the search were checked, and where they could fail."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import ui
from site_data import SiteData

PII_LABELS = {
    "USER": "Usernames and @mentions", "ACCOUNT": "Account-like numbers", "EMAIL": "Emails",
    "PROFILE_LINK": "Profile links", "AADHAAR": "Aadhaar numbers", "PHONE": "Phone numbers", "PAN": "PAN numbers",
    "OTP": "OTPs",
}


def render(site: SiteData) -> None:
    if not site.ready:
        ui.not_ready(site.missing)
        return
    page = site.pages.get("validation", {})
    retrieval = page.get("retrieval", {"status": "not_computed", "reason": "", "missing_step": "phase 6"})
    total, failed = len(site.checks), site.checks_failed
    held_out = retrieval.get("holdout") if retrieval.get("status") == "computed" else None
    if held_out:
        title = (f"Retrieval finds a relevant post in the top 3 for {held_out['top3_hits']} of "
                 f"{held_out['in_scope_items']} unseen test questions, below the 80% target; "
                 f"{total - failed} of {total} pipeline checks pass")
    elif retrieval.get("status") == "computed":
        title = (f"Retrieval finds a relevant post in the top 3 for {retrieval['top3_hits']} of "
                 f"{retrieval['in_scope_items']} test questions, and {total - failed} of {total} pipeline checks pass")
    else:
        title = f"{total - failed} of {total} pipeline checks pass; retrieval accuracy is not yet measured"
    ui.page_header("05 · Validation", title, "How were the data, the tags and the search checked? Where could they fail?")

    computed = retrieval.get("status") == "computed"
    held = retrieval.get("holdout") if computed else None
    hit = f"{held['top3_hit_rate']:.0%}" if held else (f"{retrieval['top3_hit_rate']:.0%}" if computed else None)
    tagging = page.get("tagging", {})
    ui.stat_tiles([
        ("Retrieval top-3 hit rate", hit,
         "on questions never used for tuning; target 80%" if held else "target 80% (provisional)"),
        ("Pipeline checks passing", f"{total - failed} of {total}", "phases 2 to 4, rerun on every build"),
        ("Posts tagged by Mistral", f"{tagging['tagged_by_model']:,}" if tagging.get("tagged_by_model") else None,
         f"{tagging.get('model') or ''}, prompt {tagging.get('prompt_version') or ''}"),
        ("Personal details removed", f"{site.pii_total:,}", "replaced with labels before storage"),
    ])

    ui.heading("Retrieval on the golden set")
    if retrieval.get("status") == "computed":
        st.write(f"Top-3 hit rate **{retrieval['top3_hit_rate']:.0%}** ({retrieval['top3_hits']} of "
                 f"{retrieval['in_scope_items']}); refusals **{retrieval['refusals_ok']} of {retrieval['refusal_items']}**"
                 + (f"; routing accuracy **{retrieval['routing_accuracy']:.0%}** of {retrieval['routed_items']} routed "
                    "questions" if retrieval.get("routing_accuracy") is not None else "")
                 + f"; personal data in stored excerpts: **{retrieval['personal_data_in_excerpts']}**.")
        if held:
            st.warning(f"On {held['in_scope_items']} held-out questions that were never used while tuning, the top-3 "
                       f"hit rate is {held['top3_hit_rate']:.0%} ({held['top3_hits']} of {held['in_scope_items']}), "
                       f"{'meeting' if held['top3_hit_rate'] >= 0.8 else 'below'} the 80% target. The golden-set "
                       "rate above is optimistic: settings were tuned on those questions, and the rank boost uses the "
                       "same tags that judge relevance.", icon="⚠️")
        st.caption(retrieval.get("golden_set", ""))
        items = retrieval.get("items", [])
        st.dataframe(pd.DataFrame([{
            "Question": i["question"], "Status": i["status"] + (f" ({i['reason']})" if i.get("reason") else ""),
            "Routed to": i.get("route") or "–", "Expected": i.get("expected_section") or "refuse",
            "Result": ("Hit ✓" if i.get("hit") else "Miss ✗") if "hit" in i else ("Refused ✓" if i.get("refused") else "Answered ✗"),
        } for i in items]), hide_index=True, width="stretch")
    else:
        ui.not_computed_item("Retrieval top-3 hit rate", retrieval)

    ui.heading("Engine vs human agreement")
    agreement = page.get("agreement", {"status": "not_computed"})
    if agreement.get("status") == "computed":
        st.write(f"Overall agreement **{agreement['overall']:.0%}** ({agreement['agree']} of {agreement['total']} "
                 f"field values, {agreement['posts_labelled']} posts).")
        ui.bars([{"label": f, "n": round(v["rate"] * 100) if v["rate"] is not None else 0,
                  "sample": "low" if v["total"] < 10 else "ok"} for f, v in agreement["per_field"].items()],
                "Agreement per field (%)", value_format="d")
    else:
        ui.not_computed_item("Engine vs human agreement", agreement)
        st.caption("A 40-post labelling sheet is ready: Data/eval/human_labels.csv, with the label list in "
                   "Data/eval/HOW_TO_LABEL.md. Fill it in, then run python -m src.phase6_retrieval_testing.agreement score.")

    survey = page.get("survey", {"status": "not_computed"})
    if survey.get("status") == "computed":
        ui.survey_heading(survey, "Engine vs survey")
        st.dataframe(pd.DataFrame([{"Theme": r["theme"], "Engine (public posts)": r["engine"],
                                    "Survey": r["survey"], "Reading": r["reading"]} for r in survey["comparison"]]),
                     hide_index=True, width="stretch")
        st.caption("Reading: Supported = the engine finds the theme in 10+ posts and 30%+ of surveyed investors "
                   "report it; Engine under-counts = 30%+ of investors report it but it is under 5% of problem posts; "
                   "Untested = the survey did not ask.")
    else:
        ui.not_computed_item("Engine vs survey", survey)

    ui.heading("Tagging quality")
    st.write(f"Model **{tagging.get('model')}**, prompt **{tagging.get('prompt_version')}**: "
             f"{tagging.get('tagged_by_model') or 0:,} posts tagged by the model, {tagging.get('tagged_by_rule') or 0:,} "
             f"store reviews with no SIP word tagged 'not about SIPs' by rule, {tagging.get('invalid_labels_dropped') or 0} "
             f"invalid labels dropped, {tagging.get('still_untagged') or 0} posts still untagged.")

    ui.heading("Pipeline checks")
    st.dataframe(pd.DataFrame([{"Phase": c.phase, "Check": c.name, "Value": c.value,
                                "Result": "Pass ✓" if c.passed else "Fail ✗"} for c in site.checks]),
                 hide_index=True, width="stretch")
    ui.heading("Personal data removed before storage")
    rows = sorted(site.pii_replacements.items(), key=lambda kv: -kv[1])
    st.dataframe(pd.DataFrame([{"Kind": PII_LABELS.get(k, k), "Replaced": v} for k, v in rows]),
                 hide_index=True, width="stretch")
    ui.source_note("The golden set and its relevance rules were drafted by AI from the PRD's questions and judged with "
                   "the engine's own tags, so the hit rate is provisional until a person reviews them.")
