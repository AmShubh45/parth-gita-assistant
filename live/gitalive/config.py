"""Settings from live/.env (no extra dependency for reading it)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent   # the live/ folder


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


@dataclass
class Config:
    # "cloud": render and stream by ourselves through ffmpeg, vertical 1080x1920 (the EscapeArenaLive way,
    # for a 24/7 server); "obs": show an overlay page that OBS captures (the laptop way).
    stream_mode: str = "cloud"
    sarathi_url: str = "https://parth-gita-assistant-1.onrender.com"
    live_token: str = ""
    yt_stream_key: str = ""
    google_client_secret: Path = HERE / "client_secret.json"
    token_file: Path = HERE / "token.json"
    obs_ws_url: str = "ws://127.0.0.1:4455"
    obs_ws_password: str = ""
    obs_exe: str = ""
    triggers: tuple[str, ...] = ("@gitalive", "!gita", "#gitalive")
    chat_daily_units: int = 9000
    answers_per_hour: int = 20
    recite_tts_per_day: int = 200
    silent_seconds: float = 20.0
    overlay_port: int = 8770
    keep_awake: bool = False
    data_dir: Path = HERE
    cache_dir: Path = HERE / "cache"
    log_dir: Path = HERE / "logs"
    state_file: Path = HERE / "state.json"
    music_file: Path = HERE / "assets" / "music.mp3"
    fonts_dir: Path = HERE / "fonts"            # baked into the Docker image, outside the data volume
    # cloud streaming (same knobs as EscapeArenaLive's .env)
    rtmp_url: str = "rtmps://a.rtmps.youtube.com/live2"
    scale: str = "auto"                         # auto | 1 (1080x1920) | 0.6667 (720x1280)
    fps: int = 30
    video_bitrate: int = 0                      # 0: 4500 kbps at 1080x1920, 3000 at 720x1280
    x264_preset: str = "veryfast"
    ffmpeg: str = "ffmpeg"
    volume: float = 1.0
    music_volume: float = 0.12
    extra: dict = field(default_factory=dict)

    @property
    def overlay_url(self) -> str:
        return f"http://127.0.0.1:{self.overlay_port}/overlay"

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Config":
        env = {**load_env(env_file or HERE / ".env"), **{k: v for k, v in os.environ.items() if k.isupper()}}
        g = env.get
        data = Path(g("DATA_DIR", str(HERE)))
        data = data if data.is_absolute() else HERE / data
        secret = Path(g("GOOGLE_CLIENT_SECRET", "client_secret.json"))
        music = data / "music.mp3"
        if not music.exists() and (HERE / "assets" / "music.mp3").exists():
            music = HERE / "assets" / "music.mp3"
        return cls(
            stream_mode=g("STREAM_MODE", "cloud").strip().lower(),
            sarathi_url=g("SARATHI_URL", cls.sarathi_url).rstrip("/"),
            live_token=g("LIVE_TOKEN", ""),
            yt_stream_key=(g("YT_STREAM_KEY") or g("YOUTUBE_STREAM_KEY") or "").strip(),
            google_client_secret=secret if secret.is_absolute() else (data / secret if (data / secret).exists() else HERE / secret),
            token_file=data / "token.json",
            data_dir=data, cache_dir=data / "cache", log_dir=data / "logs", state_file=data / "state.json",
            music_file=music, fonts_dir=Path(g("FONTS_DIR", str(HERE / "fonts"))),
            rtmp_url=g("YOUTUBE_RTMP_URL", cls.rtmp_url).rstrip("/"),
            scale=g("SCALE", "auto"), fps=int(g("FPS", "30")), video_bitrate=int(g("VIDEO_BITRATE_KBPS", "0") or 0),
            x264_preset=g("X264_PRESET", "veryfast"), ffmpeg=g("FFMPEG_PATH", "ffmpeg"),
            volume=float(g("VOLUME", "1.0")), music_volume=float(g("MUSIC_VOLUME", "0.12")),
            obs_ws_url=g("OBS_WS_URL", cls.obs_ws_url),
            obs_ws_password=g("OBS_WS_PASSWORD", ""),
            obs_exe=g("OBS_EXE", ""),
            # kept as typed (the first one is shown on screen); matching ignores case
            triggers=tuple(t.strip() for t in g("CHAT_TRIGGERS", "@gitalive,!gita,#gitalive").split(",") if t.strip()),
            chat_daily_units=int(g("CHAT_DAILY_UNITS", "9000")),
            answers_per_hour=int(g("ANSWERS_PER_HOUR", "20")),
            recite_tts_per_day=int(g("RECITE_TTS_PER_DAY", "200")),
            silent_seconds=float(g("SILENT_SECONDS", "20")),
            overlay_port=int(g("OVERLAY_PORT", "8770")),
            keep_awake=g("KEEP_SERVER_AWAKE", "0") == "1",
        )

    def problems(self, need_youtube: bool = True, need_obs: bool = True) -> list[str]:
        """What is missing, in plain words (shown by `run_live.py --check`)."""
        out = []
        if not self.live_token:
            out.append("LIVE_TOKEN is empty: the stream would share the website's daily budgets.")
        if need_obs and not self.yt_stream_key:
            out.append("YT_STREAM_KEY is empty: there is nothing to stream to (YouTube Studio > Go live > Stream key).")
        if need_obs and self.stream_mode == "obs" and not self.obs_ws_password:
            out.append("OBS_WS_PASSWORD is empty: enable OBS > Tools > WebSocket Server Settings and copy the password.")
        if need_youtube and not self.token_file.exists():
            out.append("token.json is missing: run `python youtube_auth.py` once to let the stream read chat.")
        return out
