# Knowledge base sources and licences

Only text listed here as **quotable** may be shown to users. Built by `scripts/build_kb.py`; every rule below is enforced by `tests/test_kb.py`.

| Data | File / field | Source | Licence | Shown to users? |
|---|---|---|---|---|
| Sanskrit verses, transliteration | `verses.json` → `sanskrit`, `transliteration` | [gita/gita](https://github.com/gita/gita) | The text is ancient (public domain); the compilation is released under the Unlicense | Yes |
| Speaker / listener | `verses.json` → `speaker`, `addressed_to` | Derived from the Sanskrit "X उवाच" lines | Our own data | Yes |
| Chapter names and summaries | `chapters.json` | gita/gita | Unlicense | Yes |
| Classical commentaries (Sanskrit): Shankara, Ramanuja, Madhva, Sridhara, Madhusudana, Abhinavagupta, Vedanta Deshika, Anandagiri, Jayatirtha, Vallabha, Purushottama, Neelakantha, Dhanapati | `commentaries.json` | gita/gita | Centuries old; public domain | As grounding; short quotes with attribution |
| Modernised English (from Purohit Swami 1935 and Swami Sivananda) | `verses.json` → `search_en` | gita/gita | Edited upstream; **not the authentic translations** | **No**: used for search only |
| Swami Swarupananda's English translation (1909) | `translations/swarupananda.json` | Four archive.org scans (1909 ×2, 1926, 1933); see `scripts/fetch_scans.sh` | Public domain worldwide (author died 1906) | Yes, **only entries with `"verified": true`** (487 of 700) |
| Further translations (Telang 1882, Besant 1905/1922) | planned | archive.org scans | Public domain | Once ingested and verified |

## Deliberately excluded

These are present upstream but under copyright, or of unknown origin:
- Hindi: Swami Ramsukhdas (Gita Press), Swami Tejomayananda, Swami Chinmayananda.
- English: Swami Gambhirananda, Swami Adidevananda, Dr S. Sankaranarayan.
- The upstream English word meanings.

## Known upstream defects (why `search_en` is quarantined)

- Purohit "translations" of 1.7 and 16.6 read "No changes needed."
- 2.48 starts with "Revised:".
- Sivananda 1.21 and 1.22 are identical.
- Archaic originals are modernised throughout. For example, Sivananda 2.47, "Thy right is to work only, but never with its fruits…", appears as "Your right is only to work…".

## How the Swarupananda text is verified

`scripts/ingest_swarupananda.py` reads the primary 1909 scan, where every translation starts with its verse number, and aligns those numbers to the canonical verse order. Each verse is then compared word by word with the other three scans:
- **A word is kept** only when at least two other scans agree with it.
- **A correction is accepted** only when two scans share it *and* one of them is the other 1909 scan. Later editions can settle OCR slips, but they can't introduce their revisions.

Anything unsettled, cut off at a page break, or containing OCR leftovers is kept with `"verified": false` and the reasons. That covers 163 verses, plus 50 that the scans didn't number legibly. These need a person to check them against the page images before they can be shown.

## Verification still to do

The Sanskrit of 2.47, 18.66 and the speaker counts are checked. A full verse-by-verse comparison against a printed critical edition is planned before launch.
