"""Discourse forums (TradingQ&A, Jupiter community, madefortrade) through their JSON endpoints.

A topic is read page by page (`<topic>.json?page=N`, 20 posts a page). Discourse repeats
its last page when N runs past the end, so paging stops when a page adds no new post.
A search entry runs `/search.json` and then loads each matching topic in full.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests

from src import config
from src.phase1_data_loading.clean import html_to_text
from src.phase1_data_loading.loaders.common import raw_item, to_iso_date

SOURCE = "forums"
log = logging.getLogger(__name__)

# Quoted replies repeat another post's text; image captions add noise.
QUOTE_SELECTORS = ("aside.quote", ".lightbox-wrapper .meta")


def _base(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}"


def _topic_key(url: str) -> tuple[str, str]:
    return _base(url), url.rstrip("/").split("/")[-1]


def _fetch_topic(entry: dict, topic_url: str, http):
    topic_url = topic_url.rstrip("/")
    seen: set[int] = set()
    expected = None
    title = ""
    for page in range(1, config.FORUM_MAX_PAGES_PER_TOPIC + 1):
        data = http.get_json(f"{topic_url}.json", params={"page": page} if page > 1 else None)
        stream = data.get("post_stream", {})
        if expected is None:
            expected = len(stream.get("stream", [])) or data.get("posts_count", 0)
            title = data.get("title", "")
        new_posts = [p for p in stream.get("posts", []) if p.get("id") not in seen]
        if not new_posts:
            break
        for post in new_posts:
            seen.add(post["id"])
            payload = {
                "id": post.get("id"),
                "post_number": post.get("post_number"),
                "created_at": post.get("created_at"),
                "cooked": post.get("cooked", ""),
                "topic_id": data.get("id"),
                "topic_title": title,
                "topic_url": topic_url,
            }
            yield raw_item(SOURCE, entry, payload, url=f"{topic_url}/{post.get('post_number')}", kind="post")
        if expected and len(seen) >= expected:
            break
    log.info("Forum %s: %d posts from %s", entry["platform"], len(seen), topic_url)


def _search_topics(entry: dict, http) -> list[str]:
    base = _base(entry["url"])
    data = http.get_json(f"{base}/search.json", params={"q": entry["query"]})
    topics = data.get("topics", [])[: config.FORUM_SEARCH_MAX_TOPICS]
    log.info("Forum %s search %r: %d topics", entry["platform"], entry["query"], len(topics))
    return [f"{base}/t/{t['slug']}/{t['id']}" for t in topics if t.get("slug") and t.get("id")]


def fetch(entries, http):
    done: set[tuple[str, str]] = set()
    for entry in entries:
        try:
            topic_urls = [entry["url"]] if entry.get("kind", "topic") == "topic" else _search_topics(entry, http)
        except (requests.RequestException, ValueError) as exc:
            log.error("Forum search %s failed: %s", entry["url"], exc)
            continue
        for topic_url in topic_urls:
            key = _topic_key(topic_url)
            if key in done:
                continue
            done.add(key)
            try:
                yield from _fetch_topic(entry, topic_url, http)
            except (requests.RequestException, ValueError) as exc:
                log.error("Forum topic %s failed: %s", topic_url, exc)


def normalise(item):
    payload = item["payload"]
    text = html_to_text(payload.get("cooked", ""), drop_selectors=QUOTE_SELECTORS)
    first = payload.get("post_number") == 1
    if first and payload.get("topic_title"):
        text = f"{payload['topic_title']}\n\n{text}"
    yield {
        "app": None,
        "url": item["url"],
        "date": to_iso_date(payload.get("created_at")),
        "doc_type": "post" if first else "comment",
        "text": text,
    }
