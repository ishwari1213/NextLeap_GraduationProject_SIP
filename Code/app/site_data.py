"""Everything the site shows, read from the pipeline's own outputs.

No number is typed into the site (UI spec rule 2). Every figure comes from:
    Data/cleaned/load_report.json and records.jsonl   (phase 1)
    Data/chunks/chunk_report.json                       (phase 2)
    Data/embeddings/embedding_report.json               (phase 3)
    Data/vector_db/vector_store_report.json             (phase 4)
    Data/sources/sources.yaml                           (the ingestion URL list)
Those phase outputs are not committed, so a deployment built from the repository alone reads
the same figures from Data/site/pipeline.json (written by src/site_export/pipeline.py).
What the pipeline has not computed yet is listed in NOT_COMPUTED with its reason and the
missing step, so the pages can show a "Not yet computed" card instead of a number.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date

import yaml

from src import config
from src.site_export import pipeline

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
    """From the local phase 1-4 reports when they exist (a machine that ran the pipeline), else
    from the committed copy Data/site/pipeline.json (a deployment that has only the repository)."""
    summary, missing = pipeline.summarize()
    if summary is None:
        summary = _json(config.PIPELINE_SUMMARY_FILE)
    if summary is None:
        return SiteData(ready=False, missing=missing)
    apps = [AppRow(a["app"], a["source"], a["reviews"], a["first"], a["last"]) for a in summary.get("apps", [])]

    # sources: URLs listed, records and excerpts, and why a listed source has no records
    try:
        listed = yaml.safe_load(config.SOURCES_FILE.read_text(encoding="utf-8")) or {}
    except OSError:
        listed = {}
    by_source = summary["records_by_source"]
    per_source = summary.get("excerpts_by_source", {})
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

    checks = [Check(phase, CHECK_NAMES.get(k, k), v, v == 0)
              for phase, values in summary.get("checks", {}).items() for k, v in values.items()]

    info = by_source.get("info_pages", 0)
    return SiteData(
        ready=True,
        pages=load_pages(),
        records_total=summary["records_total"],
        investor_records=summary["records_total"] - info,
        info_records=info,
        excerpts_total=summary["excerpts_total"],
        distinct_texts=summary["distinct_texts"],
        vector_rows=summary["vector_rows"],
        first_date=summary.get("first_date"),
        last_date=summary.get("last_date"),
        last_updated=summary.get("last_updated"),
        model=summary.get("model", ""),
        dim=summary.get("dim", 0),
        chunk_settings=summary.get("chunk_settings", {}),
        pii_replacements=summary.get("pii_replacements", {}),
        sources=rows,
        apps=apps,
        checks=checks,
    )
