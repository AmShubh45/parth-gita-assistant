# Gita Sarathi Live · 24/7 YouTube stream

A YouTube live stream that recites the Bhagavad Gita verse by verse (Sanskrit, then the 1909 translation) and,
between verses, answers viewers who type **@gitalive** and a question in chat. Questions can be in हिंदी, Hinglish
or English. Answers come from the same grounded engine as the website (exact verses, checked explanations) and
are shown and spoken on stream. The stream says the question's author's name on screen ("Asha asks …").

It runs on your laptop next to OBS, like the cricket stream: this folder hosts a local overlay page, OBS shows it
as a Browser Source and streams it to YouTube. The website on Render supplies verses, answers and voices.

```
YouTube chat ──► run_live.py ──► Gita Sarathi server (Render): /api/recite, /api/ask, /api/speak
                    │
                    └─► http://127.0.0.1:8770/overlay ──► OBS (profile + scene "GitaLive") ──► YouTube Live
```

## One-time setup (about 30 minutes)

### 1. Render (the website)
Make a long random secret on any computer:

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

On Render → **parth-v2** → **Environment**, add `PARTH_LIVE_TOKEN` = that secret, and save (it redeploys).
The stream then gets its own daily budgets (`PARTH_LIVE_AI_LIMIT`, default 100 answers; `PARTH_LIVE_TTS_LIMIT`,
default 300 voice pieces), so it never uses up the website's, and the website never starves the stream.

### 2. The laptop
Install **Python 3.12** (tick "Add to PATH") and **OBS 30+**. Then, in a terminal:

```
git clone -b v2 https://github.com/AmShubh45/parth-gita-assistant.git C:\GitaSarathi
cd C:\GitaSarathi\live
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Open `.env` in Notepad and fill in:
- `LIVE_TOKEN`: the same secret as on Render.
- `YT_STREAM_KEY`: YouTube Studio → **Go live** → **Stream** → Stream key. (Keep it secret; never paste it in chat.)
- `OBS_WS_PASSWORD`: OBS → **Tools → WebSocket Server Settings** → tick *Enable*, **Show connect info**, copy the password.
- `OBS_EXE`: where OBS is installed (the default path is usually right).

You don't need to build scenes in OBS: the first run creates its own **GitaLive** profile, scene collection and
scene, with the overlay as a 1920×1080 Browser Source (audio routed through OBS) and your stream key. Other OBS
setups on the laptop are left alone.

### 3. YouTube
- Live streaming must be enabled on the channel (YouTube Studio → Go live; it can take 24 hours the first time).
- In YouTube Studio → **Stream** settings for your stream key: turn **Auto-start** on and **Auto-stop** off, so the
  broadcast starts whenever OBS connects and keeps going. Set the title, description, category, "Not made for
  kids", and leave live chat on.

### 4. Let the stream read chat (Google Cloud, free)
1. [console.cloud.google.com](https://console.cloud.google.com) → new project "Gita Sarathi Live".
2. **APIs & Services → Library** → enable **YouTube Data API v3**.
3. **OAuth consent screen** → External → app name, your email → add yourself as a test user → then **Publish app**
   ("In production"). An unverified app is fine for your own channel; publishing avoids the weekly re-sign-in that
   "Testing" mode forces.
4. **Credentials → Create credentials → OAuth client ID → Desktop app** → **Download JSON** → save it in this
   folder as `client_secret.json`.
5. Run `python youtube_auth.py`, sign in with the **channel's** Google account and allow read-only access
   ("Google hasn't verified this app" → Advanced → continue). This saves `token.json` here.

`client_secret.json`, `token.json` and `.env` stay on this laptop; they are git-ignored.

## Try it, check it, go live

```
python run_live.py --preview     # no OBS, no YouTube: open http://127.0.0.1:8770/preview
python run_live.py --check       # checks Render, the token, OBS and the YouTube sign-in
python run_live.py               # sets up OBS and goes live
```

In preview you see exactly what will be streamed, and can ask test questions as a viewer.

### Run it 24/7 (autopilot)
```
powershell -ExecutionPolicy Bypass -File .\install_autopilot.ps1
```
This adds a Windows Task Scheduler task, **GitaSarathiLive**, that starts one minute after you sign in and restarts
if anything stops it. `start_gitalive.bat` restarts the stream if it ever exits, and the OBS watchdog restarts the
stream (or OBS itself) if it drops. For a truly unattended laptop, set Windows to sign in automatically, never
sleep when plugged in, and install updates outside streaming hours.

## How it behaves on air
- **Recitation:** verses in order, resuming where it stopped. Each verse is recorded once with Gemini's voice and
  kept in `live/cache` for ever. New recordings are limited to `RECITE_TTS_PER_DAY` (default 200), so in the first
  few days the stream loops over the verses already recorded and adds more each day; after about four days all
  701 are recorded and recitation costs nothing. Verses whose translation is still being verified show the
  Sanskrit only.
- **Questions:** a chat message with `@gitalive` (also `!gita` or `#gitalive`) becomes a question. Links, abuse,
  repeats and very short messages are dropped quietly. One question per viewer every 5 minutes, at most
  `ANSWERS_PER_HOUR` (default 20) answers an hour. Super Chats, moderators and you go first. The current verse
  finishes, then the stream shows "Asha asks …", then the answer with its verses, spoken. Someone in distress
  gets the helplines (Tele-MANAS 14416, KIRAN), never a lecture.
