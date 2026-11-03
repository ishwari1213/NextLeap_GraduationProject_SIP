"""Ask the engine: the full-page research tool (architecture phase 5, served by /api/ask and /api/retrieve).

Empty state: an intro, the disclaimer and exactly 4 sample questions; no answer until the reader
asks (UI spec section 4). A result shows the status badge, the supporting-post count, the page
section the question was routed to, the written answer with its confidence and quotes, the two
follow-ups ("Show quotes", "Break down by segment"), every retrieved excerpt with its match score,
the information-page context and the evidence bundle itself.
"""
from __future__ import annotations

import time
from html import escape

import pandas as pd
import streamlit as st

import research_client as client
import ui
from site_data import SiteData
from src import config

HISTORY = 8


def _run(question: str | None = None) -> None:
    """Button callback: run a question with the chosen filters and keep the result."""
    question = " ".join((question or st.session_state.get("rq_input", "")).split())
    if len(question) < 3:
        st.session_state["rq_result"] = ({"status": "invalid", "detail": "Type a question of at least 3 characters."},
                                         "", 0.0)
        return
    st.session_state["rq_input"] = question
    app = st.session_state.get("rq_app")
    app = None if app in (None, client.ALL_SOURCES) else app
    source = client.SOURCE_FILTERS.get(st.session_state.get("rq_source", ""), None)
    mode = client.MODES.get(st.session_state.get("rq_mode", ""), "answer")
    started = time.monotonic()
    result, how = client.query(question, app=app, source=source, mode=mode)
    st.session_state["rq_result"] = (result, how, round(time.monotonic() - started, 1))
    history = [q for q in st.session_state.get("rq_history", []) if q != question]
    st.session_state["rq_history"] = [question, *history][:HISTORY]


def _clear() -> None:
    st.session_state.pop("rq_result", None)
    st.session_state["rq_input"] = ""


def _quotes_html(items: list[dict], with_score: bool = False) -> str:
    rows = []
    for q in items:
        meta = f"{client.source_label(q)} · {client.month(q)}"
        if with_score and q.get("score") is not None:
            meta += f" · match {q['score']:.2f}"
        rows.append(f'<div class="sde-quote">“{escape(client.short(q.get("text", "")))}”'
                    f'<span class="meta">{escape(meta)}</span></div>')
    return "".join(rows)


def _status_line(status: dict | None) -> None:
    if status:
        st.caption(f"✅ Connected to the retrieval API at {config.API_BASE_URL}: {status.get('excerpts', 0):,} excerpts, "
                   f"{status.get('sections', 0)} page sections, last updated from sources "
                   f"{status.get('last_updated_from_sources') or 'unknown'}.")
    elif not client.local_store_ready():
        st.warning(client.UNAVAILABLE, icon="⚠️")
    else:
        st.warning("The retrieval API on port 8001 is not running, so questions are answered in-process (the first "
                   "one loads the search model, about 10 seconds). To start it, run from the Code folder: "
                   "uvicorn src.api.main:app --port 8001", icon="⚠️")


