"""HTTP API and the web page.

GET  /                 the Parth web app (voice-first)
POST /api/ask          {"question": "..."} -> grounded text answer (JSON)
POST /api/live/token   ephemeral, config-locked token for a Gemini Live voice session
GET  /api/verses?q=    verified verses for the voice model's find_verses tool (and the page's cards)
POST /api/triage       {"text": "..."} -> crisis check on what the person said
POST /api/feedback     {"question", "verse", "helpful"} -> logged
GET  /api/verse/x.y    one verse
GET  /healthz
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import Engine
from .guard import AnswerCache, DailyBudget, RateLimiter
from . import live
from .kb import KnowledgeBase
from .lang import detect
from .llm import Gemini
from .safety import triage

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("parth")
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Parth", version="2.0", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_kb = KnowledgeBase.load()
_gemini = Gemini()
engine = Engine(_kb, _gemini if _gemini.available else None)
budget, limiter, cache = DailyBudget(), RateLimiter(), AnswerCache()
voice_budget = DailyBudget(int(os.environ.get("PARTH_DAILY_VOICE_LIMIT", "100")))
voice_limiter = RateLimiter(per_minute=3)

RATE_MSG = {
    "en": "You're asking very quickly. Please wait a minute and try again.",
    "hi": "आप बहुत जल्दी-जल्दी पूछ रहे हैं। कृपया एक मिनट बाद फिर कोशिश करें।",
    "hinglish": "Aap bahut jaldi-jaldi pooch rahe hain. Please ek minute baad phir try kariye.",
}


class Ask(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


class Triage(BaseModel):
    text: str = Field(max_length=4000)


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


@app.post("/api/live/token")
async def live_token(request: Request, attempt: int = 0):
    if not _gemini.available:
        return JSONResponse({"error": "voice_unavailable"}, status_code=503)
    if not voice_limiter.allow(_client(request)):
        return JSONResponse({"error": "rate_limited"}, status_code=429)
    if attempt == 0 and not voice_budget.take():
        return JSONResponse({"error": "daily_limit"}, status_code=429)
    model = live.LIVE_MODELS[min(attempt, len(live.LIVE_MODELS) - 1)]
    try:
        token = await asyncio.to_thread(live.mint_token, _gemini.key, model)
    except Exception as exc:  # the SDK raises several error types; the page falls back to typing
        log.warning("live token failed for %s: %s", model, exc)
        return JSONResponse({"error": "token_failed"}, status_code=502)
    return {"token": token, "model": model, "ws_url": live.WS_URL, "session_minutes": live.SESSION_MINUTES,
            "more_models": attempt + 1 < len(live.LIVE_MODELS)}


@app.get("/api/verses")
def verses(q: str, k: int = 3) -> dict:
    """Verified verses for a situation: what the voice model may quote and what the page shows."""
    cands, sits = engine.retriever.search(q[:500], k=max(1, min(k, 5)))
    out = []
    for c in cands:
        card = engine._card(c.verse)
        ch = _kb.chapters[c.verse.chapter]
        out.append({**{f: getattr(card, f) for f in ("id", "ref", "chapter", "chapter_name", "chapter_name_sanskrit",
                                                    "speaker", "addressed_to", "sanskrit", "transliteration",
                                                    "translation", "translation_source")},
                    "chapter_theme": ch["meaning"]})
    log.info("find_verses q=%r -> %s", q[:200], [v["id"] for v in out])
    return {"verses": out, "situations": sits,
            "note": "Quote translations exactly as given. If none fit, say the Gita does not address this directly."}


@app.post("/api/triage")
def check(body: Triage) -> dict:
    lang = detect(body.text)
    t = triage(body.text, lang)
    if t.kind != "ok":
        log.warning("voice triage: %s", t.kind)
    return {"kind": t.kind, "lang": lang, "message": t.message}


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
