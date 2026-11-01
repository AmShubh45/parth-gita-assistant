"""HTTP API and the web page.

GET  /              the Parth web app
POST /api/ask       {"question": "..."} -> grounded answer (JSON)
POST /api/feedback  {"question", "verse", "helpful"} -> logged
GET  /api/verse/x.y one verse
GET  /healthz
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .engine import Engine
from .guard import AnswerCache, DailyBudget, RateLimiter
from .kb import KnowledgeBase
from .llm import Gemini

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("parth")
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Parth", version="2.0", docs_url=None, redoc_url=None)
_kb = KnowledgeBase.load()
_gemini = Gemini()
engine = Engine(_kb, _gemini if _gemini.available else None)
budget, limiter, cache = DailyBudget(), RateLimiter(), AnswerCache()

RATE_MSG = {
    "en": "You're asking very quickly. Please wait a minute and try again.",
    "hi": "आप बहुत जल्दी-जल्दी पूछ रहे हैं। कृपया एक मिनट बाद फिर कोशिश करें।",
    "hinglish": "Aap bahut jaldi-jaldi pooch rahe hain. Please ek minute baad phir try kariye.",
}


class Ask(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class Feedback(BaseModel):
    question: str = Field(max_length=2000)
    verse: str = Field(max_length=20)
    helpful: bool


def _client(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "answerable_verses": len(_kb.answerable), "model": bool(engine.llm),
            "ai_answers_today": budget.used, "ai_daily_limit": budget.limit}


@app.post("/api/ask")
async def ask(body: Ask, request: Request):
    from .lang import detect
    if not limiter.allow(_client(request)):
        return JSONResponse({"kind": "rate_limited", "lang": detect(body.question),
                             "opening": RATE_MSG[detect(body.question)], "verses": []}, status_code=429)
    cached = cache.get(body.question)
    if cached:
        return cached
    use_model = bool(engine.llm) and budget.take()
    ans = await engine.answer(body.question, use_model=use_model)
    log.info("ask kind=%s lang=%s model=%s trace=%s", ans.kind, ans.lang, use_model, ans.trace)
    out = ans.to_dict()
    out.pop("trace", None)
    if ans.kind == "answer":
        cache.put(body.question, out)
    return out


@app.post("/api/feedback")
def feedback(body: Feedback) -> dict:
    log.info("feedback verse=%s helpful=%s question=%r", body.verse, body.helpful, body.question[:200])
    return {"ok": True}


@app.get("/api/verse/{ref}")
def verse(ref: str) -> dict:
    v = _kb.get(ref)
    if not v:
        raise HTTPException(404, "No such verse")
    return {"id": v.id, "speaker": v.speaker, "addressed_to": v.addressed_to, "sanskrit": v.sanskrit,
            "transliteration": v.transliteration, "translation": v.translation,
            "translation_status": "verified" if v.translation else "under review"}
