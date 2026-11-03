"""Vector cache keyed by a hash of the embedded text (architecture phase 3).

    Data/embeddings/vectors.npy   float32 [rows, 384], one row per distinct text
    Data/embeddings/keys.json     {"model", "dim", "normalized", "keys": [text hash of each row]}

The same text always has the same key, so a rerun embeds only new or changed text, and
identical excerpts (e.g. "good app" on two apps) share one vector. Phase 4 looks vectors up
here with `get([text_key(excerpt_text), ...])`. A cache made by another model or dimension
is ignored, never mixed in.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)


def text_key(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


class VectorCache:
    def __init__(self, model: str, dim: int, vectors: np.ndarray | None = None, keys: list[str] | None = None):
        self.model = model
        self.dim = dim
        self.vectors = vectors if vectors is not None else np.zeros((0, dim), dtype=np.float32)
        self.keys = list(keys or [])
        self._index = {k: i for i, k in enumerate(self.keys)}

    @classmethod
    def load(cls, vectors_path: Path, keys_path: Path, model: str, dim: int) -> "VectorCache":
        if not (vectors_path.exists() and keys_path.exists()):
            return cls(model, dim)
        meta = json.loads(keys_path.read_text(encoding="utf-8"))
        if meta.get("model") != model or meta.get("dim") != dim:
            log.warning("Cached vectors were made by %s (%s-d); starting a fresh cache for %s",
                        meta.get("model"), meta.get("dim"), model)
            return cls(model, dim)
        vectors = np.load(vectors_path)
        if vectors.shape != (len(meta.get("keys", [])), dim):
            log.warning("Cache files disagree (%s rows vs %s keys); starting a fresh cache",
                        vectors.shape[0], len(meta.get("keys", [])))
            return cls(model, dim)
        return cls(model, dim, vectors.astype(np.float32, copy=False), meta["keys"])

    def __len__(self) -> int:
        return len(self.keys)

    def __contains__(self, key: str) -> bool:
        return key in self._index

    def missing(self, keys: list[str]) -> list[str]:
        """Keys with no vector yet, de-duplicated, in first-seen order."""
        return list(dict.fromkeys(k for k in keys if k not in self._index))

    def add(self, keys: list[str], vectors: np.ndarray) -> None:
        if vectors.shape != (len(keys), self.dim):
            raise ValueError(f"expected {(len(keys), self.dim)} vectors, got {vectors.shape}")
        fresh = [i for i, k in enumerate(keys) if k not in self._index]
        if not fresh:
            return
        start = len(self.keys)
        self.vectors = np.vstack([self.vectors, vectors[fresh].astype(np.float32, copy=False)])
        for offset, i in enumerate(fresh):
            self.keys.append(keys[i])
            self._index[keys[i]] = start + offset

    def get(self, keys: list[str]) -> np.ndarray:
        return self.vectors[[self._index[k] for k in keys]]

    def prune(self, keep: set[str]) -> int:
        """Drop vectors whose text is no longer used. Returns how many were dropped."""
        rows = [i for i, k in enumerate(self.keys) if k in keep]
        dropped = len(self.keys) - len(rows)
        if dropped:
            self.vectors = self.vectors[rows]
            self.keys = [self.keys[i] for i in rows]
            self._index = {k: i for i, k in enumerate(self.keys)}
        return dropped

    def save(self, vectors_path: Path, keys_path: Path) -> None:
        """Write both files atomically so a crash never leaves them out of step."""
        vectors_path.parent.mkdir(parents=True, exist_ok=True)
        vec_part = vectors_path.with_name(vectors_path.name + ".part")
        key_part = keys_path.with_name(keys_path.name + ".part")
        with vec_part.open("wb") as f:
            np.save(f, self.vectors)
        meta = {"model": self.model, "dim": self.dim, "normalized": True, "rows": len(self.keys), "keys": self.keys}
        key_part.write_text(json.dumps(meta), encoding="utf-8")
        vec_part.replace(vectors_path)
        key_part.replace(keys_path)
