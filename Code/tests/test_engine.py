"""Tests for tagging (FR-5), scoring (FR-6), the answer step and its guardrail (FR-9 to FR-14) and
the phase 6 relevance rule. Mistral is never called: model answers are stubbed."""
import pytest

from src import config
from src.answer import generate
from src.phase6_retrieval_testing.evaluate import relevant
from src.site_export import scoring
from src.tagging import tagger, taxonomy


# --- tagging --------------------------------------------------------------------------------

def test_route_sends_store_reviews_without_sip_words_to_rule():
    assert tagger.route({"source": "play_store", "text": "Great app, love it"}) == "rule"
    assert tagger.route({"source": "play_store", "text": "My SIP autopay failed"}) == "llm"
    assert tagger.route({"source": "reddit", "text": "Great app"}) == "llm"
    assert tagger.route({"source": "info_pages", "text": "What is SIP"}) == "skip"


def test_clean_handles_lists_spellings_and_unknown_words():
    tags, invalid = taxonomy.clean({"stage": ["first_instalment", "onboarding"], "experience": "First-time",
                                    "failure_mode": "Not stated", "income": "banker"})
    assert tags["stage"] == "first_instalment" and tags["experience"] == "first_time"
    assert tags["failure_mode"] == "none" and tags["income"] == "not_stated" and invalid == 1


@pytest.mark.parametrize("response", [
    {"posts": [{"id": 1, "about_sip": False}, {"id": 2, "about_sip": True, "event": "stopped"}]},
    [{"id": 1, "about_sip": False}, {"id": "2", "about_sip": True, "event": "stopped"}],
    {"results": [{"id": 1, "about_sip": False}, {"id": 2, "about_sip": True, "event": "stopped"}]},
])
def test_parse_accepts_every_answer_shape(response):
    batch = [{"id": "a", "source": "reddit", "text": "x"}, {"id": "b", "source": "reddit", "text": "y"}]
    rows, _ = tagger.parse(response, batch)
    assert [(r["record_id"], r["about_sip"], r["event"]) for r in rows] == [("a", False, "not_stated"),
                                                                            ("b", True, "stopped")]


def test_parse_leaves_unanswered_posts_untagged():
    rows, _ = tagger.parse({"posts": [{"id": 2, "about_sip": False}]},
                           [{"id": "a", "source": "reddit", "text": "x"}, {"id": "b", "source": "reddit", "text": "y"}])
    assert [r["record_id"] for r in rows] == ["b"]


# --- scoring ----------------------------------------------------------------------------------

def post(fm, event="not_stated", stage="not_stated", experience="not_stated"):
    return {"failure_mode": fm, "event": event, "stage": stage, "experience": experience}


def test_score_follows_the_prd_formula_and_left_out_rule():
    posts = ([post("instalment_failed", "stopped", "months_2_6", "first_time")] * 10 +
             [post("instalment_failed", "continued", "after_year_1", "experienced")] * 10 +
             [post("cannot_pause_or_change_amount")] * 6 + [post("losses_shake_confidence")] * 2)
    rows = {r["id"]: r for r in scoring.score(posts)}
    top = rows["reliable_instalments"]
    # reach 1.0, severity 0.5, stage fit 0.5, segment fit 0.5 -> 100 x (0.4 + 0.15 + 0.075 + 0.075) = 70
    assert top["score"] == 70 and top["tag"] == "Scored" and top["left_out"] == []
    flex = rows["flexible_controls"]  # only reach is stated by 5+ posts: 6/20 -> 30
    assert flex["score"] == 30 and set(flex["left_out"]) == {"severity", "stage_fit", "segment_fit"}
    assert flex["tag"] == "Small sample"
    assert rows["confidence_losses"]["score"] is None and rows["easy_return"]["tag"] == "Not scored"
    assert scoring.score(posts)[0]["id"] == "reliable_instalments"


# --- answer step and guardrail ------------------------------------------------------------------

def bundle(status="evidence", **extra):
    return {"question": "Why do SIPs fail?", "status": status, "supporting_items": 20, "page_link": "Drop-offs → Failure modes",
            "section_data": {"key_numbers": {"Instalment failed: posts": 451}},
            "excerpts": [{"chunk_id": f"c{i}", "text": f"my sip failed twice in month {i}", "source": "play_store",
                          "app": "Groww", "date": "2026-10-01"} for i in range(1, 4)], **extra}


def test_tidy_removes_excerpt_ids_and_markdown():
    assert generate.tidy("SIPs fail (**451** posts). Excerpts **E2** and **E3** agree (E1).") == "SIPs fail (451 posts). agree."


def test_check_flags_unsupported_numbers_bad_quotes_and_advice():
    b = bundle()
    assert generate.check({"answer": "451 posts report failures.", "quote_ids": ["E1"]}, b) == []
    problems = generate.check({"answer": "999 posts; you should invest more.", "quote_ids": ["E9"]}, b)
    assert any("999" in p for p in problems) and any("quote_ids" in p for p in problems) and any("advice" in p for p in problems)


def test_answer_passes_or_retries_then_falls_back(monkeypatch):
    replies = iter([{"answer": "999 posts fail.", "quote_ids": ["E1"], "confidence": "High"},
                    {"answer": "451 posts report failed instalments.", "quote_ids": ["E1", "E2"],
                     "confidence": "High", "confidence_reason": "many posts"}])
    monkeypatch.setattr(generate, "chat_json", lambda *a, **k: next(replies))
    a = generate.answer(bundle())
    assert a["guardrail"]["retried"] and a["guardrail"]["passed"] and a["text"].startswith("451 posts")
    assert [q["chunk_id"] for q in a["quotes"]] == ["c1", "c2"] and a["confidence"] == "High"

    monkeypatch.setattr(generate, "chat_json", lambda *a, **k: {"answer": "777 posts.", "quote_ids": []})
    fallback = generate.answer(bundle())
    assert fallback["guardrail"]["fallback"] and fallback["confidence"] == "Low" and len(fallback["quotes"]) == 3


def test_confidence_is_capped_by_evidence(monkeypatch):
    monkeypatch.setattr(generate, "chat_json", lambda *a, **k: {"answer": "451 posts.", "quote_ids": ["E1"],
                                                                 "confidence": "High"})
    assert generate.answer(bundle(status="insufficient_evidence"))["confidence"] == "Low"
    assert generate.answer(bundle(supporting_items=8))["confidence"] == "Medium"


def test_out_of_scope_never_calls_the_model(monkeypatch):
    monkeypatch.setattr(generate, "chat_json", lambda *a, **k: pytest.fail("model called"))
    a = generate.answer(bundle(status="out_of_scope", reason="investment_advice", decline_links=config.OFFICIAL_LINKS))
    assert "not investment advice" in a["text"] and a["links"] == config.OFFICIAL_LINKS and a["badge"] == "Out of scope"


# --- phase 6 relevance rule -----------------------------------------------------------------------

def test_relevance_rule():
    tags = {**taxonomy.empty_tags(), "about_sip": True, "failure_mode": "instalment_failed"}
    assert relevant(tags, {"failure_mode": "any"})
    assert relevant(tags, {"failure_mode": ["instalment_failed"], "theme": ["sip_controls"]})
    assert not relevant(tags, {"checking": "any"})
    assert not relevant({**tags, "about_sip": False}, {"failure_mode": "any"})
