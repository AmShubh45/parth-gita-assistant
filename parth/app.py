"""HTTP API and the web page.

GET  /                 the Gita Sarathi web app
POST /api/ask          {"question": "..."} -> grounded answer (JSON), with the pieces to speak it
POST /api/voice        {"audio": base64 WAV, "history": [...]} -> transcript + grounded answer, to be spoken
POST /api/speak        {"text", "lang", "sig"} -> WAV of a piece of an answer this server wrote (204: use the browser voice)
POST /api/live/token   ephemeral, config-locked token for a real-time Gemini Live session (beta)
GET  /api/recite       every verse with its signed recitation piece, for the YouTube live stream
                       (the stream's laptop sends X-Live-Token: it gets its own AI and TTS budgets)
GET  /api/verses?q=    verified verses for the voice model's find_verses tool (and the page's cards)
POST /api/triage       {"text": "..."} -> crisis check on what the person said
POST /api/live/event   voice-session milestones from the page, logged (no audio, no transcripts)
POST /api/feedback     {"question", "verse", "helpful"} -> logged
GET  /api/verse/x.y    one verse
GET  /healthz
"""
from __future__ import annotations

import asyncio
import base64
import hmac
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import Engine
from .guard import AnswerCache, DailyBudget, RateLimiter
from . import live, speech
from .kb import SPEAKER_HI, KnowledgeBase
from .lang import detect
from .llm import Gemini, LLMError
from .safety import triage

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("parth")
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Gita Sarathi", version="2.1", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_kb = KnowledgeBase.load()
_gemini = Gemini()
engine = Engine(_kb, _gemini if _gemini.available else None)
budget, limiter, cache = DailyBudget(), RateLimiter(), AnswerCache()
voice_budget = DailyBudget(int(os.environ.get("PARTH_DAILY_VOICE_LIMIT", "100")))
voice_limiter = RateLimiter(per_minute=3)
event_limiter = RateLimiter(per_minute=60)
speaker = speech.Speaker(_gemini.key)
turn_limiter = RateLimiter(per_minute=6)     # spoken questions per visitor per minute
speak_limiter = RateLimiter(per_minute=40)   # spoken answer pieces per visitor per minute
MAX_WAV = 1_100_000                           # about 34 s of 16 kHz mono 16-bit audio
# The YouTube live stream (live/ on the streaming laptop) identifies itself with this shared secret and gets
# separate budgets, so the stream never uses up website visitors' answers or voice, and vice versa.
LIVE_TOKEN = os.environ.get("PARTH_LIVE_TOKEN", "").strip()
live_budget = DailyBudget(int(os.environ.get("PARTH_LIVE_AI_LIMIT", "100")))
live_speaker = speech.Speaker(_gemini.key, daily_limit=int(os.environ.get("PARTH_LIVE_TTS_LIMIT", "300")))
live_limiter = RateLimiter(per_minute=60)

RATE_MSG = {
    "en": "You're asking very quickly. Please wait a minute and try again.",
    "hi": "आप बहुत जल्दी-जल्दी पूछ रहे हैं। कृपया एक मिनट बाद फिर कोशिश करें।",
    "hinglish": "Aap bahut jaldi-jaldi pooch rahe hain. Please ek minute baad phir try kariye.",
}


class Ask(BaseModel):
    question: str = Field(min_length=2, max_length=2000)
    history: list[str] = Field(default_factory=list, max_length=6)  # earlier questions, for follow-ups
    lang: str | None = Field(default=None, pattern="^(hi|hinglish|en)$")  # answer language; None: the question's own


class Voice(BaseModel):
    audio: str = Field(min_length=100, max_length=1_500_000)  # base64 WAV
    history: list[str] = Field(default_factory=list, max_length=6)
    lang: str | None = Field(default=None, pattern="^(hi|hinglish|en)$")


class Speak(BaseModel):
    text: str = Field(min_length=1, max_length=2500)
    lang: str = Field(pattern="^(en|hi|hinglish)$")
    sig: str = Field(max_length=64)


class Triage(BaseModel):
    text: str = Field(max_length=4000)


