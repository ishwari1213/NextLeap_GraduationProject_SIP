"""Phase 1 unit tests: personal-data removal, cleaning, ids, each loader's normaliser and the
record build. All offline: payloads are small synthetic samples shaped like each source."""
import json

import pytest

from src.phase1_data_loading import clean, pii
from src.phase1_data_loading import run as phase1
from src.phase1_data_loading.loaders import app_store, discourse, info_pages, play_store, reddit, team_bhp, youtube
from src.phase1_data_loading.loaders.common import drop_identity_fields, to_iso_date


# --- personal data ----------------------------------------------------------------------

@pytest.mark.parametrize("raw, label, secret", [
    ("mail me at investor.one@gmail.com please", "EMAIL", "investor.one@gmail.com"),
    ("call +91 98765 43210 now", "PHONE", "98765 43210"),
    ("my number 9876543210", "PHONE", "9876543210"),
    ("PAN ABCDE1234F was rejected", "PAN", "ABCDE1234F"),
    ("aadhaar 2345 6789 0123 linked", "AADHAAR", "2345 6789 0123"),
    ("account 123456789012345 debited", "ACCOUNT", "123456789012345"),
    ("the OTP is 482913 but failed", "OTP", "482913"),
    ("thanks u/some_user for this", "USER", "some_user"),
    ("ping @rahul_k1990 about it", "USER", "rahul_k1990"),
    ("see https://www.reddit.com/user/someone123 here", "PROFILE_LINK", "someone123"),
])
def test_strip_pii_removes_each_kind(raw, label, secret):
    text, counts = pii.strip_pii(raw)
    assert secret not in text
    assert counts[label] >= 1


def test_strip_pii_keeps_ordinary_numbers_and_brand_handles():
    raw = "SIP of Rs 5000 on the 5th, NAV 123.45, date 2026-08-14, ref 20260814. Thanks @Groww"
    text, counts = pii.strip_pii(raw)
    assert text == raw
    assert not counts


# --- cleaning and ids -----------------------------------------------------------------

def test_html_to_text_keeps_paragraphs_and_drops_quotes():
    markup = "<aside class='quote'>someone else said this</aside><p>First <b>para</b>.</p><p>Second<br>line</p>"
    text = clean.normalise_whitespace(clean.html_to_text(markup, drop_selectors=("aside.quote",)))
    assert text == "First para.\n\nSecond\nline"


def test_finalise_builds_stable_id_and_strips_pii():
    partial = {"app": "Groww", "url": "u", "date": "2026-08-14", "doc_type": "review",
               "text": "  Instalment failed,   call 9876543210  "}
    first, counts = clean.finalise("play_store", partial, {})
    second, _ = clean.finalise("play_store", dict(partial), {})
    assert first["id"] == second["id"] and first["id"].startswith("play_store:groww:")
    assert first["text"] == "Instalment failed, call [PHONE]"
    assert counts["PHONE"] == 1
    assert set(first) == {"id", "source", "app", "url", "date", "doc_type", "text"}


def test_finalise_drops_empty_text_and_uses_platform_without_app():
    assert clean.finalise("reddit", {"doc_type": "comment", "text": "   "}, {})[0] is None
    record, _ = clean.finalise("reddit", {"doc_type": "comment", "text": "hi"}, {"platform": "IndiaInvestments"})
    assert record["id"].startswith("reddit:indiainvestments:")


def test_drop_identity_fields_is_recursive():
    payload = {"userName": "x", "content": "ok", "snippet": {"authorDisplayName": "y", "textOriginal": "t"},
               "author": {"name": "z"}, "name": "w", "items": [{"username": "q", "body": "b"}]}
    assert drop_identity_fields(payload) == {"content": "ok", "snippet": {"textOriginal": "t"}, "items": [{"body": "b"}]}


@pytest.mark.parametrize("value, expected", [
    ("2026-10-31T17:41:04", "2026-10-31"), (1636003810, "2021-11-04"), ("1636003810", "2021-11-04"),
    ("2025-03-22T09:31:06.000Z", "2025-03-22"), (None, None), ("not a date", None),
])
def test_to_iso_date(value, expected):
    assert to_iso_date(value) == expected


# --- loader normalisers -----------------------------------------------------------------

def _item(kind, payload, entry=None, url="https://example.com/x"):
    return {"source": "s", "kind": kind, "url": url, "fetched_at": "2026-11-01T10:00:00+00:00",
            "entry": entry or {}, "payload": payload}


def test_play_store_normalise():
    item = _item("review", {"content": "SIP debited twice", "at": "2026-10-31T17:41:04", "score": 1},
                 {"app": "Groww"})
    [rec] = play_store.normalise(item)
    assert rec == {"app": "Groww", "url": item["url"], "date": "2026-10-31", "doc_type": "review",
                   "text": "SIP debited twice"}


def test_app_store_normalise_joins_title_and_content():
    payload = {"title": {"label": "Autopay failed"}, "content": {"label": "Mandate keeps failing."},
               "updated": {"label": "2026-09-01T10:00:00-07:00"}, "im:rating": {"label": "1"}}
    [rec] = app_store.normalise(_item("review", payload, {"app": "Groww"}))
    assert rec["text"] == "Autopay failed\n\nMandate keeps failing."
    assert rec["date"] == "2026-09-01"


def test_app_store_normalise_web_page_review():
    payload = {"title": "Good for SIPs", "contents": "Easy to start a SIP.", "rating": 5,
               "date": "2026-08-18T13:45:51.000Z"}
    [rec] = app_store.normalise(_item("review_web", payload, {"app": "Groww"}))
    assert rec["text"] == "Good for SIPs\n\nEasy to start a SIP." and rec["date"] == "2026-08-18"


