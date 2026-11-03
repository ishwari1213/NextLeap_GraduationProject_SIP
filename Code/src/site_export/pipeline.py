"""A compact copy of what the site needs from the phase 1-4 reports: Data/site/pipeline.json.

The reports, records, excerpts, vectors and the vector store are rebuilt locally and are not
committed (they are large, and Data/raw/ can still hold personal data). The site only needs a
few counts from them, so this module writes those counts to Data/site/pipeline.json, which is
committed. A deployment that has only the repository (for example Render) reads that file.

Run from the Code/ folder after phases 1-4 (python -m src.site_export.run also writes it):
    python -m src.site_export.pipeline
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone

from src import config
from src.jsonl import read_jsonl

REPORTS = {
    "phase 1 load report": "LOAD_REPORT_FILE",
    "phase 2 chunk report": "CHUNK_REPORT_FILE",
    "phase 3 embedding report": "EMBEDDING_REPORT_FILE",
    "phase 4 vector store report": "VECTOR_STORE_REPORT_FILE",
}
STORE_SOURCES = ("play_store", "app_store")


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def summarize() -> tuple[dict | None, list[str]]:
    """(summary, missing): the site's pipeline figures computed from the local reports and
    records, or (None, the names of the missing inputs)."""
    reports = {name: _json(getattr(config, attr)) for name, attr in REPORTS.items()}
    missing = [name for name, data in reports.items() if data is None]
    if not config.RECORDS_FILE.exists():
        missing.append("records.jsonl")
    if missing:
        return None, missing
    load, chunk, embed, store = reports.values()

    # records: date span of investor posts, and per-app review windows
    span: list[str] = []
    per_app: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in read_jsonl(config.RECORDS_FILE):
        if r["source"] != "info_pages" and r.get("date"):
            span.append(r["date"])
        if r["source"] in STORE_SOURCES and r.get("app") and r.get("date"):
            per_app[(r["app"], r["source"])].append(r["date"])
    apps = sorted(({"app": app, "source": src, "reviews": len(d), "first": min(d), "last": max(d)}
                   for (app, src), d in per_app.items()), key=lambda a: (a["source"], -a["reviews"]))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "records_total": load["records"]["total"],
        "records_by_source": load["records"]["by_source"],
        "pii_replacements": load.get("pii_replacements", {}),
        "excerpts_total": chunk["excerpts"],
        "excerpts_by_source": chunk.get("per_source", {}),
        "model": chunk.get("model", ""),
        "chunk_settings": chunk.get("settings", {}),
        "distinct_texts": embed["distinct_excerpt_texts"],
        "dim": embed.get("dim", 0),
        "vector_rows": store["excerpts"]["rows"],
        "last_updated": store.get("build_info", {}).get("last_updated_from_sources"),
        "first_date": min(span) if span else None,
        "last_date": max(span) if span else None,
        "apps": apps,
        "checks": {
            "Phase 2 · Chunking": chunk.get("checks", {}),
            "Phase 3 · Embedding": embed.get("checks", {}),
            "Phase 4 · Vector store": store.get("checks", {}),
        },
    }, []


def write() -> dict | None:
    """Write Data/site/pipeline.json from the local reports; None (file untouched) if they are missing."""
    summary, _ = summarize()
    if summary is not None:
        config.SITE_DIR.mkdir(parents=True, exist_ok=True)
        config.PIPELINE_SUMMARY_FILE.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def main() -> int:
    summary, missing = summarize()
    if summary is None:
        print("Missing pipeline outputs: " + ", ".join(missing) + ". Run phases 1-4 first.")
        return 1
    write()
    print(f"{summary['records_total']:,} records, {summary['excerpts_total']:,} excerpts, "
          f"{summary['vector_rows']:,} store rows -> "
          f"{config.PIPELINE_SUMMARY_FILE.relative_to(config.PROJECT_DIR).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