def _result(result: dict, how: str, seconds: float) -> None:
    status = result.get("status")
    if status in ("invalid", "unavailable"):
        st.warning(result.get("detail", ""))
        return
    label, kind = client.BADGES.get(status, (status, "muted"))
    st.markdown(f'<div class="sde-h">{escape(result.get("question", ""))}</div>', unsafe_allow_html=True)
    route = result.get("page_link") or "–"
    n = result.get("supporting_items", 0)
    ui.stat_tiles([
        ("Status", label, (client.REASONS.get(result.get("reason"), "") if status == "out_of_scope"
                           else f"{n} of {result.get('evidence_needed', 15)} supporting posts needed")),
        ("Supporting posts", f"{n}" if status != "out_of_scope" else "–", "distinct posts above the relevance cut-off"),
        ("Routed to", route, "page section the answer draws on"),
        ("Time", f"{seconds:.1f} s", "via the API" if how == "api" else "in-process (API not running)"),
    ])

    if status == "out_of_scope":
        answer = result.get("answer") or {}
        st.markdown(f'<span class="sde-pill pill-{kind}">{escape(label)}</span>', unsafe_allow_html=True)
        st.write(answer.get("text") or client.REFUSALS.get(result.get("reason"), "This question is out of scope."))
        for link in result.get("decline_links", []):
            st.markdown(f"- [{link['label']}]({link['url']})")
        return

    answer = result.get("answer")
    if answer:
        ui.heading("Answer")
        st.markdown(f'<span class="sde-pill pill-{kind}">{escape(label)}</span>&nbsp; '
                    f'{escape(answer.get("sample_size", ""))}'
                    + (f' &nbsp;·&nbsp; Confidence: <b>{escape(answer["confidence"])}</b>' if answer.get("confidence") else ""),
                    unsafe_allow_html=True)
        st.write(answer.get("text", ""))
        if answer.get("confidence_reason"):
            st.caption(answer["confidence_reason"])
        st.markdown(_quotes_html(answer.get("quotes", [])), unsafe_allow_html=True)
        if answer.get("page_link"):
            st.caption(f"See: {answer['page_link']}")
        if (answer.get("guardrail") or {}).get("fallback"):
            st.caption("Shown as a plain evidence summary: a written answer did not pass the number and quote checks.")
        left, right, _ = st.columns([1, 1, 2])
        left.button("Show quotes", key="rq-fu-quotes", width="stretch",
                    on_click=lambda: st.session_state.update(rq_show_all=True))
        right.button("Break down by segment", key="rq-fu-segment", width="stretch", on_click=_run,
                     args=(f"How does this differ by segment (age, income, first-time or experienced)? "
                           f"{result.get('question', '')}",))
    elif result.get("excerpts"):
        st.caption("Evidence only: no written answer was requested.")

    if status == "insufficient_evidence":
        st.info(f"Fewer than {result.get('evidence_needed', 15)} supporting posts passed the relevance cut-off. More "
                "data would help: a longer Play Store window, YouTube comments or the survey.", icon="ℹ️")
    if result.get("filters"):
        st.caption("Filters: " + ", ".join(f"{k} = {v}" for k, v in result["filters"].items())
                   + ". The app filter covers app-store reviews only.")

    excerpts = result.get("excerpts", [])
    ui.heading(f"Evidence retrieved ({len(excerpts)} excerpts, best first)")
    show_all = st.session_state.pop("rq_show_all", False)
    if excerpts:
        st.dataframe(pd.DataFrame([{
            "Rank": i, "Match": round(e.get("score", 0), 2), "Source": client.source_label(e),
            "Month": client.month(e), "Type": e.get("doc_type", ""), "Excerpt (up to 25 words)": client.short(e.get("text", "")),
        } for i, e in enumerate(excerpts, 1)]), hide_index=True, width="stretch")
        with st.expander("Read them as quotes", expanded=show_all):
            st.markdown(_quotes_html(excerpts, with_score=True), unsafe_allow_html=True)
    else:
        st.caption("No excerpt passed the relevance cut-off.")
    if result.get("context"):
        with st.expander(f"Background from SIP information pages ({len(result['context'])})"):
            st.markdown(_quotes_html(result["context"], with_score=True), unsafe_allow_html=True)
            st.caption("Context for definitions only, never counted as evidence.")
    for note in result.get("notes", []):
        st.caption(note)
    with st.expander("Evidence bundle (what the answer step receives)"):
        st.json(client.safe_bundle(result), expanded=False)
    st.caption(f"Last updated from sources: {result.get('last_updated') or 'unknown'}. Counts are mentions in public "
               "posts, not population percentages.")


def render(site: SiteData) -> None:
    excerpts = f"{site.excerpts_total:,} excerpts" if site.ready else "the evidence store"
    ui.page_header("Research tool · Ask the engine",
                   f"Ask a question and get an answer grounded in {excerpts} from public posts and reviews",
                   "any discovery question, answered only from the evidence, with its sample size, confidence, quotes "
                   "and the page section it comes from.")
    _status_line(client.api_status())
    st.info("Research tool, not investment advice. It does not recommend funds, calculate returns or answer "
            "questions about individuals.", icon="ℹ️")

    st.text_area("Your question", key="rq_input", height=90, max_chars=config.QUESTION_MAX_CHARS,
                 placeholder="e.g. Why do SIP instalments fail even after money is debited?")
    apps = [a.app for a in site.apps if a.source == "play_store"]
    c1, c2, c3 = st.columns([1.2, 1.2, 1.6])
    c1.selectbox("Evidence from", [client.ALL_SOURCES, *apps], key="rq_app",
                 help="An app filter covers that app's store reviews only, not forum or Reddit posts.")
    c2.selectbox("Source", list(client.SOURCE_FILTERS), key="rq_source")
    c3.radio("Show", list(client.MODES), key="rq_mode", horizontal=True,
             help="Evidence only skips the written answer, so it is faster and makes no Mistral call.")
    b1, b2, _ = st.columns([1, 1, 4])
    b1.button("Ask", type="primary", width="stretch", on_click=_run, key="rq-ask")
    b2.button("Clear", width="stretch", on_click=_clear, key="rq-clear")

    result = st.session_state.get("rq_result")
    if not result:
        ui.heading("Try a sample question")
        cols = st.columns(2)
        for i, q in enumerate(client.SAMPLE_QUESTIONS):
            cols[i % 2].button(q, key=f"rq-sample-{i}", width="stretch", on_click=_run, args=(q,))
    else:
        _result(*result)

    history = st.session_state.get("rq_history", [])
    if len(history) > 1:
        ui.heading("Recent questions")
        for i, q in enumerate(history[1:]):
            st.button(q, key=f"rq-history-{i}", on_click=_run, args=(q,))