LIVE_EVENTS = {"token_ok", "token_error", "start_error", "mic_denied", "setup_complete", "first_audio_sent",
               "first_server_content", "tool_call", "no_mic_level", "go_away", "closed", "turn_summary", "unknown_keys",
               "user_interrupt", "echo_ignored", "voice_error", "tts_fallback"}


class LiveEvent(BaseModel):
    sid: str = Field(max_length=40)
    event: str = Field(max_length=40)
    detail: str = Field(default="", max_length=300)


class Feedback(BaseModel):
    question: str = Field(max_length=2000)
    verse: str = Field(max_length=20)
    helpful: bool


def _client(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return fwd.split(",")[0].strip() or (request.client.host if request.client else "?")


def _broadcaster(request: Request) -> bool:
    got = request.headers.get("x-live-token", "")
    return bool(LIVE_TOKEN) and hmac.compare_digest(got.encode(), LIVE_TOKEN.encode())


def _history(items: list[str]) -> list[str]:
    return [h.strip()[:300] for h in items if h and h.strip()][-2:]


def _sign_key() -> str:
    return _gemini.key or "no-key"


def _cache_key(question: str, lang: str | None) -> str:
    return f"{lang} {question}" if lang else question


def _public(ans) -> dict:
    """An answer as the page receives it: no internal trace, plus the pieces to speak it aloud.
    A fallback says briefly why (shown only in the page's debug log)."""
    out = ans.to_dict()
    trace = out.pop("trace", None) or {}
    if ans.kind == "fallback":
        out["why"] = str(trace.get("fallback_reason", ""))[:120]
    out["speech"] = speech.speech_items(out, _sign_key())
    return out


@app.get("/")
def home() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "answerable_verses": len(_kb.answerable), "model": bool(engine.llm),
            "ai_answers_today": budget.used, "ai_daily_limit": budget.limit, "tts_today": speaker.used,
            "live_stream": {"enabled": bool(LIVE_TOKEN), "ai_today": live_budget.used, "tts_today": live_speaker.used}}


@app.post("/api/ask")
async def ask(body: Ask, request: Request):
    live = _broadcaster(request)
    if not (live_limiter.allow("live") if live else limiter.allow(_client(request))):
        return JSONResponse({"kind": "rate_limited", "lang": detect(body.question),
                             "opening": RATE_MSG[detect(body.question)], "verses": []}, status_code=429)
    history = _history(body.history)
    cached = None if history else cache.get(_cache_key(body.question, body.lang))
    if cached:
        return cached
    use_model = bool(engine.llm) and (live_budget if live else budget).take()
    ans = await engine.answer(body.question, use_model=use_model, history=history, lang=body.lang)
    log.info("ask kind=%s lang=%s model=%s trace=%s", ans.kind, ans.lang, use_model, ans.trace)
    out = _public(ans)
    if ans.kind == "answer" and not history:
        cache.put(_cache_key(body.question, body.lang), out)
    return out


@app.post("/api/voice")
async def voice(body: Voice, request: Request):
    """A spoken question: one model call transcribes and understands it, then the same grounded
    engine as typed questions answers it. The page speaks the answer with /api/speak."""
    if not engine.llm:
        return JSONResponse({"error": "voice_unavailable"}, status_code=503)
    if not turn_limiter.allow(_client(request)):
        return JSONResponse({"error": "rate_limited"}, status_code=429)
    try:
        audio = base64.b64decode(body.audio, validate=True)
    except ValueError:
        return JSONResponse({"error": "bad_audio"}, status_code=400)
    if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE" or not 44 + 8000 <= len(audio) <= MAX_WAV:
        return JSONResponse({"error": "bad_audio"}, status_code=400)
    if not budget.take():
        return JSONResponse({"error": "daily_limit"}, status_code=429)
    history = _history(body.history)
    try:
        u = await engine.understand_audio(audio, history)
    except LLMError as exc:
        log.warning("voice transcription failed: %s", exc)
        return JSONResponse({"error": "transcribe_failed"}, status_code=502)
    transcript = (u.get("transcript") or "").strip()[:2000]
    if len(transcript) < 2:
        return {"transcript": "", "error": "no_speech"}

    async def lines():
        # the transcript goes out at once, so the page shows what it heard while the answer is written
        yield json.dumps({"transcript": transcript}, ensure_ascii=False) + "\n"
        out = None if history else cache.get(_cache_key(transcript, body.lang))
        if out is None:
            ans = await engine.answer(transcript, use_model=True, understanding=u, history=history, lang=body.lang)
            log.info("voice kind=%s lang=%s secs=%.1f trace=%s", ans.kind, ans.lang, (len(audio) - 44) / 32000, ans.trace)
            out = _public(ans)
            if ans.kind == "answer" and not history:
                cache.put(_cache_key(transcript, body.lang), out)
        yield json.dumps({"answer": out}, ensure_ascii=False) + "\n"

    return StreamingResponse(lines(), media_type="application/x-ndjson", headers={"Cache-Control": "no-store"})


