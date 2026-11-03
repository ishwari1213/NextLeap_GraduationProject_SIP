"""Helpers shared by the loaders.

A loader module exposes:
    SOURCE                  name of its Data/raw/<SOURCE>/ folder and the record's `source`
    fetch(entries, http)    yields raw items (see raw_item) for the active sources.yaml entries
    normalise(item)         yields partial records {"app", "url", "date", "doc_type", "text"}
    skip_reason()           optional: a reason the whole source cannot run (e.g. missing key)
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone

from src import config
from src.phase1_data_loading.http_client import Http

log = logging.getLogger(__name__)

WAYBACK_AVAILABLE = "https://archive.org/wayback/available"

# Author identity is never written to disk, not even in Data/raw/ (PRD: no usernames).
_IDENTITY_PARTS = ("author", "user", "avatar", "reviewer")
_IDENTITY_KEYS = {"name"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def drop_identity_fields(value):
    """Recursively remove author, user and avatar fields from an API payload."""
    if isinstance(value, dict):
        return {
            k: drop_identity_fields(v)
            for k, v in value.items()
            if k.lower() not in _IDENTITY_KEYS and not any(p in k.lower() for p in _IDENTITY_PARTS)
        }
    if isinstance(value, list):
        return [drop_identity_fields(v) for v in value]
    return value


def raw_item(source: str, entry: dict, payload: dict, *, url: str, kind: str) -> dict:
    """One line of Data/raw/<source>/<date>.jsonl."""
    return {
        "source": source,
        "kind": kind,
        "url": url,
        "fetched_at": now_iso(),
        "entry": entry,
        "payload": drop_identity_fields(payload),
    }


def to_iso_date(value) -> str | None:
    """YYYY-MM-DD from a datetime, a Unix timestamp or an ISO-like string."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (int, float)) or (isinstance(value, str) and re.fullmatch(r"\d+(\.\d+)?", value)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc).date().isoformat()
    if isinstance(value, str):
        match = re.match(r"(\d{4}-\d{2}-\d{2})", value)
        return match.group(1) if match else None
    return None


def wayback_fetch(http: Http, url: str) -> tuple[str, str, str] | None:
    """Latest Wayback Machine copy of url as (html, snapshot_timestamp, archive_url), or None."""
    avail = http.get_json(WAYBACK_AVAILABLE, params={"url": url})
    closest = (avail.get("archived_snapshots") or {}).get("closest") or {}
    if not closest.get("available"):
        log.warning("No Wayback copy of %s", url)
        return None
    timestamp = closest["timestamp"]
    archive_url = f"https://web.archive.org/web/{timestamp}id_/{url}"
    resp = http.get(
        archive_url,
        max_retries=config.WAYBACK_MAX_RETRIES,
        backoff=config.WAYBACK_BACKOFF_SECONDS,
    )
    if resp.status_code != 200:
        log.warning("Wayback copy of %s returned HTTP %s", url, resp.status_code)
        return None
    return Http.text_of(resp), timestamp, archive_url
