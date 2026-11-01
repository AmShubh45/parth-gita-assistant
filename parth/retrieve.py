"""Find candidate verses for a question.

Two signals, combined:
1. the life-situation index (kb/situations.json): Hindi, Hinglish and English keywords mapped to the
   verses that address that situation, most central first. This is what lets a Hindi question find
   English-language verses without any model;
2. BM25 over each verse's English text (verified translation + search text + chapter theme), for
   questions the index does not cover. When the model's "understand" step runs, it adds an English
   restatement of the question and situation ids, which feed both signals.
Only answerable verses (with a verified translation) are returned."""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from .kb import KnowledgeBase, Verse

_STOP = set("""a an the and or but if then so of to in on at for with from by as is are was were be been being am i me my
mine myself you your yours we our us he him his she her it its they them their what which who whom this that these
those do does did doing have has had having not no nor can could should would will shall may might must very just
about into over under again further once here there when where why how all any both each few more most other some
such only own same than too s t don now get got feel feeling really always never every much many one also like""".split())


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z]+", text.lower())
    return [w[:-1] if w.endswith("s") and len(w) > 4 else w for w in words if w not in _STOP and len(w) > 2]


@dataclass
class Candidate:
    verse: Verse
    score: float
    situations: list[str]


class Retriever:
    def __init__(self, kb: KnowledgeBase):
        self.kb = kb
        self.docs = {}
        for v in kb.answerable:
            ch = kb.chapters[v.chapter]
            text = " ".join([v.translation or "", *v.search_en, ch["name_en"], ch["meaning"]])
            self.docs[v.id] = Counter(_tokens(text))
        self.avg_len = sum(sum(c.values()) for c in self.docs.values()) / max(1, len(self.docs))
        df: Counter = Counter()
        for c in self.docs.values():
            df.update(c.keys())
        n = len(self.docs)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self._kw = [(s, [k.lower() for k in s["keywords"]]) for s in kb.situations]

    @staticmethod
    def _stem(word: str) -> str:
        """Light English stemmer for keyword matching: comparing / compared / compares -> compar."""
        for suf in ("ingly", "edly", "ness", "ing", "ed", "es", "ly", "s", "e"):
            if word.endswith(suf) and len(word) - len(suf) >= 4:
                return word[: -len(suf)]
        return word

    def situations_in(self, text: str) -> list[str]:
        t = " " + re.sub(r"\s+", " ", text.lower()) + " "
        stems = {self._stem(w) for w in re.findall(r"[a-z]+", t)}
        hits = []
        for s, kws in self._kw:
            for k in kws:
                if not re.search(r"[a-z]", k):
                    found = k in t  # Devanagari: match anywhere (Hindi inflects by suffix)
                elif " " in k or "-" in k:
                    found = re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", t) is not None
                else:
                    found = self._stem(k) in stems or re.search(rf"(?<![a-z]){re.escape(k)}(?![a-z])", t) is not None
                if found:
                    hits.append(s["id"])
                    break
        return hits

    def _bm25(self, q: list[str], doc: Counter, k1: float = 1.4, b: float = 0.75) -> float:
        dl = sum(doc.values())
        s = 0.0
        for w in q:
            f = doc.get(w)
            if f:
                s += self.idf[w] * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / self.avg_len))
        return s

    def search(self, question: str, *, english: str = "", situation_ids: list[str] | None = None,
               k: int = 8) -> tuple[list[Candidate], list[str]]:
        sits = list(dict.fromkeys((situation_ids or []) + self.situations_in(question) + self.situations_in(english)))
        by_id = {s["id"]: s for s in self.kb.situations}
        q = _tokens(question + " " + english + " " + " ".join(by_id[s]["en"] for s in sits if s in by_id))
        scores: dict[str, float] = {}
        tags: dict[str, list[str]] = {}
        if q:
            raw = {vid: self._bm25(q, doc) for vid, doc in self.docs.items()}
            top = max(raw.values()) or 1.0
            for vid, s in raw.items():
                if s > 0:
                    scores[vid] = s / top  # 0..1
        for sid in sits:
            refs = by_id[sid]["verses"] if sid in by_id else []
            for rank, ref in enumerate(refs):
                vid = f"BG {ref}"
                if vid in self.docs:
                    bonus = 1.5 - rank * 0.08  # curated: strong, ordered
                    if self.kb.verses[vid].speaker != "Krishna":
                        bonus *= 0.8  # the teaching comes from Krishna; Arjuna's words describe the problem
                    scores[vid] = scores.get(vid, 0.0) + bonus
                    tags.setdefault(vid, []).append(sid)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
        return [Candidate(self.kb.verses[vid], round(s, 3), tags.get(vid, [])) for vid, s in ranked], sits
