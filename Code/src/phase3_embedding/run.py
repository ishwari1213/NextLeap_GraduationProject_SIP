"""Phase 3 entry point: Data/chunks/chunks.jsonl (+ Data/site/sections_index.json) -> Data/embeddings/.

Run from the Code/ folder:
    python -m src.phase3_embedding.run            # embed new or changed text only
    python -m src.phase3_embedding.run --prune    # also drop cached vectors no longer used

Checks the architecture's "done when" conditions and exits with code 1 if any fails:
  * every excerpt has a vector
  * every vector has 384 dimensions, unit length, finite values
A rerun with no new data embeds nothing (`embedded_now` is 0 in the report).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

import numpy as np

from src import config
from src.jsonl import read_jsonl
from src.phase1_data_loading.loaders.common import now_iso
from src.phase3_embedding.cache import VectorCache, text_key
from src.phase3_embedding.embedder import Embedder

log = logging.getLogger("phase3")

PROGRESS_EVERY = 2048  # texts per progress line


def load_sections() -> tuple[list[dict], str | None]:
    """Sections to embed for routing, and a note when there are none."""
    path = config.SECTIONS_INDEX_FILE
    if not path.exists():
        return [], (f"{path.relative_to(config.PROJECT_DIR).as_posix()} not found; it is written by the "
                    "FR-7 page-data export, which is not built yet")
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("sections", []) if isinstance(data, dict) else data
    sections = []
    for item in items:
        section_id = item.get("section_id") or item.get("id")
        text = "\n\n".join(p for p in (item.get("title", ""), item.get("text", "")) if p).strip()
        if not section_id or not text:
            log.warning("Skipping a section without an id or text: %s", str(item)[:80])
            continue
        sections.append({"page": item.get("page"), "section_id": section_id, "text": text})
    return sections, None if sections else f"{path.name} has no usable sections"


def embed_missing(cache: VectorCache, texts_by_key: dict[str, str], embedder) -> int:
    todo = cache.missing(list(texts_by_key))
    for start in range(0, len(todo), PROGRESS_EVERY):
        batch = todo[start:start + PROGRESS_EVERY]
        cache.add(batch, embedder.embed([texts_by_key[k] for k in batch]))
        log.info("Embedded %d / %d new texts", min(start + PROGRESS_EVERY, len(todo)), len(todo))
    return len(todo)


def run_checks(cache: VectorCache, excerpt_keys: list[str]) -> dict:
    distinct = list(dict.fromkeys(excerpt_keys))
    have = [k for k in distinct if k in cache]
    vectors = cache.get(have) if have else np.zeros((0, cache.dim), dtype=np.float32)
    norms = np.linalg.norm(vectors, axis=1) if len(vectors) else np.zeros(0)
    return {
        "excerpts_without_vector": sum(1 for k in excerpt_keys if k not in cache),
        "wrong_dimension": 0 if cache.vectors.shape[1] == config.EMBEDDING_DIM else len(cache),
        "not_unit_length": int(np.sum(np.abs(norms - 1.0) > 1e-3)),
        "non_finite": int(np.sum(~np.isfinite(vectors).all(axis=1))) if len(vectors) else 0,
    }


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Phase 3: embedding")
    parser.add_argument("--prune", action="store_true", help="drop cached vectors whose text is no longer used")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpx2", "huggingface_hub", "urllib3", "sentence_transformers"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if not config.CHUNKS_FILE.exists():
        log.error("%s not found: run phase 2 first (python -m src.phase2_chunking.run)", config.CHUNKS_FILE)
        return 1
    started = time.monotonic()
    excerpts = list(read_jsonl(config.CHUNKS_FILE))
    sections, sections_note = load_sections()
    if sections_note:
        log.warning("Sections not embedded: %s", sections_note)

    excerpt_keys = [text_key(e["text"]) for e in excerpts]
    section_keys = [text_key(s["text"]) for s in sections]
    texts_by_key = {k: e["text"] for k, e in zip(excerpt_keys, excerpts)}
    texts_by_key.update({k: s["text"] for k, s in zip(section_keys, sections)})

    cache = VectorCache.load(config.EMBEDDING_VECTORS_FILE, config.EMBEDDING_KEYS_FILE,
                             config.EMBEDDING_MODEL, config.EMBEDDING_DIM)
    log.info("%d excerpts (%d distinct texts), %d sections; %d vectors already cached",
             len(excerpts), len(set(excerpt_keys)), len(sections), len(cache))
    embedded_now = embed_missing(cache, texts_by_key, Embedder()) if cache.missing(list(texts_by_key)) else 0
    pruned = cache.prune(set(texts_by_key)) if args.prune else 0
    cache.save(config.EMBEDDING_VECTORS_FILE, config.EMBEDDING_KEYS_FILE)

    config.EMBEDDED_SECTIONS_FILE.write_text(json.dumps(
        [{"page": s["page"], "section_id": s["section_id"], "key": k} for s, k in zip(sections, section_keys)],
        indent=2), encoding="utf-8")

    checks = run_checks(cache, excerpt_keys + section_keys)
    report = {
        "run_at": now_iso(),
        "model": config.EMBEDDING_MODEL,
        "dim": config.EMBEDDING_DIM,
        "excerpts": len(excerpts),
        "distinct_excerpt_texts": len(set(excerpt_keys)),
        "sections": len(sections),
        "sections_note": sections_note,
        "embedded_now": embedded_now,
        "from_cache": len(set(texts_by_key)) - embedded_now,
        "pruned": pruned,
        "cache_rows": len(cache),
        "seconds": round(time.monotonic() - started, 1),
        "checks": checks,
    }
    config.EMBEDDING_REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nPhase 3 summary")
    print(f"Excerpts: {report['excerpts']} ({report['distinct_excerpt_texts']} distinct texts) | "
          f"sections: {report['sections']}")
    print(f"Embedded now: {embedded_now} | from cache: {report['from_cache']} | pruned: {pruned} | "
          f"cache rows: {len(cache)} | {report['seconds']}s")
    print("Checks: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in checks.items()))
    if sections_note:
        print(f"Note: sections not embedded: {sections_note}")
    print(f"Vectors -> {config.EMBEDDING_VECTORS_FILE.relative_to(config.PROJECT_DIR).as_posix()}")

    failed = {k: v for k, v in checks.items() if v}
    if failed:
        log.error("Phase 3 checks failed: %s", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
