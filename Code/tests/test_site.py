"""Site tests: the data loader on synthetic reports, and every page rendered with Streamlit's
AppTest against the real pipeline outputs (skipped if they are missing)."""
import json
import re
import sys
from pathlib import Path

import pytest

from src import config
from src.jsonl import write_jsonl

APP_DIR = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP_DIR))

import site_data  # noqa: E402


@pytest.fixture
def reports(tmp_path, monkeypatch):
    paths = {
        "LOAD_REPORT_FILE": tmp_path / "load_report.json", "RECORDS_FILE": tmp_path / "records.jsonl",
        "CHUNK_REPORT_FILE": tmp_path / "chunk_report.json", "EMBEDDING_REPORT_FILE": tmp_path / "embed.json",
        "VECTOR_STORE_REPORT_FILE": tmp_path / "store.json", "SOURCES_FILE": tmp_path / "sources.yaml",
        "SITE_DIR": tmp_path / "site", "PIPELINE_SUMMARY_FILE": tmp_path / "site" / "pipeline.json",
    }
    for name, value in paths.items():
        monkeypatch.setattr(config, name, value)
    monkeypatch.setattr(config, "YOUTUBE_API_KEY", "")
    paths["LOAD_REPORT_FILE"].write_text(json.dumps({"records": {"total": 4, "by_source": {
        "play_store": 3, "info_pages": 1}}, "pii_replacements": {"USER": 2, "PHONE": 1}}))
    write_jsonl([
        {"source": "play_store", "app": "Groww", "date": "2026-10-24", "doc_type": "review"},
        {"source": "play_store", "app": "Groww", "date": "2026-10-31", "doc_type": "review"},
        {"source": "play_store", "app": "Kotak MF", "date": "2024-01-01", "doc_type": "review"},
        {"source": "info_pages", "app": "Kotak", "date": "2026-11-01", "doc_type": "info_page"},
    ], paths["RECORDS_FILE"])
    paths["CHUNK_REPORT_FILE"].write_text(json.dumps({
        "excerpts": 5, "model": "m", "settings": {"model_max_tokens": 256, "target_tokens": 200, "overlap_tokens": 40},
        "per_source": {"play_store": {"excerpts": 3, "records_split": 0}, "info_pages": {"excerpts": 2, "records_split": 1}},
        "checks": {"over_limit": 0, "orphan_excerpts": 0}}))
    paths["EMBEDDING_REPORT_FILE"].write_text(json.dumps({"distinct_excerpt_texts": 4, "dim": 384,
                                                          "checks": {"excerpts_without_vector": 0}}))
    paths["VECTOR_STORE_REPORT_FILE"].write_text(json.dumps({
        "excerpts": {"rows": 5}, "build_info": {"last_updated_from_sources": "2026-11-01"},
        "checks": {"excerpt_count_mismatch": 1}}))
    paths["SOURCES_FILE"].write_text("play_store:\n  - {app: Groww, url: u, status: active}\n"
                                     "youtube:\n  - {url: y, status: active}\nx:\n  - {url: z, status: dropped}\n")
    return paths


def test_site_data_is_computed_from_reports(reports):
    site = site_data.load_site_data()
    assert site.ready and site.records_total == 4 and site.investor_records == 3 and site.info_records == 1
    assert (site.first_date, site.last_date) == ("2024-01-01", "2026-10-31")  # info pages excluded
    assert site.app_row("Groww").reviews == 2 and site.app_row("Groww").first == "2026-10-24"
    assert site.pii_total == 3 and site.last_updated == "2026-11-01"
    assert len(site.checks) == 4 and site.checks_failed == 1
    notes = {s.key: s.note for s in site.sources}
    assert "YOUTUBE_API_KEY" in notes["youtube"] and notes["x"].startswith("Dropped")
    assert [s.key for s in site.active_sources] == ["play_store", "info_pages"]


def test_site_data_reports_missing_inputs(reports):
    reports["CHUNK_REPORT_FILE"].unlink()
    site = site_data.load_site_data()
    assert not site.ready and site.missing == ["phase 2 chunk report"]


def test_deployment_without_phase_outputs_reads_the_committed_summary(reports):
    """Render has the repository only: the reports and records are git-ignored, pipeline.json is not."""
    from src.site_export import pipeline
    local = site_data.load_site_data()
    assert pipeline.write() is not None and reports["PIPELINE_SUMMARY_FILE"].exists()
    for name in ("LOAD_REPORT_FILE", "RECORDS_FILE", "CHUNK_REPORT_FILE", "EMBEDDING_REPORT_FILE",
                 "VECTOR_STORE_REPORT_FILE"):
        reports[name].unlink()
    deployed = site_data.load_site_data()
    assert deployed.ready
    assert deployed.sources == local.sources and deployed.apps == local.apps and deployed.checks == local.checks
    assert (deployed.records_total, deployed.excerpts_total, deployed.distinct_texts, deployed.vector_rows) == (4, 5, 4, 5)
    assert (deployed.first_date, deployed.last_date, deployed.last_updated) == ("2024-01-01", "2026-10-31", "2026-11-01")


def test_summary_file_matches_the_local_reports():
    """The committed Data/site/pipeline.json must not lag behind the local pipeline outputs."""
    from src.site_export import pipeline
    summary, missing = pipeline.summarize()
    if summary is None:
        pytest.skip("pipeline outputs not built: " + ", ".join(missing))
    committed = json.loads(config.PIPELINE_SUMMARY_FILE.read_text(encoding="utf-8"))
    summary.pop("generated_at"), committed.pop("generated_at")
    assert committed == summary, "rerun: python -m src.site_export.pipeline"


def test_month_and_day_labels():
    assert site_data.month_label("2026-10-30") == "Oct 2026" and site_data.day_label("2026-10-03") == "3 Oct 2026"
    assert site_data.month_label(None) == ""


real_data = pytest.mark.skipif(not config.VECTOR_STORE_REPORT_FILE.exists(), reason="pipeline outputs not built")

PAGE_SCRIPT = """
import sys
sys.path[:0] = [{code!r}, {app!r}]
import site_data, ui
from views import {module}
ui.css()
{module}.render(site_data.load_site_data())
"""


@real_data
@pytest.mark.parametrize("module", ["overview", "journey", "dropoffs", "segments", "validation", "method"])
def test_every_page_renders(module):
    from streamlit.testing.v1 import AppTest
    script = PAGE_SCRIPT.format(code=str(APP_DIR.parent), app=str(APP_DIR), module=module)
    at = AppTest.from_string(script, default_timeout=60).run()
    assert not at.exception, at.exception
    text = " ".join(m.value for m in at.markdown)
    assert "sde-title" in text  # the page header rendered
    title = re.search(r'class="sde-title">(.*?)</div>', text).group(1)
    assert not re.search(r"\d", title), f"page titles carry no research numbers: {title}"
    if module in ("overview", "journey", "dropoffs", "segments", "validation"):
        survey_loaded = config.SURVEY_RESPONSES_FILE.exists()
        shows_survey = any(h in text for h in ("What the survey adds", "Investor types from the survey",
                                                "Engine vs survey"))
        assert shows_survey if survey_loaded else ("Not computed" in text)
    if module in ("validation", "method"):
        assert "Engine vs human agreement" not in text


@real_data
def test_full_app_starts_with_empty_research_tool():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP_DIR / "streamlit_app.py"), default_timeout=60).run()
    assert not at.exception, at.exception
    chips = [b.label for b in at.sidebar.button]
    assert chips[:2] == ["Ask", "Clear"] and len(chips) == 6  # exactly 4 sample questions, no answer yet
