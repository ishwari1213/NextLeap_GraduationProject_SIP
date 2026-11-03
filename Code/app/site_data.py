"""Everything the site shows, read from the pipeline's own outputs.

No number is typed into the site (UI spec rule 2). Every figure comes from:
    Data/cleaned/load_report.json and records.jsonl   (phase 1)
    Data/chunks/chunk_report.json                       (phase 2)
    Data/embeddings/embedding_report.json               (phase 3)
    Data/vector_db/vector_store_report.json             (phase 4)
    Data/sources/sources.yaml                           (the ingestion URL list)
What the pipeline has not computed yet is listed in NOT_COMPUTED with its reason and the
missing step, so the pages can show a "Not yet computed" card instead of a number.
"""
from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

import yaml

from src import config
from src.jsonl import read_jsonl

SOURCE_LABELS = {
    "play_store": "Google Play",
    "app_store": "App Store",
    "forums": "Forums (TradingQ&A, Jupiter, madefortrade)",
    "reddit": "Reddit",
    "team_bhp": "Team-BHP",
    "youtube": "YouTube",
    "info_pages": "SIP information pages",
    "x": "X (Twitter)",
}
STORE_SOURCES = ("play_store", "app_store")

TAGGING = "the FR-5 tagging step (stage, trigger, event, segment, theme and failure mode for every post)"
SCORING = "the FR-6 opportunity scoring, which runs on the tags"
SURVEY = "the 21-person investor survey, whose data is not loaded into this project"
GOLDEN = "the phase 6 golden set of 20 hand-checked questions"

NOT_COMPUTED = {
    "opportunity_ranking": ("Opportunity ranking", "Each opportunity's score needs reach, severity, stage fit and "
                            "segment fit counted from tagged posts.", f"{TAGGING}, then {SCORING}"),
    "failure_modes": ("Posts per failure mode", "Failure modes are a tag on each post.", TAGGING),
    "metric_tree": ("Metric tree counts", "Each branch counts posts tagged to it.", TAGGING),
    "expectations": ("Why people start and what they expect", "Needs expectation and motivation tags, and the survey.",
                     f"{TAGGING}; {SURVEY}"),
    "stages": ("Posts by journey stage", "Needs the stage tag on each post.", TAGGING),
    "checking": ("What investors check, and how often", "Needs checking-behaviour tags, and the survey.",
                 f"{TAGGING}; {SURVEY}"),
    "confusion": ("What confuses investors inside the app", "Needs theme tags.", TAGGING),
    "outside_app": ("Where investors go outside the app", "Needs help-seeking tags, and the survey.",
                    f"{TAGGING}; {SURVEY}"),
    "events": ("Pause, reduce and stop events", "Needs the event tag on each post.", TAGGING),
    "triggers": ("What triggers a pause or stop", "Needs the trigger tag on each post.", TAGGING),
    "market_or_not": ("Market-driven or not", "Compares market-related failure modes with instalment problems.",
                      TAGGING),
    "continuers": ("Continuers vs drop-offs", "Needs event tags to tell the two groups apart.", TAGGING),
    "segment_table": ("Patterns by segment", "Needs segment tags (income, age, source of money, influence, "
                      "experience, residency).", TAGGING),
    "first_time": ("First-time investor patterns", "Needs the experience tag.", TAGGING),
    "survey_patterns": ("Survey patterns", "Comes from the survey responses.", SURVEY),
    "agreement": ("Engine vs human agreement", "Compares the engine's tags with a person's labels on the same posts.",
                  f"{TAGGING}, then a human-labelled sample"),
    "precision_recall": ("Precision and recall per class", "Needs tags and a human-labelled sample.",
                         f"{TAGGING}, then a human-labelled sample"),
    "retrieval_accuracy": ("Retrieval top-3 hit rate", "Measures whether a relevant excerpt is in the top 3 "
                           "(PRD target: 80% or more).", GOLDEN),
    "engine_vs_survey": ("Engine vs survey", "Compares engine findings with survey answers.", f"{TAGGING}; {SURVEY}"),
}


@dataclass
class Check:
    phase: str
    name: str
    value: int
    passed: bool


@dataclass
class SourceRow:
    key: str
    label: str
    urls_active: int
    urls_dropped: int
    records: int
    excerpts: int
    records_split: int
    note: str


@dataclass
class AppRow:
    app: str
    source: str
    reviews: int
    first: str
    last: str


PAGE_FILES = ("overview", "journey", "dropoffs", "segments", "validation", "method", "sections_index")


def load_pages() -> dict:
    """The FR-7 page data written by `python -m src.site_export.run` (empty if not run yet)."""
    pages = {}
    for name in PAGE_FILES:
        data = _json(config.SITE_DIR / f"{name}.json")
        if data is not None:
            pages[name] = data
    return pages


