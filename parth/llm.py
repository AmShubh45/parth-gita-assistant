"""Gemini calls that return JSON, with a model fallback chain (same approach as Samajh).

The engine talks to an `LLM` protocol, so tests use a scripted fake and production uses Gemini."""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)
_API = "https://generativelanguage.googleapis.com/v1beta"
FAST_MODELS = ("gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-flash-lite-latest", "gemini-flash-latest")
SMART_MODELS = ("gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-latest", "gemini-3.5-flash-lite")
# The verifier should be a different model from the writer where possible, so it does not share its blind spots.
CHECK_MODELS = ("gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-flash-lite-latest")


class LLMError(Exception):
    pass


class LLM(Protocol):
    async def json(self, step: str, system: str, prompt: str, schema: dict, *, smart: bool = False,
                   max_tokens: int = 800, timeout_s: float = 20.0) -> dict: ...


class Gemini:
    def __init__(self, api_key: str | None = None):
        self.key = (api_key or os.environ.get("GEMINI_API_KEY", "")).strip()
        self._exhausted: dict[str, float] = {}

    @property
    def available(self) -> bool:
        return bool(self.key)

    async def json(self, step: str, system: str, prompt: str, schema: dict, *, smart: bool = False,
                   max_tokens: int = 800, timeout_s: float = 20.0) -> dict:
        if not self.key:
            raise LLMError("GEMINI_API_KEY is not set")
        models = CHECK_MODELS if step == "verify" else (SMART_MODELS if smart else FAST_MODELS)
        last = "no Gemini model available"
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            for model in models:
                if time.monotonic() - self._exhausted.get(model, -1e9) < 3 * 3600:
                    continue
                cfg: dict[str, Any] = {"temperature": 0.3 if step == "compose" else 0.1, "maxOutputTokens": max_tokens,
                                       "responseMimeType": "application/json", "responseSchema": schema}
                if model.startswith("gemini-3"):
                    cfg["thinkingConfig"] = {"thinkingLevel": "low"}
                elif model.startswith("gemini-2.5"):
                    cfg["thinkingConfig"] = {"thinkingBudget": 0}
                payload = {"system_instruction": {"parts": [{"text": system}]},
                           "contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": cfg}
                try:
                    r = await client.post(f"{_API}/models/{model}:generateContent",
                                          headers={"x-goog-api-key": self.key}, json=payload)
                except httpx.TimeoutException:
                    last = f"{model} timed out"
                    continue
                except httpx.HTTPError as exc:
                    raise LLMError(f"network error: {type(exc).__name__}") from exc
                if r.status_code == 404 or (r.status_code == 400 and "thinking" in r.text.lower()):
                    continue
                if r.status_code >= 500:
                    last = f"{model} busy ({r.status_code})"
                    continue
                if r.status_code == 429:
                    if "PerDay" in r.text:
                        self._exhausted[model] = time.monotonic()
                    last = "Gemini quota reached"
                    continue
                if r.status_code >= 400:
                    raise LLMError(f"HTTP {r.status_code}: {r.text[:200]}")
                try:
                    cand = r.json()["candidates"][0]
                    return json.loads("".join(p.get("text", "") for p in cand["content"]["parts"]))
                except (KeyError, IndexError, ValueError) as exc:
                    raise LLMError(f"unreadable response from {model}") from exc
        raise LLMError(last)
