"""Page 6: Method. How the workflow gathers and prepares data, and the limits stated plainly."""
from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

import ui
from site_data import SiteData, day_label
from src import config

OKABE_ITO = {"Records": "#0072B2", "Excerpts": "#E69F00"}  # colour-blind safe; bars also carry value labels


def _chart(site: SiteData) -> alt.Chart:
    rows = [{"Source": s.label, "Measure": m, "Count": v}
            for s in site.active_sources for m, v in (("Records", s.records), ("Excerpts", s.excerpts))]
    data = pd.DataFrame(rows)
    order = [s.label for s in sorted(site.active_sources, key=lambda s: -s.records)]
    base = alt.Chart(data).encode(
        y=alt.Y("Source:N", sort=order, title=None),
        yOffset=alt.YOffset("Measure:N", sort=["Records", "Excerpts"]),
        x=alt.X("Count:Q", title="Count"),
    )
    bars = base.mark_bar().encode(
        color=alt.Color("Measure:N", scale=alt.Scale(domain=list(OKABE_ITO), range=list(OKABE_ITO.values())),
                        legend=alt.Legend(orient="top", title=None)),
        tooltip=["Source", "Measure", alt.Tooltip("Count:Q", format=",")],
    )
    labels = base.mark_text(align="left", dx=4, fontSize=13).encode(text=alt.Text("Count:Q", format=","))
    return (bars + labels).properties(height=alt.Step(18), title="Records and excerpts per source")


def limits(site: SiteData) -> list[str]:
    items = ["Public posts lean towards complaints, so counts show relative importance, not population shares."]
    groww = site.app_row("Groww")
    if groww:
        items.append(f"Groww's Play Store reviews cover only {day_label(groww.first)} to {day_label(groww.last)} "
                     f"({groww.reviews:,} reviews): the loader keeps each app's newest reviews.")
    store = site.source("app_store")
    if store and store.records:
        n_apps = len([a for a in site.apps if a.source == "app_store"])
        items.append(f"App Store: {store.records} reviews across {n_apps} apps. The review feed was empty at fetch time, "
                     "so only the newest reviews shown on each app's page were loaded.")
    for s in site.sources:
        if s.note and s.records == 0:
            items.append(f"{s.label}: {s.note[0].lower() + s.note[1:]}.")
    survey = (site.pages.get("overview") or {}).get("survey") or {}
    if survey.get("status") == "computed":
        items.append(survey["sample"]["note"] + " Names and emails were dropped when the survey was loaded.")
    else:
        items.append("The investor survey is not loaded yet (python -m src.survey.load).")
    items.append("Tags come from a language model (Mistral); stage, event and segment are stated in only a minority "
                 "of posts, so those counts are small.")
    items.append("The golden set was drafted by AI and judged with the engine's own tags; treat the hit rate as "
                 "provisional until a person reviews it.")
    return items


