"""FR-6 + FR-7 entry point: score opportunities and write the site's page data.

Run from the Code/ folder (after tagging):
    python -m src.site_export.run

Writes Data/site/overview.json, journey.json, dropoffs.json, segments.json, validation.json,
method.json and sections_index.json. Rerun phases 3 and 4 afterwards so the sections are
embedded and stored for routing.
"""
from __future__ import annotations

import json
import logging
import sys

from src import config
from src.jsonl import read_jsonl
from src.phase1_data_loading.loaders.common import now_iso
from src.site_export.build import build

log = logging.getLogger("site_export")


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def latest_evaluation() -> dict | None:
    reports = sorted((config.EVAL_DIR / "reports").glob("*.json")) if (config.EVAL_DIR / "reports").exists() else []
    return _json(reports[-1]) if reports else None


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    if not config.TAGS_FILE.exists():
        log.error("%s not found: run tagging first (python -m src.tagging.run)", config.TAGS_FILE)
        return 1
    records = list(read_jsonl(config.RECORDS_FILE))
    tags = {t["record_id"]: t for t in read_jsonl(config.TAGS_FILE)}
    store = _json(config.VECTOR_STORE_REPORT_FILE) or {}
    reports = {
        "generated_at": now_iso(),
        "last_updated": store.get("build_info", {}).get("last_updated_from_sources"),
        "tags": _json(config.TAG_REPORT_FILE),
        "evaluation": latest_evaluation(),
        "agreement": _json(config.EVAL_DIR / "agreement.json"),
        "survey_rows": list(read_jsonl(config.SURVEY_RESPONSES_FILE)) if config.SURVEY_RESPONSES_FILE.exists() else [],
    }
    pages = build(records, tags, reports)
    config.SITE_DIR.mkdir(parents=True, exist_ok=True)
    for name, data in pages.items():
        (config.SITE_DIR / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    o = pages["overview"]
    print("\nSite export summary")
    print(f"  posts {o['tiles']['posts']['n']:,} | SIP posts {o['tiles']['sip_posts']['n']:,} | "
          f"problem posts {o['tiles']['problem_posts']['n']:,}")
    for opp in o["opportunities"]["all"]:
        print(f"  {opp['score'] if opp['score'] is not None else '–':>4}  {opp['name']:<34} {opp['posts']:>4} posts  "
              f"{opp['tag']}{'  (left out: ' + ', '.join(opp['left_out']) + ')' if opp['left_out'] else ''}")
    print(f"  sections for routing: {len(pages['sections_index'])}")
    print(f"  written -> {config.SITE_DIR.relative_to(config.PROJECT_DIR).as_posix()}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
