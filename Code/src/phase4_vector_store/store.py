"""ChromaDB access, shared by phase 4 (build) and phase 5 (search).

Collections live in Data/vector_db/chroma/ and use cosine distance (0 = same direction).
They never get Chroma's own embedding function: vectors always come from phase 3's model,
so a query can never be embedded by a different model by mistake.

Metadata values must be single values. Chroma drops a record's whole metadata when one
value is None, so missing values are stored as "" and tags as one comma-joined string.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import chromadb
import numpy as np
from chromadb.config import Settings

from src import config

log = logging.getLogger(__name__)

COSINE = {"hnsw": {"space": "cosine"}}
EXCERPT_FIELDS = ("record_id", "source", "app", "url", "date", "doc_type", "tags", "token_count")


def client(path: Path | None = None):
    path = Path(path or config.VECTOR_DB_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path), settings=Settings(anonymized_telemetry=False))


def get_or_create(db, name: str):
    return db.get_or_create_collection(name, configuration=COSINE, embedding_function=None)


def open_collection(db, name: str):
    """An existing collection, for reading (phase 5)."""
    return db.get_collection(name, embedding_function=None)


def row_hash(document: str, metadata: dict) -> str:
    """Fingerprint of what is stored for a row, so unchanged rows are not rewritten."""
    payload = json.dumps({"document": document, "metadata": metadata}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


TAG_FIELDS = ("stage", "event", "trigger", "failure_mode", "theme", "expectation", "checking", "confusion",
              "help_seeking", "experience", "income", "age", "money_source", "influence", "residency")


def excerpt_metadata(excerpt: dict, record_tags: dict | None = None) -> dict:
    """Metadata for one excerpt. With the record's FR-5 tags, each tag becomes its own field
    (filterable in phase 5), `about_sip` a boolean, and `tags` the stated labels joined."""
    meta = {
        "record_id": excerpt["record_id"],
        "source": excerpt["source"],
        "app": excerpt.get("app") or "",
        "url": excerpt["url"],
        "date": excerpt.get("date") or "",
        "doc_type": excerpt["doc_type"],
        "tags": ",".join(excerpt.get("tags") or []),
        "token_count": int(excerpt.get("token_count") or 0),
    }
    if record_tags:
        meta["about_sip"] = bool(record_tags.get("about_sip"))
        for field in TAG_FIELDS:
            meta[field] = record_tags.get(field) or ""
        meta["tags"] = ",".join(f"{f}:{record_tags[f]}" for f in TAG_FIELDS
                                if record_tags.get(f) not in (None, "", "not_stated", "none", "other"))
    meta["row_hash"] = row_hash(excerpt["text"], meta)
    return meta


def section_metadata(section: dict) -> dict:
    meta = {"page": section.get("page") or "", "section_id": section["section_id"]}
    meta["row_hash"] = row_hash(section["text"], meta)
    return meta


def _existing_hashes(collection, batch: int) -> dict[str, str]:
    hashes: dict[str, str] = {}
    offset = 0
    while True:
        page = collection.get(include=["metadatas"], limit=batch, offset=offset)
        for rid, meta in zip(page["ids"], page["metadatas"]):
            hashes[rid] = (meta or {}).get("row_hash", "")
        if len(page["ids"]) < batch:
            return hashes
        offset += batch


def sync(collection, ids: list[str], vectors: np.ndarray, documents: list[str], metadatas: list[dict],
         batch: int | None = None) -> dict:
    """Make the collection hold exactly these rows: upsert new or changed ones, delete the rest."""
    batch = batch or config.CHROMA_BATCH_SIZE
    if len(set(ids)) != len(ids):
        raise ValueError("ids must be unique")
    existing = _existing_hashes(collection, batch)
    wanted = set(ids)

    stale = [rid for rid in existing if rid not in wanted]
    for start in range(0, len(stale), batch):
        collection.delete(ids=stale[start:start + batch])

    changed = [i for i, rid in enumerate(ids) if existing.get(rid) != metadatas[i]["row_hash"]]
    for start in range(0, len(changed), batch):
        rows = changed[start:start + batch]
        collection.upsert(
            ids=[ids[i] for i in rows],
            embeddings=vectors[rows],
            documents=[documents[i] for i in rows],
            metadatas=[metadatas[i] for i in rows],
        )
        log.info("%s: wrote %d / %d rows", collection.name, min(start + batch, len(changed)), len(changed))

    added = sum(1 for i in changed if ids[i] not in existing)
    return {"added": added, "updated": len(changed) - added, "unchanged": len(ids) - len(changed),
            "deleted": len(stale)}


def build_info(collection) -> dict:
    """Build metadata stored with a collection (phase 5 reads `last_updated_from_sources`)."""
    return dict(collection.metadata or {})
