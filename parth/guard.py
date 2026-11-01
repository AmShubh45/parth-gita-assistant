"""Protecting the shared Gemini quota (Parth uses the same key as Samajh).

- DailyBudget: at most PARTH_DAILY_AI_LIMIT model-backed answers per UTC day. After that Parth keeps
  answering from the knowledge base alone, so Samajh never runs out because of Parth traffic.
- RateLimiter: per-visitor limit on questions per minute.
- AnswerCache: identical questions within 24 hours reuse the answer instead of calling the model again.
"""
from __future__ import annotations

import os
import re
import time
from collections import OrderedDict, deque
from datetime import datetime, timezone


class DailyBudget:
    def __init__(self, limit: int | None = None):
        self.limit = limit if limit is not None else int(os.environ.get("PARTH_DAILY_AI_LIMIT", "300"))
        self.day = ""
        self.used = 0

    def take(self) -> bool:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.day:
            self.day, self.used = today, 0
        if self.used >= self.limit:
            return False
        self.used += 1
        return True


class RateLimiter:
    def __init__(self, per_minute: int = 8):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits.setdefault(key, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= self.per_minute:
            return False
        q.append(now)
        if len(self.hits) > 10000:  # forget idle visitors
            for k in [k for k, v in self.hits.items() if not v][:5000]:
                self.hits.pop(k, None)
        return True


class AnswerCache:
    def __init__(self, size: int = 500, ttl_s: int = 24 * 3600):
        self.size, self.ttl = size, ttl_s
        self.items: OrderedDict[str, tuple[float, dict]] = OrderedDict()

    @staticmethod
    def key(question: str) -> str:
        return re.sub(r"[^\wऀ-ॿ]+", " ", question.lower()).strip()

    def get(self, question: str) -> dict | None:
        k = self.key(question)
        hit = self.items.get(k)
        if not hit or time.monotonic() - hit[0] > self.ttl:
            return None
        self.items.move_to_end(k)
        return hit[1]

    def put(self, question: str, answer: dict) -> None:
        self.items[self.key(question)] = (time.monotonic(), answer)
        self.items.move_to_end(self.key(question))
        while len(self.items) > self.size:
            self.items.popitem(last=False)
