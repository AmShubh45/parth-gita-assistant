"""What goes on air, and when. The conductor recites the Gita verse by verse and, between verses, answers
viewers' questions. Overlay pages are players: they show what they are sent, play its voice, and say when
they have finished (if no page is connected, the conductor keeps time itself)."""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from .audio import AudioCache
from .moderation import Moderator, Question
from .sarathi import Sarathi, SarathiError

log = logging.getLogger("gitalive.conductor")
VERSE_FIELDS = ("id", "ref", "chapter", "verse", "chapter_name", "chapter_name_sanskrit", "speaker", "addressed_to",
                "speaker_hindi", "listener_hindi", "sanskrit", "transliteration", "translation", "translation_source")
CARD_FIELDS = ("id", "ref", "chapter", "chapter_name", "chapter_name_sanskrit", "speaker", "addressed_to", "sanskrit",
               "transliteration", "translation", "translation_source", "context", "meaning", "application")


class Hub:
    """Where things go on air. In OBS mode: the overlay pages connected over WebSocket (a page says when it has
    finished). In cloud mode a player (broadcast.LocalPlayer) renders and voices each item itself; preview pages
    still receive everything."""

    def __init__(self, player=None) -> None:
        self.player = player
        self.clients: set = set()
        self.current: dict | None = None
        self.queue_msg: dict = {"type": "queue", "waiting": []}
        self.config: dict = {"type": "config", "music": False, "trigger": "@gitalive"}
        self._done: dict[str, asyncio.Event] = {}

    async def send_all(self, msg: dict) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_json(msg)
            except Exception:
                self.clients.discard(ws)

    async def join(self, ws) -> None:
        self.clients.add(ws)
        await ws.send_json(self.config)
        await ws.send_json(self.queue_msg)
        if self.current:
            await ws.send_json({**self.current, "late": True})

    def page_done(self, item_id: str) -> None:
        ev = self._done.get(item_id)
        if ev:
            ev.set()

    async def show(self, item: dict, seconds: float) -> None:
        """Put an item on air and wait until a page has played it (or, with no page, for its length)."""
        self.current = item
        if self.player:
            await self.send_all(item)
            await self.player.play(item, seconds)
            return
        ev = self._done[item["id"]] = asyncio.Event()
        try:
            await self.send_all(item)
            if not self.clients:
                await asyncio.sleep(seconds)
                return
            try:
                await asyncio.wait_for(ev.wait(), seconds + 15)
            except asyncio.TimeoutError:
                log.info("no page reported the end of %s; moving on", item["id"])
        finally:
            self._done.pop(item["id"], None)

    async def announce(self, item: dict) -> None:
        """Show something without waiting for it to finish (e.g. "Asha asks …" while the answer is written)."""
        self.current = item
        await self.send_all(item)
        if self.player:
            await asyncio.to_thread(self.player.r.build_scene, item)

    async def queue(self, waiting: list[str], answered: list[str] | None = None) -> None:
        self.queue_msg = {"type": "queue", "waiting": waiting}
        await self.send_all(self.queue_msg)
        if self.player:
            await asyncio.to_thread(self.player.r.set_queue, waiting, answered)


def reading_seconds(*texts: str) -> float:
    n = sum(len(t or "") for t in texts)
    return max(15.0, min(90.0, n / 14))


