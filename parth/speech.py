"""Speaking answers aloud: the spoken script and Gemini text-to-speech.

The script is built from the verified answer (never from new model text), in the person's language.
Audio comes from Gemini TTS, cached and capped per day. When TTS is unavailable the page reads the
same script with the browser's own voice, so an answer is always spoken."""
from __future__ import annotations

import base64
import hashlib
import hmac
import io
import logging
import os
import time
import wave
from collections import OrderedDict

import httpx

from .kb import SPEAKER_HI

log = logging.getLogger(__name__)
_API = "https://generativelanguage.googleapis.com/v1beta"
TTS_MODELS = tuple(m.strip() for m in os.environ.get(
    "PARTH_TTS_MODEL", "gemini-3.8-flash-lite-tts,gemini-3.8-flash-tts,gemini-3.1-flash-tts-preview,gemini-2.5-flash-preview-tts"
).split(",") if m.strip())
VOICE = os.environ.get("PARTH_TTS_VOICE", "Charon")
STYLE = {
    "hi": "Read this in calm, warm, natural Hindi, like a wise elder speaking gently to someone who is troubled:",
    "hinglish": "Read this in calm, warm, natural Hindi (it is written in Roman letters), like a wise elder speaking gently:",
    "en": "Read this in a calm, warm, gentle voice with an Indian English accent, like a wise elder speaking to someone who is troubled:",
}


def segments(answer: dict) -> list[str]:
    """What to say for an answer, in its language, as short pieces spoken one after another
    (the first piece is ready quickly, the rest are prepared while it plays). Uses only the answer's own fields."""
    lang = answer.get("lang", "en")
    kind = answer.get("kind")
    out = [answer.get("opening", "")]
    if kind in ("answer", "fallback"):
        for v in answer.get("verses", []):
            num = v["ref"].split(".")[1]
            if lang == "hi":
                head = f"अध्याय {v['chapter']}, श्लोक {num} में {SPEAKER_HI.get(v['speaker'], v['speaker'])} कहते हैं।"
            elif lang == "hinglish":
                head = f"Adhyay {v['chapter']}, shlok {num} mein {v['speaker']} kehte hain."
            else:
                head = f"In chapter {v['chapter']}, verse {num}, {v['speaker']} says:"
            # with an explanation: its meaning and what it means for you; without one: the authentic translation itself
            body = [v.get("meaning", ""), v.get("application", "")] if kind == "answer" else [v.get("translation", "")]
            out.append(" ".join(p.strip() for p in [head, *body] if p and p.strip()))
        out.append(answer.get("closing", ""))
    return [p.strip() for p in out if p and p.strip()]


def script(answer: dict) -> str:
    return " ".join(segments(answer))


def sign(key: str, lang: str, text: str) -> str:
    """Only text this server wrote can be spoken through /api/speak (it is not a free text-to-speech service)."""
    secret = hashlib.sha256(b"gita-sarathi-speak|" + key.encode()).digest()
    return hmac.new(secret, f"{lang}|{text}".encode(), hashlib.sha256).hexdigest()[:32]


def speech_items(answer: dict, key: str) -> list[dict]:
    lang = answer.get("lang", "en")
    return [{"text": t, "sig": sign(key, lang, t)} for t in segments(answer)]


def wav(pcm: bytes, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


class Speaker:
    """Gemini TTS with a model fallback chain, an LRU cache and a daily cap."""

    def __init__(self, api_key: str, daily_limit: int | None = None, cache_size: int = 300):
        self.key = api_key
        self.limit = daily_limit if daily_limit is not None else int(os.environ.get("PARTH_DAILY_TTS_LIMIT", "600"))
        self.day, self.used = "", 0
        self.cache: OrderedDict[str, bytes] = OrderedDict()
        self.cache_size = cache_size
        self._dead: dict[str, float] = {}

    def _take(self) -> bool:
        today = time.strftime("%Y-%m-%d", time.gmtime())
        if today != self.day:
            self.day, self.used = today, 0
        if self.used >= self.limit:
            return False
        self.used += 1
        return True

    async def speak(self, text: str, lang: str) -> bytes | None:
        """WAV bytes, or None (no key, cap reached, or every model failed): the page then uses its own voice."""
        text = (text or "").strip()[:2500]
        if not text or not self.key:
            return None
        k = hashlib.sha256(f"{VOICE}|{lang}|{text}".encode()).hexdigest()
        if k in self.cache:
            self.cache.move_to_end(k)
            return self.cache[k]
        if not self._take():
            return None
        prompt = f"{STYLE.get(lang, STYLE['en'])}\n\n{text}"
        async with httpx.AsyncClient(timeout=40) as client:
            for model in TTS_MODELS:
                if time.monotonic() - self._dead.get(model, -1e9) < 3600:
                    continue
                payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
                           "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {
                               "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": VOICE}}}}}
                try:
                    r = await client.post(f"{_API}/models/{model}:generateContent",
                                          headers={"x-goog-api-key": self.key}, json=payload)
                except httpx.HTTPError as exc:
                    log.warning("tts %s network error: %s", model, type(exc).__name__)
                    continue
                if r.status_code in (404, 400) or r.status_code == 429:
                    self._dead[model] = time.monotonic()
                    log.info("tts %s unavailable (%s): %s", model, r.status_code, r.text[:160])
                    continue
                if r.status_code >= 400:
                    log.warning("tts %s HTTP %s", model, r.status_code)
                    continue
                try:
                    part = next(p for p in r.json()["candidates"][0]["content"]["parts"] if "inlineData" in p)
                    pcm = base64.b64decode(part["inlineData"]["data"])
                    mime = part["inlineData"].get("mimeType", "")
                    rate = int(mime.split("rate=")[1].split(";")[0]) if "rate=" in mime else 24000
                except (KeyError, IndexError, StopIteration, ValueError):
                    log.warning("tts %s returned no audio", model)
                    continue
                audio = wav(pcm, rate)
                self.cache[k] = audio
                while len(self.cache) > self.cache_size:
                    self.cache.popitem(last=False)
                log.info("tts ok model=%s chars=%d bytes=%d", model, len(text), len(audio))
                return audio
        return None
