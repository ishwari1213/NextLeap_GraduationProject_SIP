"""Team-BHP forum pages through their Wayback Machine copy (the live site blocks scripts).

Team-BHP runs vBulletin: each post's text sits in <div id="post_message_<id>"> and its
date in the first td.thead of <table id="post<id>">, e.g. "14th February 2025, 18:30".
Quoted posts are removed so a reply does not repeat someone else's text.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from src.phase1_data_loading.clean import html_to_text
from src.phase1_data_loading.loaders.common import raw_item, wayback_fetch

SOURCE = "team_bhp"
log = logging.getLogger(__name__)

_DATE = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})")


def fetch(entries, http):
    for entry in entries:
        try:
            result = wayback_fetch(http, entry["url"])
        except (requests.RequestException, ValueError) as exc:
            log.error("Team-BHP %s failed: %s", entry["url"], exc)
            continue
        if result is None:
            continue
        page_html, timestamp, archive_url = result
        log.info("Team-BHP: Wayback copy %s of %s", timestamp, entry["url"])
        payload = {"html": page_html, "snapshot_timestamp": timestamp, "archive_url": archive_url}
        yield raw_item(SOURCE, entry, payload, url=entry["url"], kind="page")


def _post_date(soup: BeautifulSoup, post_id: str, fallback: str | None) -> str | None:
    table = soup.find(id=f"post{post_id}")
    head = table.select_one("td.thead") if table else None
    match = _DATE.search(head.get_text(" ", strip=True)) if head else None
    if match:
        try:
            return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date().isoformat()
        except ValueError:
            pass
    return fallback


def _remove_quotes(message) -> None:
    for label in message.select("div.smallfont"):
        if label.get_text(strip=True).lower().startswith("quote"):
            (label.parent or label).decompose()


def normalise(item):
    payload = item["payload"]
    soup = BeautifulSoup(payload["html"], "lxml")
    ts = payload.get("snapshot_timestamp", "")
    fallback = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}" if len(ts) >= 8 else None
    for message in soup.select('div[id^="post_message_"]'):
        post_id = message["id"].rsplit("_", 1)[-1]
        _remove_quotes(message)
        yield {
            "app": None,
            "url": f"{item['url']}#post{post_id}",
            "date": _post_date(soup, post_id, fallback),
            "doc_type": "post",
            "text": html_to_text(str(message)),
        }
