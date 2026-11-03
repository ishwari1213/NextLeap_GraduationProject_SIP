# SIP Discovery Engine: Website UI Spec (for Cursor / Claude Code)

> Instruction to Claude Code: Read this whole file and the existing repo first. Work in **Plan mode**, show a plan (stack, files to create or change, data files, build order), then wait for approval. Do not change `data/raw/` or `data/uploads/`, and do not break the existing pipeline, chat backend (FastAPI on :8000) or Streamlit app (:8501).

## 1. What this website is

A public, read-only research site that shows **how the SIP Discovery Engine gathered, analysed and validated evidence about why first-time investors stop SIPs on Groww**, plus a research tool ("Ask the engine") that answers questions from that evidence.

Business metric: share of first-time investors with an active SIP 12 months after their first one (active = one successful instalment in the last 30 days).

A stranger should understand in two minutes: what was studied, what was found, how sure we are, and what to solve first.

### Hard rules
1. **6 pages only** (list in section 3), one sticky top nav, no extra pages.
2. **Every number comes from generated JSON files**, never hard-coded. If a value is not computed, show a "Not yet computed" card with the reason and the missing step. Never invent numbers.
3. No investment advice, no fund or stock recommendations, no return calculations or comparisons (link to the official factsheet, AMFI or SEBI pages). No fear, FOMO or urgency language. Disclaimer in the footer and in the research tool.
4. No usernames, personal data, links to private profiles or raw records. Quotes are de-identified, max 25 words, labelled with source and month only.
5. Counts are mentions in public posts and a small survey, **not population percentages**. Say so on the Overview and Method pages. Mark any figure under 10 posts "low sample".
6. Accessibility: colour-blind-safe palette (Okabe-Ito), never colour alone (labels, patterns, markers), body text 16px or more, charts readable on mobile, tables scroll sideways inside their own container.
7. Every page title is a sentence stating the page's key message, not a label.

## 2. Visual style (from the two reference sites)

Take the **structure** only, not the text or branding.
- Single clean light theme, one accent colour (teal `#0b6e69`), warm off-white background (`#f5f3ee`), white cards with a thin border.
- Page header: small section tag (e.g. "02 Journey"), then the message-title, then one italic sentence saying what the page answers.
- Content blocks: a row of 3 to 4 **stat tiles** (big number + label), then charts and tables inside cards, then a "Key insights" panel, then a "Source and limits" line. Charts always have a title that states the message, labelled axes, value labels, a one-line caption and a source note.
- Tags beside values: `Scored`, `Low sample`, `Not computed`, `Context only`.
- Keep the layout the same on every page so readers learn it once.

## 3. Pages (6) and what each one shows

### Page 1: Overview (`/overview`)
**Title:** "Reliable instalments are the highest-potential opportunity, but first-time evidence is thin"
**Answers:** Which opportunity should Groww solve first, and why? What unmet needs emerge?
- Stat tiles: 5,005 records from 7 sources · 1,240 SIP posts (37% of 3,310 posts) · 252 name a problem (20%) · 21 SIP investors surveyed.
- Metric tree (diagram): 12-month SIP continuation → A set-up works · B instalments keep succeeding · C understands progress and keeps confidence · D can adjust instead of quitting · E gets help when stuck. Each node shows its post count.
- Chart 1, horizontal bars: opportunity score (Reliable instalments 80, Clear returns and progress 42, Confidence through early losses 36, Flexible SIP controls 32; "Easy return after a pause" shown as "no posts, not scored").
- Table: opportunity, SIP posts, reach, severity, stage fit, segment fit, tag (`Scored`/`Small sample`), with the "left out because fewer than 5 posts" flags visible.
- Key insights panel (4 items): instalments are 64 of 252 problem posts (25%); about half of problem posts (app bugs 60, withdrawals 41, support 15) sit outside the score; expectation is not the gap (226 posts expect long-term growth, 9 quick gains); evidence is thin where it matters (months 2 to 12 have 10 posts, first-time writers 93 with 10 stating a problem).
- "What Groww could do" drafts per opportunity (marked "draft, no fund recommendations").

