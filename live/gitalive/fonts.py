"""Fonts for the headless renderer, downloaded once (SIL Open Font License, from Google Fonts' repository).

    python -m gitalive.fonts [folder]     # the Docker image runs this at build time, like EscapeArena's assets.js

Devanagari is shaped with HarfBuzz through Pillow's raqm layout, so conjuncts and matras render correctly."""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/google/fonts/main/ofl/"
FONTS = {
    "sanskrit": "tirodevanagarisanskrit/TiroDevanagariSanskrit-Regular.ttf",   # shlokas
    "sanskrit_italic": "tirodevanagarisanskrit/TiroDevanagariSanskrit-Italic.ttf",  # IAST transliteration
    "hindi_serif": "tirodevanagarihindi/TiroDevanagariHindi-Regular.ttf",     # headings
    "ui": "mukta/Mukta-Regular.ttf",                                           # Hindi + English text
    "ui_semibold": "mukta/Mukta-SemiBold.ttf",
    "ui_bold": "mukta/Mukta-ExtraBold.ttf",
}


def ensure(folder: Path, log=print) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for name, rel in FONTS.items():
        path = folder / Path(rel).name
        if not path.exists() or path.stat().st_size < 10_000:
            log(f"downloading font {path.name}")
            with urllib.request.urlopen(BASE + rel, timeout=60) as r:
                data = r.read()
            if data[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO"):
                raise RuntimeError(f"{path.name}: not a font file")
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            tmp.replace(path)
        out[name] = path
    return out


if __name__ == "__main__":
    here = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "fonts"
    for k, v in ensure(here).items():
        print(f"{k:16} {v}")
