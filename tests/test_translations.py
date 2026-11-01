"""Checks on kb/translations: only verified, clean, authentic text may ever reach users."""
import json
import re
from pathlib import Path

import pytest

KB = Path(__file__).resolve().parent.parent / "kb"


@pytest.fixture(scope="module")
def swarup():
    return json.loads((KB / "translations" / "swarupananda.json").read_text("utf-8"))


@pytest.fixture(scope="module")
def verse_ids():
    return {v["id"] for v in json.loads((KB / "verses.json").read_text("utf-8"))["verses"]}


def test_source_is_public_domain_and_traceable(swarup):
    src = swarup["source"]
    assert src["translator"] == "Swami Swarupananda"
    assert "1909" in src["published"] and "Public domain" in src["licence"]
    assert len(src["scans"]) == 4 and all(s.startswith("https://archive.org/details/") for s in src["scans"])


def test_keys_are_real_verses(swarup, verse_ids):
    assert set(swarup["verses"]) <= verse_ids
    assert set(swarup["missing"]) <= verse_ids
    assert not set(swarup["verses"]) & set(swarup["missing"])
    assert "BG 13.1" not in swarup["verses"]  # 700-verse recension: 13.1 does not exist in this translation


def test_coverage(swarup):
    verified = [k for k, v in swarup["verses"].items() if v["verified"]]
    assert len(verified) >= 480, len(verified)


def test_verified_text_is_clean(swarup):
    for key, v in swarup["verses"].items():
        if not v["verified"]:
            assert v["issues"], f"{key}: unverified without a reason"
            continue
        t = v["text"]
        assert 15 <= len(t) <= 900, key
        assert re.search(r"[.!?][”’\"')\]]*$", t), f"{key}: incomplete sentence"
        assert not re.search(r"\d|[\[\]{}<>^«»|$#@%*■~]", t), f"{key}: OCR leftovers: {t}"
        assert not re.search(r"[ऀ-ॿ]", t), f"{key}: Devanagari in English text"
        assert not re.search(r"\b(\w+) \1\b", t, re.I), f"{key}: doubled word: {t}"
        assert v["scans_agreeing"] >= 3, key


@pytest.mark.parametrize("key,expected", [
    ("BG 2.47", "Thy right is to work only; but never to the fruits thereof. Be thou not the producer of the "
                "fruits of (thy) actions; neither let thy attachment be towards inaction."),
    ("BG 18.66", "Relinquishing all Dharmas take refuge in Me alone; I will liberate thee from all sins; grieve not."),
    ("BG 4.8", "For the protection of the good, for the destruction of the wicked, and for the establishment of "
               "Dharma, I come into being in every age."),
])
def test_known_verses_verbatim(swarup, key, expected):
    v = swarup["verses"][key]
    assert v["verified"] and v["text"] == expected
