"""Talking to the Gita Sarathi server: verses to recite, grounded answers, and voices."""
from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx

log = logging.getLogger("gitalive.sarathi")


class SarathiError(Exception):
    pass


class Sarathi:
    def __init__(self, base_url: str, live_token: str = "", transport: httpx.AsyncBaseTransport | None = None):
        headers = {"X-Live-Token": live_token} if live_token else {}
        # Render's free plan sleeps when idle; the first request can take about a minute to wake it.
        self.http = httpx.AsyncClient(base_url=base_url, headers=headers, timeout=httpx.Timeout(90, connect=20),
                                      transport=transport)

    async def close(self) -> None:
        await self.http.aclose()

    async def recitation(self, cache_file: Path | None = None) -> list[dict]:
        """Every verse in order (cached on disk, so a restart needs no server)."""
        try:
            r = await self.http.get("/api/recite")
            r.raise_for_status()
            verses = r.json()["verses"]
            if cache_file:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps(verses, ensure_ascii=False), encoding="utf-8")
            return verses
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            if cache_file and cache_file.exists():
                log.warning("server unreachable (%s); using the saved verse list", type(exc).__name__)
                return json.loads(cache_file.read_text(encoding="utf-8"))
            raise SarathiError(f"could not load verses: {exc}") from exc

    async def ask(self, question: str) -> dict:
        try:
            r = await self.http.post("/api/ask", json={"question": question})
        except httpx.HTTPError as exc:
            raise SarathiError(f"network: {type(exc).__name__}") from exc
        if r.status_code == 429:
            raise SarathiError("rate_limited")
        if r.status_code >= 400:
            raise SarathiError(f"HTTP {r.status_code}")
        return r.json()

    async def speak(self, item: dict, lang: str) -> bytes | None:
        """WAV for one signed piece, or None when the server has no voice to give (budget, outage)."""
        try:
            r = await self.http.post("/api/speak", json={"text": item["text"], "lang": lang, "sig": item["sig"]})
        except httpx.HTTPError as exc:
            log.warning("speak failed: %s", type(exc).__name__)
            return None
        if r.status_code == 200 and r.content[:4] == b"RIFF":
            return r.content
        if r.status_code not in (204,):
            log.warning("speak HTTP %s", r.status_code)
        return None

    async def ping(self) -> bool:
        try:
            return (await self.http.get("/healthz", timeout=90)).status_code == 200
        except httpx.HTTPError:
            return False

    async def health(self) -> dict:
        r = await self.http.get("/healthz")
        r.raise_for_status()
        return r.json()
