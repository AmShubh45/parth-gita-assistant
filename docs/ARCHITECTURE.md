# Gita Sarathi (Parth v2): architecture

Gita Sarathi · गीता सारथी (the charioteer: Krishna's role for Arjuna) answers real human problems (grief, fear, anger, confusion about duty, heartbreak, failure, comparison, guilt, loneliness) with what the Bhagavad Gita actually says. Every answer is grounded in specific verses, quoted exactly, read in their real context: who is speaking, to whom, at what moment of the Mahabharata, and how the classical commentators understood it. The aim is a product people anywhere can trust: it never invents a verse, never puts words in Krishna's mouth, and says so when the Gita does not address something.

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
| L2 Translations | Authentic public-domain English translations, quoted verbatim | Swami Swarupananda 1909, from four archive.org scans with word-level consensus; Telang 1882 and Besant 1922 next | **Built: 487/700 verified** (`kb/translations/swarupananda.json`); 213 awaiting review against page images |
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

- **Web app** (`parth/static/index.html`): one reading column. Ask by voice or text; each answer is verse cards (Sanskrit, transliteration, translation, context, meaning, "for you") with "This helped / doesn't fit" feedback.
- **Spoken answers** (the default voice mode, built):
  - **Ask:** tap the mic and speak. The page records 16 kHz audio (worklet) and stops by itself after about 1.5 s of silence (30 s maximum, or tap again).
  - **Understand:** `POST /api/voice` sends the WAV. One fast Gemini call transcribes it and does the engine's "understand" step together, then the deterministic crisis triage runs on the transcript, then the same select → compose → verify pipeline as typed questions. The transcript streams back first (NDJSON), so the page shows what it heard while the answer is written.
  - **Speak:** the spoken script is built only from the verified answer (`parth/speech.py`): opening, then for each verse its chapter, verse and speaker with the meaning and "for you", then the closing. The page plays it piece by piece through `POST /api/speak` (Gemini TTS, cached, daily cap `PARTH_DAILY_TTS_LIMIT`), preparing the next piece while one plays. Pieces are HMAC-signed so the endpoint speaks only text this server wrote. If TTS is unavailable, the browser's own voice reads the same text.
  - **Conversation mode** re-opens the mic after each spoken answer, and the last two questions travel with the next one so follow-ups ("aur batao") make sense.
  - **Audio on phones:** answers play through `<audio>` elements unlocked during the tap, never through the Web Audio context that records the mic (after the mic has been used, phones send Web Audio output to the quiet call earpiece). The mic opens without echo cancellation or the browser's gain control, which put phones in call mode; nothing plays while recording, and the page normalises the recording's level itself. On iOS the page also sets `navigator.audioSession` to `playback` before speaking.
  - **One voice, one language per answer:** only the answer text is sent to TTS (a style instruction in front of it gets read aloud), with one fixed voice, the model that last worked kept first, and loudness normalised. A failed piece is retried once; the browser voice takes over only when Gemini's voice is unavailable, and then uses a single (Hindi) voice for every language. Answers follow the language of the question, or the visitor's choice (Auto · हिंदी · English). A Hindi answer never contains English: its cards lead with the Hindi भावार्थ (the authentic English translation is one tap away), and a Hindi fallback speaks the Sanskrit shloka instead of the English translation.
- **Live (beta)** (real-time, `parth/live.py`):
  - **Connection:** the browser talks to Gemini Live directly, using a single-use ephemeral token whose session config is locked (system instruction, tools, audio, transcription).
  - **Grounding:** the model must call `find_verses`, which our server answers from the verified knowledge base. The page shows those exact verse cards while Gita Sarathi speaks.
  - **Half duplex:** Live audio streams to an `<audio>` element (loudspeaker). While Gita Sarathi's audio plays (plus a 400 ms tail) the page sends silence instead of the microphone, so a phone's loudspeaker cannot make it hear and interrupt itself. An `interrupted` that arrives while the mic is muted is ignored as echo; a "रोकें · Interrupt" button stops it by hand.
  - **Diagnostics:** `?debug=1` shows every milestone on screen. Each turn reports a `turn_summary` (audio received, transcript lengths, interrupts, echo ignored, server keys seen) and any unknown server keys to `/api/live/event`, so Render's logs show exactly where a session fails. No audio or transcripts are logged.
  - **Safety:** user transcripts run through the same safety triage, with helplines on screen.
  - **Limits:** a daily voice-session cap, a per-visitor rate limit, and 10-minute sessions.
  - **Honest limit:** spoken words are grounded and instructed, not verified word by word like the spoken answers above.
- **Testing:** `scripts/e2e_voice_mock.py` drives both modes in Chromium with a fake microphone and mocked Gemini: record → auto-stop → transcript → cards → every piece played → conversation mode's second question; and Live's half duplex, echo handling and tool call.
- **Gita Sarathi Live** (YouTube, 24/7, vertical, built: `live/`, setup in [live/README.md](../live/README.md)).
  - **Streams the EscapeArenaLive way** (default `STREAM_MODE=cloud`): no OBS and no browser. `render.py` draws the vertical 1080×1920 frame with Pillow (Devanagari shaped by HarfBuzz/raqm) in three layers (static once, scene per item, a few dynamic shapes per frame, about 5 ms), `broadcast.py` mixes the voice over optional music, and ffmpeg gets raw frames on stdin and PCM over TCP (no input probing, separate writer threads so neither pipe blocks the other) and sends H.264 `veryfast` 4500 kbps + AAC to YouTube RTMPS. 720×1280 on small machines (`SCALE`). It runs in Docker with `restart: unless-stopped` on the Oracle Always Free server next to Escape Arena ([live/FREE-DEPLOY.md](../live/FREE-DEPLOY.md)), or on a PC with `start_gitalive.bat`.
  - **OBS mode** (`STREAM_MODE=obs`, the first version) remains: a 16:9 overlay page as an OBS Browser Source, OBS driven over WebSocket with its own GitaLive profile and scene, a watchdog, and a Task Scheduler autopilot.
  - **The conductor decides what is on air** (the page only plays it): recitation in order, resuming where it stopped; between verses, viewer questions. With no page connected it keeps time itself.
  - **Recitation:** `GET /api/recite` gives every verse with one signed piece (chapter and verse, the Sanskrit, then the verified translation; Sanskrit only while a translation is unverified). Each piece is voiced once through `/api/speak` and kept on the laptop for ever, with a daily ration of new recordings; until all 701 are recorded the stream loops over the recorded ones.
  - **Viewer questions:** a chat message with `@gitalive` (or `!gita`, `#gitalive`) passes moderation (links, abuse, length, repeats, one per viewer every 5 minutes, a per-hour cap, Super Chats and moderators first) and goes through `/api/ask`, the same pipeline as the website. It appears as "Asha asks …", then the answer with its verses, spoken. Crisis questions get helplines.
  - **Chat reading:** `liveChatMessages.list` (5 units) with a quota governor that spreads the free 10,000 units a day (Pacific-time reset), reading faster for ten minutes after a question. The sign-in token is refreshed over plain HTTP.
  - **Budgets:** the laptop sends `X-Live-Token` (`PARTH_LIVE_TOKEN` on Render) and gets separate AI and TTS budgets, so the stream and the website never use up each other's.
  - **Testing:** `tests/test_live.py` (moderation, quota, chat parsing with a mocked API, the conductor, OBS against a fake obs-websocket server, the endpoints) and `scripts/e2e_live_overlay.py` (the overlay in Chromium: verses with voice, a question answered, recitation resumes).

## 5. Stack

- **Backend:** Python 3.12 and FastAPI, matching Samajh and the cricket engine.
- **Knowledge base:** versioned JSON in the repo, rebuilt by scripts and gated by tests. Embeddings are precomputed at deploy time (701 verses fit in memory; no vector database needed).
- **Models:**
  - Gemini for selection, writing, verification and embeddings, on a separate key from Samajh.
  - Gemini TTS for spoken answers and the live stream's recitation (browser speech as the website's fallback).
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

