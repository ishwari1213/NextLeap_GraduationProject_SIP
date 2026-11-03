"""Phase 2 entry point: Data/cleaned/records.jsonl -> Data/chunks/chunks.jsonl.

Run from the Code/ folder:
    python -m src.phase2_chunking.run

Checks the architecture's "done when" conditions and exits with code 1 if any fails:
  * no excerpt exceeds the model's 256 word pieces ([CLS] and [SEP] included)
  * every excerpt maps back to a record, and every record has at least one excerpt
Counts per source go to the console and to Data/chunks/chunk_report.json.
"""
from __future__ import annotations

import json
import logging
import sys
from collections import defaultdict
from statistics import mean

from src import config
from src.jsonl import read_jsonl, write_jsonl
from src.phase1_data_loading.loaders.common import now_iso
from src.phase2_chunking.chunker import SPECIAL_TOKENS, WordPieceCounter, chunk_records

log = logging.getLogger("phase2")


def build_report(records: list[dict], excerpts: list[dict]) -> dict:
    limit = config.MODEL_MAX_TOKENS - SPECIAL_TOKENS
    record_ids = {r["id"] for r in records}
    excerpt_record_ids = {e["record_id"] for e in excerpts}

    per_source: dict[str, dict] = {}
    by_source = defaultdict(list)
    for e in excerpts:
        by_source[e["source"]].append(e)
    records_by_source = defaultdict(int)
    for r in records:
        records_by_source[r["source"]] += 1
    for source in sorted(records_by_source):
        items = by_source.get(source, [])
        tokens = [e["token_count"] for e in items]
        split = {e["record_id"] for e in items if not e["chunk_id"].endswith("-0")}
        per_source[source] = {
            "records": records_by_source[source],
            "excerpts": len(items),
            "records_split": len(split),
            "max_tokens": max(tokens, default=0),
            "mean_tokens": round(mean(tokens), 1) if tokens else 0,
        }

    return {
        "run_at": now_iso(),
        "model": config.EMBEDDING_MODEL,
        "settings": {
            "model_max_tokens": config.MODEL_MAX_TOKENS,
            "target_tokens": config.CHUNK_TARGET_TOKENS,
            "overlap_tokens": config.CHUNK_OVERLAP_TOKENS,
        },
        "records": len(records),
        "excerpts": len(excerpts),
        "per_source": per_source,
        "checks": {
            "over_limit": sum(1 for e in excerpts if e["token_count"] > limit),
            "orphan_excerpts": len(excerpt_record_ids - record_ids),
            "records_without_excerpts": len(record_ids - excerpt_record_ids),
            "duplicate_chunk_ids": len(excerpts) - len({e["chunk_id"] for e in excerpts}),
        },
    }


def print_summary(report: dict) -> None:
    print("\nPhase 2 summary")
    print(f"{'source':<12} {'records':>8} {'excerpts':>9} {'split':>6} {'max tok':>8} {'mean tok':>9}")
    for source, s in report["per_source"].items():
        print(f"{source:<12} {s['records']:>8} {s['excerpts']:>9} {s['records_split']:>6} "
              f"{s['max_tokens']:>8} {s['mean_tokens']:>9}")
    print(f"{'total':<12} {report['records']:>8} {report['excerpts']:>9}")
    checks = report["checks"]
    print("\nChecks: " + ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in checks.items()))
    print(f"Excerpts written -> {config.CHUNKS_FILE.relative_to(config.PROJECT_DIR).as_posix()}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpx2", "huggingface_hub", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if not config.RECORDS_FILE.exists():
        log.error("%s not found: run phase 1 first (python -m src.phase1_data_loading.run)", config.RECORDS_FILE)
        return 1
    records = list(read_jsonl(config.RECORDS_FILE))
    log.info("Loaded %d records; loading the %s tokenizer", len(records), config.EMBEDDING_MODEL)

    counter = WordPieceCounter(config.EMBEDDING_MODEL)
    excerpts = chunk_records(records, counter, target=config.CHUNK_TARGET_TOKENS,
                             overlap=config.CHUNK_OVERLAP_TOKENS, max_tokens=config.MODEL_MAX_TOKENS)
    write_jsonl(excerpts, config.CHUNKS_FILE)

    report = build_report(records, excerpts)
    config.CHUNK_REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print_summary(report)

    failed = {k: v for k, v in report["checks"].items() if v}
    if failed:
        log.error("Phase 2 checks failed: %s", failed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
