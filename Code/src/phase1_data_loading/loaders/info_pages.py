"""SIP information pages: context for factual answers only, never for return calculations.

Each sources.yaml entry names how to get it:
    fetch: html     the live page
    fetch: wayback  the latest Wayback Machine copy (kotakmf.com shows a bot captcha)
    fetch: upload   a PDF you download by hand into Data/uploads/<file>
                    (the Kotak document server serves an app page, not the PDF, to scripts)
"""
from __future__ import annotations

import logging

import requests
from bs4 import BeautifulSoup

from src import config
from src.phase1_data_loading.clean import html_to_text
from src.phase1_data_loading.loaders.common import raw_item, to_iso_date, wayback_fetch

SOURCE = "info_pages"
log = logging.getLogger(__name__)

# Content is found by paragraph density, not by class names: sites wrap whole pages in
# <form> (kotak.bank.in even in <header>), and utility class names defeat selectors.
NEVER_CONTENT = ("script", "style", "noscript", "template", "svg", "iframe", "button")
CHROME_TAGS = ("nav", "header", "footer", "aside")  # removed unless they wrap the page
WRAPS_PAGE_SHARE = 0.9  # a chrome tag holding this share of paragraph text wraps the page; keep it
CONTENT_SHARE = 0.8     # descend into a child while it holds at least this share of paragraph text
LINK_LIST_SHARE = 0.6   # a block with no paragraphs whose text is mostly links is a menu
MIN_INFO_CHARS = 300    # shorter extracted text is a banner or a script-rendered page
CAPTCHA_MARKERS = ("radware captcha", "captcha page", "are you a robot", "just a moment...")


def _looks_blocked(page_html: str) -> bool:
    head = page_html[:20000].lower()
    return any(marker in head for marker in CAPTCHA_MARKERS)


def _read_pdf(path) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        log.warning("pypdf is not installed; run `pip install pypdf` to read %s", path.name)
        return None
    return "\n\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def fetch(entries, http):
    for entry in entries:
        mode = entry.get("fetch", "html")
        try:
            if mode == "upload":
                path = config.UPLOADS_DIR / entry["file"]
                if not path.exists():
                    log.warning("Missing %s: download %s in a browser and save it as Data/uploads/%s",
                                entry["file"], entry["url"], entry["file"])
                    continue
                text = _read_pdf(path)
                if text:
                    yield raw_item(SOURCE, entry, {"pdf_text": text, "file": entry["file"]}, url=entry["url"], kind="pdf")
                continue

            if mode == "wayback":
                result = wayback_fetch(http, entry["url"])
                if result is None:
                    continue
                page_html, timestamp, archive_url = result
                payload = {"html": page_html, "snapshot_timestamp": timestamp, "archive_url": archive_url}
            else:
                resp = http.get(entry["url"])
                if resp.status_code != 200:
                    log.warning("Info page %s returned HTTP %s", entry["url"], resp.status_code)
                    continue
                page_html = http.text_of(resp)
                payload = {"html": page_html, "final_url": resp.url}

            if _looks_blocked(page_html):
                log.warning("Info page %s returned a bot check, not content; skipped", entry["url"])
                continue
            log.info("Info page %s (%s): %d KB", entry["url"], mode, len(page_html) // 1024)
            yield raw_item(SOURCE, entry, payload, url=entry["url"], kind="page")
        except (requests.RequestException, ValueError, OSError) as exc:
            log.error("Info page %s failed: %s", entry["url"], exc)


def _paragraph_chars(el) -> int:
    return sum(len(p.get_text(" ", strip=True)) for p in el.find_all("p"))


def _main_text(page_html: str) -> str:
    """Text of the smallest block holding most of the page's paragraphs.

    Menus are mostly links, not paragraphs, so walking down towards the paragraph-dense
    block leaves them behind.
    """
    soup = BeautifulSoup(page_html, "lxml")
    for el in soup(NEVER_CONTENT):
        el.decompose()
    total = _paragraph_chars(soup)
    for el in soup(CHROME_TAGS):
        if _paragraph_chars(el) < WRAPS_PAGE_SHARE * total:
            el.decompose()

    node = soup.body or soup
    while True:
        children = node.find_all(recursive=False)
        node_chars = _paragraph_chars(node)
        if not children or node_chars == 0:
            break
        densest = max(children, key=_paragraph_chars)
        if _paragraph_chars(densest) < CONTENT_SHARE * node_chars:
            break
        node = densest
    _drop_link_lists(node)
    return html_to_text(str(node))


def _drop_link_lists(node) -> None:
    """Remove menus left inside the content block: blocks of links with no paragraphs."""
    for el in node.find_all(["ul", "ol", "div", "section", "table"]):
        if el.find("p"):
            continue
        text_chars = len(el.get_text(" ", strip=True))
        link_chars = sum(len(a.get_text(" ", strip=True)) for a in el.find_all("a"))
        if text_chars and link_chars >= LINK_LIST_SHARE * text_chars:
            el.decompose()


def normalise(item):
    payload = item["payload"]
    text = payload["pdf_text"] if "pdf_text" in payload else _main_text(payload.get("html", ""))
    if len(text.strip()) < MIN_INFO_CHARS:
        log.warning("Info page %s gave only %d characters of text; skipped", item["url"], len(text.strip()))
        return
    yield {
        "app": item["entry"].get("app"),
        "url": item["url"],
        "date": to_iso_date(item["fetched_at"]),
        "doc_type": "info_page",
        "text": text,
    }
