# SIP Discovery Engine: RAG Architecture

Version 1.1 · 2026-11-01 · Based on the [PRD](sip_discovery_engine_prd.md)

## 1. Summary

Retrieval runs as six phases. Four offline phases build a ChromaDB store of de-identified excerpts. One online phase turns a question into an evidence bundle. One test phase proves retrieval meets the PRD target: a top-3 hit rate of 80% or more on a 20-item golden set.

Everything here comes from the PRD. Where the PRD leaves something open, it is listed in section 7, not decided here.

**Scope:** phases 1 to 6 below. Answer generation (Mistral prompt, guardrail, badges: FR-9 to FR-14), tagging and scoring (FR-5, FR-6) and the Streamlit pages consume this pipeline's outputs; the PRD specifies them.

## 2. System overview

```
OFFLINE: build the evidence store (rerun on each source refresh)

  Data/sources/sources.yaml  (every URL from the PRD appendix)
        |
        v
  [1] Data loading ---> Data/raw/<source>/           untouched dumps
        |               Data/cleaned/records.jsonl   cleaned, deduped, PII-stripped
        v
  [2] Chunking -------> Data/chunks/chunks.jsonl     excerpts + metadata
        v
  [3] Embedding ------> Data/embeddings/             384-d vectors, cached by text hash
        v
  [4] Vector store ---> Data/vector_db/chroma/       collections: excerpts, sections


ONLINE: answer a question (FastAPI /api/ask, port 8000)

  question --> [5] Retrieval logic --> evidence bundle --> answer step --> Streamlit (port 8501)
               check input and scope                      Mistral + guardrail
               embed, route, search                       (PRD FR-9 to FR-14)


QUALITY GATE

  [6] Retrieval testing: 20-item golden set, rerun after every rebuild of phases 1 to 4
```

Data flows one way: raw → cleaned → chunks → embeddings → vector DB. Each phase reads only the previous phase's output, so any phase can be rerun on its own.

## 3. Folder structure

Three top-level folders keep documents, data and code apart. Code never stores data inside `Code/`; every phase reads from and writes to `Data/`.

