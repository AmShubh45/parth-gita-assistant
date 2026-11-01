"""Speaking answers aloud: the spoken script and Gemini text-to-speech.

The script is built from the verified answer (never from new model text), in the answer's language
only: a Hindi answer is never read with English in it. Audio comes from Gemini TTS with one fixed
voice, cached, capped per day and loudness-normalised. Only the answer text is sent to TTS (a style
instruction in front of it gets read aloud). When TTS is unavailable the page reads the same script
with the browser's own voice, so an answer is always spoken."""
from __future__ import annotations

import base64
import array
import hashlib
import hmac
import io
import logging
import os
import re
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
ON_SCREEN = {"hi": "इसका अनुवाद स्क्रीन पर लिखा है।", "hinglish": "Iska anuvaad screen par likha hai."}


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
            if kind == "answer":      # its meaning and what it means for you, in the answer's language
                body = [v.get("meaning", ""), v.get("application", "")]
            elif lang == "en":        # no explanation available: the authentic translation itself
                body = [v.get("translation", "")]
            else:                     # Hindi/Hinglish without an explanation: the Sanskrit, never the English
                sp, to = SPEAKER_HI.get(v["speaker"], v["speaker"]), SPEAKER_HI.get(v["addressed_to"], v["addressed_to"])
                head = (f"अध्याय {v['chapter']}, श्लोक {num} में {sp} {to} से कहते हैं:" if lang == "hi" else
                        f"Adhyay {v['chapter']}, shlok {num} mein {v['speaker']} {v['addressed_to']} se kehte hain:")
                body = [_shloka(v.get("sanskrit", "")), ON_SCREEN[lang]]
            out.append(" ".join(p.strip() for p in [head, *body] if p and p.strip()))
        out.append(answer.get("closing", ""))
    return [p.strip() for p in out if p and p.strip()]


def _shloka(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[।॥]+", "।", text)).strip()


def script(answer: dict) -> str:
    return " ".join(segments(answer))


def sign(key: str, lang: str, text: str) -> str:
    """Only text this server wrote can be spoken through /api/speak (it is not a free text-to-speech service)."""
    secret = hashlib.sha256(b"gita-sarathi-speak|" + key.encode()).digest()
    return hmac.new(secret, f"{lang}|{text}".encode(), hashlib.sha256).hexdigest()[:32]


def speech_items(answer: dict, key: str) -> list[dict]:
    lang = answer.get("lang", "en")
    return [{"text": t, "sig": sign(key, lang, t)} for t in segments(answer)]


def louder(pcm: bytes, peak_to: float = 0.89) -> bytes:
    """Peak-normalise 16-bit PCM to about -1 dBFS (gain capped at 8x), so answers are not quiet."""
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) // 2 * 2])
    peak = max((abs(x) for x in a), default=0)
    if not peak:
        return pcm
    g = min(8.0, peak_to * 32767 / peak)
    if 0.95 < g < 1.05:
        return pcm
    return array.array("h", (max(-32768, min(32767, int(x * g))) for x in a)).tobytes()


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
        self.preferred = ""  # the model that last worked: kept first, so the voice does not change between pieces

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
        order = sorted(TTS_MODELS, key=lambda m: m != self.preferred)
        async with httpx.AsyncClient(timeout=40) as client:
            for model in order:
                if time.monotonic() - self._dead.get(model, -1e9) < 3600:
                    continue
                payload = {"contents": [{"role": "user", "parts": [{"text": text}]}],
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
                audio = wav(louder(pcm), rate)
                self.preferred = model
                self.cache[k] = audio
                while len(self.cache) > self.cache_size:
                    self.cache.popitem(last=False)
                log.info("tts ok model=%s chars=%d bytes=%d", model, len(text), len(audio))
                return audio
        return None
