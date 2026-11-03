"""Turn a loader's partial record into a final record (architecture phase 1, steps 2 to 4).

    partial = {"app", "url", "date", "doc_type", "text"}   from a loader's normalise()
    record  = {"id", "source", "app", "url", "date", "doc_type", "text"}

Text is unescaped, stripped of HTML and invisible characters, whitespace-normalised
(paragraph breaks kept for chunking), then stripped of personal data. The id is
"<source>:<app or platform>:<hash of the stored text>", so the same text from the same
place always gets the same id and duplicates collapse.
"""
from __future__ import annotations

import hashlib
import html
import re
from collections import Counter

from bs4 import BeautifulSoup

from src.phase1_data_loading.pii import strip_pii

DOC_TYPES = {"review", "post", "comment", "info_page"}

_BLOCK_TAGS = [
    "p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "table",
    "blockquote", "section", "article", "pre", "dd", "dt",
]
_INVISIBLE = re.compile("[​-‏‪-‮⁠﻿]")
_SPACES = re.compile(r"[ \t\f\v]+")
_MANY_NEWLINES = re.compile(r"\n{3,}")


def html_to_text(markup: str, drop_selectors: tuple[str, ...] = ()) -> str:
    """Readable text from HTML: block elements become paragraphs, inline text stays joined."""
    soup = BeautifulSoup(markup, "lxml")
    for selector in ("script", "style", "noscript", "template", *drop_selectors):
        for el in soup.select(selector):
            el.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_after("\n\n")
    return soup.get_text()


def normalise_whitespace(text: str) -> str:
    text = html.unescape(text)
    text = _INVISIBLE.sub("", text).replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    lines = [_SPACES.sub(" ", line).strip() for line in text.split("\n")]
    return _MANY_NEWLINES.sub("\n\n", "\n".join(lines)).strip()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "unknown"


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def finalise(source: str, partial: dict, entry: dict) -> tuple[dict | None, Counter]:
    """Clean one partial record. Returns (record, pii_counts); record is None if no text is left."""
    text = normalise_whitespace(partial.get("text") or "")
    text, pii_counts = strip_pii(text)
    if not text:
        return None, pii_counts

    app = partial.get("app") or entry.get("app")
    owner = app or entry.get("platform") or source
    doc_type = partial.get("doc_type")
    if doc_type not in DOC_TYPES:
        raise ValueError(f"unknown doc_type {doc_type!r} from {source}")

    record = {
        "id": f"{source}:{slug(owner)}:{text_hash(text)}",
        "source": source,
        "app": app,
        "url": partial.get("url") or entry.get("url"),
        "date": partial.get("date"),
        "doc_type": doc_type,
        "text": text,
    }
    return record, pii_counts
