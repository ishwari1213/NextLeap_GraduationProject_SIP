"""FR-5 entry point: Data/cleaned/records.jsonl -> Data/tags/tags.jsonl.

Run from the Code/ folder:
    python -m src.tagging.run              # tag every record not tagged yet with this prompt version
    python -m src.tagging.run --limit 200  # tag at most 200 new posts (a cheap trial)

Tags are kept per record id and prompt version, so a rerun only sends new or failed posts to
Mistral, and a new prompt version re-tags everything. A batch that fails is logged and left
for the next run; the run never stops halfway because of one bad answer.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

from src import config, llm
from src.jsonl import read_jsonl, write_jsonl
from src.phase1_data_loading.loaders.common import now_iso
from src.tagging import tagger

log = logging.getLogger("tagging")


def load_existing() -> dict[str, dict]:
    if not config.TAGS_FILE.exists():
        return {}
    return {t["record_id"]: t for t in read_jsonl(config.TAGS_FILE)
            if t.get("prompt_version") == config.TAG_PROMPT_VERSION}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="FR-5: tag posts with Mistral")
    parser.add_argument("--limit", type=int, help="tag at most this many new posts")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    started = time.monotonic()

    records = list(read_jsonl(config.RECORDS_FILE))
    current = {r["id"] for r in records}
    tags = {rid: t for rid, t in load_existing().items() if rid in current}
    routes = Counter()
    todo = []
    for r in records:
        way = tagger.route(r)
        routes[way] += 1
        if way == "rule" and r["id"] not in tags:
            tags[r["id"]] = tagger.rule_tags(r)
        elif way == "llm" and r["id"] not in tags:
            todo.append(r)
    if args.limit:
        todo = todo[:args.limit]
    log.info("%d records: %d to the model, %d by rule, %d info pages skipped; %d already tagged, %d to tag now",
             len(records), routes["llm"], routes["rule"], routes["skip"], len(tags) - routes["rule"], len(todo))

    batches = [todo[i:i + config.TAG_BATCH_SIZE] for i in range(0, len(todo), config.TAG_BATCH_SIZE)]
    invalid = failed_batches = unanswered = done = 0
    with ThreadPoolExecutor(max_workers=config.TAG_WORKERS) as pool:
        futures = {pool.submit(tagger.tag_batch, b): b for b in batches}
        for n, future in enumerate(as_completed(futures), 1):
            batch = futures[future]
            try:
                rows, bad = future.result()
            except llm.LLMError as exc:
                failed_batches += 1
                log.error("Batch of %d failed: %s", len(batch), exc)
                continue
            invalid += bad
            unanswered += len(batch) - len(rows)
            for row in rows:
                tags[row["record_id"]] = row
            done += len(rows)
            if n % 10 == 0 or n == len(batches):
                write_jsonl(tags.values(), config.TAGS_FILE)  # save progress
                log.info("Batches %d / %d done (%d posts tagged)", n, len(batches), done)

    write_jsonl(tags.values(), config.TAGS_FILE)
    llm_tags = [t for t in tags.values() if t["tagged_by"] == "llm"]
    report = {
        "run_at": now_iso(), "model": config.TAGGING_MODEL, "prompt_version": config.TAG_PROMPT_VERSION,
        "records": len(records), "routes": dict(routes), "tagged_total": len(tags),
        "tagged_by_model": len(llm_tags), "about_sip_true": sum(1 for t in tags.values() if t["about_sip"]),
        "tagged_this_run": done, "still_untagged": routes["llm"] - len(llm_tags),
        "failed_batches": failed_batches, "unanswered_posts": unanswered, "invalid_labels_dropped": invalid,
        "usage_this_run": dict(llm.usage), "seconds": round(time.monotonic() - started, 1),
    }
    config.TAG_REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nTagging summary")
    for key in ("records", "tagged_total", "tagged_by_model", "about_sip_true", "tagged_this_run", "still_untagged",
                "failed_batches", "unanswered_posts", "invalid_labels_dropped", "seconds"):
        print(f"  {key.replace('_', ' ')}: {report[key]}")
    print(f"  Mistral usage this run: {llm.usage}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
