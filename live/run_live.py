"""Gita Sarathi Live: a 24/7 vertical YouTube stream that recites the Gita and answers viewers' questions.

    python run_live.py                               live to YouTube (YT_STREAM_KEY in .env)
    python run_live.py --out test.mp4 --seconds 30   record a test clip instead
    python run_live.py --preview                     no YouTube: watch http://127.0.0.1:8770/preview, ask test questions
    python run_live.py --check                       check settings and connections, then exit
    python run_live.py --no-stream                   OBS mode only: set OBS up but do not go live

STREAM_MODE=cloud (default) renders the vertical 1080x1920 stream itself and sends it through ffmpeg, the
EscapeArenaLive way: no OBS, no browser, runs 24/7 in Docker. STREAM_MODE=obs shows an overlay page in OBS.
Settings come from live/.env (see .env.example). Logs go to logs/live.log in the data folder.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import shutil
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from gitalive.audio import AudioCache  # noqa: E402
from gitalive.broadcast import RATE, LocalPlayer, Mixer, Streamer, auto_scale, decode_music  # noqa: E402
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
    print(f"  · mode: {cfg.stream_mode} · data folder: {cfg.data_dir}")
    if cfg.stream_mode == "cloud":
        if shutil.which(cfg.ffmpeg):
            s = auto_scale(cfg.scale)
            print(f"  ✓ ffmpeg found · will stream {int(1080 * s / 2) * 2}x{int(1920 * s / 2) * 2} @ {cfg.fps} fps")
        else:
            print(f"  ✗ ffmpeg not found ({cfg.ffmpeg}). Install it (Windows: winget install Gyan.FFmpeg) or set FFMPEG_PATH.")
            ok = False
        try:
            from gitalive.fonts import ensure
            ensure(cfg.fonts_dir, log=lambda m: None)
            print("  ✓ fonts ready")
        except Exception as exc:
            print(f"  ✗ fonts: {exc}")
            ok = False
    for p in cfg.problems(need_youtube=True, need_obs=True):
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
    if cfg.stream_mode == "obs":
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


class SilentClock(threading.Thread):
    """--preview in cloud mode: nothing is streamed, but voices still "play" in real time so items advance."""

    def __init__(self, mixer: Mixer):
        super().__init__(daemon=True)
        self.mixer, self.stopped = mixer, threading.Event()

    def run(self) -> None:
        import time
        while not self.stopped.is_set():
            self.mixer.render(RATE // 10)
            time.sleep(0.1)


async def main(args) -> int:
    cfg = Config.load()
    setup_logging(cfg)
    if args.check:
        return await check(cfg)
    cloud = cfg.stream_mode != "obs"
    sar = Sarathi(cfg.sarathi_url, cfg.live_token)
    audio = AudioCache(cfg.cache_dir, sar, cfg.recite_tts_per_day)
    mod = Moderator(cfg.triggers, per_hour=cfg.answers_per_hour)
    renderer = mixer = streamer = None
    if cloud:
        from gitalive.fonts import ensure
        from gitalive.render import Fonts, Renderer
        renderer = Renderer(Fonts(ensure(cfg.fonts_dir, log=log.info)), trigger=cfg.triggers[0] if cfg.triggers else "@gitalive")
        music = decode_music(cfg.music_file, cfg.ffmpeg) if cfg.music_file.exists() else None
        mixer = Mixer(music, cfg.volume, cfg.music_volume)
        hub = Hub(LocalPlayer(renderer, mixer, cfg.cache_dir))
    else:
        hub = Hub()
    conductor = Conductor(sar, audio, hub, mod, cfg.state_file, cfg.cache_dir / "verses.json", cfg.silent_seconds)

    obs = chat = None
    if cloud and not args.preview:
        if not args.out and not cfg.yt_stream_key:
            log.error("YT_STREAM_KEY is empty. Put the Gita channel's stream key in .env, or run with --out test.mp4.")
            return 1
        streamer = Streamer(renderer, mixer, target=args.out or cfg.rtmp_url, key="" if args.out else cfg.yt_stream_key,
                            fps=cfg.fps, scale=auto_scale(cfg.scale), bitrate=cfg.video_bitrate or None,
                            preset=cfg.x264_preset, ffmpeg=cfg.ffmpeg, seconds=args.seconds or 0)
    elif not cloud and not args.preview:
        obs = Obs(ObsClient(cfg.obs_ws_url, cfg.obs_ws_password), cfg.overlay_url, cfg.yt_stream_key, cfg.obs_exe)
        obs.want_live = not args.no_stream
    if not args.preview and not args.out:
        if cfg.token_file.exists():
            chat = ChatReader(cfg.token_file, QuotaGovernor(cfg.chat_daily_units), conductor.offer)
        else:
            log.warning("token.json missing: chat questions are off. Run `python youtube_auth.py` once and copy it here.")
    extra = lambda: {"mode": cfg.stream_mode, "stream": streamer.status if streamer else ("preview" if args.preview else None),
                     "obs": obs.status if obs else None, "chat": chat.status if chat else "off",
                     "chat_units_left": chat.gov.left() if chat else None}
    app = make_app(conductor, cfg.cache_dir, cfg.music_file, extra, renderer=renderer)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=cfg.overlay_port, log_level="warning"))

    async def keep_awake():
        while True:
            await asyncio.sleep(600)
            await sar.ping()

    async def run_streamer():
        await asyncio.to_thread(streamer.run)
        if streamer.error:
            raise SystemExit(1)       # Docker / the .bat loop restarts us
        server.should_exit = True
        raise SystemExit(0)

    tasks = [server.serve(), conductor.run()]
    if streamer:
        tasks.append(run_streamer())
    elif cloud and args.preview:
        SilentClock(mixer).start()
    if obs:
        tasks.append(obs.watchdog())
    if chat:
        tasks.append(chat.run())
    if cfg.keep_awake:
        tasks.append(keep_awake())
    log.info("mode %s · preview: http://127.0.0.1:%d/preview · status: http://127.0.0.1:%d/status",
             cfg.stream_mode, cfg.overlay_port, cfg.overlay_port)
    for p in cfg.problems(need_youtube=bool(chat), need_obs=not args.preview and not args.out):
        log.warning("setup: %s", p)
    try:
        await asyncio.gather(*tasks)
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        if streamer:
            streamer.stopped.set()
        await sar.close()
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preview", action="store_true", help="no YouTube; watch it in a browser")
    ap.add_argument("--out", help="record a test video to this file instead of going live (cloud mode)")
    ap.add_argument("--seconds", type=float, default=0, help="with --out: length of the test video")
    ap.add_argument("--no-stream", action="store_true", help="OBS mode: set up OBS but do not go live")
    ap.add_argument("--check", action="store_true", help="check settings and connections, then exit")
    try:
        sys.exit(asyncio.run(main(ap.parse_args())))
    except KeyboardInterrupt:
        pass
