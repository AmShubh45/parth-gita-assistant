"""Integrity checks for the knowledge base. If any of these fail, Parth could quote the wrong verse,
the wrong speaker or a source we may not use, so they gate every change to kb/."""
import json
import re
from collections import Counter
from pathlib import Path

import pytest

KB = Path(__file__).resolve().parent.parent / "kb"
CHAPTER_SIZES = [47, 72, 43, 42, 29, 47, 30, 28, 34, 42, 55, 20, 35, 27, 20, 24, 28, 78]  # 13 includes optional 13.1


@pytest.fixture(scope="module")
def verses():
    return json.loads((KB / "verses.json").read_text("utf-8"))["verses"]


@pytest.fixture(scope="module")
def by_ref(verses):
    return {v["ref"]: v for v in verses}


def test_every_verse_present_once_in_order(verses):
    assert len(verses) == sum(CHAPTER_SIZES) == 701
    assert [v["order"] for v in verses] == list(range(1, 702))
    counts = Counter(v["chapter"] for v in verses)
    assert [counts[c] for c in range(1, 19)] == CHAPTER_SIZES
    assert len({v["id"] for v in verses}) == 701


def test_speaker_counts_match_tradition(verses):
    # Krishna 574, Arjuna 85 (+ the optional 13.1), Sanjaya 40, Dhritarashtra 1.
    assert Counter(v["speaker"] for v in verses) == {"Krishna": 574, "Arjuna": 86, "Sanjaya": 40, "Dhritarashtra": 1}


@pytest.mark.parametrize("ref,speaker", [
    ("1.1", "Dhritarashtra"), ("1.2", "Sanjaya"), ("1.21", "Arjuna"), ("2.2", "Krishna"),
    ("2.9", "Sanjaya"), ("2.47", "Krishna"), ("11.15", "Arjuna"), ("13.1", "Arjuna"),
    ("18.66", "Krishna"), ("18.73", "Arjuna"), ("18.78", "Sanjaya"),
])
def test_known_speakers(by_ref, ref, speaker):
    assert by_ref[ref]["speaker"] == speaker


def test_addressed_to_follows_speaker(verses):
    pairs = {("Krishna", "Arjuna"), ("Arjuna", "Krishna"), ("Sanjaya", "Dhritarashtra"), ("Dhritarashtra", "Sanjaya")}
    assert {(v["speaker"], v["addressed_to"]) for v in verses} <= pairs


def test_sanskrit_is_clean(verses):
    for v in verses:
        s = v["sanskrit"]
        assert s and re.search(r"[ऀ-ॿ]", s), v["id"]
        assert not re.search(r"\d+\.\d+", s), f"verse-number tag left in {v['id']}"
        assert not s.startswith(("श्री भगवानुवाच", "अर्जुन उवाच", "सञ्जय उवाच")), f"speaker line left in {v['id']}"
        assert "\n" in s, f"half-verses not split in {v['id']}"
        assert v["transliteration"] and not v["transliteration"].lower().startswith(("arjuna uvācha", "śhrī")), v["id"]


def test_known_verse_text(by_ref):
    assert by_ref["2.47"]["sanskrit"].startswith("कर्मण्येवाधिकारस्ते मा फलेषु कदाचन")
    assert by_ref["18.66"]["sanskrit"].startswith("सर्वधर्मान्परित्यज्य मामेकं शरणं व्रज")
    assert any("right" in t.lower() for t in by_ref["2.47"]["search_en"])


def test_only_permitted_sources():
    meta = json.loads((KB / "verses.json").read_text("utf-8"))["meta"]
    assert meta["translations"] == {}, "only authentic, verified translations may be listed as quotable"
    raw = (KB / "verses.json").read_text("utf-8") + (KB / "commentaries.json").read_text("utf-8")
    for banned in ("Ramsukhdas", "Chinmayananda", "Tejomayananda", "Gambirananda", "Adidevananda", "Sankaranarayan"):
        assert banned not in raw, f"{banned} is under copyright and must not be in kb/"


def test_edited_english_is_search_only(verses):
    """Upstream English was modernised and edited, so it must never sit under `translations`."""
    for v in verses:
        assert v["translations"] == {}, v["id"]
        assert 1 <= len(v["search_en"]) <= 2 and all(len(t) > 20 for t in v["search_en"]), v["id"]
        for t in v["search_en"]:
            assert not re.match(r"\s*(no changes needed|revised|corrected|updated)\b", t, re.I), (v["id"], t)


def test_commentaries_are_classical_and_non_empty():
    com = json.loads((KB / "commentaries.json").read_text("utf-8"))
    assert len(com) == 701
    assert all(notes for notes in com.values())
    assert sum("shankara" in n for n in com.values()) > 600  # Shankara begins at 2.10
    allowed = set(json.loads((KB / "verses.json").read_text("utf-8"))["meta"]["commentaries"])
    assert {k for n in com.values() for k in n} <= allowed


def test_chapters():
    ch = json.loads((KB / "chapters.json").read_text("utf-8"))
    assert [c["chapter"] for c in ch] == list(range(1, 19))
    assert [c["verses"] for c in ch] == CHAPTER_SIZES
    assert all(c["summary_en"] and c["summary_hi"] for c in ch)
