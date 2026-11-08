"""Phase 5 unit tests: scope rules, search helpers, every bundle status (with a stand-in
store), the API, and one end-to-end check against the real vector DB when it exists."""
import numpy as np
import pytest

from src import config
from src.phase5_retrieval import scope
from src.phase5_retrieval.retriever import Retriever
from src.phase5_retrieval.search import build_where, supporting_count

DISCOVERY_QUESTIONS = [  # problem statement + the four sample chips: all must stay in scope
    "Why do people start a SIP, and what do they expect to happen?",
    "What changes in their behaviour in the months after starting?",
    "What leads investors to pause, reduce or stop a SIP?",
    "What do investors check, and how often, once they have started?",
    "What confuses or worries them inside the app?",
    "What do they do outside the app when they feel unsure?",
    "What separates investors who continue from those who quietly drop off?",
    "How do these patterns differ across user segments (income stability, age, source of money, who influenced them)?",
    "What unmet needs emerge consistently across conversations?",
    "Where do investors go when they are unsure?",
    "Which opportunity should we solve first, and why?",
    "How do first-time investors differ from experienced ones?",
    "What confuses investors about returns in the first months?",
    "Why did my SIP autopay mandate fail?",
]


@pytest.mark.parametrize("question", DISCOVERY_QUESTIONS)
def test_discovery_questions_stay_in_scope(question):
    assert scope.check_input(question).allowed
    assert scope.check_scope(question).allowed, scope.check_scope(question).detail


@pytest.mark.parametrize("question, reason", [
    ("Which is the safest SIP?", "investment_advice"),
    ("Should I stop my SIP now?", "investment_advice"),
    ("What is the best mutual fund for 2027?", "investment_advice"),
    ("Can you recommend a good fund for me?", "investment_advice"),
    ("Is Parag Parikh flexi cap good?", "investment_advice"),
    ("How much will 5000 a month become in 10 years?", "returns_or_projection"),
    ("What are the expected returns of an index fund?", "returns_or_projection"),
    ("Which fund gives the highest returns?", "returns_or_projection"),
    ("Will the market crash next month?", "returns_or_projection"),
    ("What did u/some_user say about Groww?", "individual"),
    ("Who wrote the review about failed payments?", "individual"),
])
def test_out_of_scope_questions(question, reason):
    result = scope.check_scope(question)
    assert not result.allowed and result.reason == reason


def test_personal_data_is_refused_and_redacted():
    result = scope.check_input("My PAN is ABCDE1234F and phone 9876543210, why did my SIP fail?")
    assert not result.allowed and result.reason == "personal_data"
    assert "ABCDE1234F" not in result.question and "9876543210" not in result.question


def test_brand_handles_are_not_individuals():
    assert scope.check_scope("Why do people complain to @Groww about SIP payments?").allowed


def test_build_where_and_supporting_count():
    assert build_where() is None
    assert build_where(app="Groww") == {"app": "Groww"}
    assert build_where(app="Groww", source="play_store") == {"$and": [{"app": "Groww"}, {"source": "play_store"}]}
    assert build_where(exclude_doc_type="info_page") == {"doc_type": {"$ne": "info_page"}}
    assert build_where(doc_type="review", exclude_doc_type="info_page") == {"doc_type": "review"}
    cands = [{"record_id": "a", "doc_type": "post"}, {"record_id": "a", "doc_type": "post"},
             {"record_id": "b", "doc_type": "review"}, {"record_id": "c", "doc_type": "info_page"}]
    assert supporting_count(cands) == 2  # one long post counts once; info pages never count


# --- retriever with a stand-in store --------------------------------------------------------

class FakeEmbedder:
    def embed(self, texts):
        v = np.zeros((len(texts), config.EMBEDDING_DIM), np.float32)
        v[:, 0] = 1.0
        return v


def matches(meta, where):
    """The subset of Chroma's `where` syntax the retriever uses: equality, $ne and $and."""
    if not where:
        return True
    if "$and" in where:
        return all(matches(meta, w) for w in where["$and"])
    (field, cond), = where.items()
    if isinstance(cond, dict):
        return meta.get(field) != cond["$ne"]
    return meta.get(field) == cond