class Conductor:
    def __init__(self, sarathi: Sarathi, audio: AudioCache, hub: Hub, moderator: Moderator, state_file: Path,
                 verse_cache: Path, silent_seconds: float = 20.0):
        self.sarathi, self.audio, self.hub, self.mod = sarathi, audio, hub, moderator
        self.state_file, self.verse_cache, self.silent = state_file, verse_cache, silent_seconds
        self.verses: list[dict] = []
        self.pos = 0
        self.n = 0
        self.status = "starting"
        self.answered = 0
        self.recent: list[str] = []      # who was answered last, newest first (shown on the vertical stream)

    # ---- recitation
    async def load(self) -> None:
        self.verses = await self.sarathi.recitation(self.verse_cache)
        try:
            self.pos = int(json.loads(self.state_file.read_text())["pos"]) % len(self.verses)
        except (OSError, ValueError, KeyError):
            self.pos = 0
        log.info("%d verses loaded; resuming at %s", len(self.verses), self.verses[self.pos]["id"])

    def _save(self) -> None:
        try:
            self.state_file.write_text(json.dumps({"pos": self.pos}))
        except OSError:
            pass

    def _playable(self, v: dict) -> bool:
        return self.audio.cached(v["speech"][0], "en") or self.audio.can_record()

    def pick(self, advance: bool = True) -> int:
        """Index of the next verse to recite: the next one in order that has (or can get) a voice today.
        Verses without a recording yet are skipped while others have one; they fill in day by day."""
        total = len(self.verses)
        for step in range(total):
            i = (self.pos + step) % total
            if self._playable(self.verses[i]):
                break
        else:
            i = self.pos  # nothing has a voice yet: show verses silently, in order
        if advance:
            self.pos = (i + 1) % total
            self._save()
        return i

    async def recite(self, i: int) -> None:
        v = self.verses[i]
        got = await self.audio.get(v["speech"][0], "en", recitation=True)
        self.n += 1
        item = {"type": "verse", "id": f"v{self.n}-{v['id']}", "verse": {k: v.get(k) for k in VERSE_FIELDS},
                "audio": [got[0]] if got else [], "seconds": (got[1] if got else self.silent),
                "progress": {"index": i + 1, "total": len(self.verses)}}
        self.status = f"reciting {v['id']}" + ("" if got else " (silent)")
        nxt = self.pick(advance=False)    # prepare the next verse's voice while this one plays
        prefetch = asyncio.create_task(self.audio.get(self.verses[nxt]["speech"][0], "en", recitation=True))
        prefetch.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        await self.hub.show(item, item["seconds"] + 2)

    # ---- viewer questions
    def offer(self, m: dict) -> bool:
        """A chat message from YouTube (or the preview page). True if it was queued as a question."""
        q = self.mod.offer(m["id"], m["author"], m.get("channel", m["author"]), m["text"],
                           superchat=m.get("superchat", False), staff=m.get("staff", False))
        if q:
            log.info("question from %s queued (%d waiting)", q.author, len(self.mod.queue))
            try:
                asyncio.get_running_loop().create_task(self.hub.queue(self.mod.waiting(), self.recent))
            except RuntimeError:   # called outside the event loop: the next item refreshes the queue
                pass
        return q is not None

    async def answer(self, q: Question) -> None:
        self.n += 1
        base = {"id": f"q{self.n}", "name": q.author, "question": q.text}
        self.status = f"answering {q.author}"
        await self.hub.queue(self.mod.waiting(), self.recent)
        await self.hub.announce({"type": "asking", **base})
        try:
            a = await self.sarathi.ask(q.text)
        except SarathiError as exc:
            log.warning("could not answer %s: %s", q.author, exc)
            if str(exc) == "rate_limited":
                self.mod.queue.insert(0, q)
                await asyncio.sleep(30)
            return
        pieces = await asyncio.gather(*(self.audio.get(p, a.get("lang", "en")) for p in a.get("speech", [])))
        audio = [u for u in pieces if u]
        texts = [a.get("opening", ""), a.get("closing", "")] + [c.get("meaning", "") + c.get("application", "")
                                                                 for c in a.get("verses", [])]
        seconds = sum(s for _, s in audio) if len(audio) == len(pieces) and audio else reading_seconds(*texts)
        item = {"type": "answer", **base, "seconds": seconds, "audio": [u for u, _ in audio] if len(audio) == len(pieces) else [],
                "answer": {"kind": a.get("kind"), "lang": a.get("lang"), "opening": a.get("opening", ""),
                           "closing": a.get("closing", ""), "note": a.get("note", ""),
                           "meaning_label": a.get("meaning_label", ""),
                           "verses": [{k: c.get(k, "") for k in CARD_FIELDS} for c in a.get("verses", [])[:2]]}}
        self.answered += 1
        self.recent = [q.author] + [n for n in self.recent if n != q.author][:5]
        await self.hub.show(item, seconds + 3)
        await self.hub.queue(self.mod.waiting(), self.recent)

    # ---- the loop
    async def run(self) -> None:
        while not self.verses:
            try:
                await self.load()
            except SarathiError as exc:
                self.status = f"waiting for the Gita Sarathi server: {exc}"
                log.warning("%s", self.status)
                await asyncio.sleep(30)
        while True:
            try:
                q = self.mod.next()
                if q:
                    await self.answer(q)
                else:
                    await self.recite(self.pick())
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("on-air loop error; continuing")
                await asyncio.sleep(5)

    def snapshot(self) -> dict:
        cached = sum(1 for v in self.verses if self.audio.cached(v["speech"][0], "en"))
        return {"status": self.status, "verses": len(self.verses), "verses_with_voice": cached,
                "next_verse": self.verses[self.pos]["id"] if self.verses else None, "answered": self.answered,
                "waiting": self.mod.waiting(), "rejected": self.mod.rejected, "pages": len(self.hub.clients),
                "recordings_left_today": max(0, self.audio.recite_per_day - self.audio._used_today()),
                "at": time.strftime("%H:%M:%S")}
