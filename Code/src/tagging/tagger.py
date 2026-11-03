"""FR-5 tagging: Mistral labels each post with the fields in taxonomy.py.

Posts go to the model in batches of 20 with short numeric ids. The model returns only what
the text states: `about_sip` for every post, and, for SIP posts, just the fields that are
stated. Anything it leaves out is stored as not_stated / none, and any label outside the
allowed list is dropped and counted.

Which posts reach the model: every forum, Reddit and Team-BHP post (those threads are about
SIPs, but many replies are not), and app-store reviews that mention a SIP word (SIP_WORDS).
The other store reviews ("great app") are tagged about_sip = false by rule. Information
pages are context, not evidence, and are never tagged.
"""
from __future__ import annotations

import re

from src import config
from src.llm import chat_json
from src.tagging import taxonomy

SIP_WORDS = re.compile(
    r"\b(sips?|systematic|mutual\s*funds?|mfs?|mandates?|e-?mandate|nach|autopay|auto\s*pay|auto-?debit|"
    r"instal+ments?|nav|step[- ]?up|top[- ]?up|redeem\w*|redemption|elss|folio|amc|lump\s*sum|lumpsum|"
    r"monthly\s+invest\w*|debited)\b", re.IGNORECASE)
STORE_SOURCES = {"play_store", "app_store"}

SYSTEM = ("You label public posts and app reviews about SIP (systematic investment plan) investing in India for a "
          "research study. Label only what the text states; never guess or infer beyond it. Answer with JSON only.")

INSTRUCTIONS = """For each post, decide `about_sip`: true only if it discusses SIPs or mutual-fund instalments
(starting, paying, mandates or autopay, pausing, stopping, returns, controls, choosing where to run a SIP).
Stock trading, IPOs, F&O and generic app praise are false.

If about_sip is false, return only {{"id": <id>, "about_sip": false}}.
If about_sip is true, also include each field below that the text clearly states, with exactly one label from its
list. Leave a field out when it is not stated. failure_mode is the main SIP problem reported, if any.

Fields and labels:
{reference}

Return {{"posts": [ ... one object per post, with its id ... ]}}.

Posts:
{posts}"""


def route(record: dict) -> str:
    """'llm', 'rule' (store review without a SIP word) or 'skip' (information page)."""
    if record["source"] == "info_pages":
        return "skip"
    if record["source"] in STORE_SOURCES and not SIP_WORDS.search(record["text"]):
        return "rule"
    return "llm"


def rule_tags(record: dict) -> dict:
    return {"record_id": record["id"], "about_sip": False, **taxonomy.empty_tags(), "tagged_by": "rule",
            "prompt_version": config.TAG_PROMPT_VERSION}


def build_prompt(batch: list[dict]) -> list[dict]:
    posts = []
    for i, record in enumerate(batch, 1):
        text = " ".join(record["text"].split())[:config.TAG_MAX_CHARS]
        where = record["source"] + (f", {record['app']}" if record.get("app") else "")
        posts.append(f"{i}. [{where}] {text}")
    user = INSTRUCTIONS.format(reference=taxonomy.prompt_reference(), posts="\n".join(posts))
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def _items(response) -> list:
    """The list of post objects, whichever shape the model chose: {"posts": [...]}, a bare list,
    or another key holding the list."""
    if isinstance(response, list):
        return response
    if isinstance(response, dict):
        if isinstance(response.get("posts"), list):
            return response["posts"]
        lists = [v for v in response.values() if isinstance(v, list)]
        if lists:
            return lists[0]
        if "id" in response:
            return [response]
    return []


def parse(response, batch: list[dict]) -> tuple[list[dict], int]:
    """Tag rows for the posts the model answered, and the number of invalid labels dropped."""
    rows, invalid = [], 0
    by_id = {}
    for item in _items(response):
        if not isinstance(item, dict):
            continue
        try:
            by_id[int(item.get("id"))] = item
        except (TypeError, ValueError):
            continue
    for i, record in enumerate(batch, 1):
        item = by_id.get(i)
        if item is None:
            continue  # not answered: left untagged, retried on the next run
        about = item.get("about_sip") is True
        tags, bad = taxonomy.clean(item) if about else (taxonomy.empty_tags(), 0)
        invalid += bad
        rows.append({"record_id": record["id"], "about_sip": about, **tags, "tagged_by": "llm",
                     "model": config.TAGGING_MODEL, "prompt_version": config.TAG_PROMPT_VERSION})
    return rows, invalid


def tag_batch(batch: list[dict]) -> tuple[list[dict], int]:
    response = chat_json(build_prompt(batch), model=config.TAGGING_MODEL, max_tokens=3000)
    return parse(response, batch)
