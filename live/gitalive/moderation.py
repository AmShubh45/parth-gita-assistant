"""Which chat messages become on-air questions, and in what order.

A message is a question when it contains a trigger (default: @gitalive, !gita, #gitalive). It is then cleaned
and checked: no links, no abuse, a sensible length, one question per viewer every few minutes, no repeats,
and a cap on answers per hour. Rejected messages are dropped quietly (never shamed on air). Super Chats and
the channel's owner and moderators go first. Crisis messages are not filtered here: the server's safety
triage answers them with helplines."""
from __future__ import annotations

import re
import time
import unicodedata
from collections import deque
from dataclasses import dataclass, field

LINK = re.compile(r"https?://|www\.|\b[\w-]+\.(com|in|net|org|io|ly|me|xyz|co)\b", re.I)
# Kept short and conservative on purpose: YouTube's own filters run first; this only stops the obvious.
ABUSE = [r"\bf+u+c+k", r"\bsh[i1]t\b", r"\bbitch", r"\bbastard", r"\bmadarchod", r"\bmc\b", r"\bbc\b",
         r"\bbhenchod", r"\bbehenchod", r"\bchutiya", r"\bgaand", r"\brandi", r"\bharami", r"\bkutta\b",
         r"मादरचोद", r"बहनचोद", r"भेनचोद", r"चूतिया", r"गांड", r"रंडी", r"हरामी"]
ABUSE_RE = re.compile("|".join(ABUSE), re.I)


@dataclass
class Question:
    id: str
    author: str
    channel: str
    text: str
    priority: int = 0          # 2 Super Chat, 1 owner/moderator, 0 everyone else
    at: float = field(default_factory=time.time)


def clean_name(name: str) -> str:
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C").strip()
    return (name[:30] + "…") if len(name) > 31 else (name or "Viewer")


def norm(text: str) -> str:
    return re.sub(r"[^\wऀ-ॿ]+", " ", text.lower()).strip()


class Moderator:
    def __init__(self, triggers=("@gitalive", "!gita", "#gitalive"), per_author_s: int = 300,
                 repeat_s: int = 6 * 3600, per_hour: int = 20, queue_max: int = 10, clock=time.time):
        self.labels = tuple(t.strip() for t in triggers if t.strip())     # as typed, for the screen
        self.triggers = tuple(t.lower() for t in self.labels)             # for matching
        self.per_author_s, self.repeat_s, self.per_hour, self.queue_max = per_author_s, repeat_s, per_hour, queue_max
        self.clock = clock
        self.queue: list[Question] = []
        self.last_by_author: dict[str, float] = {}
        self.seen: dict[str, float] = {}
        self.answered: deque[float] = deque()
        self.rejected: dict[str, int] = {}

    def _reject(self, why: str) -> None:
        self.rejected[why] = self.rejected.get(why, 0) + 1

    def extract(self, text: str) -> str | None:
        """The question in a message, without its trigger, or None if the message is not a question."""
        low = text.lower()
        hit = next((t for t in self.triggers if t in low), None)
        if not hit:
            return None
        i = low.index(hit)
        q = (text[:i] + " " + text[i + len(hit):])
        q = re.sub(r"\s+", " ", q).strip(" :,-–—")
        return q

    def offer(self, msg_id: str, author: str, channel: str, text: str, superchat: bool = False,
              staff: bool = False) -> Question | None:
        """Consider one chat message. Returns the queued Question, or None."""
        q = self.extract(text or "")
        if q is None:
            return None
        now = self.clock()
        if len(q) < 4 or len(q) > 300:
            return self._reject("length")
        if LINK.search(q):
            return self._reject("link")
        if ABUSE_RE.search(q):
            return self._reject("abuse")
        letters = sum(ch.isalpha() for ch in q)
        if letters < 3:
            return self._reject("no_words")
        n = norm(q)
        if now - self.seen.get(n, -1e12) < self.repeat_s:
            return self._reject("repeat")
        if not (staff or superchat) and now - self.last_by_author.get(channel, -1e12) < self.per_author_s:
            return self._reject("cooldown")
        if any(x.channel == channel for x in self.queue) and not superchat:
            return self._reject("already_queued")
        self.seen[n] = now
        self.last_by_author[channel] = now
        item = Question(msg_id, clean_name(author), channel, q, 2 if superchat else 1 if staff else 0, now)
        self.queue.append(item)
        self.queue.sort(key=lambda x: (-x.priority, x.at))
        while len(self.queue) > self.queue_max:   # drop the newest ordinary question
            drop = max((x for x in self.queue if x.priority == 0), key=lambda x: x.at, default=None)
            if not drop:
                break
            self.queue.remove(drop)
            self._reject("queue_full")
        return item

    def next(self) -> Question | None:
        """The next question to answer now, if the hourly cap allows."""
        now = self.clock()
        while self.answered and now - self.answered[0] > 3600:
            self.answered.popleft()
        if not self.queue or len(self.answered) >= self.per_hour:
            return None
        self.answered.append(now)
        return self.queue.pop(0)

    def waiting(self) -> list[str]:
        return [q.author for q in self.queue]
