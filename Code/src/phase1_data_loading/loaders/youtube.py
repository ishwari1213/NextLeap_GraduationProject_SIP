"""YouTube comments through the YouTube Data API v3 (needs YOUTUBE_API_KEY).

A search entry finds videos, then reads each video's comment threads (top-level comments
plus the replies the API includes). The key travels as a query parameter, so this module
checks status codes itself and never logs a full request URL or exception text.
"""
from __future__ import annotations

import logging

import requests

from src import config
from src.phase1_data_loading.loaders.common import raw_item, to_iso_date

SOURCE = "youtube"
log = logging.getLogger(__name__)

API = "https://www.googleapis.com/youtube/v3"


def skip_reason() -> str | None:
    return None if config.YOUTUBE_API_KEY else "YOUTUBE_API_KEY not set in Code/.env"


def _get(http, path: str, params: dict) -> dict | None:
    try:
        resp = http.get(f"{API}/{path}", params={**params, "key": config.YOUTUBE_API_KEY})
    except requests.RequestException as exc:
        log.error("YouTube %s request failed (%s)", path, type(exc).__name__)
        return None
    if resp.status_code != 200:  # 403 also means comments are disabled on that video
        log.warning("YouTube %s returned HTTP %s", path, resp.status_code)
        return None
    return resp.json()


def _comments(http, video_id: str):
    page_token, count = None, 0
    while count < config.YOUTUBE_MAX_COMMENTS_PER_VIDEO:
        params = {"part": "snippet,replies", "videoId": video_id, "maxResults": 100, "textFormat": "plainText"}
        if page_token:
            params["pageToken"] = page_token
        data = _get(http, "commentThreads", params)
        if not data:
            return
        for thread in data.get("items", []):
            top = thread.get("snippet", {}).get("topLevelComment", {})
            yield top
            count += 1
            for reply in thread.get("replies", {}).get("comments", []):
                yield reply
                count += 1
        page_token = data.get("nextPageToken")
        if not page_token:
            return


def fetch(entries, http):
    if skip_reason():
        return
    for entry in entries:
        found = _get(http, "search", {
            "part": "snippet", "q": entry["query"], "type": "video",
            "maxResults": min(config.YOUTUBE_MAX_VIDEOS, 50), "regionCode": "IN", "relevanceLanguage": "en",
        })
        videos = (found or {}).get("items", [])
        log.info("YouTube search %r: %d videos", entry["query"], len(videos))
        for video in videos:
            video_id = video.get("id", {}).get("videoId")
            if not video_id:
                continue
            title = video.get("snippet", {}).get("title", "")
            for comment in _comments(http, video_id):
                payload = {**comment, "video_id": video_id, "video_title": title}
                url = f"https://www.youtube.com/watch?v={video_id}&lc={comment.get('id', '')}"
                yield raw_item(SOURCE, entry, payload, url=url, kind="comment")


def normalise(item):
    snippet = item["payload"].get("snippet", {})
    yield {
        "app": None,
        "url": item["url"],
        "date": to_iso_date(snippet.get("publishedAt")),
        "doc_type": "comment",
        "text": snippet.get("textOriginal") or snippet.get("textDisplay") or "",
    }
