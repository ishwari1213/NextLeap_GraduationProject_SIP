"""Steps 1 and 2: questions that must never be searched.

1. Input check: a question carrying personal data (PAN, Aadhaar, account number, OTP, email,
   phone) is refused, and only a redacted copy is echoed back (PRD privacy rule).
2. Scope check: investment advice, fund picks, "safest SIP", return calculations or
   projections, and questions about a named individual are out of scope; the answer step
   declines them with an official link (PRD FR-13).

The rules are narrow on purpose. Discovery questions about returns ("what confuses investors
about returns?") stay in scope; only computing, projecting or comparing returns is refused.
Questions from the product team ("which opportunity should we solve first?") stay in scope;
"should I ..." asks for personal advice and is refused.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.phase1_data_loading.pii import BRAND_HANDLES, strip_pii

PII_KINDS = ("EMAIL", "PHONE", "PAN", "AADHAAR", "ACCOUNT", "OTP")

_FUNDISH = r"(?:sips?|mutual\s+funds?|funds?|schemes?|stocks?|portfolios?|elss|etfs?|index\s+funds?)"

_RULES: list[tuple[str, re.Pattern]] = [
    ("investment_advice", re.compile(p, re.IGNORECASE)) for p in (
        r"\bshould\s+i\b",
        r"\bsafest\b",
        r"\b(?:which|what)\s+(?:is\s+|are\s+)?(?:the\s+)?(?:best|safest|top|good|better|right)\b.*\b" + _FUNDISH + r"\b",
        r"\b(?:best|top\s*\d*|good|better)\s+" + _FUNDISH + r"\b(?!\s+(?:apps?|platforms?|brokers?))",
        r"\brecommend\w*\b.*\b" + _FUNDISH + r"\b",
        r"\bis\s+(?:it\s+)?(?:a\s+)?(?:good|safe|wise|right|worth)\b.*\b(?:invest\w*|" + _FUNDISH + r")\b",
        r"\b(?:is|are)\b.*\b(?:flexi\s*cap|small\s*cap|mid\s*cap|large\s*cap|index\s+fund|elss|etf)s?\b.*\b(?:good|safe|worth|better|best)\b",
    )
] + [
    ("returns_or_projection", re.compile(p, re.IGNORECASE)) for p in (
        r"\bhow\s+much\b.*\b(?:returns?|earn|get|grow|become|make|corpus|profit)\b",
        r"\b(?:expected|guaranteed|future|projected)\s+returns?\b",
        r"\breturns?\b.*\b(?:will|would)\s+(?:i|we|it)\b",
        r"\bwhat\s+returns?\b.*\b(?:get|give|expect)\b",
        r"\b(?:calculate|projection|forecast|predict)\w*\b",
        r"\b(?:cagr|xirr)\b",
        r"\b(?:highest|best|better|top)\s+returns?\b",
        r"\bcompare\b.*\breturns?\b",
        r"\bwill\s+(?:the\s+)?(?:market|nifty|sensex|nav|fund|stock)s?\b.*\b(?:go|rise|fall|crash|recover|grow)\b",
    )
] + [
    ("individual", re.compile(p, re.IGNORECASE)) for p in (
        r"(?<![\w/])/?u/[A-Za-z0-9_-]{3,}",
        r"\bwho\s+(?:wrote|posted|said|complained|reviewed|commented)\b",
        r"\b(?:user|reviewer|commenter|poster|author)\s+(?:named|called)\b",
    )
]
_HANDLE = re.compile(r"(?<![\w.@])@([A-Za-z0-9_.]{3,30})\b")


@dataclass
class ScopeResult:
    allowed: bool
    question: str               # safe to echo: personal data redacted
    reason: str | None = None   # personal_data | investment_advice | returns_or_projection | individual
    detail: str | None = None


def check_input(question: str) -> ScopeResult:
    redacted, counts = strip_pii(question)
    found = [kind for kind in PII_KINDS if counts.get(kind)]
    if found:
        return ScopeResult(False, redacted, "personal_data",
                           "Remove personal details (" + ", ".join(k.lower() for k in found) + ") and ask again.")
    return ScopeResult(True, question)


def check_scope(question: str) -> ScopeResult:
    for reason, pattern in _RULES:
        match = pattern.search(question)
        if match:
            return ScopeResult(False, question, reason, f"matched '{match.group(0)}'")
    for match in _HANDLE.finditer(question):
        if match.group(1).lower().rstrip(".") not in BRAND_HANDLES:
            return ScopeResult(False, question, "individual", f"matched '{match.group(0)}'")
    return ScopeResult(True, question)
