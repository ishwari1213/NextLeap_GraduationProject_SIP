"""Google Play reviews through the google-play-scraper library.

The PRD lists app IDs only; google-play-scraper is the chosen scraper (architecture
section 7). Developer replies stay in Data/raw/ but are not records: they are company
text, not investor evidence.

Per app, sources.yaml may set `count` (reviews per sort order, default
PLAY_STORE_REVIEWS_PER_APP) and `sorts` (default [newest]). "newest" alone covers only the
last few days for a busy app like Groww; adding "most_relevant" reaches older, longer
reviews. Repeats across sort orders collapse later, because a record's id is its text hash.
"""
from __future__ import annotations

import logging
from datetime import datetime

from src import config
from src.phase1_data_loading.loaders.common import raw_item, to_iso_date

SOURCE = "play_store"
log = logging.getLogger(__name__)


def _jsonable(review: dict) -> dict:
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in review.items()}


def fetch(entries, http):
    from google_play_scraper import Sort, reviews

    sorts = {"newest": Sort.NEWEST, "most_relevant": Sort.MOST_RELEVANT}
    for entry in entries:
        count = int(entry.get("count", config.PLAY_STORE_REVIEWS_PER_APP))
        if config.PLAY_STORE_REVIEWS_PER_APP < 100:  # quick mode caps per-app overrides too
            count = min(count, config.PLAY_STORE_REVIEWS_PER_APP)
        seen: set[str] = set()
        for sort_name in entry.get("sorts", ["newest"]):
            try:
                batch, _ = reviews(entry["app_id"], lang=config.PLAY_STORE_LANG, country=config.PLAY_STORE_COUNTRY,
                                   sort=sorts[sort_name], count=count)
            except Exception as exc:  # the scraper raises its own error types
                log.error("Play Store %s (%s, %s) failed: %s", entry["app"], entry["app_id"], sort_name, exc)
                continue
            fresh = [r for r in batch if r.get("reviewId") not in seen]
            seen.update(r.get("reviewId") for r in fresh)
            log.info("Play Store %s (%s): %d reviews, %d new", entry["app"], sort_name, len(batch), len(fresh))
            for review in fresh:
                yield raw_item(SOURCE, entry, _jsonable(review), url=entry["url"], kind="review")


def normalise(item):
    payload = item["payload"]
    yield {
        "app": item["entry"]["app"],
        "url": item["url"],
        "date": to_iso_date(payload.get("at")),
        "doc_type": "review",
        "text": payload.get("content") or "",
    }