```
NextLeap_GraduationProject_SIP/
├── requirements.txt                   Python dependencies (pip install -r requirements.txt)
├── Docs/                              documents only
│   ├── GraduationPrject_Probelm statment.docx
│   ├── sip_discovery_engine_prd.md
│   ├── sip_discovery_engine_prd_architecture.png
│   ├── sip_discovery_engine_ui_spec.md
│   └── architecture.md                this document
│
├── Data/                              data only, one folder per pipeline stage
│   ├── sources/                       input: sources.yaml, every ingestion URL with loader and status
│   ├── raw/                           phase 1 output: untouched dumps, never edited by hand
│   │   ├── play_store/
│   │   ├── app_store/
│   │   ├── forums/                    TradingQ&A, Jupiter, madefortrade (Discourse JSON)
│   │   ├── reddit/
│   │   ├── team_bhp/
│   │   ├── youtube/
│   │   └── info_pages/
│   ├── uploads/                       files downloaded by hand (the two Kotak PDFs)
│   ├── cleaned/                       phase 1 output: records.jsonl (deduped, personal data removed)
│   ├── chunks/                        phase 2 output: chunks.jsonl (excerpts with metadata), chunk_report.json
│   ├── embeddings/                    phase 3 output: vectors.npy + keys.json (cache by text hash), sections.json
│   ├── vector_db/
│   │   ├── chroma/                    phase 4 output: ChromaDB files (collections: excerpts, sections)
│   │   └── vector_store_report.json
│   ├── tags/                          FR-5 output: tags.jsonl (one row per record), tag_report.json
│   ├── site/                          FR-7 output: one JSON per page + sections_index.json (routing) + pipeline.json (phase 1-4 counts)
│   └── eval/
│       ├── golden_set.jsonl           phase 6 input: the 20 test questions
│       └── reports/                   phase 6 output: one report per run
│
└── Code/                              code only
    ├── src/
    │   ├── config.py                  paths to Data/, model name, chunk size, k, thresholds
    │   ├── jsonl.py                   read and write the JSON Lines files phases hand to each other
    │   ├── phase1_data_loading/
    │   │   ├── loaders/               one module per source: play_store, app_store, discourse,
    │   │   │                          reddit, team_bhp, youtube, info_pages (+ common.py)
    │   │   ├── http_client.py         shared session: polite delay per host, retries
    │   │   ├── clean.py               normalise text, build record ids
    │   │   ├── pii.py                 strip personal data
    │   │   └── run.py                 entry point
    │   ├── phase2_chunking/           chunker.py, run.py
    │   ├── phase3_embedding/          embedder.py (shared with phase 5), cache.py, run.py
    │   ├── phase4_vector_store/       store.py (shared with phase 5), run.py
    │   ├── phase5_retrieval/          scope.py, router.py, search.py, bundle.py, retriever.py, cli.py
    │   ├── phase6_retrieval_testing/  evaluate.py, run.py, agreement.py (engine vs human labels)
    │   ├── tagging/                   FR-5: taxonomy.py, tagger.py, run.py (Mistral)
    │   ├── site_export/               FR-6 scoring.py + FR-7 build.py, run.py (page data, sections), pipeline.py (pipeline.json)
    │   ├── answer/                    generate.py: the answer step and its guardrail (FR-9 to FR-14)
    │   ├── llm.py                     shared Mistral client (rate limit, retries)
    │   └── api/                       main.py: FastAPI /api/retrieve (later /api/ask), calls phase5_retrieval
    ├── app/                           Streamlit site (port 8502)
    │   ├── streamlit_app.py           entry point: top navigation, sidebar research tool, footer
    │   ├── site_data.py               every number the site shows, read from the phase reports
    │   ├── ui.py                      shared page blocks: header, stat tiles, Not computed cards, insights
    │   ├── research_client.py         the site's retrieval client: /api/ask, /api/retrieve, in-process fallback
    │   ├── ask.py                     "Ask the engine" in the sidebar of every page
    │   └── views/                     one module per page: overview, journey, dropoffs, segments,
    │                                  validation, method, research (the full-page "Ask the engine");
    │                                  not "pages/": Streamlit reserves that name
    ├── .streamlit/config.toml         theme (teal #0b6e69, off-white #f5f3ee) and port 8502
    ├── tests/                         unit tests per phase, site tests, the golden-set test
    ├── pytest.ini
    ├── .env                           API keys (never committed; see /.gitignore)
    └── .env.example                   MISTRAL_API_KEY, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, YOUTUBE_API_KEY
```

The folders exist now. The files named inside them arrive as each phase is built. `Code/src/config.py` finds the data folder as `../Data` relative to `Code/`, so no data path is hard-coded anywhere else.

## 4. Phases

### Phase 1: Data loading

**Goal:** turn every active URL in the PRD appendix into clean, de-identified records.

**Code:** `Code/src/phase1_data_loading/` · **Reads:** `Data/sources/sources.yaml`, `Data/uploads/` · **Writes:** `Data/raw/<source>/`, `Data/cleaned/records.jsonl`

**Loaders**, one per source type:

| Source | Loader | Note from the PRD link check |
| --- | --- | --- |
| Google Play (11 apps) | `google-play-scraper` library, by app ID, newest first | 1,000 reviews per app by default |
| App Store (5 apps) | RSS JSON feed, `page=1` to `page=10`; if an app's feed is empty, its "see all reviews" web page | 50 reviews per feed page; the web page holds only the 10 newest; Sundaram MF has only 5 |
| TradingQ&A, Jupiter, madefortrade | Discourse topic JSON (`<thread URL>.json`), `?page=N` for long threads | The pooling thread has 1,038 posts |
| Reddit | Reddit API (OAuth "script" app), or Arctic Shift: `posts/search`, then `comments/tree` per post | Arctic Shift comment search times out |
| Team-BHP | Wayback raw copy (`id_` URL), requests spaced out | Archive returned 429 during testing |
| YouTube | YouTube Data API, comments on the search results | Needs an API key |
| SIP information pages | HTML fetch, keeping the block that holds most of the page's paragraphs; Kotak PDFs read from `Data/uploads/`; kotakmf.com via its Wayback copy | Context only, never used to calculate returns |
| X | None | Dropped |

**Steps**

