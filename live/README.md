# Gita Sarathi Live · vertical 24/7 YouTube stream

A vertical (1080×1920) live stream that recites the Bhagavad Gita verse by verse (the Sanskrit, then the 1909
translation) and, between verses, answers viewers who type **@gitalive** and a question in chat, in हिंदी,
Hinglish or English. Answers come from the same grounded engine as the website (exact verses, checked
explanations) and are shown and spoken on stream ("Asha पूछते हैं …").

It streams **the EscapeArenaLive way**: no OBS and no browser. `run_live.py` draws every frame itself, mixes Gita
Sarathi's voice (and optional music), and sends both through **ffmpeg** straight to YouTube. Put it on the same
free Oracle Cloud server as Escape Arena (Docker restarts it by itself), or run it on your PC.

```
YouTube chat ─► run_live.py ─► Gita Sarathi server (Render): /api/recite, /api/ask, /api/speak
                   │
                   └─ renderer (1080×1920) + voice mixer ─► ffmpeg ─► YouTube Live (vertical)
```

What viewers see, top to bottom: LIVE · 24/7 and the verse count; **गीता सारथी**; the chapter with a progress bar;
the stage (the verse being recited, or a viewer's question and its answer with verse cards, with a waveform while
it speaks); **next questions** and **just answered**; the 18 chapters; and "चैट में लिखें @gitalive + अपना सवाल".

**Channel name, logo, banner, thumbnail, descriptions, titles, tags and the growth plan:** see
**[CHANNEL-KIT.md](CHANNEL-KIT.md)** and the images in `branding/` (redraw with `python branding.py`).

## 1. Before you start (once)

**Render (the website).** Make a long random secret:

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

On Render → **parth-v2** → **Environment**, add `PARTH_LIVE_TOKEN` = that secret. The stream then gets its own
daily budgets (`PARTH_LIVE_AI_LIMIT` = 100 answers, `PARTH_LIVE_TTS_LIMIT` = 300 voice pieces by default), so it
never uses up the website's.

**YouTube.** Use a separate channel for Gita Sarathi (like @EscapeArenaLive is its own). In **YouTube Studio → Go
live → Stream**: copy the **stream key**, turn **Auto-start ON** and **Auto-stop OFF**, set the title and
description, audience "No, it's not made for kids", and leave live chat on.

