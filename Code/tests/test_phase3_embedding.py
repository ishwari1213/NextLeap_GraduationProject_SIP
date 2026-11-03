"""Phase 3 unit tests. A fake embedder (deterministic vectors from the text hash) keeps the
cache and run tests fast and offline; one test uses the real MiniLM model when it is cached."""
import hashlib
import json

import numpy as np
import pytest

from src import config
from src.jsonl import write_jsonl
from src.phase3_embedding import run as phase3
from src.phase3_embedding.cache import VectorCache, text_key

DIM = config.EMBEDDING_DIM


class FakeEmbedder:
    calls: list[list[str]] = []

    def embed(self, texts):
        FakeEmbedder.calls.append(list(texts))
        rows = []
        for t in texts:
            seed = int(hashlib.sha1(t.encode()).hexdigest()[:8], 16)
            v = np.random.default_rng(seed).normal(size=DIM).astype(np.float32)
            rows.append(v / np.linalg.norm(v))
        return np.vstack(rows) if rows else np.zeros((0, DIM), np.float32)


def unit(n, seed=0):
    v = np.random.default_rng(seed).normal(size=(n, DIM)).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


# --- cache ------------------------------------------------------------------------------

def test_cache_roundtrip_and_dedup(tmp_path):
    cache = VectorCache("m", DIM)
    vecs = unit(2)
    cache.add(["a", "b"], vecs)
    cache.add(["a"], unit(1, seed=9))  # already cached: ignored
    assert len(cache) == 2 and cache.missing(["a", "c", "c", "b"]) == ["c"]
    cache.save(tmp_path / "v.npy", tmp_path / "k.json")
    loaded = VectorCache.load(tmp_path / "v.npy", tmp_path / "k.json", "m", DIM)
    assert np.allclose(loaded.get(["b", "a"]), vecs[[1, 0]])


def test_cache_from_another_model_is_ignored(tmp_path):
    cache = VectorCache("old-model", DIM)
    cache.add(["a"], unit(1))
    cache.save(tmp_path / "v.npy", tmp_path / "k.json")
    assert len(VectorCache.load(tmp_path / "v.npy", tmp_path / "k.json", "new-model", DIM)) == 0


def test_cache_rejects_wrong_shape_and_prunes():
    cache = VectorCache("m", DIM)
    with pytest.raises(ValueError):
        cache.add(["a"], np.zeros((1, 10), np.float32))
    cache.add(["a", "b", "c"], unit(3))
    assert cache.prune({"a", "c"}) == 1 and cache.keys == ["a", "c"] and cache.get(["c"]).shape == (1, DIM)


# --- run ---------------------------------------------------------------------------------

@pytest.fixture
def workspace(tmp_path, monkeypatch):
    for name, value in {
        "PROJECT_DIR": tmp_path,
        "CHUNKS_FILE": tmp_path / "chunks.jsonl",
        "SECTIONS_INDEX_FILE": tmp_path / "site" / "sections_index.json",
        "EMBEDDING_VECTORS_FILE": tmp_path / "emb" / "vectors.npy",
        "EMBEDDING_KEYS_FILE": tmp_path / "emb" / "keys.json",
        "EMBEDDED_SECTIONS_FILE": tmp_path / "emb" / "sections.json",
        "EMBEDDING_REPORT_FILE": tmp_path / "emb" / "report.json",
    }.items():
        monkeypatch.setattr(config, name, value)
    (tmp_path / "emb").mkdir()
    monkeypatch.setattr(phase3, "Embedder", FakeEmbedder)
    FakeEmbedder.calls = []
    return tmp_path


def excerpt(i, text):
    return {"chunk_id": f"r{i}-0", "record_id": f"r{i}", "source": "play_store", "app": "Groww",
            "url": "u", "date": "2026-01-01", "doc_type": "review", "tags": [], "text": text, "token_count": 3}


def report(ws):
    return json.loads((ws / "emb" / "report.json").read_text())


def test_rerun_embeds_only_new_text(workspace):
    write_jsonl([excerpt(1, "instalment failed"), excerpt(2, "good app"), excerpt(3, "good app")],
                config.CHUNKS_FILE)
    assert phase3.main([]) == 0
    first = report(workspace)
    assert first["embedded_now"] == 2 and first["distinct_excerpt_texts"] == 2
    assert first["checks"] == {"excerpts_without_vector": 0, "wrong_dimension": 0, "not_unit_length": 0,
                               "non_finite": 0}
    assert "not found" in first["sections_note"]

    assert phase3.main([]) == 0
    assert report(workspace)["embedded_now"] == 0

    write_jsonl([excerpt(1, "instalment failed"), excerpt(4, "autopay mandate rejected")], config.CHUNKS_FILE)
    assert phase3.main(["--prune"]) == 0
    third = report(workspace)
    assert third["embedded_now"] == 1 and third["pruned"] == 1 and third["cache_rows"] == 2


def test_sections_are_embedded_for_routing(workspace):
    write_jsonl([excerpt(1, "instalment failed")], config.CHUNKS_FILE)
    config.SECTIONS_INDEX_FILE.parent.mkdir()
    config.SECTIONS_INDEX_FILE.write_text(json.dumps([
        {"page": "Drop-offs", "section_id": "failure-modes", "title": "Failure modes", "text": "Why SIPs stop"},
        {"page": "Journey", "id": "outside-the-app", "title": "Outside the app", "text": "Where investors go"},
        {"page": "Broken", "title": "no id"},
    ]))
    assert phase3.main([]) == 0
    saved = json.loads(config.EMBEDDED_SECTIONS_FILE.read_text())
    assert [s["section_id"] for s in saved] == ["failure-modes", "outside-the-app"]
    cache = VectorCache.load(config.EMBEDDING_VECTORS_FILE, config.EMBEDDING_KEYS_FILE, config.EMBEDDING_MODEL, DIM)
    assert all(s["key"] in cache for s in saved)
    assert saved[0]["key"] == text_key("Failure modes\n\nWhy SIPs stop")


# --- real model ----------------------------------------------------------------------------

def test_real_model_vectors(tmp_path):
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(config.EMBEDDING_MODEL, local_files_only=True)
    except Exception:
        pytest.skip("MiniLM model not cached locally")
    from src.phase3_embedding.embedder import Embedder
    v = Embedder().embed(["My SIP instalment failed", "SIP payment failed but money was debited", "Nice weather"])
    assert v.shape == (3, DIM) and v.dtype == np.float32
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0, atol=1e-4)
    assert v[0] @ v[1] > v[0] @ v[2]
