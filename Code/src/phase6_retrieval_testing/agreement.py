"""Engine-vs-human agreement on the tags (UI spec: Validation page).

    python -m src.phase6_retrieval_testing.agreement export   # write Data/eval/human_labels.csv to fill in
    python -m src.phase6_retrieval_testing.agreement score    # compare filled-in labels with the engine's

The sheet holds 40 posts sent to the model (20 it judged about SIPs, 20 not), with empty
columns for the 6 fields the UI spec compares: about_sip, stage, event, trigger, theme,
failure_mode. A person fills them using the labels in Data/eval/HOW_TO_LABEL.md without
looking at the engine's tags. `score` writes Data/eval/agreement.json, which the site shows.
"""
from __future__ import annotations

import csv
import json
import random
import sys

from src import config
from src.jsonl import read_jsonl
from src.tagging.taxonomy import FIELDS

SHEET = config.EVAL_DIR / "human_labels.csv"
GUIDE = config.EVAL_DIR / "HOW_TO_LABEL.md"
RESULT = config.EVAL_DIR / "agreement.json"
COMPARED = ["about_sip", "stage", "event", "trigger", "theme", "failure_mode"]


def export(n_each: int = 20, seed: int = 7) -> None:
    if SHEET.exists():
        print(f"{SHEET} already exists; delete it first to draw a new sample.")
        return
    records = {r["id"]: r for r in read_jsonl(config.RECORDS_FILE)}
    llm = [t for t in read_jsonl(config.TAGS_FILE) if t["tagged_by"] == "llm" and t["record_id"] in records]
    rng = random.Random(seed)
    picks = rng.sample([t for t in llm if t["about_sip"]], n_each) + rng.sample([t for t in llm if not t["about_sip"]], n_each)
    rng.shuffle(picks)
    with SHEET.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["record_id", "source", "text", *COMPARED])
        for t in picks:
            r = records[t["record_id"]]
            writer.writerow([r["id"], r["source"], " ".join(r["text"].split())[:1200], *[""] * len(COMPARED)])
    lines = ["# How to label Data/eval/human_labels.csv", "",
             "Read each post and fill the six columns from what the text states. Leave a cell empty when the text "
             "does not state it. Do not look at the engine's tags first.", "",
             "- about_sip: yes or no (is the post about SIPs or mutual-fund instalments?)"]
    for field in COMPARED[1:]:
        lines.append(f"- {field}: " + ", ".join(FIELDS[field]["labels"]) + " (empty = not stated)")
    lines += ["", "Then run: python -m src.phase6_retrieval_testing.agreement score"]
    GUIDE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(picks)} posts to {SHEET} and the label guide to {GUIDE}")


def score() -> int:
    if not SHEET.exists():
        print("No human_labels.csv yet: run the export first.")
        return 1
    tags = {t["record_id"]: t for t in read_jsonl(config.TAGS_FILE)}
    with SHEET.open(encoding="utf-8-sig") as f:
        rows = [r for r in csv.DictReader(f) if any(r.get(c, "").strip() for c in COMPARED)]
    if not rows:
        print("human_labels.csv has no labels filled in yet.")
        return 1
    per_field = {}
    for field in COMPARED:
        agree = total = 0
        for r in rows:
            engine = tags.get(r["record_id"])
            if not engine:
                continue
            human = r.get(field, "").strip().lower()
            if field == "about_sip":
                human_value, engine_value = human in ("yes", "y", "true", "1"), engine["about_sip"]
            else:
                human_value = human.replace(" ", "_") or FIELDS[field]["unknown"]
                engine_value = engine[field]
            total += 1
            agree += human_value == engine_value
        per_field[field] = {"agree": agree, "total": total, "rate": round(agree / total, 3) if total else None}
    agree_all = sum(v["agree"] for v in per_field.values())
    total_all = sum(v["total"] for v in per_field.values())
    result = {"posts_labelled": len(rows), "overall": round(agree_all / total_all, 3) if total_all else None,
              "agree": agree_all, "total": total_all, "per_field": per_field}
    RESULT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "export"
    sys.exit(score() if command == "score" else export() or 0)
