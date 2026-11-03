"""Page 4: Segments. How patterns differ by segment, and what is specific to first-time investors."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import ask
import ui
from site_data import SiteData


def render(site: SiteData) -> None:
    page = site.pages.get("segments")
    if not site.ready or not page:
        ui.not_ready(site.missing or ["Data/site/segments.json (run python -m src.site_export.run)"])
        return
    t, ft = page["tiles"], page["first_time"]
    no_problem = ft["no_problem"] / ft["n"] if ft["n"] else 0
    top_ft = ft["failure_modes"][0]["label"].lower() if ft["failure_modes"] else "none stated"
    ui.page_header("04 · Segments",
                   f"{ft['n']} posts come from first-time investors; {no_problem:.0%} describe no problem, and the "
                   f"most common problem they name is {top_ft}",
                   "How do patterns differ across segments (income, age, source of money, who influenced them)? "
                   "What is specific to first-time investors?")
    st.info("Segment tags exist only where a writer states them, so most posts are 'not stated'.", icon="ℹ️")
    ui.stat_tiles([
        ("Posts stating a segment", ui.tile_value(t["stated"], share=True), "share of SIP posts"),
        ("First-time investor posts", ui.tile_value(t["first_time"]), "posts" + ui.low(t["first_time"])),
        ("First-time posts naming a problem", ui.tile_value(t["first_time_problem"]),
         "posts" + ui.low(t["first_time_problem"])),
    ])
    ui.heading("Patterns by segment")
    rows = page["table"]["rows"]
    st.dataframe(pd.DataFrame([{
        "Segment": r["segment"], "Group": r["group"], "Posts": r["n"], "With a problem": r["with_problem"],
        "Top failure modes": ", ".join(r["top_failure_modes"]) or "–",
        "Tag": "Low sample" if r["sample"] == "low" else "",
    } for r in rows]), hide_index=True, width="stretch")

    ui.heading("First-time investors")
    left, right = st.columns(2)
    with left:
        ui.bars(ft["failure_modes"], "Problems first-time investors name")
    with right:
        ui.bars(ft["expectations"], "What first-time investors expect")
    s = page["survey"]
    if s.get("status") == "computed":
        n = s["sample"]["n"]
        ui.survey_heading(s, "Survey patterns")
        cols = st.columns(len(s["patterns"]))
        for col, p in zip(cols, s["patterns"]):
            col.markdown(f'<div class="sde-tile"><div class="label">{p["name"]}</div>'
                         f'<div class="value">{p["n"]} of {n}</div>'
                         f'<div class="caption">{p["definition"]}; {p["detail"]}.</div></div>', unsafe_allow_html=True)
        st.caption("The groups overlap: one investor can be in more than one.")
        with st.expander("Who answered the survey"):
            st.dataframe(pd.DataFrame([{"Question": q, "Answer": r["label"], "Investors": r["n"]}
                                       for q, rows in s["profile"].items() for r in rows]),
                         hide_index=True, width="stretch")
    else:
        ui.not_computed_item("Survey patterns", s)
    ask.explore_buttons(["How do first-time investors differ from experienced ones?",
                         "What problems do NRIs face with SIPs?",
                         "How do students and salaried investors talk about SIPs?"], key="segments")
    ui.source_note("Groups overlap: one post can state several segments. Any group under 10 posts is marked low sample.")
