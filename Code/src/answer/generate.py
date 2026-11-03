"""The answer step (PRD FR-9 to FR-14): evidence bundle -> a short, checked answer.

1. Out-of-scope bundles get a fixed, polite reply; they never reach the model (FR-13).
2. Otherwise Mistral writes at most 4 sentences from the routed section's numbers and the
   retrieved excerpts only, and picks 2-3 excerpts to quote (FR-9, FR-10).
3. Guardrail (FR-11): every number in the answer must appear in the evidence, quotes must be
   retrieved excerpts, and advice wording is not allowed. On failure the model gets one retry
   with the problems listed; if that fails too, a plain evidence summary is shown instead.
4. Confidence: the model proposes High / Medium / Low with a reason; it is capped at Low for
   insufficient evidence and at Medium when fewer than 15 posts support the answer.
"""
from __future__ import annotations

import re

from src import config
from src.llm import LLMError, chat_json

BADGES = {"evidence": "Evidence-grounded", "insufficient_evidence": "Insufficient evidence",
          "out_of_scope": "Out of scope"}
REFUSALS = {
    "investment_advice": "This is a research tool, not investment advice, so it does not recommend funds, SIPs or "
                         "actions. For scheme facts, see the official factsheet or the investor pages below.",
    "returns_or_projection": "This tool does not calculate, project or compare returns. For scheme facts, see the "
                             "official factsheet or the investor pages below.",
    "personal_data": "Please remove personal details (PAN, Aadhaar, account numbers, OTPs, phone numbers or emails) "
                     "and ask again. Nothing you typed was stored.",
    "individual": "This tool does not answer questions about individual people.",
    "off_topic": "This question is outside what the engine studies: how investors start, continue, pause and stop "
                 "SIPs.",
}
FOLLOW_UPS = ["Show quotes", "Break down by segment"]
QUOTE_WORDS = 25
ADVICE = re.compile(r"\b(you should (invest|buy|sell|stop|start)|we recommend|i recommend|best fund|safest)\b", re.I)
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

SYSTEM = ("You answer questions in a research tool about why investors start, continue, pause and stop SIPs. "
          "Use only the evidence given. Never give investment advice, name funds to buy, or calculate returns. "
          "Answer with JSON only.")

PROMPT = """Question: {question}

Evidence status: {status_note}

Section data (each label says what its number is):
{section}

Excerpts from public posts and reviews:
{excerpts}

Write an answer of at most 4 plain sentences (no markdown, no bullet points, no excerpt ids in the sentences),
using only this evidence. Every number you write must appear above, described with its own label exactly as
written (do not regroup counts under new headings).
Counts are mentions in public posts, not population percentages; say "posts", not "investors" or "%"
unless the evidence gives a percentage. Pick 2 or 3 excerpt ids that best support the answer.
Rate confidence: High (many posts agree), Medium (some support), Low (thin or mixed evidence), with one short reason.

Return {{"answer": "...", "quote_ids": ["E1", "E2"], "confidence": "High|Medium|Low", "confidence_reason": "..."}}"""


def _short(text: str) -> str:
    words = " ".join(text.split()).split()
    return " ".join(words[:QUOTE_WORDS]) + ("…" if len(words) > QUOTE_WORDS else "")


def _month(iso: str | None) -> str:
    from datetime import date
    try:
        return date.fromisoformat((iso or "")[:10]).strftime("%b %Y")
    except ValueError:
        return ""


def _quote(ex: dict) -> dict:
    return {"chunk_id": ex["chunk_id"], "text": _short(ex["text"]), "source": ex["source"], "app": ex.get("app"),
            "month": _month(ex.get("date"))}


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "").rstrip(".") for n in NUMBER.findall(text)}


def allowed_numbers(bundle: dict) -> set[str]:
    pool = [bundle.get("question", "")] + [e["text"] for e in bundle.get("excerpts", [])]
    section = bundle.get("section_data") or {}
    pool += [str(v) for v in (section.get("key_numbers") or {}).values()]
    pool += [section.get("text", ""), str(bundle.get("supporting_items", "")), str(len(bundle.get("excerpts", [])))]
    return set().union(*(_numbers(p) for p in pool))


EXCERPT_REF = re.compile(r"\s*[\(\[]?\b(?:excerpts?\s+)?E\d+(?:\s*(?:,|and|&)\s*E\d+)*\b[\)\]]?", re.I)


def tidy(text: str) -> str:
    """Plain text for display: no excerpt ids, no markdown emphasis, single spaces."""
    text = EXCERPT_REF.sub("", text.replace("**", "").replace("__", ""))
    return re.sub(r"\s+([.,;:])", r"\1", re.sub(r"\s{2,}", " ", text)).strip()


