"""Try retrieval from the terminal, without starting the API.

Run from the Code/ folder:
    python -m src.phase5_retrieval.cli "What leads investors to pause, reduce or stop a SIP?"
    python -m src.phase5_retrieval.cli "Why did my SIP autopay fail?" --app Groww
    python -m src.phase5_retrieval.cli "Which is the safest SIP?" --json
"""
from __future__ import annotations

import argparse
import json
import logging
import sys

from src.phase5_retrieval.retriever import Retriever


def show(bundle: dict) -> None:
    print(f"\nQ: {bundle['question']}")
    line = f"status: {bundle['status']}"
    if bundle["reason"]:
        line += f" ({bundle['reason']})"
    print(line + f" | supporting records: {bundle['supporting_items']}/{bundle['evidence_needed']} needed"
                 f" | {bundle['timing_ms']} ms")
    if bundle["detail"]:
        print(f"detail: {bundle['detail']}")
    if bundle["filters"]:
        print(f"filters: {bundle['filters']}")
    if bundle["page_link"]:
        print(f"route: {bundle['page_link']} (score {bundle['route']['score']})")
    for link in bundle["decline_links"]:
        print(f"decline with: {link['label']} - {link['url']}")
    for i, ex in enumerate(bundle["excerpts"], 1):
        text = " ".join(ex["text"].split())
        where = f"{ex['source']}/{ex['app'] or '-'} {ex['date'] or ''}".strip()
        print(f"  {i}. {ex['score']:.2f} [{where}] {text[:150]}{'...' if len(text) > 150 else ''}")
    for ex in bundle.get("context", []):
        text = " ".join(ex["text"].split())
        print(f"  context {ex['score']:.2f} [info page/{ex['app'] or '-'}] {text[:120]}...")
    for note in bundle["notes"]:
        print(f"note: {note}")
    print(f"last updated from sources: {bundle['last_updated']}")


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Phase 5: retrieve evidence for a question")
    parser.add_argument("questions", nargs="+", help="one or more questions, each in quotes")
    parser.add_argument("--app", help="only this app, e.g. Groww")
    parser.add_argument("--source", help="only this source, e.g. play_store, reddit, forums")
    parser.add_argument("--json", action="store_true", help="print the raw evidence bundle")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    retriever = Retriever().warm_up()
    for question in args.questions:
        bundle = retriever.retrieve(question, app=args.app, source=args.source)
        print(json.dumps(bundle, indent=2, ensure_ascii=False)) if args.json else show(bundle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
