"""Phase 6 entry point: run the golden set and write Data/eval/reports/<date>.json.

Run from the Code/ folder:
    python -m src.phase6_retrieval_testing.run

Exits with code 1 when the gate fails: top-3 hit rate under 80%, any refusal missed, or
personal data found in stored excerpts.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date

from src import config
from src.jsonl import read_jsonl
from src.phase1_data_loading.loaders.common import now_iso
from src.phase5_retrieval.retriever import Retriever
from src.phase6_retrieval_testing.evaluate import evaluate

GOLDEN_FILE = config.EVAL_DIR / "golden_set.jsonl"
HOLDOUT_FILE = config.EVAL_DIR / "holdout_set.jsonl"  # never used while tuning settings


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.WARNING)
    golden = list(read_jsonl(GOLDEN_FILE))
    tags = {t["record_id"]: t for t in read_jsonl(config.TAGS_FILE)} if config.TAGS_FILE.exists() else {}
    retriever = Retriever().warm_up()
    report = evaluate(golden, retriever.retrieve, tags, list(read_jsonl(config.CHUNKS_FILE)))
    report = {"run_at": now_iso(), **report}
    if HOLDOUT_FILE.exists():  # questions never used for tuning: the honest generalisation check
        held = evaluate(list(read_jsonl(HOLDOUT_FILE)), retriever.retrieve, tags, [])
        report["holdout"] = {k: held[k] for k in ("top3_hit_rate", "top3_hits", "in_scope_items", "refusals_ok",
                                                   "refusal_items", "routing_accuracy", "misses")}
    out = config.EVAL_DIR / "reports" / f"{date.today().isoformat()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nPhase 6: retrieval testing")
    print(f"  top-3 hit rate: {report['top3_hits']}/{report['in_scope_items']} = {report['top3_hit_rate']:.0%} "
          f"(target 80%) -> {'PASS' if report['meets_target'] else 'FAIL'}")
    print(f"  refusals: {report['refusals_ok']}/{report['refusal_items']}")
    if report["routing_accuracy"] is not None:
        print(f"  routing accuracy: {report['routing_accuracy']:.0%} of {report['routed_items']} routed questions")
    print(f"  personal data in stored excerpts: {report['personal_data_in_excerpts']}")
    if "holdout" in report:
        h = report["holdout"]
        print(f"  held-out set (not used for tuning): top-3 hit {h['top3_hits']}/{h['in_scope_items']} = "
              f"{h['top3_hit_rate']:.0%}, refusals {h['refusals_ok']}/{h['refusal_items']}")
    for miss in report["misses"]:
        print(f"  miss {miss['id']}: {miss['problem']} | {miss['question']}")
    print(f"  report -> {out.relative_to(config.PROJECT_DIR).as_posix()}")
    print(f"  note: {report['golden_set']}")
    gate = report["meets_target"] and report["refusals_ok"] == report["refusal_items"] \
        and report["personal_data_in_excerpts"] == 0
    return 0 if gate else 1


if __name__ == "__main__":
    sys.exit(main())