def check(answer: dict, bundle: dict) -> list[str]:
    """Guardrail problems with an answer; empty when it passes."""
    problems = []
    text = tidy(answer.get("answer") or "")
    if not text.strip():
        problems.append("the answer is empty")
    unsupported = sorted(_numbers(text) - allowed_numbers(bundle))
    if unsupported:
        problems.append("these numbers are not in the evidence: " + ", ".join(unsupported))
    ids = {f"E{i}" for i in range(1, len(bundle.get("excerpts", [])) + 1)}
    if not [q for q in answer.get("quote_ids", []) if q in ids]:
        problems.append("quote_ids must name excerpts E1 to E" + str(len(ids)))
    if ADVICE.search(text):
        problems.append("the answer contains advice wording")
    return problems


def _messages(bundle: dict, feedback: list[str] | None = None) -> list[dict]:
    section = bundle.get("section_data") or {}
    nums = section.get("key_numbers") or {}
    section_text = (f"{bundle.get('page_link') or section.get('title', '')}: " +
                    "; ".join(f"{k}: {v}" for k, v in nums.items())) if nums else "(no section numbers)"
    excerpts = "\n".join(f"E{i} [{e['source']}{', ' + e['app'] if e.get('app') else ''}, {_month(e.get('date'))}] "
                         f"{' '.join(e['text'].split())[:600]}" for i, e in enumerate(bundle.get("excerpts", []), 1))
    note = (f"{bundle.get('supporting_items', 0)} supporting posts" +
            ("; fewer than needed, so say the evidence is limited and what data would help"
             if bundle["status"] == "insufficient_evidence" else ""))
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": PROMPT.format(question=bundle["question"], status_note=note,
                                                          section=section_text, excerpts=excerpts)}]
    if feedback:
        messages.append({"role": "user", "content": "Your previous answer failed these checks: " + "; ".join(feedback)
                         + ". Rewrite it so every check passes."})
    return messages


def _cap_confidence(level: str, bundle: dict) -> str:
    level = level if level in ("High", "Medium", "Low") else "Low"
    if bundle["status"] == "insufficient_evidence":
        return "Low"
    if bundle.get("supporting_items", 0) < config.INSUFFICIENT_EVIDENCE_BELOW and level == "High":
        return "Medium"
    return level


def _first_sentences(text: str, k: int = 4) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return " ".join(parts[:k])


def answer(bundle: dict) -> dict:
    """The answer object for a bundle; always returns, never raises."""
    status = bundle["status"]
    base = {"badge": BADGES.get(status, status), "page_link": bundle.get("page_link"),
            "sample_size": f"n = {bundle.get('supporting_items', 0)} supporting posts",
            "follow_ups": [] if status == "out_of_scope" else FOLLOW_UPS}
    if status == "out_of_scope":
        return {**base, "text": REFUSALS.get(bundle.get("reason"), REFUSALS["off_topic"]), "quotes": [],
                "confidence": None, "confidence_reason": None, "links": bundle.get("decline_links", []),
                "guardrail": {"passed": True, "retried": False, "fallback": False, "model": None}}

    excerpts = bundle.get("excerpts", [])
    guard = {"passed": False, "retried": False, "fallback": False, "model": config.ANSWER_MODEL, "problems": []}
    result = None
    try:
        result = chat_json(_messages(bundle), model=config.ANSWER_MODEL, max_tokens=600)
        problems = check(result, bundle)
        if problems:
            guard["retried"] = True
            result = chat_json(_messages(bundle, problems), model=config.ANSWER_MODEL, max_tokens=600)
            problems = check(result, bundle)
        guard["problems"] = problems
        guard["passed"] = not problems
    except LLMError as exc:
        guard["problems"] = [str(exc)]

    if guard["passed"]:
        ids = [q for q in result.get("quote_ids", []) if re.fullmatch(r"E\d+", str(q))]
        quotes = [_quote(excerpts[int(q[1:]) - 1]) for q in ids if 0 < int(q[1:]) <= len(excerpts)][:3]
        return {**base, "text": _first_sentences(tidy(result["answer"])), "quotes": quotes,
                "confidence": _cap_confidence(result.get("confidence", "Low"), bundle),
                "confidence_reason": result.get("confidence_reason", ""), "links": [], "guardrail": guard}

    # fallback: a plain summary of the evidence, nothing the evidence does not say
    guard["fallback"] = True
    lead = (f"The engine found {bundle.get('supporting_items', 0)} supporting posts"
            + (f" for {bundle['page_link']}" if bundle.get("page_link") else "") + ". The most relevant ones say:")
    return {**base, "text": lead, "quotes": [_quote(e) for e in excerpts[:3]], "confidence": "Low",
            "confidence_reason": "Shown as a plain evidence summary because a written answer did not pass the checks.",
            "links": [], "guardrail": guard}