class FakeCollection:
    """Returns rows with the given similarity scores, honouring `where` filters."""

    def __init__(self, rows, metadata=None):
        self.rows, self.metadata = rows, metadata or {"last_updated_from_sources": "2026-11-01"}

    def count(self):
        return len(self.rows)

    def query(self, query_embeddings, n_results, where=None, include=None):
        rows = [r for r in self.rows if matches(r["meta"], where)]
        rows = sorted(rows, key=lambda r: -r["score"])[:n_results]
        return {"ids": [[r["id"] for r in rows]], "documents": [[r["text"] for r in rows]],
                "metadatas": [[r["meta"] for r in rows]], "distances": [[1 - r["score"] for r in rows]]}


def rows(n, score, app="Groww", doc_type="review", prefix="r"):
    return [{"id": f"{prefix}{i}-0", "score": score - i * 0.001, "text": f"excerpt {prefix}{i}",
             "meta": {"record_id": f"{prefix}{i}", "source": "play_store", "app": app, "doc_type": doc_type,
                      "date": "2026-10-01", "url": "https://example.com"}} for i in range(n)]


def retriever(excerpt_rows, section_rows=()):
    return Retriever(embedder=FakeEmbedder(), excerpts=FakeCollection(excerpt_rows),
                     sections=FakeCollection(list(section_rows))).warm_up()


def test_status_evidence_with_top_excerpts_only():
    b = retriever(rows(20, 0.8)).retrieve("What leads investors to stop a SIP?")
    assert b["status"] == "evidence" and b["supporting_items"] == 20
    assert len(b["excerpts"]) == config.RETRIEVAL_PROMPT_EXCERPTS and b["excerpts"][0]["score"] == 0.8
    assert b["last_updated"] == "2026-11-01" and b["route"] is None and b["notes"]  # no sections yet


def test_info_pages_are_context_never_evidence():
    data = rows(10, 0.95, app="Kotak", doc_type="info_page", prefix="info") + rows(20, 0.7)
    b = retriever(data).retrieve("What does pausing a SIP mean?")
    assert b["status"] == "evidence" and b["supporting_items"] == 20
    assert all(e["doc_type"] != "info_page" for e in b["excerpts"])
    assert len(b["context"]) == config.RETRIEVAL_CONTEXT_EXCERPTS and b["context"][0]["doc_type"] == "info_page"


def test_status_insufficient_when_few_records_pass_the_cutoff():
    b = retriever(rows(5, 0.8) + rows(15, 0.40, prefix="low")).retrieve("Why do NRIs pause SIPs?")
    assert b["status"] == "insufficient_evidence" and b["supporting_items"] == 5
    assert all(e["score"] >= config.RETRIEVAL_MIN_SIMILARITY for e in b["excerpts"])


def test_status_off_topic_when_best_excerpt_is_weak():
    b = retriever(rows(20, 0.3)).retrieve("What is the capital of France?")
    assert b["status"] == "out_of_scope" and b["reason"] == "off_topic" and b["excerpts"] == []


def test_filter_with_little_data_is_insufficient_not_off_topic():
    data = rows(20, 0.8, app="Groww") + rows(3, 0.7, app="Sundaram MF", prefix="s")
    b = retriever(data).retrieve("Why do SIP payments fail?", app="Sundaram MF")
    assert b["status"] == "insufficient_evidence" and b["supporting_items"] == 3 and b["filters"] == {"app": "Sundaram MF"}


def test_advice_is_refused_before_search_with_official_links():
    b = retriever(rows(20, 0.8)).retrieve("Which is the safest SIP?")
    assert b["status"] == "out_of_scope" and b["reason"] == "investment_advice"
    assert [link["url"] for link in b["decline_links"]] == [link["url"] for link in config.OFFICIAL_LINKS]


