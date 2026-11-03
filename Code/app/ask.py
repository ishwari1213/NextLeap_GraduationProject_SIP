"""'Ask the engine' in the sidebar of every page (PRD UX section); the full-page view is views/research.py.

Empty state: a short intro, the disclaimer and exactly 4 sample questions; no answer is shown
until the reader clicks one or asks their own (UI spec section 4). Questions go through the
shared client (research_client.py): POST /api/ask on port 8001, or in-process if the API is down.
Quotes are de-identified, at most 25 words, labelled with source and month only (UI spec rule 4).
"""
from __future__ import annotations

from html import escape

import streamlit as st

from research_client import ALL_SOURCES, BADGES, QUOTE_WORDS, REFUSALS, SAMPLE_QUESTIONS, query
from site_data import SOURCE_LABELS, SiteData, month_label
from src import config


def retrieve(question: str, app: str | None) -> tuple[dict, str]:
    """(bundle with `answer`, how) where how is 'api' or 'local'."""
    return query(question, app=app, mode="answer")


def submit(question: str | None = None) -> None:
    """Button callback: run a question and keep the result for the sidebar to show."""
    question = (question or st.session_state.get("ask_input", "")).strip()
    if len(question) < 3:
        st.session_state["ask_result"] = ({"status": "invalid", "detail": "Type a question first."}, "")
        return
    app = st.session_state.get("ask_app")
    app = None if app in (None, ALL_SOURCES) else app
    st.session_state["ask_input"] = question
    st.session_state["ask_result"] = retrieve(question, app)


def clear() -> None:
    st.session_state.pop("ask_result", None)
    st.session_state["ask_input"] = ""


def _quote(text: str) -> str:
    words = text.split()
    return " ".join(words[:QUOTE_WORDS]) + ("…" if len(words) > QUOTE_WORDS else "")


def _quote_html(ex: dict) -> str:
    label = SOURCE_LABELS.get(ex.get("source", ""), ex.get("source", ""))
    if ex.get("app"):
        label += f" · {ex['app']}"
    month = month_label(ex.get("date"))
    meta = f"{label} · {month}" if month else label
    return (f'<div class="sde-quote">“{escape(_quote(ex.get("text", "")))}”'
            f'<span class="meta">{escape(meta)} · match {ex.get("score", 0):.2f}</span></div>')


def _answer_quote_html(q: dict) -> str:
    label = SOURCE_LABELS.get(q.get("source", ""), q.get("source", ""))
    if q.get("app"):
        label += f" · {q['app']}"
    meta = f"{label} · {q['month']}" if q.get("month") else label
    return f'<div class="sde-quote">“{escape(q.get("text", ""))}”<span class="meta">{escape(meta)}</span></div>'


def _show_result(bundle: dict, how: str) -> None:
    status = bundle.get("status")
    if status in ("invalid", "unavailable"):
        st.warning(bundle.get("detail", ""))
        return
    st.markdown(f"**{escape(bundle.get('question', ''))}**")
    label, kind = BADGES.get(status, (status, "muted"))
    n = bundle.get("supporting_items", 0)
    st.markdown(f'<span class="sde-pill pill-{kind}">{escape(label)}</span>'
                + (f'&nbsp; n = {n} supporting posts' if status != "out_of_scope" else ""),
                unsafe_allow_html=True)

    ans = bundle.get("answer")
    if status == "out_of_scope":
        st.write(ans["text"] if ans else REFUSALS.get(bundle.get("reason"), "This question is out of scope."))
        for link in bundle.get("decline_links", []):
            st.markdown(f"- [{link['label']}]({link['url']})")
        return

    if ans:
        st.write(ans["text"])
        if ans.get("confidence"):
            st.caption(f"Confidence: **{ans['confidence']}** · {ans.get('confidence_reason', '')}")
        st.markdown("".join(_answer_quote_html(q) for q in ans.get("quotes", [])), unsafe_allow_html=True)
        if ans.get("page_link"):
            st.caption(f"See: {ans['page_link']}")
        if ans.get("guardrail", {}).get("fallback"):
            st.caption("Shown as a plain evidence summary: a written answer did not pass the number and quote checks.")
        left, right = st.columns(2)
        left.button("Show quotes", key="fu-quotes", width="stretch",
                    on_click=lambda: st.session_state.update(ask_show_all=True))
        right.button("Break down by segment", key="fu-segment", width="stretch", on_click=submit,
                     args=(f"How does this differ by segment (age, income, first-time or experienced)? "
                           f"{bundle.get('question', '')}",))

    if status == "insufficient_evidence":
        st.caption(f"Fewer than {bundle.get('evidence_needed', 15)} supporting posts passed the relevance cut-off. "
                   "More data would help: a longer Play Store window, YouTube comments or the survey.")
    if bundle.get("filters"):
        st.caption("Filter: " + ", ".join(f"{k} = {v}" for k, v in bundle["filters"].items())
                   + " (app filter covers app-store reviews only)")

    excerpts = bundle.get("excerpts", [])
    if not ans:
        st.markdown("".join(_quote_html(e) for e in excerpts[:3]), unsafe_allow_html=True)
    with st.expander(f"All evidence retrieved ({len(excerpts)})", expanded=st.session_state.pop("ask_show_all", False)):
        st.markdown("".join(_quote_html(e) for e in excerpts), unsafe_allow_html=True)
    if bundle.get("context"):
        with st.expander("Background from SIP information pages"):
            st.markdown("".join(_quote_html(e) for e in bundle["context"]), unsafe_allow_html=True)
            st.caption("Context for definitions only, never counted as evidence.")
    st.caption(f"Answer written by Mistral from the evidence only, checked for unsupported numbers and quotes. "
               f"Last updated from sources: {bundle.get('last_updated') or 'unknown'}."
               + (" Answered in-process because the API on port 8001 is not running." if how == "local" else ""))


def sidebar(site: SiteData, full_view=None) -> None:
    with st.sidebar:
        st.markdown("### 💬 Ask the engine")
        excerpts = f"{site.excerpts_total:,} excerpts" if site.ready else "the evidence store"
        st.caption(f"Searches {excerpts} from public posts and reviews and shows the evidence behind an answer.")
        if full_view is not None:
            st.page_link(full_view, label="Open the full research view", icon="🔎")
        st.info("Research tool, not investment advice. It does not recommend funds or calculate returns.",
                icon="ℹ️")

        apps = [a.app for a in site.apps if a.source == "play_store"]
        st.selectbox("Evidence from", [ALL_SOURCES, *apps], key="ask_app",
                     help="An app filter covers that app's store reviews only, not forum or Reddit posts.")
        st.text_area("Your question", key="ask_input", height=80, max_chars=config.QUESTION_MAX_CHARS,
                     placeholder="e.g. Why do SIP instalments fail?")
        left, right = st.columns(2)
        left.button("Ask", type="primary", width="stretch", on_click=submit)
        right.button("Clear", width="stretch", on_click=clear)

        result = st.session_state.get("ask_result")
        if not result:
            st.caption("Try a sample question:")
            for q in SAMPLE_QUESTIONS:
                st.button(q, key=f"chip-{q}", width="stretch", on_click=submit, args=(q,))
            return
        st.divider()
        _show_result(*result)


def explore_buttons(questions: list[str], key: str) -> None:
    """Buttons on a page that send its questions to the sidebar tool."""
    st.caption("Explore the evidence now: each button runs the question in Ask the engine (sidebar).")
    for col, q in zip(st.columns(len(questions)), questions):
        col.button(q, key=f"{key}-{q}", width="stretch", on_click=submit, args=(q,))
