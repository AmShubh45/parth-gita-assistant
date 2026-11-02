"""End-to-end check of the vertical cloud stream (the EscapeArenaLive way), with Gemini mocked.

    python scripts/e2e_live_stream.py [frames-prefix]

Runs the real Gita Sarathi server (scripted model, fake voices, a live-stream token), then the real
`live/run_live.py --out test.mp4 --seconds 25` in cloud mode, and asks a question as a viewer partway through.
Checks the recording with ffprobe (1080x1920, 30 fps, AAC audio, ~25 s), that the voice is audible, and that the
stream went verse -> question -> answer -> verse. Saves a frame of each scene for review.
"""
from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP_PORT, LIVE_PORT, SECONDS = 8303, 8772, 25


def tone(seconds: float, rate: int = 24000, f: float = 220) -> bytes:
    return b"".join(struct.pack("<h", int(9000 * math.sin(2 * math.pi * f * i / rate) * (0.6 + 0.4 * math.sin(2 * math.pi * 3 * i / rate))))
                    for i in range(int(rate * seconds)))


def run_sarathi():
    import asyncio
    from parth import app as appmod, speech
    from parth.engine import Engine
    from tests.test_engine import FakeLLM, GOOD_HI, SELECT, UNDERSTAND
    appmod._gemini.key = "mock-key"
    appmod.LIVE_TOKEN = "live-secret"
    appmod.engine = Engine(appmod._kb, FakeLLM({"understand": UNDERSTAND, "select": SELECT, "compose": GOOD_HI,
                                                "verify": {"ok": True, "problems": []}}))

    async def fake_speak(text, lang):
        await asyncio.sleep(0.05)
        return speech.wav(tone(3.0 if text.startswith("Chapter") else 1.6))
    appmod.live_speaker.speak = fake_speak
    uvicorn.run(appmod.app, host="127.0.0.1", port=APP_PORT, log_level="warning")


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def loudness(path: Path, start: float, length: float) -> float:
    out = subprocess.run(["ffmpeg", "-v", "info", "-ss", str(start), "-t", str(length), "-i", str(path), "-af", "volumedetect",
                          "-f", "null", "-"], capture_output=True, text=True).stderr
    for line in out.splitlines():
        if "mean_volume" in line:
            return float(line.split("mean_volume:")[1].split("dB")[0])
    return -99.0


def main(prefix: str | None) -> int:
    threading.Thread(target=run_sarathi, daemon=True).start()
    time.sleep(2.5)
    tmp = Path(tempfile.mkdtemp())
    out = tmp / "test.mp4"
    env = {**os.environ, "SARATHI_URL": f"http://127.0.0.1:{APP_PORT}", "LIVE_TOKEN": "live-secret", "DATA_DIR": str(tmp),
           "STREAM_MODE": "cloud", "OVERLAY_PORT": str(LIVE_PORT), "SCALE": "1", "YT_STREAM_KEY": "", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen([sys.executable, str(ROOT / "live" / "run_live.py"), "--out", str(out), "--seconds", str(SECONDS)],
                            env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    timeline, asked, t0 = [], None, time.monotonic()
    with httpx.Client(timeout=5) as h:
        while proc.poll() is None:
            t = time.monotonic() - t0
            try:
                st = h.get(f"http://127.0.0.1:{LIVE_PORT}/status").json()
                if not timeline or timeline[-1][1] != st["status"]:
                    timeline.append((round(t, 1), st["status"]))
                if asked is None and st["status"].startswith("reciting") and t > 6:
                    asked = h.post(f"http://127.0.0.1:{LIVE_PORT}/preview/ask", json={"name": "Asha", "text": "मुझे बहुत गुस्सा आता है"}).json()
            except httpx.HTTPError:
                pass
            time.sleep(0.4)
    log = proc.stdout.read()
    if not out.exists():
        print(log[-3000:])
        print("FAIL: no recording")
        return 1
    info = probe(out)
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), {})
    dur = float(info["format"]["duration"])
    # the recording starts when ffmpeg starts, a moment after the process: map timeline times onto the video
    offset = next((t for t, s in timeline if s.startswith("reciting")), 2.0) - 0.5
    when = {}
    for t, s in timeline:
        k = "answer" if s.startswith("answering") else "verse" if s.startswith("reciting") else None
        if k and k not in when:
            when[k] = max(0.5, t - offset + 1.5)
    resumed = next((t for t, s in timeline if s.startswith("reciting") and any(x[1].startswith("answering") for x in timeline if x[0] < t)), None)
    shots = {}
    for name, t in (("verse", when.get("verse", 3)), ("answer", when.get("answer", 14) + 2), ("resumed", (resumed or 22) - offset + 1)):
        t = min(max(0.5, t), dur - 0.5)
        path = Path(f"{prefix}-{name}.png") if prefix else tmp / f"{name}.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(out), "-frames:v", "1", str(path)], check=True)
        shots[name] = (round(t, 1), str(path))
    voice_db = loudness(out, when.get("verse", 3) - 1, 2.5)
    result = {"size": f"{v['width']}x{v['height']}", "fps": v.get("r_frame_rate"), "video": v["codec_name"],
              "audio": a.get("codec_name"), "duration": round(dur, 1), "voice_mean_db": voice_db, "asked": asked,
              "timeline": timeline, "frames": shots}
    print(json.dumps(result, ensure_ascii=False, indent=1))
    ok = (result["size"] == "1080x1920" and result["fps"] == "30/1" and result["video"] == "h264" and result["audio"] == "aac"
          and abs(dur - SECONDS) < 1.5 and voice_db > -40 and asked and asked.get("queued")
          and any(s.startswith("answering Asha") for _, s in timeline) and resumed is not None and proc.returncode == 0)
    if not ok:
        print(log[-2500:])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else None))