1. **Knowledge base L1–L3**: done. Authentic Swarupananda translation (L2): 487/700 verses verified.
2. **Remaining translations:** review the 213 unverified verses against page images, and add Telang and Besant. Then L4–L6 through the draft → verify → approve pipeline, and the answer engine with tests and evals.
3. **Answer engine**: done (`parth/`). Safety triage, Hindi/Hinglish/English, retrieval over verified verses with the situation index, select → compose → verify with code-level guardrails, and an offline fallback. Covered by 112 tests (86 for the app, 26 for the live stream), plus end-to-end checks for voice, the OBS overlay, and a real vertical recording through ffmpeg.
4. **Web app**: done and deployed on Render as Gita Sarathi, with spoken answers, conversation mode and Live (beta). The Node.js version is kept on the `legacy-node` branch.
5. **Gita Sarathi Live**: built (`live/`): vertical 24/7 cloud stream like Escape Arena (OBS mode optional), recitation loop and YouTube chat Q&A. Next: deploy it on the Oracle server.
6. **Growth**: voice, more languages, sharing cards.

## 9. Needed from the owner

- **Gemini:** a separate API key for Parth, set on Render.
- **YouTube:** a Google Cloud OAuth client for chat reading, and the channel's stream key. Both go in the live folder's `.env` and are never committed.
- **Review:** about 30 minutes to review a sample of context notes and life-situation mappings before launch.