def test_routing_uses_sections_when_they_exist(monkeypatch, tmp_path):
    index = tmp_path / "sections_index.json"
    index.write_text('[{"page": "Drop-offs", "section_id": "failure-modes", "title": "Failure modes", "text": "t"}]')
    monkeypatch.setattr(config, "SECTIONS_INDEX_FILE", index)
    section = [{"id": "failure-modes", "score": 0.7, "text": "t", "meta": {"page": "Drop-offs", "section_id": "failure-modes"}}]
    b = retriever(rows(20, 0.8), section).retrieve("What leads investors to stop a SIP?")
    assert b["route"] == {"page": "Drop-offs", "section": "failure-modes", "title": "Failure modes", "score": 0.7}
    assert b["page_link"] == "Drop-offs → Failure modes" and b["section_data"]["title"] == "Failure modes"
    assert b["notes"] == []


def test_a_chosen_section_overrides_routing(monkeypatch, tmp_path):
    """The "Break down by segment" follow-up must be answered from Segments, whatever its wording."""
    index = tmp_path / "sections_index.json"
    index.write_text('[{"page": "Drop-offs", "section_id": "failure-modes", "title": "Failure modes", "text": "t"},'
                     ' {"page": "Segments", "section_id": "segments", "title": "Patterns by segment", "text": "s",'
                     '  "key_numbers": {"Experienced (experience): posts": 160}}]')
    monkeypatch.setattr(config, "SECTIONS_INDEX_FILE", index)
    section = [{"id": "failure-modes", "score": 0.7, "text": "t", "meta": {"page": "Drop-offs", "section_id": "failure-modes"}}]
    r = retriever(rows(20, 0.8), section)
    chosen = r.retrieve("How does this differ by investor segment? What leads investors to stop a SIP?", section="segments")
    assert chosen["status"] == "evidence" and chosen["route"]["section"] == "segments" and chosen["route"]["chosen"]
    assert chosen["page_link"] == "Segments → Patterns by segment"
    assert chosen["section_data"]["key_numbers"] == {"Experienced (experience): posts": 160}
    unknown = r.retrieve("What leads investors to stop a SIP?", section="no-such-section")
    assert unknown["route"]["section"] == "failure-modes"  # an unknown id falls back to routing


# --- API --------------------------------------------------------------------------------------

def test_api_retrieve_and_validation(monkeypatch):
    from fastapi.testclient import TestClient

    from src.api import main
    monkeypatch.setattr(main, "retriever", retriever(rows(20, 0.8)))
    with TestClient(main.app) as client:
        assert client.get("/api/health").json()["excerpts"] == 20
        body = client.post("/api/retrieve", json={"question": "Why do SIPs fail?", "app": "Groww"}).json()
        assert body["status"] == "evidence" and body["filters"] == {"app": "Groww"}
        assert client.post("/api/retrieve", json={"question": "Why do SIPs fail?", "section": "segments"}).status_code == 200
        assert client.post("/api/retrieve", json={"question": "hi"}).status_code == 422


# --- the real store ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real():
    if not (config.VECTOR_DB_DIR / "chroma.sqlite3").exists():
        pytest.skip("vector DB not built")
    return Retriever().warm_up()


def test_real_store_end_to_end(real):
    b = real.retrieve("Why did my SIP autopay mandate fail?")
    assert b["status"] == "evidence" and len(b["excerpts"]) == config.RETRIEVAL_PROMPT_EXCERPTS
    assert all(e["url"] and e["record_id"] for e in b["excerpts"])
    assert real.retrieve("What is the capital of France?")["reason"] == "off_topic"
    assert real.retrieve("Which is the safest SIP?")["reason"] == "investment_advice"


def test_real_segment_follow_up_uses_the_segments_section(real):
    q = ("How does this differ by investor segment (first-time or experienced, income, age)? "
         "What leads investors to pause, reduce or stop a SIP?")
    b = real.retrieve(q, section="segments")
    assert b["route"]["section"] == "segments" and b["status"] in ("evidence", "insufficient_evidence")
    assert "Experienced (experience): posts" in b["section_data"]["key_numbers"]
