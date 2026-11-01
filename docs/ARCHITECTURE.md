# Parth v2: architecture

Parth answers real human problems (grief, fear, anger, confusion about duty, heartbreak, failure, comparison, guilt, loneliness) with what the Bhagavad Gita actually says. Every answer is grounded in specific verses, quoted exactly, read in their real context: who is speaking, to whom, at what moment of the Mahabharata, and how the classical commentators understood it. The aim is a product people anywhere can trust: it never invents a verse, never puts words in Krishna's mouth, and says so when the Gita does not address something.

## 1. Principles

1. **Verses are never generated.** The model chooses verse IDs. The Sanskrit, transliteration and translation shown to the user are copied from the knowledge base by ID. A model cannot misquote what it never writes.
2. **Cite or stay silent.** Every claim in an answer points to a verse or a curated context note. If nothing supports it, Parth says the Gita does not speak to it directly.
3. **Context before application.** A verse is explained first in its own setting (speaker, listener, situation, the question it answers), then applied to the user's life. Lines lifted out of context, a common source of popular misreadings, are exactly what this prevents.
4. **The tradition, not the internet.** "What Krishna actually means" is anchored in the classical Sanskrit commentaries (Shankara, Ramanuja, Madhva, Sridhara, Madhusudana and others). Where schools read a verse differently, Parth says so rather than picking one silently.
5. **Safety first.** Self-harm, crisis or abuse routes to human help before anything else. Parth is not a substitute for a doctor, therapist, lawyer or teacher, and says so when it matters.
6. **Licences are part of the data.** Only public-domain or permitted text is ever displayed, and every source carries its licence in the knowledge base.

## 2. Knowledge base (layers)

| Layer | Contents | Source | Status |
|---|---|---|---|
| L1 Canon | 701 verses: Sanskrit, IAST transliteration, chapter, verse, speaker, listener | `gita/gita` (Unlicense); text is ancient, public domain | **Built** (`kb/verses.json`) |
| L2 Translations | Authentic public-domain English translations, quoted verbatim | Telang 1882, Besant 1905, Swarupananda 1909 (and Arnold 1885 for poetry), ingested from original scans | **Blocked:** source sites not reachable from the build environment |
| L2b Search text | Modernised English derived from Purohit Swami / Sivananda, used for retrieval only, never displayed | `gita/gita` | Built, quarantined (`search_en`) |
| L3 Classical commentaries | 13 Sanskrit commentaries per verse | `gita/gita`; centuries old, public domain | **Built** (`kb/commentaries.json`) |
| L4 Context notes | Per verse: the situation, the question it answers, what comes before/after, key terms, notes where schools differ | Drafted by a model from L1–L3, checked by a second model against the sources, approved by a human | Phase 2 |
| L5 Life-situation index | ~60 situations/emotions → verse IDs, each with a one-line justification and reviewer sign-off | Same draft → verify → approve pipeline | Phase 2 |
| L6 Evaluation set | 300+ real questions with expected verses, plus adversarial and crisis cases | Hand-written, grown from real user questions | Phase 2 |

Hindi: word meanings and explanations written for Parth and clearly labelled as explanation, never as a translation, until a licensed Hindi translation is available.

**Data found while building L1–L3 (why the checks matter):**
- The upstream English contains "No changes needed." in place of two verses and a "Revised:" prefix on another, and modernises the originals ("Thy right is to work only…" became "Your right is only to work…"). It is therefore not quotable.
- Speakers are detected from the Sanskrit "X उवाच" lines and checked against the traditional count: Krishna 574, Arjuna 85 (+ the optional 13.1), Sanjaya 40, Dhritarashtra 1.
- Every rule is enforced by `tests/test_kb.py`.

## 3. Answer pipeline

```
question
  → safety triage        crisis / self-harm → helplines + gentle message first; abuse, hate, politics → decline
  → understand           emotion, situation, language (Hindi / English / Hinglish)
  → retrieve             hybrid: BM25 over search text, transliteration and context notes
                         + embeddings, boosted by the life-situation index; rerank to ~8 candidates
  → select (LLM, JSON)   1–3 verse IDs + why each fits, from the candidates only
  → compose (LLM)        explanation that cites only the selected IDs and their context notes
  → verify (2nd model)   every claim supported? context right? no quoted text outside the KB?
                         fail → regenerate once → else fall back to "verses + context, no commentary"
  → render               verse text injected from the KB by ID; stream to the user
```