### Page 2: Journey (`/journey`)
**Title:** "Investors start for long-term wealth, check often, and look for answers outside the app"
**Answers:** Why people start and what they expect · what changes after starting · what they check and how often · what confuses or worries them · what they do outside the app.
- Stat tiles: 226 posts expect long-term growth (9 quick gains) · 12 of 21 surveyed check weekly or more · 14 of 21 look at profit or loss or return % first · only 3 of 21 ask their investment app when unsure.
- Chart 1, stage bars: posts by stage (Before starting 68, Onboarding 10, First instalment 29, Months 2-6 8, Months 7-12 2, After year 1 106) with the share carrying a problem inside each bar (6, 5, 12, 5, 1, 24). Note: stage stated in 223 of 1,240 posts; months 2-6 and 7-12 are low sample.
- Chart 2, expectations: long-term growth 226, habit 29, tax benefit 14, quick gains 9 (low sample), steady returns 7 (low sample). Beside it, survey: wealth creation 17 of 21, retirement 10; influenced by friends 10, family 8, own research 8.
- Chart 3, checking and feelings: engine (30 posts only: monthly 18, rarely 7, daily 4, weekly 1) next to survey (12 of 21 weekly or more; first look: profit or loss 7, return % 7, fund performance 3, goal progress 2). Survey feelings: 6 rarely worry, 6 watch and continue, 4 worry often, 5 paused or reduced.
- Chart 4, in-app confusion: returns or P&L 75, payment status 62, NAV or units 36, SIP dates 28, fund details 22, charges 20.
- Chart 5, outside the app, two bars side by side: engine (forum or community 42, contacts support 36, other apps or AMC 26, YouTube 7, friends or family 4, advisor 1) and survey (Google 12, friends or family 12, YouTube 9, advisor 6, social media 4, investment app 3).
- Source note: the survey has 21 SIP investors (23 responses), mostly aged 26 to 30 and salaried; only 3 are under a year into their SIP.

### Page 3: Drop-offs (`/drop-offs`)
**Title:** "Failed instalments, confusing returns and cash shocks lead investors to pause or stop, not only market falls"
**Answers:** What leads investors to pause, reduce or stop? What separates those who continue from those who drop off?
- Stat tiles: 104 posts state an event · 18 stopped · 13 considering stopping · 12 of 21 surveyed considered stopping.
- Chart 1, events: continued 42, started 28, stopped 18, considering stopping 13, paused 3 (low sample), reduced 1 (low sample). Caption: few people say they paused or reduced, so quiet drop-offs are under-recorded.
- Chart 2, failure modes (bars with severity text): app bug 60 (context only), instalment failed 50, withdrawal problem 41 (context only), confusing returns or progress 29, losses shake confidence 25, cannot pause or change amount 17, support not resolving 15 (context only), debited after cancel or twice 14, amount too high 2 (low sample). Out of 1,240 SIP posts, 886 describe no problem and 102 are not stated.
- Panel "Market or not?": market-related (losses shake confidence) is 25 of 252 problem posts (10%); instalment problems are 64 (25%). Survey: of 12 who considered stopping, returns or market worries led 5, cash flow or life 4, both 3. Looking ahead, 15 of 21 name job loss, income cut, emergency or family duties as a reason they might stop, 8 name poor returns, a crash or low confidence.
- Chart 3, triggers: switching platform or plan 29, goal or wealth 26, market fall or losses 25, rule change 25, charges or tax 24, habit discipline 23, app bug 18, fund issue 12 (stated in 217 posts).
- Quote cards (3 per failure mode for instalment failed, confusing returns, losses shake confidence), each with source and month. Example: "money stays blocked but app says failed" (Play Store, 2026-08).
- Block "Continuers vs drop-offs": show what exists (42 continued vs 18 stopped posts; 17 of 21 surveyed still active, 4 not) and a `Not yet computed` card for the full contrast, with the reason (only 104 posts state an event).