- **Chat reading and the free YouTube quota:** YouTube allows 10,000 API units a day (reset at midnight Pacific
  time); each chat read costs 5. The stream spreads `CHAT_DAILY_UNITS` (default 9,000) over the day, about one read
  every 45 seconds, and reads twice as often for ten minutes after someone asks. So an answer usually starts within
  a minute or two of the question.
- **Background music (optional):** put a music file you have the rights to stream at `live/assets/music.mp3`
  (for example from the YouTube Audio Library). It plays quietly and dips while Gita Sarathi speaks.

## Keeping an eye on it
- `http://127.0.0.1:8770/status`: what is on air, the question queue, OBS and chat status, quota left.
- `live/logs/live.log`: everything that happened (rotates at 2 MB).
- Render's free plan sleeps when idle; the first question after a quiet spell can take about a minute while it
  wakes. `KEEP_SERVER_AWAKE=1` pings it every 10 minutes, but uses Render's free monthly hours (750 per account,
  shared with Samajh).

## Stop
Close the terminal (or `Stop-ScheduledTask -TaskName GitaSarathiLive`), then stop streaming in OBS. Remove the
autopilot with `Unregister-ScheduledTask -TaskName GitaSarathiLive -Confirm:$false`.

## Files
| File | What it does |
|---|---|
| `run_live.py` | Starts everything; `--preview`, `--check`, `--no-stream` |
| `gitalive/conductor.py` | Decides what is on air: recitation, questions between verses |
| `gitalive/moderation.py` | Which chat messages become questions, in what order |
| `gitalive/youtube.py` | Finds the live chat, reads it within the quota, refreshes the sign-in |
| `gitalive/obs.py` | OBS over WebSocket: GitaLive profile/scene/overlay, stream key, watchdog |
| `gitalive/audio.py` | Voices fetched once and kept on disk; daily ration for new verse recordings |
| `gitalive/sarathi.py` | Talks to the Gita Sarathi server |
| `gitalive/server.py`, `static/` | The local overlay page, preview page, status |
| `youtube_auth.py` | One-time YouTube sign-in |
| `start_gitalive.bat`, `install_autopilot.ps1` | Windows autopilot |

Tests: `pytest tests/test_live.py` (from the repo root). Browser check: `python scripts/e2e_live_overlay.py`.
