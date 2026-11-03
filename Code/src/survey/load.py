"""Load the investor survey (Docs/SIP Investor Behavior Survey.csv) into de-identified responses.

Run from the Code/ folder:
    python -m src.survey.load

Writes Data/survey/responses.jsonl (one row per response), questions.json (key -> question) and
survey_report.json. Personal data never leaves this function: the timestamp, the follow-up
question and the optional name and email columns are dropped before anything is written, and
free-text answers go through the same personal-data filter as public posts (PRD privacy rule).
Multiple-choice answers with several picks (separated by ";") become lists.
"""
from __future__ import annotations

import json
import logging
import re
import sys
from collections import Counter

import pandas as pd

from src import config
from src.jsonl import write_jsonl
from src.phase1_data_loading.loaders.common import now_iso
from src.phase1_data_loading.pii import strip_pii

log = logging.getLogger("survey")

DROP = {"timestamp", "q31", "q32", "q33"}           # timestamp, follow-up interest, name, email
MULTI = {"q7", "q18", "q19", "q23", "q26", "q27"}   # several picks joined by ";"
FREE_TEXT = {"q8", "q20", "q21", "q22", "q24"}
NUMERIC = {"q28"}                                   # 1-5 likelihood
_KEY = re.compile(r"^\s*Q(\d+)\.", re.IGNORECASE)


def column_key(column: str) -> str:
    match = _KEY.match(column)
    return f"q{match.group(1)}" if match else column.strip().lower()


def load(path=None) -> tuple[list[dict], dict, dict]:
    """(responses, questions, report) from the raw CSV, already de-identified."""
    raw = pd.read_csv(path or config.SURVEY_SOURCE_FILE)
    keys = {c: column_key(c) for c in raw.columns}
    questions = {k: re.sub(r"^\s*Q\d+\.\s*", "", c).strip() for c, k in keys.items() if k not in DROP}
    pii = Counter()
    responses = []
    for i, row in enumerate(raw.itertuples(index=False), 1):
        out = {"id": f"s{i:02d}"}
        for column, value in zip(raw.columns, row):
            key = keys[column]
            if key in DROP:
                continue
            if pd.isna(value):
                out[key] = [] if key in MULTI else None
            elif key in MULTI:
                out[key] = [part.strip() for part in str(value).split(";") if part.strip()]
            elif key in NUMERIC:
                out[key] = int(float(value))
            elif key in FREE_TEXT:
                text, counts = strip_pii(str(value).strip())
                pii.update(counts)
                out[key] = text
            else:
                out[key] = str(value).strip()
        responses.append(out)
    report = {
        "run_at": now_iso(),
        "source": config.SURVEY_SOURCE_FILE.name,
        "responses": len(responses),
        "sip_investors": sum(1 for r in responses if r.get("q2") == "Yes"),
        "questions_kept": len(questions),
        "columns_dropped": sorted(c for c, k in keys.items() if k in DROP),
        "personal_data_replaced_in_free_text": dict(pii),
    }
    return responses, questions, report


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    if not config.SURVEY_SOURCE_FILE.exists():
        log.error("Survey file not found: %s", config.SURVEY_SOURCE_FILE)
        return 1
    responses, questions, report = load()
    config.SURVEY_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(responses, config.SURVEY_RESPONSES_FILE)
    config.SURVEY_QUESTIONS_FILE.write_text(json.dumps(questions, indent=2, ensure_ascii=False), encoding="utf-8")
    config.SURVEY_REPORT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Survey: {report['responses']} responses ({report['sip_investors']} SIP investors), "
          f"{report['questions_kept']} questions kept; dropped columns: {', '.join(report['columns_dropped'])}")
    print(f"Written -> {config.SURVEY_RESPONSES_FILE.relative_to(config.PROJECT_DIR).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
