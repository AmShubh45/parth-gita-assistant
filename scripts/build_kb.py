"""Build Parth's knowledge base from the public-domain layers of the gita/gita dataset.

    git clone --depth 1 https://github.com/gita/gita.git /tmp/gita
    python scripts/build_kb.py /tmp/gita/data

Writes kb/verses.json (Sanskrit canon), kb/commentaries.json (classical Sanskrit commentaries)
and kb/chapters.json. Everything else in the upstream dataset (modern translations and
commentaries under copyright, and word meanings of unknown origin) is left out on purpose.

The upstream English "Purohit" and "Sivananda" texts are NOT the authentic translations: they
have been modernised and edited (thy -> your, a "Revised:" prefix, "No changes needed." in
place of two verses). They are kept only as `search_en`, unquotable text that helps retrieval.
`translations` stays empty until authentic public-domain translations are ingested from
original scans (scripts/ingest_translation.py, phase 2). See kb/LICENSES.md.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KB = ROOT / "kb"

# Upstream English used ONLY as search text (modernised, unverified; never quoted). key -> upstream author
SEARCH_EN = {"purohit": "Shri Purohit Swami", "sivananda": "Swami Sivananda"}
_JUNK = re.compile(r"^\s*no changes needed\.?\s*$", re.I)
_EDIT_PREFIX = re.compile(r"^\s*(revised|corrected|updated)\s*:\s*", re.I)

# Classical Sanskrit commentaries (centuries old: public domain everywhere). key -> (upstream name, label)
COMMENTARIES = {
    "shankara": ("Sri Shankaracharya", "Adi Shankaracharya (Advaita)"),
    "ramanuja": ("Sri Ramanujacharya", "Ramanujacharya (Vishishtadvaita)"),
    "madhva": ("Sri Madhavacharya", "Madhvacharya (Dvaita)"),
    "sridhara": ("Sri Sridhara Swami", "Sridhara Swami"),
    "madhusudana": ("Sri Madhusudan Saraswati", "Madhusudana Saraswati"),
    "abhinavagupta": ("Sri Abhinavgupta", "Abhinavagupta"),
    "vedanta_deshika": ("Sri Vedantadeshikacharya Venkatanatha", "Vedanta Deshika"),
    "anandagiri": ("Sri Anandgiri", "Anandagiri"),
    "jayatirtha": ("Sri Jayatritha", "Jayatirtha"),
    "vallabha": ("Sri Vallabhacharya", "Vallabhacharya"),
    "purushottama": ("Sri Purushottamji", "Purushottama"),
    "neelakantha": ("Sri Neelkanth", "Neelakantha"),
    "dhanapati": ("Sri Dhanpati", "Dhanapati"),
}

# Speaker lines ("X उवाच") mapped to who is speaking.
SPEAKERS = [("श्रीभगवान", "Krishna"), ("अर्जुन", "Arjuna"), ("सञ्जय", "Sanjaya"), ("संजय", "Sanjaya"),
            ("धृतराष्ट्र", "Dhritarashtra")]
ADDRESSED_TO = {"Krishna": "Arjuna", "Arjuna": "Krishna", "Sanjaya": "Dhritarashtra", "Dhritarashtra": "Sanjaya"}

_NUM_TAG = re.compile(r"[।|]{1,2}\s*\d+\.\d+\s*[।|]{1,2}")
_EMPTY = re.compile(r"did not comment|commentary starts from|no commentary", re.I)


_SPEAKER_PREFIX = re.compile(r"^\s*((?:श्री\s*भगवान्?\s*ु|श्री\s*भगवान\s*उ)वाच|(?:अर्जुन|सञ्जय|संजय|धृतराष्ट्र)\s*उवाच)\s*")
_TRANSLIT_PREFIX = re.compile(r"^\s*(?:śhrī[ -]bhagavān|arjuna|sañjaya|dhṛitarā(?:ṣ|ś)h?ṭ?ra)\s+uvācha\s*", re.I)


def _speaker_of(line: str) -> str | None:
    """Who speaks, if the text starts with a speaker line ("अर्जुन उवाच", "श्री भगवानुवाच")."""
    m = _SPEAKER_PREFIX.match(line)
    if not m:
        return None
    head = m.group(1).replace(" ", "")
    for prefix, name in SPEAKERS:
        if head.startswith(prefix):
            return name
    return None


def _clean_sanskrit(text: str) -> tuple[str, str | None]:
    """Split a verse into (shloka lines, speaker line or None); drop the trailing ।।2.47।। tag.
    The speaker line is sometimes glued to the first half-verse with no line break."""
    text = text.strip()
    speaker_line = None
    m = _SPEAKER_PREFIX.match(text)
    if m:
        speaker_line = m.group(1).strip()
        text = text[m.end():]
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    shloka = "\n".join(_NUM_TAG.sub("।।", ln).rstrip() for ln in lines).strip()
    if "\n" not in shloka:  # a few verses come as one line: break after the first half-verse
        shloka = re.sub(r"।(?=[^।\s])", "।\n", shloka, count=1)
    return shloka, speaker_line


def _clean_translit(text: str, had_speaker: bool) -> str:
    text = text.strip()
    if had_speaker:
        text = _TRANSLIT_PREFIX.sub("", text, count=1)
    return "\n".join(ln.strip() for ln in text.split("\n") if ln.strip())


def _clean_prose(text: str) -> str:
    text = re.sub(r"^\s*\d+\.\d+\s*", "", text.strip())
    return re.sub(r"\s+", " ", text).strip()


def build(src: Path) -> dict:
    verses_raw = sorted(json.loads((src / "verse.json").read_text("utf-8")), key=lambda v: v["id"])
    translations = json.loads((src / "translation.json").read_text("utf-8"))
    commentary = json.loads((src / "commentary.json").read_text("utf-8"))
    chapters_raw = json.loads((src / "chapters.json").read_text("utf-8"))

    by_author_t = {key: {t["verse_id"]: t["description"] for t in translations if t["authorName"] == name}
                   for key, name in SEARCH_EN.items()}
    by_author_c = {key: {c["verse_id"]: c["description"] for c in commentary if c["authorName"] == name}
                   for key, (name, _) in COMMENTARIES.items()}

    verses, comments, current = [], {}, None
    for v in verses_raw:
        shloka, speaker_line = _clean_sanskrit(v["text"])
        if speaker_line:
            current = _speaker_of(speaker_line)
        ref = f"{v['chapter_number']}.{v['verse_number']}"
        verses.append({
            "id": f"BG {ref}",
            "ref": ref,
            "chapter": v["chapter_number"],
            "verse": v["verse_number"],
            "order": v["id"],
            "speaker": current,
            "addressed_to": ADDRESSED_TO.get(current),
            "sanskrit": shloka,
            "transliteration": _clean_translit(v["transliteration"], bool(speaker_line)),
            "translations": {},  # authentic, quotable translations only (none verified yet)
            "search_en": [_EDIT_PREFIX.sub("", _clean_prose(by_author_t[key][v["id"]]))
                          for key in SEARCH_EN
                          if v["id"] in by_author_t[key] and not _JUNK.match(by_author_t[key][v["id"]])],
        })
        notes = {key: by_author_c[key][v["id"]].strip() for key in COMMENTARIES
                 if v["id"] in by_author_c[key] and not _EMPTY.search(by_author_c[key][v["id"]])
                 and len(by_author_c[key][v["id"]].strip()) > 20}
        if notes:
            comments[f"BG {ref}"] = notes

    chapters = [{
        "chapter": c["chapter_number"],
        "name_sanskrit": c["name"],
        "name_transliterated": c["name_transliterated"],
        "name_en": c["name_translation"],
        "meaning": c["name_meaning"],
        "verses": c["verses_count"],
        "summary_en": c["chapter_summary"].strip(),
        "summary_hi": c["chapter_summary_hindi"].strip(),
    } for c in sorted(chapters_raw, key=lambda c: c["chapter_number"])]

    return {
        "verses": verses,
        "commentaries": comments,
        "chapters": chapters,
        "sources": {
            "translations": {},
            "search_en": "Modernised English derived from Purohit Swami and Swami Sivananda via gita/gita. "
                         "Edited upstream; unverified; used for retrieval only, never displayed as a translation.",
            "commentaries": {k: v[1] for k, v in COMMENTARIES.items()},
        },
    }


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    kb = build(Path(sys.argv[1]))
    KB.mkdir(exist_ok=True)
    meta = {"source": "https://github.com/gita/gita (Unlicense compilation; see kb/LICENSES.md)", **kb["sources"]}
    (KB / "verses.json").write_text(json.dumps({"meta": meta, "verses": kb["verses"]}, ensure_ascii=False, indent=1), "utf-8")
    (KB / "commentaries.json").write_text(json.dumps(kb["commentaries"], ensure_ascii=False, separators=(",", ":")), "utf-8")
    (KB / "chapters.json").write_text(json.dumps(kb["chapters"], ensure_ascii=False, indent=1), "utf-8")
    speakers: dict[str, int] = {}
    for v in kb["verses"]:
        speakers[v["speaker"]] = speakers.get(v["speaker"], 0) + 1
    print(f"verses: {len(kb['verses'])}  chapters: {len(kb['chapters'])}  "
          f"verses with commentary: {len(kb['commentaries'])}  speakers: {speakers}")


if __name__ == "__main__":
    main()