1. Fetch each source and write the response to `Data/raw/<source>/<date>.jsonl`, unchanged except that author, user and reviewer fields are removed before anything touches disk.
2. Normalise every item to the record schema below.
3. Remove duplicates: same source, same app (or platform) and same text hash, which is exactly the record `id`.
4. Strip personal data from the text: usernames and @handles, profile links, PAN, Aadhaar, OTPs, phone numbers, emails, account numbers (FR-2).
5. Write `Data/cleaned/records.jsonl`, plus `Data/cleaned/load_report.json` with counts per source.

**Record schema**

| Field | Example | Note |
| --- | --- | --- |
| `id` | `play_store:groww:<text hash>` | Stable across reruns |
| `source` | `play_store` | |
| `app` | `Groww` | Where the source is about one app |
| `url` | Listing or thread URL | Used for the answer's citation (FR-10) |
| `date` | `2026-08-14` | Current corpus spans 2016-12-14 to 2026-10-28 |
| `doc_type` | `review`, `post`, `comment` or `info_page` | `info_page` is context only |
| `text` | Cleaned text | Personal data removed |

**Done when:** every active source has records; sample PAN, Aadhaar, phone and email strings are absent from `records.jsonl`; a rerun creates no duplicate ids.

**Options:** `--sources reddit forums` fetches only those sources; `--skip-fetch` rebuilds `records.jsonl` from `Data/raw/` without network calls; `--quick` uses small volumes for a smoke test. Records are always rebuilt from every raw file, so a partial fetch never shrinks the record set.

### Phase 2: Chunking

**Goal:** split records into excerpts small enough for the embedding model, each traceable to its record.

**Code:** `Code/src/phase2_chunking/` · **Reads:** `Data/cleaned/records.jsonl` · **Writes:** `Data/chunks/chunks.jsonl`

| Record type | Rule |
| --- | --- |
| Review, comment, short post (254 word pieces or fewer) | One excerpt per record, text unchanged |
| Long post or information page (more than 254) | Split into sentences, keeping paragraph and line breaks; pack sentences into excerpts of about 200 word pieces; each excerpt repeats up to about 40 word pieces of whole sentences from the end of the one before |
| A single sentence over 200 word pieces | Cut into windows at word boundaries, using the tokenizer's character offsets so the original text and capitals are kept |

Why about 200 tokens: all-MiniLM-L6-v2 reads at most 256 word pieces, `[CLS]` and `[SEP]` included, and silently drops the rest; 200 leaves headroom. Sizes are counted with the model's own tokenizer, loaded from the local cache.

**Excerpt metadata:** `chunk_id` (record id + position), `record_id`, `source`, `app`, `url`, `date`, `doc_type`, `tags` (empty until the tagging step, FR-5), `text`, `token_count`.

**Done when:** no excerpt exceeds 256 word pieces; every excerpt maps back to a record; excerpt counts are logged per source (console and `Data/chunks/chunk_report.json`). The run exits with code 1 if a check fails.

### Phase 3: Embedding

**Goal:** one vector per excerpt, from the same model the question side uses.

**Code:** `Code/src/phase3_embedding/` · **Reads:** `Data/chunks/chunks.jsonl`, `Data/site/sections_index.json` · **Writes:** `Data/embeddings/`

- Model: `sentence-transformers/all-MiniLM-L6-v2` (PRD), pinned in `Code/src/config.py`. 384 dimensions, runs locally on CPU, loaded from the local cache.
- Normalise vectors, so cosine similarity equals the dot product.
- Encode in batches of 64.
- Cache vectors keyed by a SHA-1 hash of the text, so a rerun embeds only new or changed excerpts, and identical excerpts share one vector. A cache made by another model is ignored, never mixed in.
- Also embed each entry of `sections_index.json` (title + text) for routing in phase 5. Until the FR-7 export writes that file, sections are skipped with a note in the report.
- `Embedder` (`embedder.py`) is the only code that makes vectors; phase 5 reuses it for questions, so both sides always match.

**Files in `Data/embeddings/`:** `vectors.npy` (float32, one row per distinct text), `keys.json` (model, dimension and the text hash of each row), `sections.json` (section id → text hash, for phase 4), `embedding_report.json`. Phase 4 finds an excerpt's vector by hashing its text and looking it up in the cache.

**Options:** `--prune` drops cached vectors whose text is no longer in `chunks.jsonl`.