### Page 4: Segments (`/segments`)
**Title:** "First-time investors mostly show doubt after early losses, while cash shocks appear across the survey"
**Answers:** How do patterns differ across segments (income stability, age, source of money, who influenced them)? What is specific to first-time investors?
- Stat tiles: 226 of 1,240 posts say anything about the writer · 93 first-time posts · 10 of those state a problem · 3 survey patterns.
- Table: segment, group, n, with a problem, top failure modes, tag (`Low sample` if n under 10). Groups: income (salaried 24, student 14), age (under 25: 27, 45 or older 12), source of money (salary 27), who influenced them (own research 43, YouTube or finfluencer 18), experience (first-time 93, experienced 44, each with 10 posts stating a problem), residency (resident 28, NRI 25).
- First-time panel: 93 posts, 85% describe no problem; top stated problems losses shake confidence (4), app bug (4), support not resolving (2); expectation long-term growth 31, habit 11. Everything here is low sample.
- Survey patterns (cards): The Watcher (12 check weekly or more, 8 have considered stopping), The Quiet Checker (9 check monthly, rarely or on debit day, 4 have considered stopping, 3 say they paused or reduced), The Cash-Squeezed (7 considered stopping over job loss, an emergency or family costs; 5 still active; 6 rate continuing 4 or 5 of 5). Note that groups overlap.
- Caveat banner: segment tags exist only where a writer states them, so most posts are "not stated".

### Page 5: Validation (`/validation`)
**Title:** "The engine agrees with a human labeller on 80% of core fields, and the survey backs most of its findings"
**Answers:** How was the quality of the insights validated? Where did it fail?
- Stat tiles: 80% engine-vs-human agreement on core fields (64 of 80) · 20-item golden set · 85% retrieval top-3 hit rate (17 of 20; target 80%) · 21 survey respondents.
- Chart 1: agreement per field (About SIPs 85%, Stage 90%, Event 95%, Trigger 90%, Theme 60%, Failure mode 80%) with a second bar for "where either gives a value" (Theme 60%, Failure mode 73%, About SIPs 85%). Highlight Theme as the weakest.
- Table: precision and recall per class (theme and failure-mode classes), each tagged `Low sample` when support is under 5.
- "Where the engine failed": theme labels confuse goals and motivation with platform and plan choice (precision 33% to 40%); SIP controls 0%; the engine labelled some non-SIP posts as SIP (Not about SIPs recall 62%).
- "Corrections" block (2 to 3 items): AI output → what the person corrected → why. Seed with real items only. Known item: the golden set was drafted by an AI assistant and then reviewed and corrected by a person; its event disagreements led to a separate event re-check. Leave placeholders titled "Add correction" for the owner to fill from the Evidence Log. Do not invent corrections.
- Table "Engine vs survey": instalments (engine 64 posts; survey did not ask) · understanding returns and early losses (engine 29 and 25; survey 12 of 21 worried after negative returns, 17 look at returns first) · adjusting (engine 17; survey 7 of 21 want SIP changes explained, 5 paused or reduced) · cash-flow fit (engine 5 posts; survey 15 of 21 name a cash shock) · help (engine support 15 and forums 42; survey 3 of 21 ask their app, 12 use Google, 12 friends or family). Reading column: Supported / Untested / Engine under-counts.
- Link button: "AI Evidence Log" (URL from config, view access for anyone with the link).

### Page 6: Method (`/method`)
**Title:** "Seven public sources were cleaned, tagged and scored with a documented formula, and the limits are stated"
**Answers:** How does the workflow gather and analyse data, identify themes and generate insights?
- Stat tiles: 5,005 raw records · 3,423 excerpts · 3,310 posts · dated 2016-12-14 to 2026-10-28.
- Pipeline strip (6 steps): Collect (public sources, dedupe) → Clean and remove personal data → Chunk and embed → Tag (stage, trigger, event, segment, theme, failure mode) → Score (opportunity formula) → Dashboard and research tool.
- Table by source: raw, excerpts, posts, SIP posts, SIP posts with a failure mode (App Store 500/187/185/24/15; Play Store 1,000/938/938/138/70; Reddit 1,226/1,050/993/480/84; TradingQ&A 104/125/94/43/8; X 9/3/3/3/0; YouTube 1,896/832/831/487/65; Team-BHP 270/288/266/65/10). Chart: bars of raw vs kept per source.
- Formula card: Score = 100 × (0.40 × reach + 0.30 × severity + 0.15 × stage fit + 0.15 × segment fit). A part stated by fewer than 5 posts is left out and the other weights are rescaled.
- Tagging card: model and prompt version from the export (ministral-14b-latest, prompt v3), events re-checked in a separate pass.
- Limits list: public posts lean towards complaints; stage stated in only 18% of posts, events in 8%; X has 3 SIP posts and is excluded from claims; Team-BHP covers 18 pages of one thread; survey is a small convenience sample skewed to 26-30, salaried, experienced investors.
- "Not yet computed" list: low-rating share, Groww index, trend per opportunity, score per failure mode or theme. Each with its missing step.
- Privacy and rules card: no personal data stored, quotes de-identified, no investment advice.

