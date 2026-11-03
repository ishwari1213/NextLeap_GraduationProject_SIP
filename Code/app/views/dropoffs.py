"""Page 3: Drop-offs. What leads investors to pause, reduce or stop, and who continues."""
from __future__ import annotations

import streamlit as st

import ask
import ui
from site_data import SiteData

QUOTE_TITLES = {"instalment_failed": "Instalment failed", "confusing_returns_or_progress": "Confusing returns",
                "losses_shake_confidence": "Losses shake confidence"}


def _profile(col, title: str, group: dict) -> None:
    with col:
        st.markdown(f"**{title}** · {group['n']} posts{' (low sample)' if group['sample'] == 'low' else ''}")
        st.write("Top failure modes: " + (", ".join(f"{r['label']} ({r['n']})" for r in group["failure_modes"]) or "none stated"))
        st.write("Top triggers: " + (", ".join(f"{r['label']} ({r['n']})" for r in group["triggers"]) or "none stated"))


def render(site: SiteData) -> None:
    page = site.pages.get("dropoffs")
    if not site.ready or not page:
        ui.not_ready(site.missing or ["Data/site/dropoffs.json (run python -m src.site_export.run)"])
        return
    t, market = page["tiles"], page["market_or_not"]
    inst, loss = market["instalments"]["n"], market["losses"]["n"]
    title = (f"Instalment problems ({inst} posts) outnumber market losses ({loss}) among the reasons SIPs falter"
             if inst >= loss else f"Market losses ({loss} posts) outnumber instalment problems ({inst})")
    ui.page_header("03 · Drop-offs", title,
                   "What leads investors to pause, reduce or stop? What separates those who continue from those who drop off?")
    ui.stat_tiles([
        ("Posts stating an event", ui.tile_value(t["event_stated"]), "of SIP posts"),
        ("Stopped", ui.tile_value(t["stopped"]), "posts" + ui.low(t["stopped"])),
        ("Considering stopping", ui.tile_value(t["considering"]), "posts" + ui.low(t["considering"])),
        ("Paused or reduced", ui.tile_value(t["paused_reduced"]), "posts" + ui.low(t["paused_reduced"])),
    ])

    fm = page["failure_modes"]
    rows = [{**r, "label": r["label"] + (" · context only" if r["context_only"] else "")} for r in fm["rows"]]
    ui.bars(rows, "SIP problems by failure mode",
            f"{fm['stated']:,} SIP posts name a problem. 'Context only' problems are real but sit outside the SIP "
            "opportunity score.", highlight={"instalment_failed", "debited_after_cancel_or_twice"})
    left, right = st.columns(2)
    with left:
        ui.bars(page["events"]["rows"], "What investors did",
                "Few people say they paused or reduced, so quiet drop-offs are under-recorded.")
    with right:
        ui.bars(page["triggers"]["rows"], "What triggered it", f"Stated in {page['triggers']['stated']:,} SIP posts.")

    ui.heading("Market or not?")
    ui.stat_tiles([
        ("Losses shake confidence", f"{loss} · {market['losses']['share']:.0%}" if market["base"] else None,
         f"of {market['base']:,} problem posts"),
        ("Instalment problems", f"{inst} · {market['instalments']['share']:.0%}" if market["base"] else None,
         f"of {market['base']:,} problem posts"),
    ])

    ui.heading("In their words")
    cols = st.columns(len(QUOTE_TITLES))
    for col, (key, label) in zip(cols, QUOTE_TITLES.items()):
        with col:
            st.markdown(f"**{label}**")
            ui.quote_cards(page["quotes"].get(key, []))
    st.caption("De-identified quotes, at most 25 words, labelled with source and month only.")

    ui.heading("Continuers vs drop-offs")
    cvd = page["continuers_vs_dropoffs"]
    left, right = st.columns(2)
    _profile(left, "Continued", cvd["continued"])
    _profile(right, "Stopped, paused, reduced or considering it", cvd["dropped"])
    s = page["survey"]
    if s.get("status") == "computed":
        n = s["sample"]["n"]
        ui.survey_heading(s, "From the investor survey: who considers stopping, and why")
        ui.stat_tiles([
            ("Have considered stopping", f"{s['considered']} of {n}", "stopping, pausing or reducing"),
            ("Would stop over a cash shock", f"{s['future_cash']} of {n}", "job loss, income cut, emergency, family"),
            ("Would stop over returns", f"{s['future_market']} of {n}", "poor returns, a crash or low confidence"),
            ("SIP still active", f"{s['active']} of {n}", f"{s['inactive']} not active"),
        ])
        left, right = st.columns(2)
        with left:
            ui.bars(s["why_considered"], f"Why they considered stopping (n = {s['considered']})",
                    "Market worries are not the whole story: cash flow and life events matter as much.")
            ui.bars(s["likelihood"], f"How likely they are to continue for 12 months (n = {n})")
        with right:
            ui.bars(s["future"], f"What would make them stop in future (n = {n}, several picks allowed)")
            ui.bars(s["keep_going"], f"Why they keep investing (n = {n}, several picks allowed)")
    else:
        ui.not_computed_item("Survey: why people considered stopping", s)
    ask.explore_buttons(["What leads investors to pause, reduce or stop a SIP?",
                         "Why do SIP instalments and autopay mandates fail?",
                         "What separates investors who continue from those who quietly drop off?"], key="dropoffs")
    ui.source_note("Public posts lean towards complaints. Counts are mentions, not population percentages.")
