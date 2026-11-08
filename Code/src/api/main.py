"""SIP Discovery Engine API (architecture phase 5).

Run from the Code/ folder:
    uvicorn src.api.main:app --port 8001

Port 8001, not the architecture's 8000: another local app already listens on 8000.

Endpoints
    GET  /api/health     store size, model and "last updated from sources" date
    POST /api/retrieve   {"question": "...", "app": "Groww"?, "source": "play_store"?, "section": "segments"?}
                         -> evidence bundle
    POST /api/ask        same body -> evidence bundle + `answer` (Mistral, checked by the guardrail)
Interactive docs: http://127.0.0.1:8001/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src import config
from src.answer.generate import answer as generate_answer
from src.phase5_retrieval.retriever import Retriever

log = logging.getLogger("api")
retriever = Retriever()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    retriever.warm_up()  # load the model and open the store once, before the first request
    log.info("Retriever ready: %s", retriever.info())
    yield


app = FastAPI(title="SIP Discovery Engine API", version="0.1.0", lifespan=lifespan)


class RetrieveRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=config.QUESTION_MAX_CHARS,
                          examples=["What leads investors to pause, reduce or stop a SIP?"])
    app: str | None = Field(None, description="Only excerpts about this app, e.g. Groww")
    source: str | None = Field(None, description="Only this source: play_store, app_store, forums, reddit, "
                                                 "team_bhp, info_pages")
    section: str | None = Field(None, description="Answer from this page section instead of routing, e.g. "
                                                  "segments; an unknown id falls back to routing")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", **retriever.info()}


@app.post("/api/retrieve")
def retrieve(request: RetrieveRequest) -> dict:
    """The evidence bundle for a question (architecture phase 5, steps 1 to 7)."""
    return retriever.retrieve(request.question, app=request.app, source=request.source, section=request.section)


@app.post("/api/ask")
def ask(request: RetrieveRequest) -> dict:
    """The evidence bundle plus a checked answer (PRD FR-9 to FR-14) under `answer`."""
    bundle = retriever.retrieve(request.question, app=request.app, source=request.source, section=request.section)
    return {**bundle, "answer": generate_answer(bundle)}
