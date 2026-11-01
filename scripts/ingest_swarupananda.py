"""Ingest Swami Swarupananda's translation (1909; public domain worldwide, the author died in 1906)
from four independent archive.org OCR scans, keeping a word only when the scans agree.

    python scripts/ingest_swarupananda.py PRIMARY.txt WITNESS.txt [WITNESS.txt ...]

PRIMARY  in.ernet.dli.2015.237563 (1909). Every translation starts with its verse number
         ("47. Thy right is to work only; ..."), which is how verses are found and aligned.
WITNESS  in.ernet.dli.2015.386852 (1909, another scan), in.ernet.dli.2015.20768 (1926 edition),
         in.ernet.dli.2015.20770 (1933 edition). Same translation, different scans.

A word from the primary is kept when at least two witnesses agree with it. Where the primary
disagrees, a reading shared by at least two witnesses replaces it, but only if the other 1909
scan is one of them, so later editions can settle OCR slips but never bring in their revisions. A verse is "verified" only if
every word is settled this way and it ends as a complete sentence; anything else is written with
"verified": false and the reasons, and is never shown to users until a person checks the page.
Output: kb/translations/swarupananda.json.
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

from spellchecker import SpellChecker

ROOT = Path(__file__).resolve().parent.parent
CHAPTER_SIZES = [47, 72, 43, 42, 29, 47, 30, 28, 34, 42, 55, 20, 35, 27, 20, 24, 28, 78]
SOURCE = {
    "translator": "Swami Swarupananda",
    "title": "Srimad-Bhagavad-Gita, with text, word-for-word translation, English rendering and comments",
    "published": "Advaita Ashrama, Mayavati, 1909",
    "licence": "Public domain worldwide (author died 1906; first published 1909).",
    "scans": ["https://archive.org/details/in.ernet.dli.2015.237563",
              "https://archive.org/details/in.ernet.dli.2015.386852",
              "https://archive.org/details/in.ernet.dli.2015.20768",
              "https://archive.org/details/in.ernet.dli.2015.20770"],
    "method": "Four OCR scans; a word is kept only when at least two scans agree with it.",
}

_SPELL = SpellChecker()
_SPELL.word_frequency.load_words(["thou", "thee", "thy", "thine", "hast", "doth", "art", "shalt", "shouldst",
                                  "wouldst", "canst", "hath", "ye", "verily", "thereof", "whereof", "unto"])
_START = re.compile(r"^(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s*\.\s+(?=[A-Z(‘\"'“])")
_DEV = re.compile(r"[ऀ-ॿ]")
_WORD = re.compile(r"[A-Za-z]+")
_JUNK_CHARS = re.compile(r"[\^«»|$#@%*■~]")
_SENTENCE_END = re.compile(r"[.!?][”’\"')\]]*$")


def _lines(text: str) -> list[str]:
    return [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.split("\n")]


def _trim_to_text(text: str) -> str:
    """Drop the preface and the opening invocation: the Gita proper starts at 'FIRST CHAPTER'."""
    m = re.search(r"FIRST\s+CHAPTER", text)
    return text[m.start():] if m else text


def _is_header(ln: str) -> bool:
    """Running heads and page numbers: '45-47)', 'WAY OF KNOWLEDGE', '57'."""
    return bool(re.fullmatch(r"\(?\d{1,3}\s*[-–]\s*\d{1,3}\)?\.?", ln) or re.fullmatch(r"\d{1,3}", ln)
                or (ln.isupper() and len(ln) < 45 and not ln[:1].isdigit()))


def _junk_line(ln: str) -> bool:
    """Devanagari that OCR turned into Latin noise: few real words, odd symbols."""
    ws = _WORD.findall(ln)
    if not ws:
        return bool(ln.strip())
    real = sum(w.lower() in _SPELL for w in ws)
    return real / len(ws) < 0.5 and (len(ws) <= 4 or bool(_JUNK_CHARS.search(ln)))


def _clean_para(text: str) -> str:
    text = re.sub(r"(\w)- (\w)", r"\1\2", text)                       # words hyphenated at line ends
    text = re.sub(r"(?<![\w.])1(?=[\s”’\"'.,;:!?]|$)", "I", text)    # the pronoun I read as 1
    text = re.sub(r"(?<![\w.])0(?=\s+[A-Z])", "O", text)              # the vocative O read as 0
    text = re.sub(r"(?<=[a-z])\d+\b", "", text)                        # footnote marks: Vyasa3
    text = re.sub(r"\s[-–]{1,2}\s*\[\.?(?=\s)", "", text)             # stray '-- [.'
    text = re.sub(r"[\[(]?\s*Chap\.?\s*[IVXLl1]{1,5}\b\.?\s*[\])]?", "", text)  # running heads: [Chap. XVI
    text = re.sub(r"SHRIMAD[- ]BHAGAVAD[- ]GITA", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def paragraphs(text: str) -> list[tuple[int, int, str]]:
    """Numbered translation paragraphs as (first verse, last verse, text), in book order.
    A paragraph carries on across page breaks until it ends a sentence."""
    lines = [ln for ln in _lines(_trim_to_text(text)) if not _is_header(ln)]
    out, i = [], 0
    while i < len(lines):
        m = _START.match(lines[i])
        if not m:
            i += 1
            continue
        first, last = int(m.group(1)), int(m.group(2) or m.group(1))
        body, j = [lines[i][m.end():]], i + 1
        while j < len(lines):
            ln = lines[j]
            if not ln:
                if _SENTENCE_END.search(body[-1]):
                    break
                j += 1
                continue
            if ln.startswith("[") or _START.match(ln) or _DEV.search(ln) or _junk_line(ln):
                break
            body.append(ln)
            j += 1
        out.append((first, last, _clean_para(" ".join(body))))
        i = j
    return out


def expected_sequence(sizes: list[int]) -> list[tuple[int, int]]:
    return [(c, v) for c, n in enumerate(sizes, 1) for v in range(1, n + 1)]


def align(paras: list[tuple[int, int, str]], sizes: list[int]) -> dict[tuple[int, int], tuple[int, int, str]]:
    """Longest-common-subsequence alignment of paragraph numbers to the canonical verse order.
    Numbered points inside notes do not fit the order and are skipped."""
    exp = expected_sequence(sizes)
    n, m = len(paras), len(exp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        first = paras[i][0]
        for j in range(m - 1, -1, -1):
            best = max(dp[i + 1][j], dp[i][j + 1])
            if exp[j][1] == first:
                best = max(best, 1 + dp[i + 1][j + 1])
            dp[i][j] = best
    out, i, j = {}, 0, 0
    while i < n and j < m:
        if exp[j][1] == paras[i][0] and dp[i][j] == 1 + dp[i + 1][j + 1]:
            out[exp[j]] = paras[i]
            i, j = i + 1, j + 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            i += 1
        else:
            j += 1
    return out


class Witness:
    """A confirming scan as a word stream with a trigram index, page heads and Devanagari removed."""

    def __init__(self, text: str):
        lines = [ln for ln in _lines(_trim_to_text(text)) if ln and not _is_header(ln) and not _DEV.search(ln)]
        joined = re.sub(r"(\w)-\s+(\w)", r"\1\2", " ".join(lines))
        self.words = _WORD.findall(joined)
        self.norm = [w.lower() for w in self.words]
        self.index: dict[tuple[str, str, str], list[int]] = {}
        for i in range(len(self.norm) - 2):
            self.index.setdefault(tuple(self.norm[i:i + 3]), []).append(i)

    def compare(self, b: list[str]) -> dict | None:
        """Where this scan agrees with the primary's words b, and what it reads instead where not."""
        votes: dict[int, int] = {}
        for i in range(len(b) - 2):
            for p in self.index.get(tuple(b[i:i + 3]), ()):
                votes[p - i] = votes.get(p - i, 0) + 1
        if not votes:
            return None
        off = max(votes, key=votes.get)
        if votes[off] < max(2, (len(b) - 2) // 6):
            return None
        lo = max(0, off - 3)
        a, a_orig = self.norm[lo: off + len(b) + 3], self.words[lo: off + len(b) + 3]
        sm = difflib.SequenceMatcher(None, b, a, autojunk=False)
        agree = [False] * len(b)
        cased: dict[int, str] = {}
        alts: dict[tuple[int, int], tuple[str, ...]] = {}
        inserts: dict[int, tuple[str, ...]] = {}
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                for k in range(i1, i2):
                    agree[k] = True
                    cased[k] = a_orig[j1 + k - i1]
            elif tag == "insert":
                if 0 < j1 and j2 < len(a):  # words beyond the primary's ends are just window padding
                    inserts[i1] = tuple(a_orig[j1:j2])
            else:
                alts[(i1, i2)] = tuple(a_orig[j1:j2])
        return {"agree": agree, "cased": cased, "alts": alts, "inserts": inserts, "ratio": sm.ratio()}


def consensus(text: str, witnesses: list[Witness]) -> dict:
    spans = list(_WORD.finditer(text))
    b = [m.group().lower() for m in spans]
    issues: list[str] = []
    if len(b) < 3:
        return {"verified": False, "text": text, "issues": ["too short"], "witnesses": 0}
    compared = [w.compare(b) for w in witnesses]
    same_edition = compared[0]  # witnesses[0] is the other 1909 scan
    found = [r for r in compared if r]
    if len(found) < 2:
        return {"verified": False, "text": text, "issues": ["found in fewer than two other scans"],
                "witnesses": len(found)}

    replace: dict[int, str] = {}
    k = 0
    while k < len(b):
        if sum(r["agree"][k] for r in found) >= 2:
            k += 1
            continue
        # the primary is outvoted or unsupported here: look for one reading shared by two scans
        ranges = {}
        for r in found:
            for (i1, i2), alt in r["alts"].items():
                if i1 <= k < i2:
                    ranges.setdefault((i1, i2, tuple(w.lower() for w in alt)), []).append(alt)
        # a correction must be the 1909 reading: the other 1909 scan has to be one of the two
        same = {(i1, i2, tuple(w.lower() for w in alt)) for (i1, i2), alt in (same_edition or {}).get("alts", {}).items()}
        winner = next(((rng, alts[0]) for rng, alts in ranges.items() if len(alts) >= 2 and rng in same), None)
        if winner:
            (i1, i2, _), alt = winner
            replace[i1] = " ".join(alt)
            for x in range(i1 + 1, i2):
                replace[x] = ""
            k = i2
            continue
        supporters = sum(r["agree"][k] for r in found)
        if supporters == 1 and spans[k].group().lower() in _SPELL and not _JUNK_CHARS.search(text):
            k += 1  # one other scan agrees and it is a real word: accept
            continue
        issues.append(f"unsettled word '{spans[k].group()}'")
        k += 1

    inserts: dict[int, str] = {}
    gaps: dict[tuple[int, tuple[str, ...]], int] = {}
    for r in found:
        for gap, words in r["inserts"].items():
            key = (gap, tuple(w.lower() for w in words))
            gaps[key] = gaps.get(key, 0) + 1
    same_inserts = {(g, tuple(w.lower() for w in ws)) for g, ws in (same_edition or {}).get("inserts", {}).items()}
    for (gap, words), n in gaps.items():
        if n >= 2 and (gap, words) in same_inserts:
            inserts[gap] = " ".join(words)

    out, last = [], 0
    for k, m in enumerate(spans):
        out.append(text[last: m.start()])
        if k in inserts:
            out.append(inserts[k] + " ")
        word = replace.get(k, m.group())
        if k in replace:
            if word and m.group()[:1].isupper():
                word = word[:1].upper() + word[1:]
        elif word[:1].isupper() and k > 0 and not re.search(r"[.!?:;“‘\"]\s*$", text[:m.start()]):
            lower = sum(1 for r in found if r["cased"].get(k, "")[:1].islower())
            if lower >= 2:  # capital mid-sentence that the other scans print in lower case
                word = word.lower()
        out.append(word)
        last = m.end()
    out.append(text[last:])
    merged = _JUNK_CHARS.sub("", "".join(out))
    if merged.count("(") > merged.count(")"):  # an opening bracket whose contents the scans voted out
        merged = re.sub(r"\(\s*[.,;]?\s+(?=\S)", "", merged)
    merged = re.sub(r"\s{2,}", " ", merged).replace(" ,", ",").replace(" ;", ";").replace(" ?", "?").strip()
    if not _SENTENCE_END.search(merged):
        issues.append("does not end as a complete sentence")
    if re.search(r"\d|[\[\]{}<>]", merged):
        issues.append("leftover OCR characters")
    return {"verified": not issues, "text": merged, "issues": issues, "witnesses": len(found)}


def main() -> None:
    if len(sys.argv) < 4:
        sys.exit(__doc__)
    primary = Path(sys.argv[1]).read_text("utf-8")
    witnesses = [Witness(Path(p).read_text("utf-8")) for p in sys.argv[2:]]
    paras = paragraphs(primary)
    # Swarupananda follows the 700-verse recension: no "prakritim purusham" verse at the start of 13.
    sizes_700 = CHAPTER_SIZES.copy()
    sizes_700[12] = 34
    aligned = align(paras, sizes_700)
    out, missing, unverified = {}, [], 0
    for (c, v) in expected_sequence(sizes_700):
        key = f"BG {c}.{v + 1 if c == 13 else v}"  # 701-verse numbering, as in kb/verses.json
        if (c, v) not in aligned:
            missing.append(key)
            continue
        first, last, text = aligned[(c, v)]
        res = consensus(text, witnesses)
        rec = {"text": res["text"], "verified": res["verified"], "scans_agreeing": res["witnesses"] + 1}
        if last != first:
            rec["covers"] = [f"BG {c}.{(x + 1) if c == 13 else x}" for x in range(first, last + 1)]
        if not res["verified"]:
            rec["issues"] = res["issues"]
            rec["primary_raw"] = text
            unverified += 1
        out[key] = rec
    dest = ROOT / "kb" / "translations"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "swarupananda.json").write_text(
        json.dumps({"source": SOURCE, "verses": out, "missing": missing}, ensure_ascii=False, indent=1), "utf-8")
    print(f"paragraphs: {len(paras)}  aligned: {len(aligned)}/700  verified: {len(out) - unverified}  "
          f"unverified: {unverified}  missing: {len(missing)}")


if __name__ == "__main__":
    main()
