"""The full-page research tool (app/views/research.py), rendered with Streamlit's AppTest. The
retrieval client is stubbed, so these tests need neither the API nor the model."""
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1] / "app"

SCRIPT = """
import sys
sys.path[:0] = [{code!r}, {app!r}]
import streamlit as st
import research_client, site_data, ui
from views import research

CALLS = st.session_state.setdefault("calls", [])

def fake_query(question, app=None, source=None, mode="answer", section=None):
    CALLS.append({{"question": question, "app": app, "source": source, "mode": mode, "section": section}})
    if "safest" in question.lower():
        return {{"question": question, "status": "out_of_scope", "reason": "investment_advice", "supporting_items": 0,
                "decline_links": [{{"label": "AMFI", "url": "https://www.amfiindia.com/investor"}}],
                "answer": {{"text": "This is a research tool, not investment advice.", "quotes": []}}}}, "api"
    excerpts = [{{"chunk_id": f"c{{i}}", "record_id": f"r{{i}}", "score": 0.7 - i / 100, "source": "play_store",
                  "app": "Groww", "doc_type": "review", "date": "2026-10-01", "url": "u",
                  "text": "my sip instalment failed and the money was debited " * 4}} for i in range(1, 9)]
    bundle = {{"question": question, "status": "evidence", "supporting_items": 20, "evidence_needed": 15,
              "page_link": "Drop-offs → Failure modes", "route": {{"section": "failure-modes"}}, "excerpts": excerpts,
              "context": [], "filters": {{k: v for k, v in (("app", app), ("source", source)) if v}},
              "notes": [], "last_updated": "2026-11-01"}}
    if mode == "answer":
        bundle["answer"] = {{"text": "Failed instalments lead the list (451 posts).", "confidence": "High",
                            "confidence_reason": "many posts agree", "sample_size": "n = 20 supporting posts",
                            "quotes": [{{"text": "my sip instalment failed", "source": "play_store", "app": "Groww",
                                        "month": "Oct 2026"}}], "page_link": "Drop-offs → Failure modes",
                            "guardrail": {{"passed": True, "fallback": False}}}}
    return bundle, "api"

research_client.query = fake_query
research_client.api_status = lambda: {{"excerpts": 19798, "sections": 13, "last_updated_from_sources": "2026-11-01"}}
ui.css()
research.render(site_data.SiteData(ready=True, excerpts_total=19798))
"""


@pytest.fixture
def app():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_string(SCRIPT.format(code=str(APP_DIR.parent), app=str(APP_DIR)), default_timeout=60).run()


def labels(at):
    return [b.label for b in at.button]


def test_empty_state_has_four_samples_and_no_results(app):
    assert not app.exception
    samples = [b for b in labels(app) if b not in ("Ask", "Clear")]
    assert len(samples) == 4 and not app.dataframe
    assert any("Connected to the retrieval API" in c.value for c in app.caption)


def test_sample_question_shows_answer_route_and_evidence(app):
    at = next(b for b in app.button if b.label.startswith("What leads investors")).click().run()
    assert not at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "Failed instalments lead the list (451 posts)." in text
    assert "Evidence-grounded" in text and "Drop-offs → Failure modes" in text
    assert len(at.dataframe[0].value) == 8  # every retrieved excerpt, best first
    assert all(len(x.split()) <= 26 for x in at.dataframe[0].value["Excerpt (up to 25 words)"])
    assert at.session_state["calls"][-1]["mode"] == "answer"


def test_answer_comes_first_and_research_detail_is_collapsed(app):
    at = next(b for b in app.button if b.label.startswith("What leads investors")).click().run()
    panel = next(e for e in at.expander if e.label == "Evidence and confidence")
    assert not panel.proto.expanded  # the detail is one click away, not in front of the answer
    assert any("Source: Drop-offs → Failure modes" in c.value and "Last updated from sources" in c.value
               for c in at.caption)


def test_segment_follow_up_asks_the_segments_section(app):
    at = next(b for b in app.button if b.label.startswith("What leads investors")).click().run()
    at = next(b for b in at.button if b.label == "Break down by segment").click().run()
    call = at.session_state["calls"][-1]
    assert call["section"] == "segments" and call["question"].startswith("How does this differ by investor segment")
    at = next(b for b in at.button if b.label == "Break down by segment").click().run()
    assert at.session_state["calls"][-1]["question"].count("How does this differ") == 1  # never prefixed twice


def test_evidence_only_mode_and_filters_reach_the_client(app):
    app.radio[0].set_value("Evidence only")
    app.selectbox[1].set_value("Reddit")
    app.text_area[0].input("Why do SIP mandates fail?")
    at = next(b for b in app.button if b.label == "Ask").click().run()
    call = at.session_state["calls"][-1]
    assert call == {"question": "Why do SIP mandates fail?", "app": None, "source": "reddit", "mode": "evidence",
                    "section": None}
    assert len(at.dataframe[0].value) == 8
    assert any("Evidence only" in c.value for c in at.caption)


def test_refusal_shows_official_links_and_no_evidence_table(app):
    app.text_area[0].input("Which is the safest SIP?")
    at = next(b for b in app.button if b.label == "Ask").click().run()
    md = " ".join(m.value for m in at.markdown)
    assert "Out of scope" in md and "amfiindia.com" in md and not at.dataframe


def test_short_question_is_rejected(app):
    app.text_area[0].input("hi")
    at = next(b for b in app.button if b.label == "Ask").click().run()
    assert at.warning and "at least 3 characters" in at.warning[0].value


def test_without_api_or_vector_store_the_client_says_unavailable(monkeypatch, tmp_path):
    """A deployment built from the repository has no vector store (it is git-ignored) and no API."""
    import importlib
    import sys
    import requests
    sys.path[:0] = [str(APP_DIR.parent), str(APP_DIR)]
    import research_client
    research_client = importlib.reload(research_client)  # the page tests above stub its functions in-process
    from src import config

    def refuse(*args, **kwargs):
        raise requests.ConnectionError("no API")
    monkeypatch.setattr(research_client.requests, "post", refuse)
    monkeypatch.setattr(config, "VECTOR_DB_DIR", tmp_path / "chroma")
    result, how = research_client.query("Why do SIP instalments fail?")
    assert result == {"status": "unavailable", "detail": research_client.UNAVAILABLE} and how == ""


def test_page_warns_up_front_when_questions_cannot_be_answered():
    from streamlit.testing.v1 import AppTest
    script = SCRIPT.replace(
        'research_client.api_status = lambda: {{"excerpts": 19798, "sections": 13, "last_updated_from_sources": "2026-11-01"}}',
        "research_client.api_status = lambda: None\nresearch_client.local_store_ready = lambda: False")
    at = AppTest.from_string(script.format(code=str(APP_DIR.parent), app=str(APP_DIR)), default_timeout=60).run()
    assert not at.exception
    assert any("not part of this deployment" in w.value for w in at.warning)