**Chat questions (optional but the point of it).** On your PC, in this folder:
1. [console.cloud.google.com](https://console.cloud.google.com): new project → **APIs & Services → Library** →
   enable **YouTube Data API v3**.
2. **OAuth consent screen** → External, add yourself as a test user, then **Publish app** (so the sign-in doesn't
   expire every 7 days).
3. **Credentials → Create credentials → OAuth client ID → Desktop app** → download the JSON as
   `client_secret.json` here.
4. `pip install -r requirements.txt`, then `python youtube_auth.py`. Sign in with the **Gita channel's** account and
   allow read-only access. It saves `token.json`.

## 2a. 24/7 on the Oracle Cloud server (recommended)
Step by step in **[FREE-DEPLOY.md](FREE-DEPLOY.md)**. In short, on the server you already use for Escape Arena:

```
git clone -b v2 https://github.com/AmShubh45/parth-gita-assistant.git ~/gita-sarathi
cd ~/gita-sarathi/live && cp .env.example .env && nano .env      # stream key, LIVE_TOKEN
docker compose build
docker compose run --rm stream python run_live.py --out data/test.mp4 --seconds 20   # test clip
docker compose up -d                                                                 # GO LIVE
```

## 2b. From your PC
Install Python 3.12 and ffmpeg (`winget install Gyan.FFmpeg`), then in this folder:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          (fill in YT_STREAM_KEY and LIVE_TOKEN)
python run_live.py --preview    (watch it at http://127.0.0.1:8770/preview and ask test questions)
python run_live.py --out test.mp4 --seconds 30    (a test clip with sound)
start_gitalive.bat              (go live; restarts by itself; close the window to stop)
```

`install_autopilot.ps1` adds a Task Scheduler task that runs `start_gitalive.bat` when you sign in.

## 2c. With OBS instead
Set `STREAM_MODE=obs` in `.env`. `run_live.py` then serves a 16:9 overlay page at `http://127.0.0.1:8770/overlay`
and drives OBS over its WebSocket (own GitaLive profile and scene, stream key, watchdog), as in the first version.

## Commands

```
python run_live.py                               live to YouTube
python run_live.py --out test.mp4 --seconds 30   record a test clip instead
python run_live.py --preview                     no YouTube: watch and ask at http://127.0.0.1:8770/preview
python run_live.py --check                       check settings, ffmpeg, fonts, the server, the YouTube sign-in
```

## How it behaves on air
- **Recitation:** verses in order, resuming where it stopped. Each verse is recorded once with Gemini's voice and
  kept in `data/cache` for ever. New recordings are limited to `RECITE_TTS_PER_DAY` (200), so in the first few days
  the stream loops over the verses already recorded and adds more each day; after about four days all 701 are
  recorded and recitation costs nothing. Verses whose translation is still being verified show the Sanskrit only.
- **Questions:** a chat message with `@gitalive` (also `!gita`, `#gitalive`) becomes a question. Links, abuse,
  repeats and very short messages are dropped quietly; one question per viewer every 5 minutes; at most
  `ANSWERS_PER_HOUR` (20). Super Chats, moderators and you go first. The current verse finishes, then "Asha
  पूछते हैं …", then the answer with its verses, spoken. Someone in distress gets the helplines (Tele-MANAS 14416,
  KIRAN), never a lecture.
- **YouTube's free API quota** (10,000 units a day, reset at midnight Pacific time): each chat read costs 5. The
  stream spreads `CHAT_DAILY_UNITS` (9,000) over the day, about one read every 45 seconds, and reads twice as often
  for ten minutes after someone asks. An answer usually starts within a minute or two.
- **Background music (optional):** a track you have the rights to stream (e.g. YouTube Audio Library) at
  `data/music.mp3` plays quietly and dips while Gita Sarathi speaks.
- **Video:** 1080×1920 at 30 fps (720×1280 on smaller machines, or `SCALE=0.6667`), H.264 `veryfast`, 4500 kbps,
  keyframe every 2 s, AAC 128 kbps; the same settings as Escape Arena. Drawing a frame takes about 5 ms; the page
  is mostly still, so the CPU goes to the encoder.

## Keeping an eye on it
- Server: `docker compose logs -f --tail 50` (fps, what is on air, questions, chat quota).
- PC: `http://127.0.0.1:8770/status` and `logs/live.log`.
- Render's free plan sleeps when idle; the first question after a quiet spell can take about a minute while it
  wakes. `KEEP_SERVER_AWAKE=1` pings it every 10 minutes but uses Render's free hours (750 a month per account,
  shared with Samajh).

## Files
| File | What it does |
|---|---|
| `run_live.py` | Starts everything; `--out`, `--preview`, `--check` |
| `gitalive/render.py` | Draws the vertical frames (Pillow, Devanagari shaped with HarfBuzz) |
| `gitalive/broadcast.py` | Voice mixer, ffmpeg encoder, the real-time streaming loop |
| `gitalive/conductor.py` | Decides what is on air: recitation, questions between verses |
| `gitalive/moderation.py` | Which chat messages become questions, in what order |
| `gitalive/youtube.py` | Finds the live chat, reads it within the quota, refreshes the sign-in |
| `gitalive/audio.py` | Voices fetched once and kept on disk; daily ration for new verse recordings |
| `gitalive/sarathi.py` | Talks to the Gita Sarathi server |
| `gitalive/fonts.py` | Downloads the fonts (baked into the Docker image) |
| `gitalive/obs.py`, `static/overlay.html` | The OBS mode |
| `gitalive/server.py`, `static/preview.html` | Local preview page and status |
| `Dockerfile`, `docker-compose.yml` | The 24/7 server setup |
| `youtube_auth.py` | One-time YouTube sign-in |
| `CHANNEL-KIT.md`, `branding.py`, `branding/` | Channel name, texts, settings, growth plan; logo, banner, thumbnail, watermark |
| `start_gitalive.bat`, `install_autopilot.ps1` | Running it from a Windows PC |

Tests: `pytest tests/test_live.py` (from the repo root). Recording check: `python scripts/e2e_live_stream.py`.
