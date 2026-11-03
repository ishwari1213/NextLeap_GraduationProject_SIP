"""Phase 1 entry point: fetch every active source, then build Data/cleaned/records.jsonl.

Run from the Code/ folder:
    python -m src.phase1_data_loading.run                        # fetch all sources, rebuild records
    python -m src.phase1_data_loading.run --sources reddit forums
    python -m src.phase1_data_loading.run --skip-fetch           # rebuild records from Data/raw/ only
    python -m src.phase1_data_loading.run --quick                # small volumes, for a smoke test

Steps (Docs/architecture.md, phase 1):
  1. each loader writes its responses to Data/raw/<source>/<date>.jsonl (author fields removed)
  2-4. every raw file is normalised, cleaned, stripped of personal data and de-duplicated
  5. Data/cleaned/records.jsonl and Data/cleaned/load_report.json are written
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from src import config
from src.jsonl import write_jsonl
from src.phase1_data_loading.clean import finalise
from src.phase1_data_loading.http_client import Http
from src.phase1_data_loading.loaders import LOADERS
from src.phase1_data_loading.loaders.common import now_iso

log = logging.getLogger("phase1")


def load_sources(path: Path | None = None) -> dict[str, list[dict]]:
    with open(path or config.SOURCES_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def active(entries: list[dict] | None) -> list[dict]:
    return [e for e in entries or [] if e.get("status", "active") != "dropped"]


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(config.PROJECT_DIR)).replace("\\", "/")
    except ValueError:
        return str(path)


def fetch_source(name: str, loader, entries: list[dict], http: Http, raw_dir: Path) -> dict:
    """Run one loader and write its raw items to raw_dir/<name>/<today>.jsonl."""
    reason = getattr(loader, "skip_reason", lambda: None)()
    if reason:
        log.warning("%s skipped: %s", name, reason)
        return {"items": 0, "skipped": reason}
    if not entries:
        return {"items": 0, "skipped": "no active entries in sources.yaml"}

    out_dir = raw_dir / name
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{date.today().isoformat()}.jsonl"
    part = target.with_name(target.name + ".part")
    count, error = 0, None
    try:
        with part.open("w", encoding="utf-8") as f:
            for item in loader.fetch(entries, http):
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
                count += 1
    except Exception as exc:  # keep other sources running
        log.exception("%s: loader stopped early", name)
        error = f"{type(exc).__name__}: {exc}"
    if count:
        part.replace(target)  # a failed run never replaces a good file with an empty one
    else:
        part.unlink(missing_ok=True)

    result = {"items": count, "file": _rel(target) if count else None}
    if error:
        result["error"] = error
    return result


def build_records(raw_dir: Path) -> tuple[list[dict], dict]:
    """Normalise, clean and de-duplicate every raw file of every source."""
    records: dict[str, dict] = {}
    stats = {key: Counter() for key in ("raw_items", "records", "duplicates", "empty", "pii")}
    for name, loader in LOADERS.items():
        # newest files first, so the latest copy of a duplicate wins
        for path in sorted((raw_dir / name).glob("*.jsonl"), reverse=True):
            with path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    item = json.loads(line)
                    stats["raw_items"][name] += 1
                    for partial in loader.normalise(item):
                        record, pii_counts = finalise(name, partial, item.get("entry", {}))
                        stats["pii"].update(pii_counts)
                        if record is None:
                            stats["empty"][name] += 1
                        elif record["id"] in records:
                            stats["duplicates"][name] += 1
                        else:
                            records[record["id"]] = record
                            stats["records"][name] += 1
    ordered = sorted(records.values(), key=lambda r: (r["source"], r["date"] or "", r["id"]))
    return ordered, stats


def print_summary(report: dict) -> None:
    fetch = report["fetch"]
    rec = report["records"]
    names = sorted(set(LOADERS) | set(fetch))
    print("\nPhase 1 summary")
    print(f"{'source':<12} {'fetched now':>11} {'records':>8} {'duplicates':>10} {'empty':>6}  note")
    for name in names:
        f = fetch.get(name, {})
        note = f.get("skipped") or f.get("error") or ("" if f else "not fetched this run")
        fetched = f.get("items", "-") if f else "-"
        print(f"{name:<12} {fetched!s:>11} {rec['by_source'].get(name, 0):>8} "
              f"{rec['duplicates'].get(name, 0):>10} {rec['empty'].get(name, 0):>6}  {note}")
    print(f"\nRecords written: {rec['total']} -> {report['records_file']}")
    pii = report["pii_replacements"]
    print("Personal data replaced: " + (", ".join(f"{k} {v}" for k, v in sorted(pii.items())) or "none"))
    for name, urls in report["dropped"].items():
        print(f"Dropped ({name}): {len(urls)} URL(s), see sources.yaml")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Phase 1: data loading")
    parser.add_argument("--sources", nargs="+", choices=sorted(LOADERS), help="fetch only these sources")
    parser.add_argument("--skip-fetch", action="store_true", help="rebuild records from Data/raw/ without fetching")
    parser.add_argument("--quick", action="store_true", help="small volumes for a smoke test")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    if args.quick:
        config.apply_quick_mode()

    sources = load_sources()
    unknown = [k for k, v in sources.items() if k not in LOADERS and active(v)]
    for name in unknown:
        log.warning("sources.yaml has active entries for %r but no loader exists", name)

    report: dict = {"run_at": now_iso(), "quick_mode": args.quick, "fetch": {}}
    if not args.skip_fetch:
        http = Http()
        for name in args.sources or list(LOADERS):
            log.info("== Fetching %s", name)
            report["fetch"][name] = fetch_source(name, LOADERS[name], active(sources.get(name)), http, config.RAW_DIR)

    log.info("== Building records from %s", _rel(config.RAW_DIR))
    records, stats = build_records(config.RAW_DIR)
    write_jsonl(records, config.RECORDS_FILE)

    report.update({
        "records_file": _rel(config.RECORDS_FILE),
        "records": {
            "total": len(records),
            "by_source": dict(stats["records"]),
            "by_doc_type": dict(Counter(r["doc_type"] for r in records)),
            "raw_items": dict(stats["raw_items"]),
            "duplicates": dict(stats["duplicates"]),
            "empty": dict(stats["empty"]),
        },
        "pii_replacements": dict(stats["pii"]),
        "dropped": {k: [e["url"] for e in v or [] if e.get("status") == "dropped"]
                    for k, v in sources.items() if any(e.get("status") == "dropped" for e in v or [])},
    })
    config.LOAD_REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print_summary(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