@dataclass
class SiteData:
    ready: bool
    missing: list[str] = field(default_factory=list)
    pages: dict = field(default_factory=dict)
    records_total: int = 0
    investor_records: int = 0
    info_records: int = 0
    excerpts_total: int = 0
    distinct_texts: int = 0
    vector_rows: int = 0
    first_date: str | None = None
    last_date: str | None = None
    last_updated: str | None = None
    model: str = ""
    dim: int = 0
    chunk_settings: dict = field(default_factory=dict)
    pii_replacements: dict = field(default_factory=dict)
    sources: list[SourceRow] = field(default_factory=list)
    apps: list[AppRow] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)

    @property
    def active_sources(self) -> list[SourceRow]:
        return [s for s in self.sources if s.records > 0]

    @property
    def investor_sources(self) -> list[SourceRow]:
        return [s for s in self.active_sources if s.key != "info_pages"]

    @property
    def checks_failed(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    @property
    def pii_total(self) -> int:
        return sum(self.pii_replacements.values())

    def source(self, key: str) -> SourceRow | None:
        return next((s for s in self.sources if s.key == key), None)

    def app_row(self, app: str, source: str = "play_store") -> AppRow | None:
        return next((a for a in self.apps if a.app == app and a.source == source), None)


CHECK_NAMES = {
    "over_limit": "Excerpts over the model's 256-token limit",
    "orphan_excerpts": "Excerpts that map to no record",
    "records_without_excerpts": "Records with no excerpt",
    "duplicate_chunk_ids": "Duplicate excerpt ids",
    "excerpts_without_vector": "Excerpts without a vector",
    "wrong_dimension": "Vectors with the wrong dimension",
    "not_unit_length": "Vectors not of unit length",
    "non_finite": "Vectors with invalid values",
    "excerpt_count_mismatch": "Store rows vs excerpts (difference)",
    "section_count_mismatch": "Section rows vs sections (difference)",
    "not_cosine": "Store not using cosine distance",
    "sample_not_found": "Sample queries that missed their own excerpt",
    "sample_missing_metadata": "Sample results with missing metadata",
}


def _json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def month_label(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        return date.fromisoformat(iso[:10]).strftime("%b %Y")
    except ValueError:
        return iso


def day_label(iso: str | None) -> str:
    if not iso:
        return ""
    try:
        d = date.fromisoformat(iso[:10])
        return f"{d.day} {d.strftime('%b %Y')}"
    except ValueError:
        return iso


def load_site_data() -> SiteData:
    reports = {
        "phase 1 load report": _json(config.LOAD_REPORT_FILE),
        "phase 2 chunk report": _json(config.CHUNK_REPORT_FILE),
        "phase 3 embedding report": _json(config.EMBEDDING_REPORT_FILE),
        "phase 4 vector store report": _json(config.VECTOR_STORE_REPORT_FILE),
    }
    missing = [name for name, data in reports.items() if data is None]
    if missing or not config.RECORDS_FILE.exists():
        return SiteData(ready=False, missing=missing + ([] if config.RECORDS_FILE.exists() else ["records.jsonl"]))
    load, chunk, embed, store = reports.values()

    # records: date span of investor posts, and per-app review windows
    span: list[str] = []
    per_app: dict[tuple[str, str], list[str]] = defaultdict(list)
    for r in read_jsonl(config.RECORDS_FILE):
        if r["source"] != "info_pages" and r.get("date"):
            span.append(r["date"])
        if r["source"] in STORE_SOURCES and r.get("app") and r.get("date"):
            per_app[(r["app"], r["source"])].append(r["date"])
    apps = sorted((AppRow(app, src, len(d), min(d), max(d)) for (app, src), d in per_app.items()),
                  key=lambda a: (a.source, -a.reviews))

    # sources: URLs listed, records and excerpts, and why a listed source has no records
    try:
        listed = yaml.safe_load(config.SOURCES_FILE.read_text(encoding="utf-8")) or {}
    except OSError:
        listed = {}
    by_source = load["records"]["by_source"]
    per_source = chunk.get("per_source", {})
    rows = []
    for key in dict.fromkeys([*listed, *by_source]):
        entries = listed.get(key) or []
        active = sum(1 for e in entries if e.get("status", "active") != "dropped")
        dropped = len(entries) - active
        records = by_source.get(key, 0)
        note = ""
        if records == 0 and dropped and not active:
            note = "Dropped: its API needs a paid plan"
        elif records == 0 and key == "youtube" and not config.YOUTUBE_API_KEY:
            note = "Skipped: needs YOUTUBE_API_KEY in Code/.env"
        elif records == 0:
            note = "No records loaded"
        rows.append(SourceRow(key, SOURCE_LABELS.get(key, key), active, dropped, records,
                              per_source.get(key, {}).get("excerpts", 0),
                              per_source.get(key, {}).get("records_split", 0), note))

    checks = [Check("Phase 2 · Chunking", CHECK_NAMES.get(k, k), v, v == 0) for k, v in chunk["checks"].items()]
    checks += [Check("Phase 3 · Embedding", CHECK_NAMES.get(k, k), v, v == 0) for k, v in embed["checks"].items()]
    checks += [Check("Phase 4 · Vector store", CHECK_NAMES.get(k, k), v, v == 0) for k, v in store["checks"].items()]

    info = by_source.get("info_pages", 0)
    return SiteData(
        ready=True,
        pages=load_pages(),
        records_total=load["records"]["total"],
        investor_records=load["records"]["total"] - info,
        info_records=info,
        excerpts_total=chunk["excerpts"],
        distinct_texts=embed["distinct_excerpt_texts"],
        vector_rows=store["excerpts"]["rows"],
        first_date=min(span) if span else None,
        last_date=max(span) if span else None,
        last_updated=store.get("build_info", {}).get("last_updated_from_sources"),
        model=chunk.get("model", ""),
        dim=embed.get("dim", 0),
        chunk_settings=chunk.get("settings", {}),
        pii_replacements=load.get("pii_replacements", {}),
        sources=rows,
        apps=apps,
        checks=checks,
    )