@app.post("/api/speak")
async def speak(body: Speak, request: Request):
    if not hmac.compare_digest(body.sig, speech.sign(_sign_key(), body.lang, body.text)):
        return JSONResponse({"error": "unknown_text"}, status_code=403)
    live = _broadcaster(request)
    if not (live_limiter.allow("live-speak") if live else speak_limiter.allow(_client(request))):
        return JSONResponse({"error": "rate_limited"}, status_code=429)
    audio = await (live_speaker if live else speaker).speak(body.text, body.lang)
    if not audio:
        return Response(status_code=204)  # the page reads it with the browser's own voice
    return Response(audio, media_type="audio/wav", headers={"Cache-Control": "private, max-age=86400"})


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


@app.get("/api/recite")
def recite() -> dict:
    """Every verse in order with what the live stream shows and says. No model call; speaking it still goes
    through /api/speak and its budgets."""
    out = []
    for v in sorted(_kb.verses.values(), key=lambda x: (x.chapter, int(x.ref.split(".")[1]))):
        ch = _kb.chapters[v.chapter]
        text = speech.recitation(v, ch["name_en"])
        out.append({"id": v.id, "ref": v.ref, "chapter": v.chapter, "verse": int(v.ref.split(".")[1]),
                    "chapter_name": ch["name_en"], "chapter_name_sanskrit": ch["name_sanskrit"],
                    "speaker": v.speaker, "addressed_to": v.addressed_to,
                    "speaker_hindi": SPEAKER_HI.get(v.speaker, v.speaker),
                    "listener_hindi": SPEAKER_HI.get(v.addressed_to, v.addressed_to),
                    "sanskrit": v.sanskrit, "transliteration": v.transliteration, "translation": v.translation or "",
                    "translation_source": "Swami Swarupananda (1909)" if v.translation else "",
                    "speech": [{"text": text, "lang": "en", "sig": speech.sign(_sign_key(), "en", text)}]})
    return {"count": len(out), "verses": out}


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
                    "chapter_theme": ch["meaning"], "speaker_hindi": SPEAKER_HI.get(card.speaker, card.speaker),
                    "listener_hindi": SPEAKER_HI.get(card.addressed_to, card.addressed_to)})
    log.info("find_verses q=%r -> %s", q[:200], [v["id"] for v in out])
    return {"verses": out, "situations": sits,
            "note": ("The translation is English. In an English conversation quote it exactly as given. In a Hindi or "
                     "Hinglish conversation do not read the English aloud: explain the verse in simple Hindi in your own "
                     "words, faithful to it, and say the exact translation is on screen. If none fit, say the Gita does "
                     "not address this directly.")}


@app.post("/api/triage")
def check(body: Triage) -> dict:
    lang = detect(body.text)
    t = triage(body.text, lang)
    if t.kind != "ok":
        log.warning("voice triage: %s", t.kind)
    return {"kind": t.kind, "lang": lang, "message": t.message}


@app.post("/api/live/event")
async def live_event(request: Request):
    """Where a voice session got to, so Render's logs show the exact step a failing session stops at."""
    try:
        ev = LiveEvent.model_validate_json(await request.body())  # sendBeacon posts raw JSON
    except Exception:
        return JSONResponse({"ok": False}, status_code=422)
    if ev.event not in LIVE_EVENTS:
        return JSONResponse({"ok": False}, status_code=422)
    if not event_limiter.allow(_client(request)):
        return JSONResponse({"ok": False}, status_code=429)
    log.info("live_event sid=%s event=%s detail=%s", ev.sid, ev.event, ev.detail.replace("\n", " "))
    return {"ok": True}


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
