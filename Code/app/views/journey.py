"""Page 2: Journey. Why people start, what they check, what confuses them, where they seek help."""
from __future__ import annotations

import streamlit as st

import ask
import ui
from site_data import SiteData


def render(site: SiteData) -> None:
    page = site.pages.get("journey")
    if not site.ready or not page:
        ui.not_ready(site.missing or ["Data/site/journey.json (run python -m src.site_export.run)"])
        return
    t = page["tiles"]
    top_help = t["top_help"]
    long_term = t["long_term"]["n"] >= t["quick_gains"]["n"]
    title = (("Investors start for the long term" if long_term else "Many investors start expecting quick gains")
             + (", but seek help outside the app" if top_help else ""))
    ui.page_header("02 · Journey", title,
                   "On this page: why investors start, what they check, what confuses them in the app and where "
                   "they look for help.")
    ui.stat_tiles([
        ("Posts expecting long-term growth", ui.tile_value(t["long_term"]),
         f"{t['quick_gains']['n']} expect quick gains{ui.low(t['quick_gains'])}"),
        ("Posts saying how often they check", ui.tile_value(t["checking_stated"]), "of SIP posts" + ui.low(t["checking_stated"])),
        ("Top in-app confusion", t["top_confusion"]["label"] if t["top_confusion"] else None,
         f"{t['top_confusion']['n']} posts" if t["top_confusion"] else ""),
        ("Top help outside the app", top_help["label"] if top_help else None, f"{top_help['n']} posts" if top_help else ""),
    ])

    stages = page["stages"]
    rows = [{**r, "label": f"{r['label']} ({r['with_problem']} with a problem)"} for r in stages["rows"]]
    ui.bars(rows, "Where in the journey problems appear",
            f"Stage stated in {stages['stated']:,} of {stages['base']:,} SIP posts. Bars count posts; the label gives "
            "how many of them report a problem.")
    left, right = st.columns(2)
    with left:
        ui.bars(page["expectations"]["rows"], "What investors expect from a SIP",
                f"Stated in {page['expectations']['stated']:,} SIP posts.")
        ui.bars(page["confusion"]["rows"], "What confuses investors inside the app",
                f"Stated in {page['confusion']['stated']:,} SIP posts.")
    with right:
        ui.bars(page["checking"]["rows"], "How often investors check",
                f"Stated in {page['checking']['stated']:,} SIP posts.")
        ui.bars(page["help_seeking"]["rows"], "Where investors go outside the app",
                f"Stated in {page['help_seeking']['stated']:,} SIP posts.")
    s = page["survey"]
    if s.get("status") == "computed":
        n = s["sample"]["n"]
        ui.survey_heading(s)
        left, right = st.columns(2)
        with left:
            ui.bars(s["checking"], "How often they check",
                    f"{n} SIP investors; {s['weekly_or_more']} of {n} check weekly or more often.")
            ui.bars(s["expectation"], "What they expected from SIPs", f"{n} SIP investors.")
            ui.bars(s["influence"], "Who influenced them to start", f"{n} SIP investors; several picks allowed.")
        with right:
            ui.bars(s["first_look"], "What they look at first", f"{n} SIP investors.")
            ui.bars(s["help"], "Where they seek answers when unsure", f"{n} SIP investors; several picks allowed.")
            ui.bars(s["profile"], "How they describe themselves as investors", f"{n} SIP investors.")
    else:
        ui.not_computed_item("Survey: checking, feelings and help-seeking", s)
    ask.explore_buttons(["Why do people start a SIP, and what do they expect to happen?",
                         "What confuses or worries investors inside the app?",
                         "Where do investors go when they are unsure?"], key="journey")
    ui.source_note("Most posts do not state a stage, expectation or checking habit, so these bars show what writers "
                   "volunteer. Counts are mentions, not population percentages.")
