"""Phase 2 unit tests. Most use a word counter (one word = one token) so they run offline and
fast; one test uses the real MiniLM tokenizer when it is cached locally."""
import re

import pytest

from src import config
from src.phase2_chunking import chunker
from src.phase2_chunking.run import build_report


class WordCounter:
    def count(self, texts):
        return [len(t.split()) for t in texts]

    def windows(self, text, size, overlap):
        words, pieces, start = text.split(), [], 0
        while start < len(words):
            pieces.append(" ".join(words[start:start + size]))
            if start + size >= len(words):
                break
            start += size - overlap
        return pieces


def record(text, rid="forums:tradingqna:abc", **extra):
    return {"id": rid, "source": "forums", "app": None, "url": "https://example.com/t/1", "date": "2026-01-01",
            "doc_type": "post", "text": text, **extra}


def sentence(i, words=10):
    return " ".join(f"w{i}_{k}" for k in range(words - 1)) + f" end{i}."


def test_split_units_keeps_separators():
    units = chunker.split_units("First one. Second one.\nNew line.\n\nNew para.")
    assert units == [("First one.", ""), ("Second one.", " "), ("New line.", "\n"), ("New para.", "\n\n")]


def test_short_record_is_one_unchanged_excerpt():
    text = "Instalment failed twice.\n\nSupport did not reply."
    [ex] = chunker.chunk_records([record(text)], WordCounter(), target=20, overlap=4, max_tokens=30)
    assert ex["text"] == text and ex["chunk_id"] == "forums:tradingqna:abc-0"
    assert ex["token_count"] == 7 and ex["tags"] == []
    assert set(ex) == {"chunk_id", "record_id", "source", "app", "url", "date", "doc_type", "tags", "text",
                       "token_count"}


def test_long_record_is_packed_with_sentence_overlap_and_covers_everything():
    paragraphs = ["\n".join([sentence(i), sentence(i + 100)]) for i in range(6)]  # 12 sentences, 120 words
    text = "\n\n".join(paragraphs)
    excerpts = chunker.chunk_records([record(text)], WordCounter(), target=30, overlap=10, max_tokens=40)
    assert len(excerpts) > 1
    assert [e["chunk_id"].rsplit("-", 1)[1] for e in excerpts] == [str(i) for i in range(len(excerpts))]
    assert all(e["token_count"] <= 30 for e in excerpts)
    for prev, nxt in zip(excerpts, excerpts[1:]):  # last sentence of one excerpt opens the next
        last_sentence = re.split(r"(?<=\.)\s+", prev["text"].strip())[-1]
        assert nxt["text"].startswith(last_sentence)
    joined = " ".join(e["text"] for e in excerpts)
    for i in range(6):
        assert f"end{i}." in joined and f"end{i + 100}." in joined
    assert "\n" in excerpts[0]["text"]  # line and paragraph breaks are kept


def test_sentence_longer_than_target_is_windowed():
    text = " ".join(f"word{k}" for k in range(95))  # one 95-word "sentence", no punctuation
    excerpts = chunker.chunk_records([record(text)], WordCounter(), target=30, overlap=5, max_tokens=40)
    assert all(e["token_count"] <= 30 for e in excerpts)
    assert excerpts[0]["text"].startswith("word0 ") and excerpts[-1]["text"].endswith("word94")


def test_overlap_never_pushes_excerpt_over_target():
    units = [("a " * 8 + "x.", ""), ("b " * 20 + "y.", " ")]  # 9 and 21 tokens
    pieces = chunker.pack(units, [9, 21], target=25, overlap=10)
    assert pieces == [units[0][0], units[1][0]]  # carrying the first unit would make 30 > 25


def test_report_flags_problems():
    records = [record("short text", rid="r1")]
    excerpts = chunker.chunk_records(records, WordCounter(), target=20, overlap=4, max_tokens=30)
    report = build_report(records, excerpts)
    assert report["checks"] == {"over_limit": 0, "orphan_excerpts": 0, "records_without_excerpts": 0,
                                "duplicate_chunk_ids": 0}
    bad = excerpts + [{**excerpts[0], "record_id": "ghost", "token_count": 999}]
    checks = build_report(records, bad)["checks"]
    assert checks["orphan_excerpts"] == 1 and checks["duplicate_chunk_ids"] == 1
    assert checks["over_limit"] == (1 if 999 > config.MODEL_MAX_TOKENS - chunker.SPECIAL_TOKENS else 0)


@pytest.fixture(scope="module")
def minilm():
    try:
        from transformers import AutoTokenizer
        AutoTokenizer.from_pretrained(config.EMBEDDING_MODEL, local_files_only=True)
    except Exception:
        pytest.skip("MiniLM tokenizer not cached locally")
    return chunker.WordPieceCounter(config.EMBEDDING_MODEL)


def test_windowed_sentence_is_never_repacked_with_duplicate_overlap():
    long_sentence = " ".join(f"word{k}" for k in range(70))  # 70 words, no sentence break
    text = f"Short opener. {long_sentence}. Short closer."
    excerpts = chunker.chunk_records([record(text)], WordCounter(), target=30, overlap=5, max_tokens=40)
    for e in excerpts:
        words = e["text"].replace(".", "").split()
        assert len(words) == len(set(words)), f"repeated words inside one excerpt: {e['text']}"


def test_real_tokenizer_cuts_punctuation_runs_without_mangling(minilm):
    text = "slove this trading view chart problem" + "." * 400 + " thanks"
    excerpts = chunker.chunk_records([record(text)], minilm, target=200, overlap=40, max_tokens=256)
    assert all(e["token_count"] <= 254 for e in excerpts)
    assert all(e["text"] in text for e in excerpts)  # every excerpt is an exact slice of the original
    assert all(". ." not in e["text"] for e in excerpts)
    assert sum(e["text"].count("trading view chart") for e in excerpts) == 1


def test_real_tokenizer_keeps_case_and_word_boundaries(minilm):
    text = " ".join(["Groww SIP instalment failed, the mandate was debited twice and nobody replied."] * 40)
    excerpts = chunker.chunk_records([record(text)], minilm, target=200, overlap=40, max_tokens=256)
    assert len(excerpts) > 1
    assert all(e["token_count"] <= 254 for e in excerpts)
    assert all(e["text"][0].isupper() for e in excerpts)  # starts at a sentence, original case kept
    pieces = minilm.windows("instalment " * 300, 50, 10)
    assert all(p.split()[0] == "instalment" and p.split()[-1] == "instalment" for p in pieces)