def render(site: SiteData) -> None:
    if not site.ready:
        ui.not_ready(site.missing)
        return
    ui.page_header("06 · Method", "How the engine was built, and its limits",
                   "On this page: sources, pipeline, scoring method, settings, limits and privacy.")
    ui.stat_tiles([
        ("Records", f"{site.records_total:,}", "after removing duplicates and empty posts"),
        ("Excerpts", f"{site.excerpts_total:,}", f"each at most {site.chunk_settings.get('model_max_tokens', '')} tokens"),
        ("Distinct vectors", f"{site.distinct_texts:,}", f"{site.dim}-number vectors, one per distinct text"),
        ("Last updated from sources", day_label(site.last_updated) or None, "date of the last fetch"),
    ])

    urls = sum(s.urls_active for s in site.sources)
    ui.heading("Pipeline")
    ui.steps([
        ("Collect", f"{urls} public URLs in sources.yaml"),
        ("Clean and de-identify", f"{site.records_total:,} records; {site.pii_total:,} personal details replaced"),
        ("Chunk", f"{site.excerpts_total:,} excerpts of about {site.chunk_settings.get('target_tokens', '')} tokens"),
        ("Embed", f"{site.model.split('/')[-1]}, {site.dim} numbers per excerpt"),
        ("Store", f"ChromaDB, {site.vector_rows:,} rows, cosine distance"),
        ("Retrieve", f"top {config.RETRIEVAL_CANDIDATES} matches, cut-off {config.RETRIEVAL_MIN_SIMILARITY}"),
    ])

    ui.heading("Data by source")
    st.altair_chart(_chart(site), width="stretch")
    st.dataframe(pd.DataFrame([{"Source": s.label, "URLs listed": s.urls_active, "Records": s.records,
                                "Excerpts": s.excerpts, "Long posts split": s.records_split, "Note": s.note}
                               for s in site.sources]), hide_index=True, width="stretch")

    ui.heading("Reviews by app")
    st.dataframe(pd.DataFrame([{"App": a.app, "Store": "Google Play" if a.source == "play_store" else "App Store",
                                "Reviews": a.reviews, "From": a.first, "To": a.last} for a in site.apps]),
                 hide_index=True, width="stretch")

    ui.heading("Model settings")
    s = site.chunk_settings
    ui.card(f"<b>Embedding model:</b> {site.model} ({site.dim} dimensions)<br>"
            f"<b>Chunking:</b> excerpts of about {s.get('target_tokens')} tokens, {s.get('overlap_tokens')} tokens of "
            f"overlap, hard limit {s.get('model_max_tokens')}<br>"
            f"<b>Retrieval:</b> top {config.RETRIEVAL_CANDIDATES} candidates, {config.RETRIEVAL_PROMPT_EXCERPTS} sent "
            f"to the answer step, evidence cut-off {config.RETRIEVAL_MIN_SIMILARITY}, at least "
            f"{config.INSUFFICIENT_EVIDENCE_BELOW} supporting posts for an answer")

    m = site.pages.get("method")
    if m:
        ui.heading("Tagging and scoring")
        tg = m["tagging"]
        defs = "".join(f"<li><b>{k.replace('_', ' ').capitalize()}</b>: {v}</li>" for k, v in m["definitions"].items())
        mapping = "".join(f"<li><b>{name}</b>: {', '.join(fms) or 'no tag yet'}</li>"
                          for name, fms in m["opportunity_failure_modes"].items())
        ui.card(f"<b>Tagging:</b> {tg.get('model')} (prompt {tg.get('prompt_version')}) labels each post's SIP "
                "relevance, stage, event, trigger, failure mode, theme, expectation, checking, confusion, help-seeking "
                "and six segments. Store reviews with no SIP word are tagged 'not about SIPs' by rule.<br><br>"
                f"<b>Formula:</b> {m['formula']}. A part stated by fewer than {m['min_posts_per_part']} posts is left "
                f"out and the other weights rescale.<ul>{defs}</ul><b>Opportunities and their failure modes:</b>"
                f"<ul>{mapping}</ul><b>Context only</b> (outside the score): {', '.join(m['context_only'])}.")

    ui.insights(limits(site), title="Limits")

    remaining = []
    if ((site.pages.get("overview") or {}).get("survey") or {}).get("status") != "computed":
        remaining.append(("Survey findings", "load the investor survey: python -m src.survey.load"))
    if remaining:  # shown only while something is pending
        ui.heading("Still to do")
        st.dataframe(pd.DataFrame([{"Item": t, "Missing step": s} for t, s in remaining]), hide_index=True,
                     width="stretch")

    ui.heading("Privacy and rules")
    ui.card("No usernames or author fields are stored, not even in the raw downloads. Personal details in post "
            "text are replaced with labels such as [PHONE]. Quotes are at most 25 words, labelled with source and "
            "month only. The engine gives no investment advice and never calculates or compares returns.")
    ui.source_note("Every number on this page comes from the pipeline's own reports in Data/.")
