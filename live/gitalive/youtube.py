"""Reading YouTube live chat for questions, within the free API quota.

- Sign-in: `youtube_auth.py` saves token.json once (read-only YouTube scope). Here the access token is
  refreshed with plain HTTP when it expires, so no Google library is needed at run time.
- The live chat is found from the channel's active broadcast (liveBroadcasts.list, 1 unit).
- Messages are read with liveChatMessages.list (5 units each). YouTube gives 10,000 units a day, reset at
  midnight Pacific time. The governor spreads the day's units evenly (about one read every 45-50 s) and reads
  faster for ten minutes after a question arrives, paying for it by reading slower when chat is quiet.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

log = logging.getLogger("gitalive.youtube")
API = "https://www.googleapis.com/youtube/v3"
PACIFIC = ZoneInfo("America/Los_Angeles")
SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


class QuotaGovernor:
    COST_READ, COST_FIND = 5, 1

    def __init__(self, daily_units: int = 9000, now=None):
        self.daily = daily_units
        self.now = now or (lambda: dt.datetime.now(PACIFIC))
        self.day = self.now().date()
        self.used = 0
        self.last_question = 0.0

    def _roll(self) -> None:
        today = self.now().date()
        if today != self.day:
            self.day, self.used = today, 0

    def spend(self, units: int) -> None:
        self._roll()
        self.used += units

    def left(self) -> int:
        self._roll()
        return max(0, self.daily - self.used)

    def seconds_left_today(self) -> float:
        n = self.now()
        midnight = dt.datetime.combine(n.date() + dt.timedelta(days=1), dt.time(), tzinfo=n.tzinfo)
        return max(60.0, (midnight - n).total_seconds())

    def interval(self, server_min_s: float = 5.0, mono=time.monotonic) -> float:
        """Seconds to wait before the next chat read."""
        left = self.left()
        if left < self.COST_READ:
            return self.seconds_left_today() + 5            # out of units: wait for the reset
        even = self.seconds_left_today() * self.COST_READ / left
        busy = mono() - self.last_question < 600
        wait = even / 2 if busy else even
        return max(server_min_s, 8.0 if busy else 15.0, min(wait, 300.0))


class Token:
    """token.json from youtube_auth.py, refreshed over HTTP."""

    def __init__(self, path: Path, http: httpx.AsyncClient):
        self.path, self.http = path, http
        self.data = json.loads(path.read_text(encoding="utf-8"))
        self.expires = 0.0

    async def header(self) -> dict:
        if not self.data.get("token") or time.time() > self.expires - 60:
            await self.refresh()
        return {"Authorization": f"Bearer {self.data['token']}"}

    async def refresh(self) -> None:
        d = self.data
        r = await self.http.post(d.get("token_uri", "https://oauth2.googleapis.com/token"), data={
            "grant_type": "refresh_token", "refresh_token": d["refresh_token"],
            "client_id": d["client_id"], "client_secret": d["client_secret"]})
        if r.status_code != 200:
            raise RuntimeError(f"YouTube sign-in expired or revoked ({r.status_code}); run youtube_auth.py again")
        j = r.json()
        d["token"] = j["access_token"]
        self.expires = time.time() + int(j.get("expires_in", 3600))
        self.path.write_text(json.dumps(d), encoding="utf-8")


def parse(item: dict) -> dict | None:
    """One liveChatMessage -> {id, author, channel, text, superchat, staff}, or None for other event types."""
    sn, au = item.get("snippet", {}), item.get("authorDetails", {})
    kind = sn.get("type")
    if kind == "textMessageEvent":
        text = sn.get("textMessageDetails", {}).get("messageText") or sn.get("displayMessage", "")
    elif kind == "superChatEvent":
        text = sn.get("superChatDetails", {}).get("userComment", "")
    else:
        return None
    return {"id": item.get("id", ""), "author": au.get("displayName", "Viewer"), "channel": au.get("channelId", ""),
            "text": text or "", "superchat": kind == "superChatEvent",
            "staff": bool(au.get("isChatOwner") or au.get("isChatModerator"))}


class ChatReader:
    def __init__(self, token_file: Path, governor: QuotaGovernor, on_message, transport=None, sleep=asyncio.sleep):
        self.http = httpx.AsyncClient(timeout=30, transport=transport)
        self.token = Token(token_file, self.http)
        self.gov = governor
        self.on_message = on_message
        self.sleep = sleep
        self.chat_id = ""
        self.page = ""
        self.status = "starting"

    async def _get(self, path: str, params: dict, cost: int) -> dict:
        self.gov.spend(cost)
        r = await self.http.get(f"{API}/{path}", params=params, headers=await self.token.header())
        if r.status_code == 401:
            await self.token.refresh()
            r = await self.http.get(f"{API}/{path}", params=params, headers=await self.token.header())
        if r.status_code == 403 and "quota" in r.text.lower():
            self.gov.used = self.gov.daily       # YouTube says we are out: wait for the reset
            raise RuntimeError("YouTube API quota used up for today")
        if r.status_code >= 400:
            raise RuntimeError(f"YouTube API {path}: HTTP {r.status_code} {r.text[:160]}")
        return r.json()

    async def find_chat(self) -> str:
        j = await self._get("liveBroadcasts", {"part": "snippet", "broadcastStatus": "active",
                                               "broadcastType": "all", "maxResults": 5}, QuotaGovernor.COST_FIND)
        for b in j.get("items", []):
            cid = b.get("snippet", {}).get("liveChatId")
            if cid:
                return cid
        return ""

    async def read_once(self) -> float:
        """One read. Returns the server's minimum wait in seconds."""
        params = {"liveChatId": self.chat_id, "part": "snippet,authorDetails", "maxResults": 200}
        first = not self.page
        if self.page:
            params["pageToken"] = self.page
        j = await self._get("liveChat/messages", params, QuotaGovernor.COST_READ)
        self.page = j.get("nextPageToken", self.page)
        if not first:               # the first page is history from before we joined: skip it
            for item in j.get("items", []):
                m = parse(item)
                if m and self.on_message(m):
                    self.gov.last_question = time.monotonic()
        return j.get("pollingIntervalMillis", 5000) / 1000

    async def run(self) -> None:
        while True:
            try:
                if not self.chat_id:
                    self.status = "looking for the live broadcast"
                    self.chat_id = await self.find_chat()
                    if not self.chat_id:
                        await self.sleep(60)
                        continue
                    self.page = ""
                    log.info("reading live chat %s…", self.chat_id[:8])
                self.status = f"reading chat · {self.gov.left()} units left today"
                server_min = await self.read_once()
                await self.sleep(self.gov.interval(server_min))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                msg = str(exc)
                self.status = f"chat paused: {msg[:120]}"
                log.warning("chat: %s", msg)
                if "liveChatEnded" in msg or "liveChatNotFound" in msg or "HTTP 404" in msg:
                    self.chat_id = ""
                wait = self.gov.seconds_left_today() + 5 if "quota" in msg.lower() else 60
                await self.sleep(min(wait, 3 * 3600))
