"""One HTTP session shared by every loader: polite delay per host, retries with backoff.

Log lines print URLs without their query string, so an API key passed as a parameter
(YouTube) never reaches the console.
"""
from __future__ import annotations

import logging
import time
from urllib.parse import urlparse

import requests

from src import config

log = logging.getLogger(__name__)

RETRY_STATUSES = (429, 500, 502, 503, 504)


def safe_url(url: str) -> str:
    """The URL without its query string, for logging."""
    return urlparse(url)._replace(query="").geturl()


def _retry_after(resp: requests.Response) -> float | None:
    value = resp.headers.get("Retry-After", "")
    return min(float(value), 120.0) if value.isdigit() else None


class Http:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": config.USER_AGENT, "Accept-Language": "en-IN,en;q=0.9"}
        )
        self._last_call: dict[str, float] = {}

    def _wait_turn(self, url: str, delay: float) -> None:
        host = urlparse(url).netloc
        elapsed = time.monotonic() - self._last_call.get(host, 0.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_call[host] = time.monotonic()

    def get(
        self,
        url: str,
        *,
        params: dict | None = None,
        headers: dict | None = None,
        delay: float | None = None,
        max_retries: int | None = None,
        backoff: float | None = None,
        retry_statuses: tuple[int, ...] = RETRY_STATUSES,
    ) -> requests.Response:
        delay = config.HTTP_DELAY_SECONDS if delay is None else delay
        retries = config.HTTP_MAX_RETRIES if max_retries is None else max_retries
        backoff = config.HTTP_BACKOFF_SECONDS if backoff is None else backoff

        for attempt in range(retries + 1):
            self._wait_turn(url, delay)
            try:
                resp = self.session.get(
                    url, params=params, headers=headers, timeout=config.HTTP_TIMEOUT_SECONDS
                )
            except requests.RequestException as exc:
                if attempt == retries:
                    raise
                wait = backoff * 2**attempt
                log.warning("%s on %s, retrying in %.0fs", type(exc).__name__, safe_url(url), wait)
                time.sleep(wait)
                continue
            if resp.status_code in retry_statuses and attempt < retries:
                wait = _retry_after(resp) or backoff * 2**attempt
                log.warning("HTTP %s from %s, retrying in %.0fs", resp.status_code, safe_url(url), wait)
                time.sleep(wait)
                continue
            return resp
        raise RuntimeError("unreachable")  # pragma: no cover

    def get_json(self, url: str, **kwargs):
        resp = self.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def text_of(resp: requests.Response) -> str:
        """Decode HTML with a better guess than requests' ISO-8859-1 default."""
        if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
            resp.encoding = resp.apparent_encoding
        return resp.text