def test_app_store_finds_reviews_in_embedded_page_data():
    data = {"data": [{"shelf": {"items": [{"review": {"contents": "a", "rating": 4, "date": "2026-01-01",
                                                      "reviewerName": "someone"}}]}}]}
    [review] = app_store._find_reviews(data)
    assert review["contents"] == "a"
    assert "reviewerName" not in drop_identity_fields(review)


def test_discourse_normalise_first_post_and_reply():
    base = {"cooked": "<p>Mandate failed again</p>", "created_at": "2024-02-03T04:05:06Z",
            "topic_title": "Coin SIP vs AMC SIP"}
    [first] = discourse.normalise(_item("post", {**base, "post_number": 1}))
    [reply] = discourse.normalise(_item("post", {**base, "post_number": 2}))
    assert first["doc_type"] == "post" and first["text"].startswith("Coin SIP vs AMC SIP\n\n")
    assert reply["doc_type"] == "comment" and clean.normalise_whitespace(reply["text"]) == "Mandate failed again"


def test_reddit_walk_comments_and_skip_removed():
    tree = [{"kind": "t1", "data": {"id": "a", "body": "top", "replies": {"kind": "Listing", "data": {"children": [
        {"kind": "t1", "data": {"id": "b", "body": "[deleted]", "replies": ""}},
        {"kind": "more", "data": {}}]}}}}]
    comments = list(reddit.walk_comments(tree))
    assert [c["id"] for c in comments] == ["a", "b"] and "replies" not in comments[0]
    assert list(reddit.normalise(_item("comment", comments[1]))) == []
    [post] = reddit.normalise(_item("post", {"title": "Autopay mandate", "selftext": "[removed]", "created_utc": 1636003810}))
    assert post["text"] == "Autopay mandate" and post["date"] == "2021-11-04"


def test_team_bhp_normalise_parses_date_and_removes_quote():
    html = """<table id="post11"><tr><td class="thead">14th February 2025, 18:30</td></tr></table>
    <div id="post_message_11"><div><div class="smallfont">Quote:</div><table><tr><td>Originally Posted by x</td></tr></table></div>
    My own reply about SIP top-ups.</div>"""
    [rec] = team_bhp.normalise(_item("page", {"html": html, "snapshot_timestamp": "20250322093106"},
                                     url="https://www.team-bhp.com/forum/t.html"))
    assert rec["date"] == "2025-02-14"
    assert "Originally Posted" not in rec["text"] and "My own reply about SIP top-ups." in rec["text"]
    assert rec["url"].endswith("#post11")


def test_youtube_normalise():
    payload = {"snippet": {"textOriginal": "Good explainer", "publishedAt": "2026-05-06T07:08:09Z"}}
    [rec] = youtube.normalise(_item("comment", payload))
    assert rec["text"] == "Good explainer" and rec["date"] == "2026-05-06" and rec["doc_type"] == "comment"


ARTICLE = "<p>" + "A SIP invests a fixed amount every month. " * 10 + "</p>"


def test_info_pages_normalise_drops_page_chrome():
    html = (f"<html><body><nav><a>Menu</a><a>Login</a></nav><main><h1>What is SIP</h1>{ARTICLE}"
            "<script>x()</script></main><footer><p>Copyright</p></footer></body></html>")
    [rec] = info_pages.normalise(_item("page", {"html": html}, {"app": "Kotak"}))
    text = clean.normalise_whitespace(rec["text"])
    assert text.startswith("What is SIP\n\nA SIP invests") and "Login" not in text and "Copyright" not in text
    assert rec["doc_type"] == "info_page" and rec["date"] == "2026-11-01"


def test_info_pages_finds_content_wrapped_in_header_and_skips_menus():
    # kotak.bank.in wraps the whole page, article included, in <header>
    html = (f"<body><header><div class='banner'><p>Dear Customer, downtime on Sunday.</p></div>"
            f"<ul class='menu'><li><a>Stocks</a></li><li><a>Login</a></li></ul>"
            f"<section><h1>What is SIP</h1>{ARTICLE}</section></header></body>")
    [rec] = info_pages.normalise(_item("page", {"html": html}, {"app": "Kotak"}))
    text = clean.normalise_whitespace(rec["text"])
    assert text.startswith("What is SIP") and "Login" not in text and "Dear Customer" not in text


def test_info_pages_skips_pages_without_content():
    html = "<body><main><p>Dear Customer, downtime on Sunday.</p></main></body>"
    assert list(info_pages.normalise(_item("page", {"html": html}, {"app": "Kotak"}))) == []


# --- record build -------------------------------------------------------------------------

def test_build_records_dedupes_across_raw_files(tmp_path):
    folder = tmp_path / "play_store"
    folder.mkdir()
    line = json.dumps(_item("review", {"content": "Instalment failed", "at": "2026-10-01"}, {"app": "Groww"}))
    other = json.dumps(_item("review", {"content": "Autopay ok", "at": "2026-10-02"}, {"app": "Groww"}))
    (folder / "2026-10-30.jsonl").write_text(line + "\n", encoding="utf-8")
    (folder / "2026-10-31.jsonl").write_text(line + "\n" + other + "\n", encoding="utf-8")
    records, stats = phase1.build_records(tmp_path)
    assert len(records) == 2
    assert stats["duplicates"]["play_store"] == 1
    assert len({r["id"] for r in records}) == 2


def test_sources_yaml_has_a_loader_for_every_active_source():
    sources = phase1.load_sources()
    for name, entries in sources.items():
        if phase1.active(entries):
            assert name in phase1.LOADERS, name
    assert all(e["status"] == "dropped" for e in sources["x"])
