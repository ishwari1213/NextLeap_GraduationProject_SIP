"""Reddit posts and comments.

Uses the official Reddit API (OAuth, application-only) when REDDIT_CLIENT_ID and
REDDIT_CLIENT_SECRET are set; otherwise the Arctic Shift research archive, which needs no
sign-up (PRD appendix, "Alternatives for blocked sources"). Both return Reddit-shaped
JSON, so one comment walker and one normaliser serve both.
"""
from __future__ import annotations

import logging

import requests

from src import config
from src.phase1_data_loading.http_client import RETRY_STATUSES, Http
from src.phase1_data_loading.loaders.common import raw_item, to_iso_date

SOURCE = "reddit"
log = logging.getLogger(__name__)

REMOVED = {"[deleted]", "[removed]", ""}


class ArcticShift:
    BASE = "https://arctic-shift.photon-reddit.com/api"
    # Arctic Shift answers 422 "Timeout. Maybe slow down a bit" when busy.
    RETRY = (*RETRY_STATUSES, 422)

    def __init__(self, http: Http):
        self.http = http

    def _get(self, path: str, params: dict):
        return self.http.get_json(
            f"{self.BASE}/{path}", params=params,
            delay=config.ARCTIC_SHIFT_DELAY_SECONDS, retry_statuses=self.RETRY,
        ).get("data") or []

    def search_posts(self, subreddit: str, query: str) -> list[dict]:
        return self._get("posts/search", {"subreddit": subreddit, "query": query, "limit": config.REDDIT_MAX_POSTS})

    def get_posts(self, ids: list[str]) -> list[dict]:
        return self._get("posts/ids", {"ids": ",".join(ids)})

    def get_comments(self, post_id: str) -> list[dict]:
        return self._get("comments/tree", {"link_id": post_id, "limit": config.REDDIT_COMMENTS_LIMIT})


class RedditAPI:
    TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
    BASE = "https://oauth.reddit.com"

    def __init__(self, http: Http, client_id: str, client_secret: str):
        self.http = http
        resp = http.session.post(
            self.TOKEN_URL, auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"}, timeout=config.HTTP_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        self.headers = {"Authorization": f"bearer {resp.json()['access_token']}"}

    def _get(self, path: str, params: dict):
        return self.http.get_json(f"{self.BASE}/{path}", params={**params, "raw_json": 1}, headers=self.headers)

    def search_posts(self, subreddit: str, query: str) -> list[dict]:
        data = self._get(f"r/{subreddit}/search", {"q": query, "restrict_sr": 1, "sort": "new",
                                                    "limit": min(config.REDDIT_MAX_POSTS, 100)})
        return [c["data"] for c in data["data"]["children"]]

    def get_posts(self, ids: list[str]) -> list[dict]:
        data = self._get("api/info", {"id": ",".join(f"t3_{i}" for i in ids)})
        return [c["data"] for c in data["data"]["children"]]

    def get_comments(self, post_id: str) -> list[dict]:
        data = self._get(f"comments/{post_id}", {"limit": config.REDDIT_COMMENTS_LIMIT})
        return data[1]["data"]["children"]


def walk_comments(things: list[dict]):
    """Every comment in a Reddit-shaped tree, depth first, without its nested replies."""
    for thing in things or []:
        if thing.get("kind") != "t1":
            continue  # "more" stubs carry no text
        data = thing.get("data", {})
        yield {k: v for k, v in data.items() if k != "replies"}
        replies = data.get("replies")
        if isinstance(replies, dict):
            yield from walk_comments(replies.get("data", {}).get("children", []))


def _client(http: Http):
    if config.REDDIT_CLIENT_ID and config.REDDIT_CLIENT_SECRET:
        log.info("Reddit: using the official API")
        return RedditAPI(http, config.REDDIT_CLIENT_ID, config.REDDIT_CLIENT_SECRET)
    log.info("Reddit: no API credentials, using the Arctic Shift archive")
    return ArcticShift(http)


def fetch(entries, http):
    client = _client(http)
    posts: dict[str, tuple[dict, dict]] = {}
    for entry in entries:
        try:
            if entry.get("kind") == "post":
                found = client.get_posts([entry["post_id"]])
            else:
                found = client.search_posts(entry["platform"], entry["query"])
        except (requests.RequestException, ValueError, KeyError) as exc:
            log.error("Reddit %s failed: %s", entry["url"], exc)
            continue
        for post in found:
            posts.setdefault(post["id"], (post, entry))
    log.info("Reddit: %d posts", len(posts))

    for post_id, (post, entry) in posts.items():
        permalink = post.get("permalink", f"/comments/{post_id}/")
        yield raw_item(SOURCE, entry, post, url=f"https://www.reddit.com{permalink}", kind="post")
        try:
            comments = list(walk_comments(client.get_comments(post_id)))
        except (requests.RequestException, ValueError, KeyError, IndexError) as exc:
            log.error("Reddit comments for %s failed: %s", post_id, exc)
            continue
        for comment in comments:
            link = comment.get("permalink") or f"{permalink.rstrip('/')}/{comment.get('id')}/"
            yield raw_item(SOURCE, entry, comment, url=f"https://www.reddit.com{link}", kind="comment")


def normalise(item):
    payload = item["payload"]
    if item["kind"] == "post":
        body = payload.get("selftext") or ""
        body = "" if body in REMOVED else body
        text = f"{payload.get('title', '')}\n\n{body}".strip()
        doc_type = "post"
    else:
        text = payload.get("body") or ""
        if text in REMOVED:
            return
        doc_type = "comment"
    yield {
        "app": None,
        "url": item["url"],
        "date": to_iso_date(payload.get("created_utc")),
        "doc_type": doc_type,
        "text": text,
    }
