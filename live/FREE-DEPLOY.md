# Free 24/7 deploy on Oracle Cloud (next to Escape Arena)

Gita Sarathi Live runs exactly like Escape Arena Live: a Docker container on the Oracle Cloud **Always Free**
server that streams straight to YouTube and restarts by itself. If you already followed Escape Arena's
`FREE-DEPLOY.md`, you have the server, SSH key and Docker; skip to step 2.

The two streams can share the server (4 ARM cores, 24 GB). Gita Sarathi's picture is mostly still, so it needs
about one core for encoding at 1080×1920. If the logs ever show fewer than 30 fps for either stream, set
`SCALE=0.6667` (720×1280) in Gita Sarathi's `.env`.

## 1. A server (only if you don't have Escape Arena's)
Follow steps 1–5 of Escape Arena's `FREE-DEPLOY.md` (Oracle account, SSH key, the Ampere A1 server with Ubuntu
24.04, and Docker). Use `retry-oracle.ps1` if Oracle says "Out of host capacity".

## 2. Get the code onto the server
Connect (replace `YOUR_IP`):

```bash
ssh -i $HOME\.ssh\oracle_key ubuntu@YOUR_IP
```

Then, on the server:

```bash
git clone -b v2 https://github.com/AmShubh45/parth-gita-assistant.git ~/gita-sarathi
```

```bash
cd ~/gita-sarathi/live && cp .env.example .env && nano .env
```

Fill in `YT_STREAM_KEY` (the **Gita Sarathi channel's** key, not Escape Arena's) and `LIVE_TOKEN` (the same secret
as `PARTH_LIVE_TOKEN` on Render). Save with **Ctrl+O, Enter, Ctrl+X**.

## 3. Let it read chat
On your PC, in the `live` folder where you ran `python youtube_auth.py`, copy the sign-in to the server:

```bash
scp -i $HOME\.ssh\oracle_key token.json ubuntu@YOUR_IP:~/gita-sarathi/live/data/
```

(Optional) background music you have the rights to stream:

```bash
scp -i $HOME\.ssh\oracle_key music.mp3 ubuntu@YOUR_IP:~/gita-sarathi/live/data/
```

## 4. Build and test (not live yet)

```bash
docker compose build
```

(The first build takes a few minutes; it downloads ffmpeg and the fonts.)

```bash
docker compose run --rm stream python run_live.py --check
```

```bash
docker compose run --rm stream python run_live.py --out data/test.mp4 --seconds 30
```

The log shows `recording … 1080x1920 @ 30fps` and, every few seconds, the fps (it should be about 30). Download the
clip to your PC and watch it (second PowerShell window, in any folder):

```bash
scp -i $HOME\.ssh\oracle_key ubuntu@YOUR_IP:~/gita-sarathi/live/data/test.mp4 .
```

## 5. GO LIVE 🔴

```bash
docker compose up -d
```

```bash
docker compose logs -f
```

YouTube Studio shows the Gita Sarathi channel **LIVE** within about 20 seconds. Press **Ctrl+C** to stop watching
the logs; the stream keeps running. You can close PowerShell and turn your laptop off.

## Daily use (connect, then `cd ~/gita-sarathi/live`)

| Task | Command |
|---|---|
| Is it running? | `docker compose ps` |
| See the logs | `docker compose logs -f --tail 50` |
| Stop the stream | `docker compose down` |
| Start it again | `docker compose up -d` |
| Change a setting | `nano .env` then `docker compose up -d` |
| Update to the latest code | `git pull` then `docker compose up -d --build` |

## Good to know
- Voices, the place in the Gita, `token.json` and the music live in `data/`, so updates and restarts keep them.
- Nothing to open in the firewall: the server only sends video to YouTube and talks to the Gita Sarathi website.
- If chat stops working after a few days, the Google sign-in expired: publish the OAuth app ("In production"),
  run `youtube_auth.py` again on the PC and copy the new `token.json`.
