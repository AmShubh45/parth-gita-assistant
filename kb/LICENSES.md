# Knowledge base sources and licences

Only text listed here as **quotable** may be shown to users. Built by `scripts/build_kb.py`; every rule below is enforced by `tests/test_kb.py`.

| Data | File / field | Source | Licence | Shown to users? |
|---|---|---|---|---|
| Sanskrit verses, transliteration | `verses.json` → `sanskrit`, `transliteration` | [gita/gita](https://github.com/gita/gita) | The text is ancient (public domain); the compilation is released under the Unlicense | Yes |
| Speaker / listener | `verses.json` → `speaker`, `addressed_to` | Derived from the Sanskrit "X उवाच" lines | Our own data | Yes |
| Chapter names and summaries | `chapters.json` | gita/gita | Unlicense | Yes |
| Classical commentaries (Sanskrit): Shankara, Ramanuja, Madhva, Sridhara, Madhusudana, Abhinavagupta, Vedanta Deshika, Anandagiri, Jayatirtha, Vallabha, Purushottama, Neelakantha, Dhanapati | `commentaries.json` | gita/gita | Centuries old; public domain | As grounding; short quotes with attribution |
| Modernised English (from Purohit Swami 1935 and Swami Sivananda) | `verses.json` → `search_en` | gita/gita | Edited upstream; **not the authentic translations** | **No**: used for search only |
| Authentic translations | `verses.json` → `translations` | Planned: Telang 1882, Besant 1905, Swarupananda 1909 (public domain worldwide) | Public domain | Yes, once ingested and verified |

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

## Verification still to do

The Sanskrit of 2.47, 18.66 and the speaker counts are checked. A full verse-by-verse comparison against a printed critical edition is planned before launch.
