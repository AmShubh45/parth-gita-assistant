"""Voices on disk. Every piece of speech is fetched once, kept in live/cache, and reused forever, so after
the first few days the recitation costs nothing. New verse recordings are limited per day."""
from __future__ import annotations

import asyncio
import datetime as dt
import hashlib
import json
import logging
import struct
from pathlib import Path

log = logging.getLogger("gitalive.audio")


def key(text: str, lang: str) -> str:
    return hashlib.sha256(f"{lang}|{text}".encode()).hexdigest()[:24]


def wav_seconds(data: bytes) -> float:
    """Duration of a PCM WAV from its header (falls back to 24 kHz mono 16-bit)."""
    try:
        if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
            channels, rate = struct.unpack("<HI", data[22:28])
            bits = struct.unpack("<H", data[34:36])[0]
            return max(0.0, (len(data) - 44) / (rate * channels * bits / 8))
    except struct.error:
        pass
    return max(0.0, (len(data) - 44) / 48000)


class AudioCache:
    def __init__(self, folder: Path, sarathi, recite_per_day: int = 200):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)
        self.sarathi = sarathi
        self.recite_per_day = recite_per_day
        self._meter = folder / "recite_meter.json"
        self._inflight: dict[str, asyncio.Future] = {}   # one fetch per piece, even when asked twice at once

    def path(self, item: dict, lang: str) -> Path:
        return self.folder / f"{key(item['text'], lang)}.wav"

    def cached(self, item: dict, lang: str) -> bool:
        return self.path(item, lang).exists()

    # ---- the daily allowance for new verse recordings
    def _used_today(self) -> int:
        try:
            m = json.loads(self._meter.read_text())
            return m["used"] if m.get("day") == dt.date.today().isoformat() else 0
        except (OSError, ValueError, KeyError):
            return 0

    def _spend(self) -> None:
        self._meter.write_text(json.dumps({"day": dt.date.today().isoformat(), "used": self._used_today() + 1}))

    def can_record(self) -> bool:
        return self._used_today() < self.recite_per_day

    async def get(self, item: dict, lang: str, recitation: bool = False) -> tuple[str, float] | None:
        """(URL path for the overlay, seconds) or None when there is no voice for it (yet)."""
        p = self.path(item, lang)
        if not p.exists() and p.name in self._inflight:
            return await asyncio.shield(self._inflight[p.name])
        fut = asyncio.get_running_loop().create_future()
        self._inflight[p.name] = fut
        try:
            res = await self._get(p, item, lang, recitation)
        except BaseException as exc:
            fut.set_result(None)
            raise exc
        finally:
            self._inflight.pop(p.name, None)
        if not fut.done():
            fut.set_result(res)
        return res

    async def _get(self, p: Path, item: dict, lang: str, recitation: bool) -> tuple[str, float] | None:
        if not p.exists():
            if recitation:
                if not self.can_record():
                    return None
                self._spend()
            data = await self.sarathi.speak(item, lang)
            if not data:
                return None
            tmp = p.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(p)
        data = p.read_bytes()
        return f"/audio/{p.name}", wav_seconds(data)
