"""Gita Sarathi Live: a 24/7 YouTube stream that recites the Gita and answers viewers' questions.

    python run_live.py              everything: overlay, recitation, chat questions, OBS on air
    python run_live.py --preview    no OBS, no YouTube: open http://127.0.0.1:8770/preview and ask test questions
    python run_live.py --no-stream  set OBS up and run everything, but do not go live
    python run_live.py --check      check settings and connections, then exit

Settings come from live/.env (see .env.example). Logs go to live/logs/live.log.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from gitalive.audio import AudioCache  # noqa: E402
from gitalive.conductor import Conductor, Hub  # noqa: E402
from gitalive.config import Config  # noqa: E402
from gitalive.moderation import Moderator  # noqa: E402
from gitalive.obs import Obs, ObsClient, ObsError  # noqa: E402
from gitalive.sarathi import Sarathi  # noqa: E402
from gitalive.server import make_app  # noqa: E402
from gitalive.youtube import ChatReader, QuotaGovernor  # noqa: E402

log = logging.getLogger("gitalive")


def setup_logging(cfg: Config) -> None:
    cfg.log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in (logging.StreamHandler(sys.stdout), RotatingFileHandler(cfg.log_dir / "live.log", maxBytes=2_000_000,
                                                                    backupCount=3, encoding="utf-8")):
        h.setFormatter(fmt)
        root.addHandler(h)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


async def check(cfg: Config) -> int:
    ok = True
    for p in cfg.problems():
        print("  ✗", p)
        ok = False
    sar = Sarathi(cfg.sarathi_url, cfg.live_token)
    try:
        h = await sar.health()
        live = h.get("live_stream", {})
        print(f"  ✓ Gita Sarathi server: {cfg.sarathi_url} (AI answers available: {h.get('model')})")
        if cfg.live_token and not live.get("enabled"):
            print("  ✗ The server has no PARTH_LIVE_TOKEN set: add it on Render (same value as LIVE_TOKEN).")
            ok = False
        verses = await sar.recitation(cfg.cache_dir / "verses.json")
        print(f"  ✓ {len(verses)} verses to recite")
    except Exception as exc:
        print(f"  ✗ Gita Sarathi server not reachable at {cfg.sarathi_url}: {exc}")
        ok = False
    finally:
        await sar.close()
    try:
        st = await ObsClient(cfg.obs_ws_url, cfg.obs_ws_password).one("GetVersion")
        print(f"  ✓ OBS {st.get('obsVersion')} reachable at {cfg.obs_ws_url}")
    except ObsError as exc:
        print(f"  ✗ {exc}. Is OBS open, with Tools > WebSocket Server Settings enabled?")
        ok = False
    if cfg.token_file.exists():
        try:
            gov = QuotaGovernor(cfg.chat_daily_units)
            reader = ChatReader(cfg.token_file, gov, lambda m: False)
            chat = await reader.find_chat()
            print("  ✓ YouTube sign-in works;", "live chat found" if chat else "no live broadcast right now (fine before going live)")
            await reader.http.aclose()
        except Exception as exc:
            print(f"  ✗ YouTube: {exc}")
            ok = False
    print("All good." if ok else "Fix the ✗ lines above, then run this again.")
    return 0 if ok else 1


async def main(args) -> int:
    cfg = Config.load()
    setup_logging(cfg)
    if args.check:
        return await check(cfg)
    sar = Sarathi(cfg.sarathi_url, cfg.live_token)
    audio = AudioCache(cfg.cache_dir, sar, cfg.recite_tts_per_day)
    mod = Moderator(cfg.triggers, per_hour=cfg.answers_per_hour)
    conductor = Conductor(sar, audio, Hub(), mod, cfg.state_file, cfg.cache_dir / "verses.json", cfg.silent_seconds)
    obs = chat = None
    if not args.preview:
        obs = Obs(ObsClient(cfg.obs_ws_url, cfg.obs_ws_password), cfg.overlay_url, cfg.yt_stream_key, cfg.obs_exe)
        obs.want_live = not args.no_stream
        if cfg.token_file.exists():
            chat = ChatReader(cfg.token_file, QuotaGovernor(cfg.chat_daily_units), conductor.offer)
        else:
            log.warning("token.json missing: chat questions are off. Run `python youtube_auth.py` once.")
    extra = lambda: {"obs": obs.status if obs else "off (preview)", "chat": chat.status if chat else "off",
                     "chat_units_left": chat.gov.left() if chat else None}
    app = make_app(conductor, cfg.cache_dir, cfg.music_file, extra)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=cfg.overlay_port, log_level="warning"))

    async def keep_awake():
        while True:
            await asyncio.sleep(600)
            await sar.ping()

    tasks = [server.serve(), conductor.run()]
    if obs:
        tasks.append(obs.watchdog())
    if chat:
        tasks.append(chat.run())
    if cfg.keep_awake:
        tasks.append(keep_awake())
    log.info("overlay: %s · preview: http://127.0.0.1:%d/preview · status: http://127.0.0.1:%d/status",
             cfg.overlay_url, cfg.overlay_port, cfg.overlay_port)
    for p in cfg.problems(need_youtube=bool(chat) or not args.preview, need_obs=not args.preview):
        log.warning("setup: %s", p)
    try:
        await asyncio.gather(*tasks)
    finally:
        await sar.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", action="store_true", help="no OBS or YouTube; test in a browser")
    ap.add_argument("--no-stream", action="store_true", help="set up OBS but do not go live")
    ap.add_argument("--check", action="store_true", help="check settings and connections, then exit")
    try:
        sys.exit(asyncio.run(main(ap.parse_args())))
    except KeyboardInterrupt:
        pass