- **Latency targets:** first words under 1.5 s; full answer under 6 s.
- **Model calls:** three short calls (select, compose, verify) on a fast Gemini model, with a fallback chain like Samajh's for quota limits.

## 4. Product surfaces

- **Web app.** Ask in text, answers stream over Server-Sent Events. Each verse card has Sanskrit, transliteration, translation and context, plus "Why this verse?" and "This helped / doesn't fit" feedback.
- **Voice** (later). Real-time voice on the same pipeline, so voice answers obey the same grounding rules.
- **Parth Live** (YouTube, 24/7).
  - Built like the MarketLab live channel: a separate folder on the laptop, OBS with its own **ParthLive** profile and **GitaLive** scene, controlled from Python over OBS WebSocket. The stream key is in that folder's `.env`, and a Windows Task Scheduler autopilot starts it.
  - OBS shows a Browser Source page from the Parth server.
  - **Recitation loop:** the Gita in order, verse by verse. Sanskrit is shown and spoken, followed by the translation and a short context card ("Krishna to Arjuna, after Arjuna lays down his bow…").
  - **Viewer questions:** a chat message containing `@gitalive` (or `!gita`) passes moderation and runs through the same pipeline. It appears on stream as "Asked by <name>", spoken and shown with its verses, then the recitation resumes.
  - **Chat reading:** YouTube Data API `liveChatMessages.streamList`, a long-lived connection at 5 quota units per call. This fits the free 10,000 units a day.
  - **Limits:** per-viewer rate limits, de-duplication, a profanity filter, and a cap on answers per hour.

## 5. Stack

- **Backend:** Python 3.12 and FastAPI, matching Samajh and the cricket engine.
- **Knowledge base:** versioned JSON in the repo, rebuilt by scripts and gated by tests. Embeddings are precomputed at deploy time (701 verses fit in memory; no vector database needed).
- **Models:**
  - Gemini for selection, writing, verification and embeddings, on a separate key from Samajh.
  - Google Cloud TTS (as in the cricket engine) for Parth Live speech.
- **Storage:** Postgres (Neon) for questions, answers, feedback and moderation logs. No personal data beyond what the user types; questions are stored anonymously.
- **Observability:** Langfuse traces per stage, plus a daily evaluation run.
- **Deploy:** Render (Docker).

## 6. Quality and evaluation

Measured on every change:
- **Citation validity:** 100%, checked deterministically. Every verse ID exists, and every displayed verse text equals the knowledge base text.
- **Retrieval:** recall@3 against the L6 set.
- **Verifier pass rate.**
- **Safety:** crisis cases must route to help 100% of the time.
- **Human ratings** on a weekly sample, plus user feedback.

A change that lowers any of these does not ship.

## 7. Safety and respect

- **Crisis:** in India, Tele-MANAS 14416 and KIRAN 1800-599-0019; local numbers elsewhere. This is shown before anything else.
- **Content:** no medical, legal or financial advice. No use of the Gita to justify violence, caste discrimination or political positions. The battlefield setting is explained as the commentators explain it.
- **Viewers:** live-stream answers pass the same filters plus moderation, because the audience is public.

## 8. Roadmap

1. **Knowledge base L1–L3**: done.
2. **Authentic translations (L2)** once source sites are reachable. Then L4–L6 through the draft → verify → approve pipeline, and the answer engine with tests and evals.
3. **Web app**: deploy to Render, replacing the Node.js version (kept on the `legacy-node` branch).
4. **Parth Live**: OBS automation, recitation loop and YouTube chat Q&A.
5. **Growth**: voice, more languages, sharing cards.

## 9. Needed from the owner

- **Network access:** allow these domains in the build environment so authentic translations can be ingested: `archive.org`, `en.wikisource.org`, `sacred-texts.com`, `gutenberg.org`.
- **Gemini:** a separate API key for Parth, set on Render.
- **YouTube:** a Google Cloud OAuth client for chat reading, and the channel's stream key. Both go in the live folder's `.env` and are never committed.
- **Review:** about 30 minutes to review a sample of context notes and life-situation mappings before launch.
