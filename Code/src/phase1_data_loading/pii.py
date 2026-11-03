"""Strip personal data from text before it is stored (PRD FR-2, privacy NFR).

Removes emails, profile links, usernames and @handles, PAN, OTPs, Indian phone numbers,
Aadhaar numbers and account-like digit runs. Matches are replaced with a label such as
[PHONE] so the sentence still reads. Order matters: specific patterns run before the
broad digit-run pattern. Over-redaction (an order id caught as [ACCOUNT]) is accepted;
under-redaction is not.
"""
from __future__ import annotations

import re
from collections import Counter

# Brand and support handles are not personal data; keep them readable.
BRAND_HANDLES = {
    "groww", "growwapp", "groww_official", "zerodha", "zerodhaonline", "zerodhacoin",
    "paytmmoney", "upstox", "angelone", "angeloneofficial", "etmoney", "indmoney",
    "kotakmf", "kotakbankltd", "iciciprumf", "sundarammf", "nseindia", "bseindia",
    "sebi_updates", "amfiindia",
}

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PROFILE_LINK = re.compile(
    r"https?://(?:www\.|old\.|m\.)?(?:"
    r"reddit\.com/(?:u|user)/|youtube\.com/(?:@|channel/|c/|user/)|"
    r"(?:x|twitter)\.com/(?!search|i/|hashtag/)|instagram\.com/|facebook\.com/|linkedin\.com/in/"
    r")\S+",
    re.IGNORECASE,
)
_REDDIT_USER = re.compile(r"(?<![\w/])/?u/[A-Za-z0-9_-]{3,20}\b")
_HANDLE = re.compile(r"(?<![\w.@])@([A-Za-z0-9_.]{3,30})\b")
_PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", re.IGNORECASE)
_OTP = re.compile(r"\b(?:otp|one[- ]time password)\b[^\d\n]{0,20}\d{4,8}\b", re.IGNORECASE)
_PHONE = re.compile(r"(?<![\d+])(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)")
_AADHAAR = re.compile(r"(?<!\d)[2-9]\d{3}[\s-]?\d{4}[\s-]?\d{4}(?!\d)")
_ACCOUNT = re.compile(r"(?<!\d)\d{9,18}(?!\d)")


def strip_pii(text: str) -> tuple[str, Counter]:
    """Return the text with personal data replaced, and a count per kind replaced."""
    counts: Counter = Counter()

    def sub(label: str, pattern: re.Pattern, value: str) -> str:
        new, n = pattern.subn(f"[{label}]", value)
        counts[label] += n
        return new

    text = sub("EMAIL", _EMAIL, text)
    text = sub("PROFILE_LINK", _PROFILE_LINK, text)
    text = sub("USER", _REDDIT_USER, text)

    def handle(m: re.Match) -> str:
        if m.group(1).lower().rstrip(".") in BRAND_HANDLES:
            return m.group(0)
        counts["USER"] += 1
        return "[USER]"

    text = _HANDLE.sub(handle, text)
    text = sub("PAN", _PAN, text)

    def otp(m: re.Match) -> str:
        counts["OTP"] += 1
        return re.sub(r"\d{4,8}$", "[OTP]", m.group(0))

    text = _OTP.sub(otp, text)
    text = sub("PHONE", _PHONE, text)
    text = sub("AADHAAR", _AADHAAR, text)
    text = sub("ACCOUNT", _ACCOUNT, text)
    return text, +counts
