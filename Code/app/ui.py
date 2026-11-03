"""Page building blocks shared by every page, so readers learn one layout (UI spec section 2):
section tag, a title that states the page's message, one italic line saying what it answers,
stat tiles, cards, a Key insights panel, then a Source and limits line.

Every piece of text that comes from data is HTML-escaped before it is rendered.
"""
from __future__ import annotations

from html import escape

import streamlit as st

STYLE = """
<style>
.block-container {max-width: 1200px; padding-top: 1.4rem;}
.sde-banner {background:#e3f1ef; border:1px solid #b9dcd7; border-radius:12px; padding:14px 20px; margin:0 0 20px;}
.sde-banner b {display:block; margin-bottom:4px;}
.sde-tag {color:#0b6e69; font-weight:600; letter-spacing:.06em; text-transform:uppercase; font-size:.9rem;}
.sde-title {font-size:1.85rem; font-weight:750; line-height:1.25; color:#14213d; margin:.25rem 0 .35rem;}
.sde-answers {font-style:italic; color:#4a5a5a; margin:0 0 1.1rem;}
.sde-h {font-size:1.2rem; font-weight:700; color:#14213d; margin:1.4rem 0 .6rem;}
.sde-card {background:#fff; border:1px solid #e3ded3; border-radius:12px; padding:18px 20px; margin-bottom:14px;}
.sde-tile {background:#fff; border:1px solid #e3ded3; border-radius:12px; padding:16px 18px; min-height:150px;}
.sde-tile .label {color:#4a5a5a; font-size:.95rem;}
.sde-tile .value {font-size:2rem; font-weight:750; color:#14213d; margin:.35rem 0 .2rem;}
.sde-tile .caption {color:#4a5a5a; font-size:.9rem; line-height:1.4;}
.sde-nc {background:#fafaf7; border:1.5px dashed #cfc8ba; border-radius:12px; padding:16px 18px; margin-bottom:12px;}
.sde-nc .head {font-weight:700; color:#14213d; margin-bottom:4px;}
.sde-nc .why {color:#3d4b4b;}
.sde-nc .step {color:#5b6b6b; font-size:.9rem; margin-top:6px;}
.sde-pill {display:inline-block; padding:1px 10px; border-radius:999px; font-size:.78rem; font-weight:600;
           border:1px solid; margin-left:8px; vertical-align:middle;}
.pill-ok {color:#0b6e69; border-color:#0b6e69; background:#e3f1ef;}
.pill-warn {color:#7a4f00; border-color:#d9a441; background:#fdf3df;}
.pill-muted {color:#4d4d4d; border-color:#b5b5b5; background:#f1f1ee;}
.sde-insights {background:#fff; border:1px solid #e3ded3; border-left:5px solid #0b6e69; border-radius:12px;
               padding:14px 20px; margin:6px 0 12px;}
.sde-insights ul {margin:.3rem 0 0 1.1rem; padding:0;}
.sde-insights li {margin:.35rem 0;}
.sde-source {color:#5b6b6b; font-size:.9rem; margin:.3rem 0 1rem;}
.sde-steps {display:flex; flex-wrap:wrap; gap:10px; margin:.4rem 0 1rem;}
.sde-step {flex:1 1 150px; background:#fff; border:1px solid #e3ded3; border-radius:12px; padding:12px 14px;}
.sde-step .n {color:#0b6e69; font-weight:700; font-size:.85rem;}
.sde-step .t {font-weight:700; color:#14213d; margin:2px 0;}
.sde-step .v {color:#4a5a5a; font-size:.9rem;}
.sde-quote {border-left:3px solid #0b6e69; padding:4px 10px; margin:10px 0; font-size:.95rem; line-height:1.45;}
.sde-quote .meta {display:block; color:#5b6b6b; font-size:.8rem; margin-top:3px;}
.sde-footer {border-top:1px solid #e3ded3; margin-top:2.2rem; padding-top:.9rem; color:#5b6b6b; font-size:.88rem;}
</style>
"""


def css() -> None:
    st.markdown(STYLE, unsafe_allow_html=True)


def banner() -> None:
    st.markdown(
        '<div class="sde-banner"><b>Facts only. No investment advice.</b>'
        "A research prototype built from public posts and reviews about SIPs. It does not recommend funds, "
        "amounts or actions.</div>", unsafe_allow_html=True)


def page_header(tag: str, title: str, answers: str) -> None:
    st.markdown(f'<div class="sde-tag">{escape(tag)}</div><div class="sde-title">{escape(title)}</div>'
                f'<div class="sde-answers">Answers: {escape(answers)}</div>', unsafe_allow_html=True)


def heading(text: str) -> None:
    st.markdown(f'<div class="sde-h">{escape(text)}</div>', unsafe_allow_html=True)


def pill(label: str, kind: str = "muted") -> str:
    return f'<span class="sde-pill pill-{kind}">{escape(label)}</span>'