**Done when:** every excerpt has a vector; every vector has 384 dimensions and unit length; a rerun with no new data embeds nothing. The run exits with code 1 if a check fails.

### Phase 4: Vector store

**Goal:** persist vectors and metadata in ChromaDB so retrieval can search and filter them.

**Code:** `Code/src/phase4_vector_store/` · **Reads:** `Data/embeddings/`, `Data/chunks/chunks.jsonl` · **Writes:** `Data/vector_db/chroma/`

- ChromaDB persistent client at `Data/vector_db/chroma/`.
- Collection `excerpts`: id = `chunk_id`, the vector, the excerpt text, and metadata `record_id`, `source`, `app`, `url`, `date`, `doc_type`, `tags`, `token_count` (FR-4). `record_id` lets phase 5 count distinct supporting records. Cosine distance.
- Collection `sections`: one entry per section in `sections_index.json`, used for routing. Empty until the FR-7 export writes that file.
- No collection gets Chroma's own embedding function: vectors always come from phase 3's model, so a question can never be embedded by a different model by mistake.
- Writes are a sync keyed by id: new or changed rows are upserted, rows whose excerpt no longer exists are deleted, unchanged rows are skipped (a `row_hash` in each row's metadata detects changes). Reloading is safe, and a rerun with no new data writes nothing.
- Each collection stores its build information: `built_at`, `sources_fetched_at` (phase 1's last fetch), `last_updated_from_sources` (the date answers show, FR-10), `model`, `dim`, `rows`.
- Chroma metadata values are single values (string, number, boolean) and Chroma drops a row's whole metadata when one value is empty (None), so a missing `app` or `date` is stored as `""` and `tags` as one comma-joined string.
- `store.py` holds the shared access code; phase 5 opens the collections through it.

**Done when:** collection counts match phases 2 and 3; a sample query returns excerpts with every metadata field filled. The run also checks the distance is cosine, writes `Data/vector_db/vector_store_report.json`, and exits with code 1 if a check fails.

### Phase 5: Retrieval logic

**Goal:** turn a question into an evidence bundle for the answer step (FR-8).

**Code:** `Code/src/phase5_retrieval/`, called by `Code/src/api/main.py` · **Reads:** `Data/vector_db/chroma/`, `Data/site/`

**Steps**

1. **Input check:** reject a question containing a PAN, Aadhaar, account number, OTP, email or phone number (PRD privacy rule).
2. **Scope check:** advice, fund picks, "safest SIP", returns, projections or a named individual → status `out_of_scope`; the answer step declines with an official factsheet, AMFI or SEBI link (FR-13).
3. **Embed** the question with the phase 3 model.
4. **Route:** find the nearest section in `sections`. Below the similarity cut-off → `out_of_scope`.
5. **Search** `excerpts`: top 20 candidates above the similarity cut-off.
6. **Count supporting items:** distinct records among the candidates. Fewer than 15 → status `insufficient_evidence` (FR-12).
7. **Build the bundle:** the routed section's JSON block (its numbers already carry `n` and a sample tag, FR-7), the top 8 excerpts for the prompt, the page link and the build date.

**Evidence bundle** (illustrative values; `status` is `evidence`, `out_of_scope` or `insufficient_evidence`):

```json
{
  "question": "What leads investors to pause, reduce or stop a SIP?",
  "route": {"page": "Drop-offs", "section": "failure-modes", "score": 0.71},
  "status": "evidence",
  "supporting_items": 18,
  "section_data": {"source_file": "Data/site/dropoffs.json"},
  "excerpts": [
    {"chunk_id": "play_store:groww:ab12-0", "text": "...", "source": "play_store",
     "url": "https://play.google.com/store/apps/details?id=com.nextbillion.groww",
     "date": "2026-08", "score": 0.66}
  ],
  "page_link": "Drop-offs → Failure modes",
  "last_updated": "2026-11-01"
}
```

**Starting settings** (in `Code/src/config.py`, tuned in phase 6):

| Setting | Start value | Reason |
| --- | --- | --- |
| Candidates searched (k) | 20 | Must be above the 15-item evidence rule |
| Excerpts sent to the prompt | 8 | Room for 2 to 3 quotes (FR-10) plus context |
| Similarity cut-off | Set in phase 6 | The PRD gives no value |
| Insufficient evidence | Fewer than 15 supporting items | FR-12 |

**As built (phase 5 implementation):**

- **Code:** `scope.py` (steps 1-2), `router.py` (step 4), `search.py` (steps 5-6), `bundle.py` (step 7), `retriever.py` (runs the steps; loads the model and store once), `cli.py` (try it from the terminal). `api/main.py` serves `GET /api/health` and `POST /api/retrieve` (`{"question", "app"?, "source"?}` → bundle). `/api/ask` arrives with the answer step.
- **Port 8001:** another local app already listens on 8000.
- **Refusals** all use `status: out_of_scope` with a `reason`: `personal_data` (the echoed question is redacted), `investment_advice` and `returns_or_projection` (bundle carries `decline_links` to the AMFI and SEBI investor pages), `individual`, `off_topic`. The rules are narrow: discovery questions about returns stay in scope, only computing, projecting or comparing returns is refused; "should we" (product questions) stays in scope, "should I" (personal advice) is refused.
- **Information pages are searched separately.** Their textbook wording crowded investor posts out of the top results, so evidence is searched with `doc_type != info_page`, and the top 2 information-page passages come back in a separate `context` field. They never count as supporting items.
- **Supporting items** are distinct `record_id`s among evidence above the cut-off.
- **Cut-offs** (starting values, calibrated on the 2026-11-01 store, tuned in phase 6): evidence 0.45; off topic when the best excerpt scores below 0.50 (on-topic questions scored 0.65-0.77, off-topic at most 0.47); routing 0.40 once sections exist.
- **Without sections** (until the FR-7 export), routing is skipped, `route`, `page_link` and `section_data` are null, and `notes` says so; the off-topic test then uses the best excerpt over the whole corpus.
- **Filters** `app` and `source` narrow the search. `app` is set only for app-store reviews and information pages, so `app=Groww` excludes forum and Reddit posts that discuss Groww.
- **Bundle fields:** `question`, `status`, `reason`, `detail`, `route`, `page_link`, `section_data`, `supporting_items`, `evidence_needed`, `candidates_above_cutoff`, `excerpts` (top 8, each with `chunk_id`, `record_id`, `score`, `source`, `app`, `doc_type`, `date`, `url`, `text`), `context`, `decline_links`, `filters`, `last_updated`, `notes`, `timing_ms`.

**Done when:** every golden-set question returns a bundle with a route and a status, and every advice question comes back `out_of_scope`.

### Phase 6: Retrieval testing

**Goal:** prove retrieval meets the PRD target before any answer is generated, and prove it again after every rebuild. These tests check retrieval only, so they never call Mistral.

**Code:** `Code/src/phase6_retrieval_testing/`, `Code/tests/` · **Reads:** `Data/eval/golden_set.jsonl` · **Writes:** `Data/eval/reports/<date>.json`

**Golden set:** 20 questions. Cover the nine discovery questions, the four sample chips and some advice questions. One line per item:

```json
{"id": "g01", "question": "What leads investors to pause, reduce or stop a SIP?", "expected_section": "dropoffs.failure-modes", "relevant_records": ["<record id>"], "out_of_scope": false}
```

**Metrics**

| Metric | Target | Source |
| --- | --- | --- |
| Top-3 hit rate: a relevant excerpt in the top 3 | 80% or more | PRD success metrics (current 85%, 17 of 20) |
| Advice and fund-pick questions routed out of scope | 100% | FR-13 |
| Insufficient evidence raised below 15 supporting items | 100% of cases | FR-12 |
| Personal data found in stored excerpts | 0 | FR-2 |
| Section routing accuracy | Reported each run | No PRD target |

**Test layers**

1. **Unit tests per phase** (`Code/tests/`): loader parsing, personal-data removal, excerpt length of 256 word pieces or fewer, vector dimension of 384, store counts.
2. **Golden-set run** (`Code/src/phase6_retrieval_testing/`): writes a report with every metric and every miss.
3. **Gate:** a rebuild of phases 1 to 4 ships only if the top-3 hit rate stays at 80% or more.

Use the misses to tune chunk size, overlap, k and the similarity cut-off, one change per run.

## 5. Run order

Run every command from the `Code/` folder.

| Phase | Command | Reads | Writes |
| --- | --- | --- | --- |
| 1 | `python -m src.phase1_data_loading.run` | `Data/sources/`, `Data/uploads/` | `Data/raw/`, `Data/cleaned/` |
| 2 | `python -m src.phase2_chunking.run` | `Data/cleaned/` | `Data/chunks/` |
| 3 | `python -m src.phase3_embedding.run` | `Data/chunks/`, `Data/site/` | `Data/embeddings/` |
| 4 | `python -m src.phase4_vector_store.run` | `Data/embeddings/`, `Data/chunks/` | `Data/vector_db/chroma/` |
| Tag (FR-5) | `python -m src.tagging.run` | `Data/cleaned/records.jsonl` | `Data/tags/` |
| Score + export (FR-6, FR-7) | `python -m src.site_export.run` | records, tags, phase reports | `Data/site/*.json`, `sections_index.json`, `pipeline.json` |
| 3 + 4 again | rerun phases 3 and 4 after an export | `Data/site/sections_index.json`, tags | section vectors; tags in store metadata |
| 5 | `uvicorn src.api.main:app --port 8001`, or `python -m src.phase5_retrieval.cli "question"` | `Data/vector_db/`, `Data/site/` | Serves `/api/retrieve` and `/api/ask` |
| 6 | `python -m src.phase6_retrieval_testing.run` and `pytest tests/` | `Data/eval/golden_set.jsonl`, `holdout_set.jsonl` | `Data/eval/reports/` |
| Site | `streamlit run app/streamlit_app.py` (port 8502) | `Data/site/*.json`, phase reports (or `Data/site/pipeline.json`), `/api/ask` | Six pages + "Ask the engine" |

A full refresh is phases 1 → 2 → 3 → 4 → tag → export → 3 → 4 → 6, then restart the API and the site. Every step only processes what changed.

## 5a. Beyond retrieval: tags, scores, page data and answers

**FR-5 tagging** (`Code/src/tagging/`, writes `Data/tags/tags.jsonl`). `ministral-14b-latest` labels each post in batches of 20: `about_sip`, stage, event, trigger, failure mode, theme, expectation, checking, confusion, help-seeking and six segment fields (`taxonomy.py`). Every forum, Reddit and Team-BHP post goes to the model; app-store reviews go only if they contain a SIP word, the rest are tagged `about_sip = false` by rule; information pages are never tagged. Answers are validated (one allowed label per field, lists and spelling variants normalised), cached per record and prompt version, and a rerun sends only untagged posts. First full run: 5,704 posts to the model, 2,324 about SIPs, about 750,000 tokens.

**FR-6 scoring** (`Code/src/site_export/scoring.py`). Score = 100 × (0.40 reach + 0.30 severity + 0.15 stage fit + 0.15 segment fit), the PRD formula. Part definitions (the prototype's; shown on the Method page): reach = the opportunity's problem posts ÷ the largest opportunity's; severity = share of its posts stating an event that report stopping, pausing, reducing or considering stopping; stage fit = share stating a stage that sit in the first 12 months; segment fit = share stating experience that are first-time. A part stated by fewer than 5 posts is left out and the weights rescale; an opportunity with fewer than 5 posts is not scored. App bugs, withdrawals and support problems are "context only", outside the score. The Overview shows two scopes, all sources and Groww only, because the competitor-review decision is open.

**FR-7 page data** (`Code/src/site_export/build.py`). One JSON file per page plus `sections_index.json`; every value carries `n`, a `sample` tag (low under 10) and a `status`. Each section has `text` (the questions it answers, used for routing) and `about` (what its posts say, used to steer search), plus labelled `key_numbers` ("…: problem posts", "…: opportunity score (0-100)") for the answer step.

**Retrieval additions** (phase 5): with tags in the store, evidence is limited to posts tagged `about_sip`; the search vector blends the question with the routed section's `about` text (`QUERY_SECTION_BLEND = 1.0`); candidates tagged for the routed section get a small rank boost (`SECTION_TAG_BOOST = 0.05`). Routing cut-off 0.40, calibrated with 13 sections (SIP questions 0.47–0.95, off-topic at most 0.36).

**Answer step** (`Code/src/answer/generate.py`, `POST /api/ask`). Out-of-scope questions get a fixed reply and never reach the model. Otherwise `ministral-14b-latest` answers the question directly in at most 4 plain sentences from the section's labelled numbers and the excerpts, picks 2–3 quotes and proposes a confidence. Post counts and sample sizes stay out of the answer unless the question asks how many (a clean-up step removes any "(451 posts)" that slips through); the site shows them with the evidence instead. Guardrail: every number must appear in the evidence, values or labels (excerpt ids are ignored), quotes must be retrieved excerpts, advice wording is rejected; one retry with the problems listed, then a plain evidence summary. Whatever shape the model returns (text, a list or a nested object) is turned into plain text before the checks, and the step never raises. Confidence is capped at Low for insufficient evidence and at Medium under 15 supporting posts. `mistral-small-latest` had no request quota on this key, hence the smaller model.

**Segment follow-up.** "Break down by segment" sends the question with `section: "segments"`, so it is answered from the Segments section whatever its wording (routing alone sent it to Stages). That section's key numbers carry every segment group with enough posts (experienced 160 posts, 74 stating a problem; first-time 97 and 36; salaried 126 and 67; and so on), written by the FR-7 export; the section text used for routing is unchanged, so nothing is re-embedded.

**Phase 6 results (2026-11-01)**: golden set 16/16 top-3 hits, 4/4 refusals, routing 16/16, no personal data in stored excerpts. This is optimistic: the 20-item golden set is AI-drafted, relevance is judged with the engine's own tags (which the rank boost also uses), and the settings were tuned on it. On 8 held-out questions never used for tuning (`Data/eval/holdout_set.jsonl`) the top-3 hit rate is 5/7 = 71%, below the 80% target. Next step: a person reviews both sets and adds hand-picked relevant posts.

**Engine vs human agreement**: `python -m src.phase6_retrieval_testing.agreement export` wrote a 40-post sheet (`Data/eval/human_labels.csv`, guide in `HOW_TO_LABEL.md`); after a person fills it, `… agreement score` writes `Data/eval/agreement.json` and the Validation page shows it.

**Investor survey** (`Code/src/survey/load.py`, `Code/src/site_export/survey.py`). `python -m src.survey.load` reads `Docs/SIP Investor Behavior Survey.csv` (23 responses, 21 SIP investors) and writes de-identified `Data/survey/responses.jsonl`: the timestamp, the follow-up question and the optional name and email columns are dropped before anything is written, and free-text answers pass the personal-data filter. The raw CSV is git-ignored. The export adds a survey section to Overview, Journey, Drop-offs, Segments (the UI spec's three patterns: Watcher, Quiet Checker, Cash-Squeezed) and Validation, where an engine-vs-survey table reads each theme as Supported, Engine under-counts, Partly supported or Untested by fixed rules. Every survey figure is "n of 21", never a population percentage. Run it before the site export.

**Data gap fixed**: Groww's Play Store pull is now 5,000 newest + 5,000 "most relevant" reviews (`count` and `sorts` per app in `sources.yaml`), widening its window from one week to September 2018 – October 2026.

**Frontend retrieval** (`app/research_client.py`, `app/views/research.py`, URL `/ask`, last tab "Ask the engine"). The full-page research tool sends a question, with optional app and source filters, to `POST /api/ask` ("Answer and evidence") or `POST /api/retrieve` ("Evidence only", no Mistral call); if the API is not running it runs the same retrieval and answer code in-process and says so. It shows the API connection status and the 4 sample questions until a question is asked. A result shows the answer first, then one line with its source section and "Last updated from sources", then the two follow-ups. The research detail sits in one "Evidence and confidence" panel, collapsed under an answer and open in "Evidence only" mode: status badge, supporting posts, routed section, timing, confidence and its reason, quotes, every retrieved excerpt with its match score (at most 25 words, source and month), the information-page context and the evidence bundle (excerpts trimmed, record ids and URLs left out). Recent questions follow. The sidebar tool on the other pages uses the same client and layout and links to this page.

**Page headers.** Each page has a section tag, a short message title built from the data but without research numbers (those live in the tiles and charts), and one "On this page: …" line. The Validation page no longer shows the engine-vs-human agreement section, and the Method page no longer lists it as pending; its "Still to do" table appears only while something is pending.

**The site** reads `Data/site/*.json` (tag-based pages and survey sections) and the phase reports (pipeline counts and checks), so no number is typed in. "Ask the engine" calls `/api/ask` (or runs retrieval and the answer step in-process if the API is down) and shows the answer, confidence, quotes, the page link and the two follow-ups ("Show quotes", "Break down by segment").

**Deployment (for example Render).** The phase outputs (`Data/raw/`, `Data/cleaned/`, `Data/chunks/`, `Data/embeddings/`, `Data/vector_db/`) are git-ignored: they are large (the vector store alone is about 125 MB) and rebuilt locally. A deployment built from the repository therefore has `Data/site/`, `Data/tags/`, `Data/survey/`, `Data/eval/`, `Data/sources/` and only four phase files kept on purpose for the vector store (below). So that the pages still show every number, the export also writes `Data/site/pipeline.json` (`Code/src/site_export/pipeline.py`): the counts, date ranges, per-app review windows and check results the site would otherwise compute from the phase reports and `records.jsonl`. The site computes them live when the reports exist and reads `pipeline.json` when they do not; a test fails if the committed file lags behind the local reports (rerun `python -m src.site_export.pipeline`). "Ask the engine" needs the vector store, which is rebuilt during the deployment's build (`render_build.sh`, the Render build command):

1. `pip install -r requirements.txt`
2. `python -m src.phase3_embedding.onnx_model` downloads the official ONNX export of the same model at the same revision phase 3 used (86 MB, git-ignored under `Data/models/`).
3. `python -m src.phase4_vector_store.run` rebuilds the store from the committed `Data/chunks/chunks.jsonl` (de-identified excerpts), `Data/embeddings/vectors.npy` and `keys.json` (their phase 3 vectors), plus the committed tags and sections. Nothing is re-embedded and no model is loaded (about 30 seconds).

At run time `EMBEDDING_BACKEND=onnx` (the default when Render's `RENDER` variable is set) makes question vectors with onnxruntime instead of PyTorch; the routing, search, cut-offs, prompts and guardrails are unchanged. Measured on 2026-11-03: ONNX question vectors match PyTorch to cosine 0.9999999; 64 of 64 retrieval bundles were identical on the local store, 56 of 56 on the rebuilt store; golden 16/16 and holdout 5/7 as before; the site peaked at about 390 MB with every page rendered and a written answer (PyTorch alone needed about 640 MB, above Render's 512 MB). `MISTRAL_API_KEY` goes in the service's environment. If neither the API nor a vector store is available, "Ask the engine" says so instead of answering. After a local pipeline refresh, commit the updated `chunks.jsonl`, `vectors.npy`, `keys.json`, `load_report.json` and `Data/site/` files so the deployment rebuilds the same store.

## 6. Key design decisions

| Decision | Choice | Reason |
| --- | --- | --- |
| Folder layout | `Docs/`, `Data/`, `Code/` kept apart | Data can be rebuilt or cleared without touching code |
| Pipeline shape | One code folder and one data folder per phase, files between them | Any phase reruns alone; each output can be checked by eye |
| Raw data | Kept untouched | Reproducible results (PRD risk: snapshot raw data) |
| Embedding model | all-MiniLM-L6-v2 on both sides | PRD choice; vectors only compare within one model |
| Routing before search | Match a section first, then search excerpts | FR-8: an answer uses the section's numbers plus excerpts |
| Tunable values and paths | All in `Code/src/config.py` | Phase 6 tunes without code changes |
| Secrets | `Code/.env`, server side only | PRD security requirement |

## 7. Open decisions

Settled during phase 1: the Play Store loader uses `google-play-scraper`; Reddit uses the official API when `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` are set in `Code/.env`, and the Arctic Shift archive otherwise.

Still open:
- Whether reviews of competitor apps count toward Groww's opportunity scores or serve as context only. The Overview shows both scopes ("All sources" and "Groww only"); the ranking is the same in both.
- Survey free-text answers (Q8, Q20–Q22, Q24) are stored de-identified but not yet used; they could be categorised or quoted later.
- Human review of the golden and held-out sets, and the human labels for engine-vs-human agreement.
- Whether the 15-item Insufficient evidence rule applies per answer or per section (PRD open question). Phase 5 applies it per question for now.
- How often sources are refreshed, which sets how often phases 1 to 4 rerun (PRD open question).
