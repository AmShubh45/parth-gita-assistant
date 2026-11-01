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
    cache_dir: Path = HERE / "cache"
    log_dir: Path = HERE / "logs"
    state_file: Path = HERE / "state.json"
    music_file: Path = HERE / "assets" / "music.mp3"
    extra: dict = field(default_factory=dict)

    @property
    def overlay_url(self) -> str:
        return f"http://127.0.0.1:{self.overlay_port}/overlay"

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Config":
        env = {**load_env(env_file or HERE / ".env"), **{k: v for k, v in os.environ.items() if k.isupper()}}
        g = env.get
        secret = Path(g("GOOGLE_CLIENT_SECRET", "client_secret.json"))
        return cls(
            sarathi_url=g("SARATHI_URL", cls.sarathi_url).rstrip("/"),
            live_token=g("LIVE_TOKEN", ""),
            yt_stream_key=g("YT_STREAM_KEY", ""),
            google_client_secret=secret if secret.is_absolute() else HERE / secret,
            obs_ws_url=g("OBS_WS_URL", cls.obs_ws_url),
            obs_ws_password=g("OBS_WS_PASSWORD", ""),
            obs_exe=g("OBS_EXE", ""),
            triggers=tuple(t.strip().lower() for t in g("CHAT_TRIGGERS", "@gitalive,!gita,#gitalive").split(",") if t.strip()),
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
            out.append("YT_STREAM_KEY is empty: OBS has nothing to stream to.")
        if need_obs and not self.obs_ws_password:
            out.append("OBS_WS_PASSWORD is empty: enable OBS > Tools > WebSocket Server Settings and copy the password.")
        if need_youtube and not self.token_file.exists():
            out.append("token.json is missing: run `python youtube_auth.py` once to let the stream read chat.")
        return out
