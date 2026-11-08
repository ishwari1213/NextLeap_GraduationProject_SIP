"""The answer step (PRD FR-9 to FR-14): evidence bundle -> a short, checked answer.

1. Out-of-scope bundles get a fixed, polite reply; they never reach the model (FR-13).
2. Otherwise Mistral answers the question directly in at most 4 plain sentences, from the
   routed section's numbers and the retrieved excerpts only, and picks 2-3 excerpts to quote
   (FR-9, FR-10). Post counts and sample sizes stay out of the answer unless the question asks
   how many; the site shows them with the evidence instead.
3. Guardrail (FR-11): every number in the answer must appear in the evidence, quotes must be
   retrieved excerpts, and advice wording is not allowed. On failure the model gets one retry
   with the problems listed; if that fails too, a plain evidence summary is shown instead.
4. Confidence: the model proposes High / Medium / Low with a reason; it is capped at Low for
   insufficient evidence and at Medium when fewer than 15 posts support the answer.

Whatever shape the model returns (text, a list, a nested object), it is turned into plain text
before the checks, and `answer()` never raises: anything unexpected falls back to the summary.
"""
from __future__ import annotations

import logging
import re

from src import config
from src.llm import LLMError, chat_json

log = logging.getLogger(__name__)

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

Answer the question directly, in 2 to 4 short plain sentences, the way you would explain it to a product
manager. Explain the reasons in words. Do not mention post counts, sample sizes, percentages or excerpt ids
unless the question asks how many or how often; if you do use a number, it must appear above with its own label.
Do not talk about the evidence, the excerpts or the quotes themselves; just answer.
{extra}No markdown, no bullet points, no headings. Use only this evidence.
Pick 2 or 3 excerpt ids that best support the answer.
Rate confidence: High (many posts agree), Medium (some support), Low (thin or mixed evidence), with one short reason.

Return JSON where "answer" is ONE plain-text string (never a list or an object):
{{"answer": "...", "quote_ids": ["E1", "E2"], "confidence": "High|Medium|Low", "confidence_reason": "..."}}"""

SEGMENT_SECTIONS = ("segments", "first-time")
SEGMENT_NOTE = ("Compare the groups in sentences (for example first-time vs experienced, salaried vs students), "
                "using the section data only. Name the groups in words and never number them (no \"Segment 1\"). "
                "Do not treat journey stages as segments.\n")
COUNT_QUESTION = re.compile(r"\b(how many|how often|how much|number of|count|percentage|what share)\b", re.I)
COUNT_PHRASE = re.compile(r"\s*\((?:n\s*=\s*\d[\d,]*|(?!(?:19|20)\d{2}\))\d[\d,]*|\d[\d,]*\s+(?:of\s+\d[\d,]*\s+)?"
                          r"(?:[a-z-]+\s+)?(?:posts?|reviews?|mentions?|comments?))\)", re.I)


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
    numbers = section.get("key_numbers") or {}
    pool += [str(v) for v in numbers.values()] + list(numbers)  # labels too: "25 to 44 (age)" names an age group
    pool += [section.get("text", ""), str(bundle.get("supporting_items", "")), str(len(bundle.get("excerpts", [])))]
    return set().union(*(_numbers(p) for p in pool))


EXCERPT_REF = re.compile(r"\s*[\(\[]?\b(?:excerpts?\s+)?E\d+(?:\s*(?:,|and|&)\s*E\d+)*\b[\)\]]?", re.I)


def as_text(value) -> str:
    """The model's answer as plain text, whatever shape it came back in: text, a list, or a
    nested object such as {"first_time": "...", "experienced": "..."} (keys are dropped)."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = [as_text(v) for v in value.values()]
    elif isinstance(value, (list, tuple)):
        parts = [as_text(v) for v in value]
    else:
        return str(value)
    parts = [p.strip() for p in parts if p and p.strip()]
    return " ".join(p if p[-1] in ".!?" else p + "." for p in parts)


def normalise(result) -> dict:
    """The model's JSON with every field in the shape the checks expect."""
    result = result if isinstance(result, dict) else {"answer": result}
    ids = result.get("quote_ids") or []
    ids = [ids] if isinstance(ids, (str, int)) else ids if isinstance(ids, (list, tuple)) else []
    ids = [f"E{i}" if isinstance(i, int) else str(i).strip() for i in ids if isinstance(i, (str, int))]
    return {"answer": as_text(result.get("answer")), "quote_ids": ids,
            "confidence": as_text(result.get("confidence")).strip().capitalize() or "Low",
            "confidence_reason": as_text(result.get("confidence_reason"))}


def tidy(text: str) -> str:
    """Plain text for display: no excerpt ids, no markdown emphasis, single spaces."""
    text = EXCERPT_REF.sub("", as_text(text).replace("**", "").replace("__", ""))
    return re.sub(r"\s+([.,;:])", r"\1", re.sub(r"\s{2,}", " ", text)).strip()


def drop_counts(text: str, question: str) -> str:
    """Remove "(451 posts)"-style counts, unless the question asks how many: the answer should
    read as an answer, and the counts are shown with the evidence."""
    if COUNT_QUESTION.search(question or ""):
        return text
    return re.sub(r"\s+([.,;:])", r"\1", COUNT_PHRASE.sub("", text)).strip()


def check(answer: dict, bundle: dict) -> list[str]:
    """Guardrail problems with an answer; empty when it passes."""
    problems = []
    text = tidy(answer.get("answer"))
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
    extra = SEGMENT_NOTE if (bundle.get("route") or {}).get("section") in SEGMENT_SECTIONS else ""
    messages = [{"role": "system", "content": SYSTEM},
                {"role": "user", "content": PROMPT.format(question=bundle["question"], status_note=note,
                                                          section=section_text, excerpts=excerpts, extra=extra)}]
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
        result = normalise(chat_json(_messages(bundle), model=config.ANSWER_MODEL, max_tokens=600))
        problems = check(result, bundle)
        if problems:
            guard["retried"] = True
            result = normalise(chat_json(_messages(bundle, problems), model=config.ANSWER_MODEL, max_tokens=600))
            problems = check(result, bundle)
        guard["problems"] = problems
        guard["passed"] = not problems
    except LLMError as exc:
        guard["problems"] = [str(exc)]
    except Exception as exc:  # an unexpected reply must not break the page: fall back to the summary
        log.exception("Answer step failed")
        guard["problems"] = [f"unexpected error: {exc}"]

    if guard["passed"]:
        ids = [q for q in result["quote_ids"] if re.fullmatch(r"E\d+", q)]
        quotes = [_quote(excerpts[int(q[1:]) - 1]) for q in ids if 0 < int(q[1:]) <= len(excerpts)][:3]
        text = drop_counts(tidy(result["answer"]), bundle.get("question", ""))
        return {**base, "text": _first_sentences(text), "quotes": quotes,
                "confidence": _cap_confidence(result["confidence"], bundle),
                "confidence_reason": result["confidence_reason"], "links": [], "guardrail": guard}

    # fallback: a plain summary of the evidence, nothing the evidence does not say
    guard["fallback"] = True
    lead = "A short written answer could not be checked against the evidence, so here are the most relevant posts:"
    return {**base, "text": lead, "quotes": [_quote(e) for e in excerpts[:3]], "confidence": "Low",
            "confidence_reason": "Shown as a plain evidence summary because a written answer did not pass the checks.",
            "links": [], "guardrail": guard}
