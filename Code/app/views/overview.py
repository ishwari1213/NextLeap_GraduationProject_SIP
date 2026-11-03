"""Page 1: Overview. Which opportunity should Groww solve first, and why?"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import ask
import ui
from site_data import SiteData

SCOPES = {"All sources": "all", "Groww only": "groww"}


def _pct(part: dict) -> str:
    if part["value"] is None:
        return "–"
    return f"{part['value']:.0%}" + ("" if part["kept"] else " (left out)")


def render(site: SiteData) -> None:
    page = site.pages.get("overview")
    if not site.ready or not page:
        ui.not_ready(site.missing or ["Data/site/overview.json (run python -m src.site_export.run)"])
        return
    tiles = page["tiles"]
    ranked = [o for o in page["opportunities"]["all"] if o["score"] is not None]
    top = ranked[0] if ranked else None
    title = (f"{top['name']} is the highest-potential opportunity, scoring {top['score']} of 100 across "
             f"{page['scope_sizes']['all']:,} problem posts" if top else
             "No opportunity has enough posts to be scored yet")
    ui.page_header("01 · Overview", title, "Which opportunity should Groww solve first, and why? What unmet needs emerge?")
    ui.stat_tiles([
        ("Posts analysed", ui.tile_value(tiles["posts"]), "investor posts, reviews and comments, tagged"),
        ("SIP posts", ui.tile_value(tiles["sip_posts"], share=True), "share of posts that are about SIPs"),
        ("Posts naming a problem", ui.tile_value(tiles["problem_posts"], share=True), "share of SIP posts"),
        ("Sources", f"{tiles['sources']['n']}", "public sources with SIP posts"),
    ])

    ui.heading("Opportunity ranking")
    choice = st.radio("Evidence", list(SCOPES), horizontal=True, key="overview_scope",
                      help="Groww only = Groww's store reviews plus forum and Reddit posts that name Groww. Whether "
                           "competitor reviews should count is still an open decision.")
    scope = SCOPES[choice]
    opps = page["opportunities"][scope]
    ui.bars([{"label": o["name"], "n": o["score"], "sample": "low" if o["tag"] == "Small sample" else "ok",
              "key": o["id"]} for o in opps if o["score"] is not None],
            f"Opportunity score (0–100), {choice.lower()}", value="n", highlight={opps[0]["id"]} if opps else None,
            value_format="d")
    st.caption(f"Based on {page['scope_sizes'][scope]:,} problem posts. Score = 100 × (0.40 reach + 0.30 severity "
               "+ 0.15 stage fit + 0.15 segment fit); a part stated by fewer than 5 posts is left out and the other "
               "weights rescale (definitions on the Method page).")
    st.dataframe(pd.DataFrame([{
        "Opportunity": o["name"], "Problem posts": o["posts"],
        "Share of problem posts": f"{o['share_of_problem_posts']:.0%}" if o["share_of_problem_posts"] is not None else "–",
        "Reach": _pct(o["parts"]["reach"]), "Severity": _pct(o["parts"]["severity"]),
        "Stage fit": _pct(o["parts"]["stage_fit"]), "Segment fit": _pct(o["parts"]["segment_fit"]),
        "Score": o["score"], "Tag": o["tag"], "Note": o["note"],
    } for o in opps]), hide_index=True, width="stretch")

    ui.heading("Metric tree: 12-month SIP continuation")
    cols = st.columns(len(page["metric_tree"]))
    for col, node in zip(cols, page["metric_tree"]):
        col.markdown(f'<div class="sde-tile"><div class="label">{node["id"]} · {node["label"]}</div>'
                     f'<div class="value" style="font-size:1.6rem">{node["n"]:,}</div>'
                     f'<div class="caption">posts{ui.low(node)}</div></div>', unsafe_allow_html=True)
    st.caption("Each branch counts SIP posts tagged to it; a post can sit under more than one branch.")

    ui.insights(page["insights"])
    s = page["survey"]
    if s.get("status") == "computed":
        n = s["surveyed"]["n"]
        ui.survey_heading(s)
        ui.stat_tiles([
            ("SIP investors surveyed", f"{n}", f"of {s['surveyed']['responses']} responses"),
            ("Have considered stopping", f"{s['considered_stopping']['n']} of {n}", "stopping, pausing or reducing"),
            ("Would stop over a cash shock", f"{s['future_cash']['n']} of {n}",
             "job loss, income cut, emergency or family duties"),
            ("SIP still active", f"{s['active']['n']} of {n}", "at the time of the survey"),
        ])
    else:
        ui.not_computed_item("Survey findings", s)
    ask.explore_buttons(["Which opportunity should we solve first, and why?",
                         "What unmet needs emerge consistently across conversations?"], key="overview")
    ui.source_note("Counts are mentions in public posts and reviews, tagged by Mistral, not population percentages. "
                   "Figures under 10 posts are marked low sample.")
