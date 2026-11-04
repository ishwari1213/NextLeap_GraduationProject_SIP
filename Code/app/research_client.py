"""The site's retrieval client, shared by the full-page research tool and the sidebar.

A question goes to the phase 5 API on port 8001 (Docs/architecture.md):
    POST /api/ask       evidence bundle + a checked, written answer (Mistral)
    POST /api/retrieve  evidence bundle only (no Mistral call)
If the API is not running, the same retrieval and answer code runs in-process instead.
Quotes are de-identified and cut to at most 25 words, labelled with source and month only
(UI spec rule 4).
"""
from __future__ import annotations

import requests
import streamlit as st

from site_data import SOURCE_LABELS, month_label
from src import config

SAMPLE_QUESTIONS = [  # exactly four, from the UI spec
    "What leads investors to pause, reduce or stop a SIP?",
    "Where do investors go when they are unsure?",
    "Which opportunity should we solve first, and why?",
    "How do first-time investors differ from experienced ones?",
]
BADGES = {
    "evidence": ("Evidence-grounded", "ok"),
    "insufficient_evidence": ("Insufficient evidence", "warn"),
    "out_of_scope": ("Out of scope", "muted"),
}
REASONS = {
    "investment_advice": "asks for investment advice or a fund pick",
    "returns_or_projection": "asks to calculate, project or compare returns",
    "personal_data": "contains personal details",
    "individual": "is about an individual person",
    "off_topic": "is outside what the engine studies",
}
REFUSALS = {
    "investment_advice": "This is a research tool, not investment advice, so it does not recommend funds, SIPs or "
                         "actions. Official investor information:",
    "returns_or_projection": "This tool does not calculate, project or compare returns. For scheme facts see the "
                             "official factsheet or these investor pages:",
    "personal_data": "Please remove personal details (PAN, Aadhaar, account numbers, OTPs, phone numbers or emails) "
                     "and ask again. Nothing you typed was stored.",
    "individual": "This tool does not answer questions about individual people.",
    "off_topic": "This question is outside what the engine studies: how investors start, continue, pause and stop "
                 "SIPs.",
}
SOURCE_FILTERS = {"All source types": None, "Google Play": "play_store", "App Store": "app_store",
                  "Forums": "forums", "Reddit": "reddit", "Team-BHP": "team_bhp"}
ALL_SOURCES = "All sources"
QUOTE_WORDS = 25
MODES = {"Answer and evidence": "answer", "Evidence only": "evidence"}


UNAVAILABLE = ("The evidence store is not part of this deployment, so questions cannot be answered here. The site's "
               "pages are built from the same pipeline. To ask questions, run the site locally after phases 1 to 4, or "
               "set API_BASE_URL to a running retrieval API.")


IN_APP_NOTE = ("Questions are answered inside this app. The first one after a restart loads the search model, "
               "about 10 to 20 seconds.")


def local_store_ready() -> bool:
    """True when the phase 4 vector store is on this machine, so questions can run in-process."""
    return (config.VECTOR_DB_DIR / "chroma.sqlite3").exists()


def in_app() -> bool:
    """True on a deployment that answers questions inside the site, with no separate API (Render)."""
    return config.EMBEDDING_BACKEND == "onnx"


@st.cache_resource(show_spinner="Loading the search model (first question only)...")
def _local_retriever():
    from src.phase5_retrieval.retriever import Retriever
    return Retriever().warm_up()


@st.cache_data(ttl=15, show_spinner=False)
def api_status() -> dict | None:
    """The API's health answer, or None when it is not reachable."""
    try:
        resp = requests.get(f"{config.API_BASE_URL}/api/health", timeout=2)
        return resp.json() if resp.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None


def query(question: str, *, app: str | None = None, source: str | None = None,
          mode: str = "answer") -> tuple[dict, str]:
    """(result, how): the evidence bundle (with `answer` in answer mode), and 'api' or 'local'.
    With neither the API nor a local vector store: status 'unavailable' and how ''."""
    payload = {"question": question, **({"app": app} if app else {}), **({"source": source} if source else {})}
    endpoint = "/api/ask" if mode == "answer" else "/api/retrieve"
    try:
        resp = requests.post(f"{config.API_BASE_URL}{endpoint}", json=payload, timeout=(2, 120))
        if resp.status_code == 422:
            return {"status": "invalid", "detail": "Questions need 3 to 500 characters."}, "api"
        resp.raise_for_status()
        return resp.json(), "api"
    except requests.RequestException:
        pass
    if not local_store_ready():
        return {"status": "unavailable", "detail": UNAVAILABLE}, ""
    try:
        bundle = _local_retriever().retrieve(question, app=app, source=source)
    except Exception as exc:  # a damaged or partial store: say so instead of crashing the page
        return {"status": "unavailable", "detail": f"The local evidence store could not be searched ({exc})."}, ""
    if mode == "answer":
        from src.answer.generate import answer
        bundle = {**bundle, "answer": answer(bundle)}
    return bundle, "local"


def short(text: str, words: int = QUOTE_WORDS) -> str:
    parts = " ".join((text or "").split()).split()
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


def source_label(ex: dict) -> str:
    label = SOURCE_LABELS.get(ex.get("source", ""), ex.get("source", ""))
    return f"{label} · {ex['app']}" if ex.get("app") else label


def month(ex: dict) -> str:
    return ex.get("month") or month_label(ex.get("date"))


def safe_bundle(bundle: dict) -> dict:
    """The bundle for display: excerpt texts cut to 25 words, record ids and URLs left out."""
    def trim(ex: dict) -> dict:
        return {"score": ex.get("score"), "source": ex.get("source"), "app": ex.get("app"),
                "doc_type": ex.get("doc_type"), "month": month(ex), "text": short(ex.get("text", ""))}
    out = {k: v for k, v in bundle.items() if k not in ("excerpts", "context", "answer")}
    out["excerpts"] = [trim(e) for e in bundle.get("excerpts", [])]
    out["context"] = [trim(e) for e in bundle.get("context", [])]
    if bundle.get("answer"):
        out["answer"] = {k: v for k, v in bundle["answer"].items() if k != "guardrail"}
        out["answer"]["guardrail"] = {k: bundle["answer"].get("guardrail", {}).get(k)
                                      for k in ("passed", "retried", "fallback", "model")}
    return out
