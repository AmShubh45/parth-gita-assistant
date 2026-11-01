"""The knowledge base, loaded once: verses, verified translations, chapters, commentaries, situations.

Only verses with a verified translation are "answerable": Parth never shows a translation that has
not passed the four-scan check (see kb/LICENSES.md)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "kb"
SPEAKER_HI = {"Krishna": "श्रीकृष्ण", "Arjuna": "अर्जुन", "Sanjaya": "संजय", "Dhritarashtra": "धृतराष्ट्र"}


@dataclass
class Verse:
    id: str
    ref: str
    chapter: int
    verse: int
    order: int
    speaker: str
    addressed_to: str
    sanskrit: str
    transliteration: str
    search_en: list[str]
    translation: str | None = None  # verified Swarupananda text, or None

    @property
    def answerable(self) -> bool:
        return self.translation is not None


@dataclass
class KnowledgeBase:
    verses: dict[str, Verse]
    chapters: dict[int, dict]
    situations: list[dict]
    translation_source: dict
    _dir: Path = field(default=KB_DIR, repr=False)

    @classmethod
    def load(cls, kb_dir: Path = KB_DIR) -> "KnowledgeBase":
        raw = json.loads((kb_dir / "verses.json").read_text("utf-8"))["verses"]
        tr = json.loads((kb_dir / "translations" / "swarupananda.json").read_text("utf-8"))
        verified = {k: v["text"] for k, v in tr["verses"].items() if v["verified"]}
        verses = {}
        for v in raw:
            verses[v["id"]] = Verse(
                id=v["id"], ref=v["ref"], chapter=v["chapter"], verse=v["verse"], order=v["order"],
                speaker=v["speaker"], addressed_to=v["addressed_to"], sanskrit=v["sanskrit"],
                transliteration=v["transliteration"], search_en=v["search_en"], translation=verified.get(v["id"]))
        chapters = {c["chapter"]: c for c in json.loads((kb_dir / "chapters.json").read_text("utf-8"))}
        situations = json.loads((kb_dir / "situations.json").read_text("utf-8"))["situations"]
        return cls(verses=verses, chapters=chapters, situations=situations, translation_source=tr["source"], _dir=kb_dir)

    @cached_property
    def commentaries(self) -> dict[str, dict[str, str]]:
        """Classical Sanskrit commentaries (16 MB), loaded on first use."""
        return json.loads((self._dir / "commentaries.json").read_text("utf-8"))

    def get(self, ref: str) -> Verse | None:
        """'2.47', 'BG 2.47' or 'bg 2.47' -> Verse."""
        ref = ref.strip().upper().replace("BG", "").strip()
        return self.verses.get(f"BG {ref}")

    def neighbours(self, v: Verse, before: int = 1, after: int = 1) -> list[Verse]:
        by_order = {x.order: x for x in self.verses.values()}
        return [by_order[o] for o in range(v.order - before, v.order + after + 1)
                if o != v.order and o in by_order and by_order[o].chapter == v.chapter]

    @property
    def answerable(self) -> list[Verse]:
        return [v for v in self.verses.values() if v.answerable]