def stat_tiles(tiles: list[tuple[str, str, str]]) -> None:
    """(label, value, caption) per tile; a value of None renders as a Not computed tile."""
    for col, (label, value, caption) in zip(st.columns(len(tiles)), tiles):
        shown = escape(value) if value is not None else "⏳ Not yet computed"
        size = "" if value is not None else ' style="font-size:1.15rem"'
        col.markdown(f'<div class="sde-tile"><div class="label">{escape(label)}</div>'
                     f'<div class="value"{size}>{shown}</div><div class="caption">{escape(caption)}</div></div>',
                     unsafe_allow_html=True)


def not_computed(item: tuple[str, str, str]) -> None:
    title, why, step = item
    st.markdown(f'<div class="sde-nc"><div class="head">⏳ {escape(title)}{pill("Not computed")}</div>'
                f'<div class="why">{escape(why)}</div><div class="step">Missing step: {escape(step)}.</div></div>',
                unsafe_allow_html=True)


def insights(items: list[str], title: str = "Key insights") -> None:
    rows = "".join(f"<li>{escape(i)}</li>" for i in items)
    st.markdown(f'<div class="sde-insights"><b>{escape(title)}</b><ul>{rows}</ul></div>', unsafe_allow_html=True)


def source_note(text: str) -> None:
    st.markdown(f'<div class="sde-source"><b>Source and limits:</b> {escape(text)}</div>', unsafe_allow_html=True)


def steps(items: list[tuple[str, str]]) -> None:
    cells = "".join(f'<div class="sde-step"><div class="n">Step {i}</div><div class="t">{escape(t)}</div>'
                    f'<div class="v">{escape(v)}</div></div>' for i, (t, v) in enumerate(items, 1))
    st.markdown(f'<div class="sde-steps">{cells}</div>', unsafe_allow_html=True)


def card(markdown_text: str) -> None:
    st.markdown(f'<div class="sde-card">{markdown_text}</div>', unsafe_allow_html=True)


def footer(last_updated: str | None) -> None:
    st.markdown(
        '<div class="sde-footer">Research prototype. Not investment advice: no fund recommendations, return '
        "calculations or comparisons. For scheme facts see the official factsheet, AMFI or SEBI investor pages. "
        "Counts are mentions in public posts and reviews, not population percentages. "
        f"Last updated from sources: {escape(last_updated or 'unknown')}.</div>", unsafe_allow_html=True)


BLUE, ORANGE, GREY = "#0072B2", "#E69F00", "#999999"  # Okabe-Ito


def bars(rows: list[dict], title: str, caption: str = "", *, value: str = "n", label: str = "label",
         highlight: set[str] | None = None, value_format: str = ",") -> None:
    """Horizontal bars with a value label on each bar. Rows under 10 posts say "(low sample)" in their
    label, and highlighted rows are orange, so meaning never rests on colour alone."""
    import altair as alt
    import pandas as pd

    if not rows:
        st.caption(f"{title}: no posts state this yet.")
        return
    data = pd.DataFrame([{
        "Label": r[label] + (" (low sample)" if r.get("sample") == "low" else ""),
        "Value": r[value],
        "Group": "highlight" if highlight and r.get("key") in highlight else "base",
    } for r in rows])
    base = alt.Chart(data).encode(y=alt.Y("Label:N", sort=None, title=None), x=alt.X("Value:Q", title=None))
    chart = base.mark_bar().encode(
        color=alt.Color("Group:N", scale=alt.Scale(domain=["base", "highlight"], range=[BLUE, ORANGE]), legend=None),
        tooltip=["Label", alt.Tooltip("Value:Q", format=value_format)],
    ) + base.mark_text(align="left", dx=4, fontSize=13).encode(text=alt.Text("Value:Q", format=value_format))
    st.markdown(f"**{escape(title)}**")
    st.altair_chart(chart.properties(height=alt.Step(26)), width="stretch")
    if caption:
        st.caption(caption)


def tile_value(item: dict | None, *, share: bool = False) -> str | None:
    """'1,234' (or '1,234 · 12%') for a computed stat; None (Not computed) otherwise."""
    if not item or item.get("status") != "computed":
        return None
    text = f"{item['n']:,}"
    if share and item.get("share") is not None:
        text += f" · {item['share']:.0%}"
    return text


def low(item: dict | None) -> str:
    return " (low sample)" if item and item.get("sample") == "low" else ""


def not_computed_item(title: str, item: dict) -> None:
    not_computed((title, item.get("reason", ""), item.get("missing_step", "")))


def quote_cards(items: list[dict]) -> None:
    html = "".join(f'<div class="sde-quote">“{escape(q["text"])}”<span class="meta">{escape(q["source"])} · '
                   f'{escape(q["month"])}</span></div>' for q in items)
    st.markdown(html or '<div class="sde-source">No short quotes for this failure mode yet.</div>',
                unsafe_allow_html=True)


def survey_heading(survey: dict, title: str = "From the investor survey") -> None:
    heading(title)
    st.caption(survey.get("sample", {}).get("note", ""))


def not_ready(missing: list[str]) -> None:
    st.warning("The pipeline outputs this page needs are missing: " + ", ".join(missing)
               + ". Run phases 1 to 4 from the Code/ folder (see Docs/architecture.md, section 5).")