## 4. Research tool ("Ask the engine")

A floating button on every page opens a side panel (full screen on mobile).

**Empty state (important):** show a short intro, the disclaimer, and **exactly 4 sample question chips. Do not show any answer until the user clicks a chip or sends a question.**
1. "What leads investors to pause, reduce or stop a SIP?"
2. "Where do investors go when they are unsure?"
3. "Which opportunity should we solve first, and why?"
4. "How do first-time investors differ from experienced ones?"

**On a question**
1. Route it to a page and section (coverage map in section 5) or to "out of scope".
2. Retrieve evidence: the matching JSON block plus the top excerpts from the vector search.
3. Call the LLM (Mistral, key kept server-side only) with the rule: answer only from the evidence, never invent a number or quote.
4. Guardrail: verify every number and quote in the answer exists in the evidence; retry once, then fall back to a plain evidence summary.
5. Show: answer text, sample size ("n = 64 of 252 problem posts"), confidence (High / Medium / Low with a reason), 2 to 3 de-identified quotes with source and month, and a link "See: Drop-offs → Failure modes" that opens the page and scrolls to the section.
6. After the answer show 2 follow-up chips ("Show quotes", "Break down by segment").

**Safe fallbacks (visible badge on each answer):** `Evidence-grounded`, `Low sample`, `Insufficient evidence`, `Out of scope`.
- Fewer than 15 supporting items: "Insufficient evidence", say what data would help.
- Requests for fund picks, "safest SIP", returns, projections or advice: decline politely, say this is a research tool and not investment advice, and link to the official factsheet, AMFI or SEBI investor pages.
- Never answer questions about individuals.

## 5. Coverage map: every question is answered on a page

| Question | Page and section |
|---|---|
| Why do people start a SIP and what do they expect? | Journey: expectations |
| What changes in behaviour in the months after starting? | Journey: stage bars |
| What leads to pause, reduce or stop? | Drop-offs: failure modes, triggers, market or not |
| What do investors check and how often? | Journey: checking and feelings |
| What confuses or worries them inside the app? | Journey: in-app confusion |
| What do they do outside the app when unsure? | Journey: outside the app |
| What separates continuers from drop-offs? | Drop-offs: continuers vs drop-offs |
| How do patterns differ across segments? | Segments |
| What unmet needs emerge consistently? | Overview: opportunities |
| How was quality validated? | Validation |
| How was it built? | Method |

## 6. Data contract

Generate one JSON file per page into `data/site/` with a script (`src/export_site_data.py`, extend the existing one if present): `overview.json`, `journey.json`, `dropoffs.json`, `segments.json`, `validation.json`, `method.json`, plus `sections_index.json` (page, section id, title, text, key numbers) used by the research tool's router. Each value carries `n`, a `sample` tag (`ok` or `low`), and a `status` (`computed` or `not_computed` with `reason`).

## 7. Stack and process

- Check what exists. Reuse the FastAPI backend (:8000) for `/api/ask` and the existing retrieval and guardrail code. Propose the simplest front end that deploys publicly (static React or Next.js reading the JSON, or Streamlit multipage if clearly simpler) and explain the trade-off.
- Charts: one lightweight library, Okabe-Ito colours, direct value labels, patterns plus colour.
- Build order: (1) JSON export script, (2) layout, nav, footer, tag components, (3) Method (its data is complete, so use it to check the chart style), (4) Overview, (5) Journey, (6) Drop-offs, (7) Segments, (8) Validation, (9) research tool, (10) deploy.
- After each step run it locally, say what to check, and wait for approval. Commit after each working step.

## 8. Acceptance checklist
- [ ] Exactly 6 pages plus the research tool; nav highlights the active page; direct links and the back button work.
- [ ] All numbers load from `data/site/*.json`; not-computed values show the reason.
- [ ] The research tool opens with 4 sample questions and no answers; answers appear only after a question.
- [ ] Each answer shows n, confidence, quotes with source and month, and a page link.
- [ ] Advice or fund-pick questions are declined with an official source link.
- [ ] Colour-blind-safe charts, 16px minimum text, mobile-friendly tables.
- [ ] No personal data, no fund names recommended, disclaimer visible on every page.
