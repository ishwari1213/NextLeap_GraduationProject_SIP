"""Step 4: route a question to the nearest page section (`sections` collection).

The section's entry in Data/site/sections_index.json (page, section id, title, text, key
numbers, written by the FR-7 export) becomes the bundle's `section_data`. Until that export
exists the collection is empty, routing is skipped, and the bundle says so in `notes`.
"""
from __future__ import annotations

import json
import logging

import numpy as np

from src import config

log = logging.getLogger(__name__)


def load_section_entries() -> dict[str, dict]:
    path = config.SECTIONS_INDEX_FILE
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("sections", []) if isinstance(data, dict) else data
    return {(i.get("section_id") or i.get("id")): i for i in items if i.get("section_id") or i.get("id")}


class Router:
    def __init__(self, sections_collection):
        self.collection = sections_collection
        self.entries = load_section_entries()

    @property
    def available(self) -> bool:
        return self.collection is not None and self.collection.count() > 0

    def route(self, vector: np.ndarray) -> tuple[dict | None, dict | None]:
        """(route, section_data) for the nearest section, or (None, None) when there are no sections."""
        if not self.available:
            return None, None
        result = self.collection.query(query_embeddings=vector[None, :], n_results=1,
                                       include=["metadatas", "distances"])
        if not result["ids"][0]:
            return None, None
        section_id = result["ids"][0][0]
        meta = result["metadatas"][0][0] or {}
        entry = self.entries.get(section_id, {})
        route = {
            "page": meta.get("page") or entry.get("page"),
            "section": section_id,
            "title": entry.get("title") or section_id,
            "score": round(1.0 - float(result["distances"][0][0]), 4),
        }
        return route, (entry or None)
