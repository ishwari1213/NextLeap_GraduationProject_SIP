"""App Store reviews.

First choice: Apple's public RSS JSON feed, 50 reviews per page, up to 10 pages (PRD:
about 500 per app). The feed sometimes answers with no entries at all (seen on
2026-11-01); for an app whose feed is empty, the loader falls back to the app's
"see all reviews" web page, which embeds only the 10 newest reviews.
"""
from __future__ import annotations

import json
import logging
import re

import requests

from src import config
from src.phase1_data_loading.loaders.common import raw_item, to_iso_date

SOURCE = "app_store"
log = logging.getLogger(__name__)

FEED = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
WEB_PAGE = "https://apps.apple.com/{country}/app/id{app_id}?see-all=reviews"
_SERVER_DATA = re.compile(r'<script type="application/json" id="serialized-server-data">(.*?)</script>', re.S)


def _label(node: dict, key: str) -> str:
    value = node.get(key) or {}
    if isinstance(value, dict):
        return value.get("label", "")
    return value if isinstance(value, str) else ""


def _feed_reviews(entry: dict, http):
    for page in range(1, config.APP_STORE_MAX_PAGES + 1):
        url = FEED.format(country=config.APP_STORE_COUNTRY, page=page, app_id=entry["app_id"])
        resp = http.get(url)
        if resp.status_code != 200:
            return
        try:
            feed_entries = resp.json().get("feed", {}).get("entry", [])
        except ValueError:
            return
        if isinstance(feed_entries, dict):  # a single entry arrives as an object
            feed_entries = [feed_entries]
        page_reviews = [e for e in feed_entries if "im:rating" in e]
        if not page_reviews:
            return
        yield from page_reviews


def _find_reviews(node):
    """Review objects ({contents, rating, date, ...}) anywhere in the page's embedded data."""
    if isinstance(node, dict):
        if {"contents", "rating", "date"} <= node.keys():
            yield node
            return
        for value in node.values():
            yield from _find_reviews(value)
    elif isinstance(node, list):
        for value in node:
            yield from _find_reviews(value)


def _web_reviews(entry: dict, http) -> list[dict]:
    resp = http.get(WEB_PAGE.format(country=config.APP_STORE_COUNTRY, app_id=entry["app_id"]))
    match = _SERVER_DATA.search(http.text_of(resp)) if resp.status_code == 200 else None
    if not match:
        return []
    try:
        return list(_find_reviews(json.loads(match.group(1))))
    except ValueError:
        return []


def fetch(entries, http):
    for entry in entries:
        try:
            reviews = list(_feed_reviews(entry, http))
            kind = "review"
            if not reviews:
                reviews = _web_reviews(entry, http)
                kind = "review_web"
                log.warning("App Store %s: RSS feed empty, using the web page (%d newest reviews)",
                            entry["app"], len(reviews))
        except requests.RequestException as exc:
            log.error("App Store %s failed: %s", entry["app"], exc)
            continue
        log.info("App Store %s: %d reviews", entry["app"], len(reviews))
        for review in reviews:
            yield raw_item(SOURCE, entry, review, url=entry["url"], kind=kind)


def normalise(item):
    payload = item["payload"]
    if item["kind"] == "review_web":
        title, content, when = payload.get("title", ""), payload.get("contents", ""), payload.get("date")
    else:
        title, content, when = _label(payload, "title"), _label(payload, "content"), _label(payload, "updated")
    title, content = title.strip(), content.strip()
    text = f"{title}\n\n{content}" if title and title.lower() not in content.lower() else content
    yield {
        "app": item["entry"]["app"],
        "url": item["url"],
        "date": to_iso_date(when),
        "doc_type": "review",
        "text": text,
    }
