"""HTTP API. POST /api/ask {"question": "..."} returns the grounded answer as JSON."""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .engine import Engine
from .kb import KnowledgeBase
from .llm import Gemini

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
app = FastAPI(title="Parth", version="2.0")
_kb = KnowledgeBase.load()
_gemini = Gemini()
engine = Engine(_kb, _gemini if _gemini.available else None)


class Ask(BaseModel):
    question: str = Field(min_length=2, max_length=2000)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "answerable_verses": len(_kb.answerable), "model": bool(engine.llm)}


@app.post("/api/ask")
async def ask(body: Ask) -> dict:
    ans = await engine.answer(body.question)
    out = ans.to_dict()
    out.pop("trace", None)  # internal: logged, not returned
    logging.getLogger("parth.ask").info("kind=%s lang=%s trace=%s", ans.kind, ans.lang, ans.trace)
    return out


@app.get("/api/verse/{ref}")
def verse(ref: str) -> dict:
    v = _kb.get(ref)
    if not v:
        raise HTTPException(404, "No such verse")
    return {"id": v.id, "speaker": v.speaker, "addressed_to": v.addressed_to, "sanskrit": v.sanskrit,
            "transliteration": v.transliteration, "translation": v.translation,
            "translation_status": "verified" if v.translation else "under review"}
