"""Central settings for the SIP Discovery Engine pipeline.

Every path and tunable value lives here (Docs/architecture.md, section 6), so phases
never hard-code a data path and phase 6 can tune values without code changes.
Secrets come from Code/.env and are never logged.
"""
from __future__ import annotations

import os
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = CODE_DIR.parent
DATA_DIR = PROJECT_DIR / "Data"

try:  # optional: load secrets from Code/.env
    from dotenv import load_dotenv

    load_dotenv(CODE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass

# --- Data folders (one per pipeline stage) -------------------------------------------
SOURCES_FILE = DATA_DIR / "sources" / "sources.yaml"
RAW_DIR = DATA_DIR / "raw"
UPLOADS_DIR = DATA_DIR / "uploads"
CLEANED_DIR = DATA_DIR / "cleaned"
RECORDS_FILE = CLEANED_DIR / "records.jsonl"
LOAD_REPORT_FILE = CLEANED_DIR / "load_report.json"
CHUNKS_DIR = DATA_DIR / "chunks"
EMBEDDINGS_DIR = DATA_DIR / "embeddings"
VECTOR_DB_DIR = DATA_DIR / "vector_db" / "chroma"
SITE_DIR = DATA_DIR / "site"
EVAL_DIR = DATA_DIR / "eval"

# --- Phase 1: HTTP behaviour -----------------------------------------------------------
USER_AGENT = "SIPDiscoveryEngine/0.1 (research prototype; public data only)"
HTTP_TIMEOUT_SECONDS = 30
HTTP_DELAY_SECONDS = 1.0          # minimum gap between two requests to the same host
HTTP_MAX_RETRIES = 3
HTTP_BACKOFF_SECONDS = 5          # doubled on each retry

# --- Phase 1: per-source volumes ---------------------------------------------------------
PLAY_STORE_REVIEWS_PER_APP = 1000
PLAY_STORE_LANG = "en"
PLAY_STORE_COUNTRY = "in"

APP_STORE_COUNTRY = "in"
APP_STORE_MAX_PAGES = 10          # 50 reviews per page, about 500 per app (PRD)

FORUM_MAX_PAGES_PER_TOPIC = 60    # Discourse returns 20 posts per page; the longest thread has 1,038
FORUM_SEARCH_MAX_TOPICS = 30      # topics fetched in full from each forum search

REDDIT_MAX_POSTS = 100            # per search (Arctic Shift and the Reddit API cap at 100)
REDDIT_COMMENTS_LIMIT = 500       # comments per post
ARCTIC_SHIFT_DELAY_SECONDS = 2.0  # Arctic Shift asks clients to slow down

WAYBACK_MAX_RETRIES = 4
WAYBACK_BACKOFF_SECONDS = 20      # the archive answered 429 during the link check

YOUTUBE_MAX_VIDEOS = 25           # per search
YOUTUBE_MAX_COMMENTS_PER_VIDEO = 300

# --- Embedding model (phases 2, 3 and 5 must agree) --------------------------------------
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_MAX_TOKENS = 256            # word pieces the model reads, [CLS] and [SEP] included; the rest is cut
EMBEDDING_DIM = 384
EMBEDDING_DEVICE = "cpu"
EMBEDDING_BATCH_SIZE = 64
# How question vectors are made. "torch" (sentence-transformers) everywhere by default. A small
# deployment (Render's 512 MB plan) sets EMBEDDING_BACKEND=onnx: the same model and revision run
# with onnxruntime, without loading PyTorch. Only for questions; the corpus vectors come from phase 3.
EMBEDDING_BACKEND = (os.getenv("EMBEDDING_BACKEND") or ("onnx" if os.getenv("RENDER") else "torch")).strip().lower()
EMBEDDING_MODEL_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"  # the revision phase 3 used
ONNX_MODEL_DIR = DATA_DIR / "models" / "all-MiniLM-L6-v2-onnx"         # downloaded at build time

# --- Phase 2: chunking ---------------------------------------------------------------------
CHUNKS_FILE = CHUNKS_DIR / "chunks.jsonl"
CHUNK_REPORT_FILE = CHUNKS_DIR / "chunk_report.json"
CHUNK_TARGET_TOKENS = 200         # window size when a record must be split
CHUNK_OVERLAP_TOKENS = 40         # text repeated from the end of one excerpt at the start of the next

# --- Phase 3: embedding --------------------------------------------------------------------
SECTIONS_INDEX_FILE = SITE_DIR / "sections_index.json"      # written by the FR-7 export
PIPELINE_SUMMARY_FILE = SITE_DIR / "pipeline.json"          # phase 1-4 counts for the site (committed)
EMBEDDING_VECTORS_FILE = EMBEDDINGS_DIR / "vectors.npy"      # one row per distinct text
EMBEDDING_KEYS_FILE = EMBEDDINGS_DIR / "keys.json"           # model, dim and the text hash of each row
EMBEDDED_SECTIONS_FILE = EMBEDDINGS_DIR / "sections.json"    # section id -> text hash, for phase 4
EMBEDDING_REPORT_FILE = EMBEDDINGS_DIR / "embedding_report.json"

# --- Phase 4: vector store -----------------------------------------------------------------
EXCERPTS_COLLECTION = "excerpts"
SECTIONS_COLLECTION = "sections"
CHROMA_BATCH_SIZE = 1000          # rows per upsert or delete call (Chroma's own cap is about 5,000)
VECTOR_STORE_REPORT_FILE = DATA_DIR / "vector_db" / "vector_store_report.json"

# --- Phase 5: retrieval (starting values; phase 6 tunes them) -----------------------------
# Calibrated on the 2026-11-01 store: on-topic questions scored 0.65-0.77 for their best
# excerpt and at least 0.47 for their 20th; off-topic questions scored at most 0.47 for their best.
RETRIEVAL_CANDIDATES = 20         # k: must stay above the 15-item evidence rule
RETRIEVAL_PROMPT_EXCERPTS = 8     # investor excerpts handed to the answer step (room for 2-3 quotes, FR-10)
RETRIEVAL_CONTEXT_EXCERPTS = 2    # information-page passages, returned separately as context only
RETRIEVAL_MIN_SIMILARITY = 0.45   # a candidate below this is not evidence
OFF_TOPIC_MAX_SIMILARITY = 0.50   # if even the best excerpt scores below this, the question is off topic
ROUTE_MIN_SIMILARITY = 0.40       # nearest section below this -> off topic. Calibrated with 13 sections:
                                  # SIP questions scored 0.47-0.95, off-topic ones at most 0.36
INSUFFICIENT_EVIDENCE_BELOW = 15  # supporting records needed (PRD FR-12)
RETRIEVAL_SIP_ONLY = True         # once tags exist, evidence = posts tagged about SIPs only
SECTION_TAG_BOOST = 0.05          # added to a candidate's rank when it carries the routed section's tag
QUERY_SECTION_BLEND = 1.0         # search vector = question + this x the routed section's `about` vector
                                  # (phase 6 compared 0, 0.5 and 1.0; see Docs/architecture.md)
QUESTION_MAX_CHARS = 500
# The retrieval API the site calls (port 8000 is another app). A deployment can point the site
# at an API hosted elsewhere by setting API_BASE_URL in its environment.
API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")

# --- Mistral (tagging and answers) ---------------------------------------------------------
MISTRAL_REQUESTS_PER_MINUTE = 28  # this key allows 30/minute; stay just under
TAGGING_MODEL = "ministral-14b-latest"   # the PRD's tagging model
ANSWER_MODEL = "ministral-14b-latest"    # mistral-small-latest had no request quota on this key (429)

# --- FR-5 tagging ----------------------------------------------------------------------------
TAGS_DIR = DATA_DIR / "tags"
TAGS_FILE = TAGS_DIR / "tags.jsonl"
TAG_REPORT_FILE = TAGS_DIR / "tag_report.json"
TAG_PROMPT_VERSION = "v1"
TAG_BATCH_SIZE = 20               # posts per Mistral request
TAG_WORKERS = 8                   # requests in flight at once; answers take ~40s, the limiter caps the rate
TAG_MAX_CHARS = 1200              # longer posts are cut for tagging only

# --- Investor survey (primary research; 23 responses, 21 SIP investors) ----------------------
SURVEY_SOURCE_FILE = PROJECT_DIR / "Docs" / "SIP Investor Behavior Survey.csv" / "SIP Investor Behavior Survey.csv"
SURVEY_DIR = DATA_DIR / "survey"
SURVEY_RESPONSES_FILE = SURVEY_DIR / "responses.jsonl"      # de-identified: no name, email or timestamp
SURVEY_QUESTIONS_FILE = SURVEY_DIR / "questions.json"
SURVEY_REPORT_FILE = SURVEY_DIR / "survey_report.json"

# --- FR-6 scoring and FR-7 site export ------------------------------------------------------
SCORE_WEIGHTS = {"reach": 0.40, "severity": 0.30, "stage_fit": 0.15, "segment_fit": 0.15}  # PRD formula
MIN_POSTS_PER_PART = 5            # a part stated by fewer posts is left out; other weights rescale
LOW_SAMPLE_BELOW = 10             # figures under 10 posts are tagged "Low sample"
OFFICIAL_LINKS = [                # where advice and returns questions are pointed (PRD FR-13)
    {"label": "AMFI investor information", "url": "https://www.amfiindia.com/investor"},
    {"label": "SEBI investor website", "url": "https://investor.sebi.gov.in/"},
]

# --- Secrets (read from the environment; never print them) ------------------------------
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY", "")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")


def apply_quick_mode() -> None:
    """Shrink every volume for a fast smoke test (`run --quick`)."""
    global PLAY_STORE_REVIEWS_PER_APP, APP_STORE_MAX_PAGES, FORUM_MAX_PAGES_PER_TOPIC
    global FORUM_SEARCH_MAX_TOPICS, REDDIT_MAX_POSTS, REDDIT_COMMENTS_LIMIT
    global YOUTUBE_MAX_VIDEOS, YOUTUBE_MAX_COMMENTS_PER_VIDEO
    PLAY_STORE_REVIEWS_PER_APP = 20
    APP_STORE_MAX_PAGES = 1
    FORUM_MAX_PAGES_PER_TOPIC = 1
    FORUM_SEARCH_MAX_TOPICS = 2
    REDDIT_MAX_POSTS = 3
    REDDIT_COMMENTS_LIMIT = 20
    YOUTUBE_MAX_VIDEOS = 2
    YOUTUBE_MAX_COMMENTS_PER_VIDEO = 20
