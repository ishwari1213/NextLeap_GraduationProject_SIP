"""Split cleaned records into excerpts the embedding model reads whole (architecture phase 2).

Rules
  * A record of at most 254 word pieces (256 minus [CLS] and [SEP]) becomes one excerpt,
    unchanged. That covers almost every review, comment and short post.
  * A longer record (long post, information page) is cut into sentences, keeping its
    paragraph and line breaks; the sentences are packed into excerpts of about 200 word
    pieces, and each excerpt after the first repeats up to about 40 word pieces of whole
    sentences from the end of the one before, so an idea split across a boundary stays
    findable.
  * A single sentence longer than 200 word pieces is cut into token windows at word
    boundaries, using the tokenizer's character offsets so the original text (capitals
    included) is kept.

Sizes are counted in the embedding model's own word pieces, because the model silently
drops everything past its limit.
"""
from __future__ import annotations

import re
from typing import Protocol

SPECIAL_TOKENS = 2  # [CLS] and [SEP], added by the model to every input

_SENTENCE_END = re.compile(r"(?<=[.!?।])\s+")


class TokenCounter(Protocol):
    def count(self, texts: list[str]) -> list[int]: ...
    def windows(self, text: str, size: int, overlap: int) -> list[str]: ...


class WordPieceCounter:
    """Counts and cuts text in the embedding model's word pieces."""

    def __init__(self, model_name: str):
        from transformers import AutoTokenizer
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()
        try:  # use the cached copy without asking the Hugging Face hub; download only if missing
            self.tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
        except OSError:
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.tokenizer.model_max_length = 10**9  # we enforce our own limit; silence length warnings

    def count(self, texts: list[str]) -> list[int]:
        if not texts:
            return []
        return [len(ids) for ids in self.tokenizer(texts, add_special_tokens=False)["input_ids"]]

    def windows(self, text: str, size: int, overlap: int) -> list[str]:
        offsets = self.tokenizer(text, add_special_tokens=False, return_offsets_mapping=True)["offset_mapping"]
        n = len(offsets)
        max_back = max(1, size // 4)  # never shrink a window by more than a quarter to find a word break

        def joined(i: int) -> bool:
            """Token i continues a word: no gap before it, letters or digits on both sides.
            Punctuation runs ("......") may be cut anywhere."""
            if not (0 < i < n) or offsets[i][0] != offsets[i - 1][1]:
                return False
            return text[offsets[i - 1][1] - 1].isalnum() and text[offsets[i][0]].isalnum()

        pieces, start = [], 0
        while start < n:
            end = min(start + size, n)
            while end < n and end > max(start + 1, start + size - max_back) and joined(end):  # not mid-word
                end -= 1
            pieces.append(text[offsets[start][0]:offsets[end - 1][1]])
            if end == n:
                break
            nxt = max(end - overlap, start + 1)
            floor = max(start + 1, nxt - max_back)
            while nxt > floor and joined(nxt):  # do not start mid-word
                nxt -= 1
            start = nxt
        return pieces


def split_units(text: str) -> list[tuple[str, str]]:
    """Sentences of a text, each with the separator that came before it ("", " ", "\\n", "\\n\\n")."""
    units: list[tuple[str, str]] = []
    for paragraph in text.split("\n\n"):
        for line_no, line in enumerate(paragraph.split("\n")):
            sentences = [s.strip() for s in _SENTENCE_END.split(line) if s.strip()]
            for sent_no, sentence in enumerate(sentences):
                if not units:
                    sep = ""
                elif sent_no > 0:
                    sep = " "
                elif line_no > 0:
                    sep = "\n"
                else:
                    sep = "\n\n"
                units.append((sentence, sep))
    return units


def _join(units: list[tuple[str, str]], idxs: list[int]) -> str:
    first, *rest = idxs
    return units[first][0] + "".join(units[i][1] + units[i][0] for i in rest)


def pack(units: list[tuple[str, str]], counts: list[int], target: int, overlap: int) -> list[str]:
    """Greedy packing of sentences into excerpts of at most `target` word pieces, with overlap."""
    chunks: list[list[int]] = []
    current: list[int] = []
    size = 0
    for i, n in enumerate(counts):
        if current and size + n > target:
            chunks.append(current)
            carry: list[int] = []
            carried = 0
            for j in reversed(current):  # whole sentences from the end, up to `overlap`
                if carried + counts[j] > overlap:
                    break
                carry.insert(0, j)
                carried += counts[j]
            if carried + n > target:  # the overlap must not push the next excerpt over size
                carry, carried = [], 0
            current, size = carry, carried
        current.append(i)
        size += n
    if current:
        chunks.append(current)
    return [_join(units, idxs) for idxs in chunks]


def split_text(text: str, counter: TokenCounter, target: int, overlap: int) -> list[str]:
    """Excerpt texts for one long record.

    Ordinary sentences are packed together. A sentence longer than `target` is cut into
    overlapping windows that become excerpts of their own: packing them with each other would
    repeat their overlap inside one excerpt."""
    units = split_units(text)
    counts = counter.count([u for u, _ in units])
    chunks: list[str] = []
    run: list[tuple[str, str]] = []

    def flush() -> None:
        if run:
            chunks.extend(pack(run, counter.count([u for u, _ in run]), target, overlap))
            run.clear()

    for (unit, sep), n in zip(units, counts):
        if n <= target:
            run.append((unit, sep))
        else:
            flush()
            chunks.extend(counter.windows(unit, target, overlap))
    flush()
    return chunks


def chunk_records(records: list[dict], counter: TokenCounter, *, target: int, overlap: int,
                  max_tokens: int) -> list[dict]:
    """Excerpts for every record. `max_tokens` is the model limit including special tokens."""
    limit = max_tokens - SPECIAL_TOKENS
    sizes = counter.count([r["text"] for r in records])

    excerpts: list[dict] = []
    for record, size in zip(records, sizes):
        texts = [record["text"]] if size <= limit else split_text(record["text"], counter, target, overlap)
        for position, text in enumerate(texts):
            excerpts.append({
                "chunk_id": f"{record['id']}-{position}",
                "record_id": record["id"],
                "source": record["source"],
                "app": record.get("app"),
                "url": record["url"],
                "date": record.get("date"),
                "doc_type": record["doc_type"],
                "tags": [],  # filled by the tagging step (PRD FR-5)
                "text": text,
            })

    for excerpt, n in zip(excerpts, counter.count([e["text"] for e in excerpts])):
        excerpt["token_count"] = n
    return excerpts
