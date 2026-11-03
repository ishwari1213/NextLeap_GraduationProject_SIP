"""Minimal Mistral chat client shared by tagging (FR-5) and the answer step (FR-9).

JSON mode only, temperature 0. A process-wide limiter keeps requests under the account's
per-minute limit (30 requests/minute on this key), and 429/5xx answers are retried with
backoff. The key comes from Code/.env (MISTRAL_API_KEY) and is never logged.
"""
from __future__ import annotations

import json
import logging
import threading
import time

import requests

from src import config

log = logging.getLogger(__name__)

API_URL = "https://api.mistral.ai/v1/chat/completions"


class LLMError(RuntimeError):
    pass


class _Limiter:
    def __init__(self, per_minute: int):
        self.interval = 60.0 / per_minute
        self.lock = threading.Lock()
        self.next_at = 0.0

    def wait(self) -> None:
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_at)
            self.next_at = start + self.interval
        if start > now:
            time.sleep(start - now)


_limiter = _Limiter(config.MISTRAL_REQUESTS_PER_MINUTE)
usage = {"requests": 0, "prompt_tokens": 0, "completion_tokens": 0}
_usage_lock = threading.Lock()


def chat_json(messages: list[dict], *, model: str, max_tokens: int = 2000, retries: int = 4) -> dict:
    """One JSON-mode chat completion, parsed. Raises LLMError when it cannot get valid JSON."""
    if not config.MISTRAL_API_KEY:
        raise LLMError("MISTRAL_API_KEY is not set in Code/.env")
    body = {"model": model, "messages": messages, "temperature": 0, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"}}
    headers = {"Authorization": f"Bearer {config.MISTRAL_API_KEY}"}
    for attempt in range(retries + 1):
        _limiter.wait()
        try:
            resp = requests.post(API_URL, json=body, headers=headers, timeout=120)
        except requests.RequestException as exc:
            if attempt == retries:
                raise LLMError(f"request failed: {type(exc).__name__}") from exc
            time.sleep(5 * 2**attempt)
            continue
        if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries:
            wait = float(resp.headers.get("Retry-After", 0) or 0) or 5 * 2**attempt
            log.warning("Mistral HTTP %s, retrying in %.0fs", resp.status_code, wait)
            time.sleep(min(wait, 90))
            continue
        if resp.status_code != 200:
            raise LLMError(f"Mistral HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        with _usage_lock:
            usage["requests"] += 1
            usage["prompt_tokens"] += data.get("usage", {}).get("prompt_tokens", 0)
            usage["completion_tokens"] += data.get("usage", {}).get("completion_tokens", 0)
        content = data["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except ValueError:
            if attempt == retries:
                raise LLMError("model did not return valid JSON")
    raise LLMError("unreachable")
