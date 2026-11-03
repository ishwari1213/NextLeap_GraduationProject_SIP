"""Phase 4 unit tests: metadata shaping, the sync logic and an end-to-end run, all against a
throwaway ChromaDB folder with small synthetic vectors."""
import json

import numpy as np
import pytest

from src import config
from src.jsonl import write_jsonl
from src.phase3_embedding.cache import VectorCache, text_key
from src.phase4_vector_store import run as phase4
from src.phase4_vector_store import store

DIM = config.EMBEDDING_DIM


def unit_vectors(texts):
    rows = []
    for t in texts:
        v = np.random.default_rng(int(text_key(t)[:8], 16)).normal(size=DIM).astype(np.float32)
        rows.append(v / np.linalg.norm(v))
    return np.vstack(rows)


def excerpt(i, text, app="Groww", tags=None):
    return {"chunk_id": f"play_store:groww:{i}-0", "record_id": f"play_store:groww:{i}", "source": "play_store",
            "app": app, "url": "https://play.google.com/x", "date": "2026-10-01", "doc_type": "review",
            "tags": tags or [], "text": text, "token_count": 4}


def test_excerpt_metadata_has_no_none_and_joins_tags():
    meta = store.excerpt_metadata(excerpt(1, "autopay failed", app=None, tags=["instalment_failed", "app_bug"]))
    assert meta["app"] == "" and meta["tags"] == "instalment_failed,app_bug"
    assert all(v is not None for v in meta.values())
    assert set(store.EXCERPT_FIELDS) <= set(meta) and len(meta["row_hash"]) == 40


def test_sync_adds_skips_updates_and_deletes(tmp_path):
    col = store.get_or_create(store.client(tmp_path / "db"), "excerpts")
    rows = [excerpt(i, f"text {i}") for i in range(3)]

    def push(rs):
        return store.sync(col, [r["chunk_id"] for r in rs], unit_vectors([r["text"] for r in rs]),
                          [r["text"] for r in rs], [store.excerpt_metadata(r) for r in rs], batch=2)

    assert push(rows) == {"added": 3, "updated": 0, "unchanged": 0, "deleted": 0}
    assert push(rows) == {"added": 0, "updated": 0, "unchanged": 3, "deleted": 0}
    changed = [rows[0], {**rows[1], "text": "text 1 edited"}]
    assert push(changed) == {"added": 0, "updated": 1, "unchanged": 1, "deleted": 1}
    assert col.count() == 2
    assert col.get(ids=[rows[1]["chunk_id"]], include=["documents"])["documents"] == ["text 1 edited"]


def test_sync_rejects_duplicate_ids(tmp_path):
    col = store.get_or_create(store.client(tmp_path / "db"), "excerpts")
    r = excerpt(1, "a")
    with pytest.raises(ValueError):
        store.sync(col, ["x", "x"], unit_vectors(["a", "a"]), ["a", "a"], [store.excerpt_metadata(r)] * 2)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    for name, value in {
        "PROJECT_DIR": tmp_path,
        "CHUNKS_FILE": tmp_path / "chunks.jsonl",
        "LOAD_REPORT_FILE": tmp_path / "load_report.json",
        "SECTIONS_INDEX_FILE": tmp_path / "site" / "sections_index.json",
        "EMBEDDING_VECTORS_FILE": tmp_path / "emb" / "vectors.npy",
        "EMBEDDING_KEYS_FILE": tmp_path / "emb" / "keys.json",
        "VECTOR_DB_DIR": tmp_path / "vector_db" / "chroma",
        "VECTOR_STORE_REPORT_FILE": tmp_path / "vector_db" / "report.json",
    }.items():
        monkeypatch.setattr(config, name, value)
    return tmp_path


def seed(ws, rows, sections=None):
    write_jsonl(rows, config.CHUNKS_FILE)
    texts = [r["text"] for r in rows]
    if sections:
        (ws / "site").mkdir(exist_ok=True)
        config.SECTIONS_INDEX_FILE.write_text(json.dumps(sections))
        texts += [f"{s['title']}\n\n{s['text']}" for s in sections]
    cache = VectorCache(config.EMBEDDING_MODEL, DIM)
    unique = list(dict.fromkeys(texts))
    cache.add([text_key(t) for t in unique], unit_vectors(unique))
    cache.save(config.EMBEDDING_VECTORS_FILE, config.EMBEDDING_KEYS_FILE)


def test_run_builds_both_collections_and_reruns_cleanly(workspace):
    rows = [excerpt(i, f"review number {i}") for i in range(7)] + [excerpt(99, "review number 1")]  # a duplicate text
    sections = [{"page": "Drop-offs", "section_id": "failure-modes", "title": "Failure modes", "text": "Why SIPs stop"}]
    seed(workspace, rows, sections)
    config.LOAD_REPORT_FILE.write_text(json.dumps({"run_at": "2026-11-01T13:19:00+00:00"}))

    assert phase4.main([]) == 0
    report = json.loads(config.VECTOR_STORE_REPORT_FILE.read_text())
    assert report["excerpts"]["rows"] == 8 and report["excerpts"]["added"] == 8
    assert report["sections"]["rows"] == 1
    assert all(v == 0 for v in report["checks"].values())
    assert report["build_info"]["last_updated_from_sources"] == "2026-11-01"

    assert phase4.main([]) == 0
    again = json.loads(config.VECTOR_STORE_REPORT_FILE.read_text())
    assert again["excerpts"]["unchanged"] == 8 and again["excerpts"]["added"] == 0

    col = store.open_collection(store.client(), config.EXCERPTS_COLLECTION)
    assert store.build_info(col)["model"] == config.EMBEDDING_MODEL


def test_run_stops_when_vectors_are_missing(workspace):
    seed(workspace, [excerpt(1, "has a vector")])
    write_jsonl([excerpt(1, "has a vector"), excerpt(2, "no vector yet")], config.CHUNKS_FILE)
    assert phase4.main([]) == 1
