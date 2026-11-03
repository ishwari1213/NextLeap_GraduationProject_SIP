"""SIP Discovery Engine site: six read-only pages and 'Ask the engine' (PRD UX section).

Run from the Code/ folder:
    streamlit run app/streamlit_app.py           # opens http://localhost:8502

For the fastest answers, also run the retrieval API (uvicorn src.api.main:app --port 8001);
without it, 'Ask the engine' searches the vector store in-process.
"""
from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
CODE_DIR = APP_DIR.parent
for path in (str(CODE_DIR), str(APP_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import streamlit as st  # noqa: E402

st.set_page_config(page_title="SIP Discovery Engine", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")

import ask  # noqa: E402
import site_data  # noqa: E402
import ui  # noqa: E402
from views import dropoffs, journey, method, overview, research, segments, validation  # noqa: E402


@st.cache_data(ttl=300, show_spinner=False)
def load_site() -> site_data.SiteData:
    return site_data.load_site_data()


site = load_site()
ui.css()


def page(module, title: str, slug: str, default: bool = False) -> st.Page:
    def run() -> None:
        module.render(site)
    run.__name__ = f"page_{slug}"
    return st.Page(run, title=title, url_path=slug, default=default)


research_page = page(research, "Ask the engine", "ask")  # the research tool, full width

navigation = st.navigation([
    page(overview, "Overview", "overview", default=True),
    page(journey, "Journey", "journey"),
    page(dropoffs, "Drop-offs", "drop-offs"),
    page(segments, "Segments", "segments"),
    page(validation, "Validation", "validation"),
    page(method, "Method", "method"),
    research_page,
], position="top")

if navigation.url_path != "ask":  # the full-page tool replaces the sidebar copy on its own page
    ask.sidebar(site, full_view=research_page)
ui.banner()
navigation.run()
ui.footer(site.last_updated)
