"""Streaming without OBS or a browser, the EscapeArenaLive way (its stream.js, in Python).

The renderer draws each frame; the mixer makes the sound (Gita Sarathi's voice over optional music); ffmpeg
gets raw RGB frames on stdin and PCM over a local TCP socket, encodes H.264 + AAC and sends them to YouTube.
Everything is paced to real time. If ffmpeg dies the process exits, so Docker (or the .bat loop) restarts it.
"""
from __future__ import annotations

import asyncio
import array
import logging
import math
import os
import queue
import socket
import subprocess
import threading
import time
import wave
from pathlib import Path

log = logging.getLogger("gitalive.broadcast")
RATE = 24000          # Gemini's voices are 24 kHz mono; the mixer works at that rate


def auto_scale(setting: str = "auto") -> float:
    """1080x1920 when the machine has room for it, else 720x1280 (EscapeArena's SCALE setting)."""
    if setting and setting != "auto":
        return float(setting)
    return 1.0 if (os.cpu_count() or 1) >= 3 else 0.6667


def load_wav(path: Path) -> array.array:
    """16-bit PCM samples at RATE, mono (other rates are resampled linearly)."""
    with wave.open(str(path), "rb") as w:
        ch, width, rate, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if width != 2:
        raise ValueError(f"{path.name}: expected 16-bit audio")
    a = array.array("h")
    a.frombytes(raw)
    if ch > 1:
        a = array.array("h", (sum(a[i:i + ch]) // ch for i in range(0, len(a), ch)))
    if rate != RATE:
        ratio = rate / RATE
        m = int(len(a) / ratio)
        a = array.array("h", (a[min(len(a) - 1, int(i * ratio))] for i in range(m)))
    return a


def decode_music(path: Path, ffmpeg: str = "ffmpeg") -> array.array | None:
    """Any audio file -> mono 16-bit at RATE, via ffmpeg. None if it cannot be read."""
    try:
        out = subprocess.run([ffmpeg, "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(RATE), "-"],
                             capture_output=True, timeout=120, check=True).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("background music not used (%s)", exc)
        return None
    a = array.array("h")
    a.frombytes(out[: len(out) // 2 * 2])
    return a if len(a) > RATE else None


class Mixer:
    """Voice clips one after another, over looping music that dips while the voice plays."""

    def __init__(self, music: array.array | None = None, volume: float = 1.0, music_volume: float = 0.12):
        self.lock = threading.Lock()
        self.queue: list[array.array] = []
        self.pos = 0
        self.on_done = None
        self.music, self.mpos = music, 0
        self.volume, self.music_volume = volume, music_volume
        self.duck = 0.0            # 0 = music at full volume, 1 = dipped under the voice
        self.level = 0.0           # loudness of the last block (drives the on-screen waveform)

    def play(self, clips: list[array.array], on_done) -> None:
        """Replace whatever is playing with these clips; on_done() is called (from the streaming thread) when
        the last one ends."""
        with self.lock:
            prev = self.on_done
            self.queue, self.pos, self.on_done = [c for c in clips if len(c)], 0, on_done
        if prev:
            prev()            # the previous item was cut short: release whoever waited for it
        if not self.queue:
            self._finish()

    def _finish(self) -> None:
        with self.lock:
            cb, self.on_done = self.on_done, None
        if cb:
            cb()

    @property
    def busy(self) -> bool:
        return bool(self.queue)

    def render(self, n: int) -> bytes:
        out = array.array("h", bytes(2 * n))
        finished = False
        with self.lock:
            i = 0
            while i < n and self.queue:
                clip = self.queue[0]
                take = min(n - i, len(clip) - self.pos)
                out[i:i + take] = clip[self.pos:self.pos + take]
                i += take
                self.pos += take
                if self.pos >= len(clip):
                    self.queue.pop(0)
                    self.pos = 0
                    finished = not self.queue
            voice = i > 0
        target = 1.0 if voice else 0.0
        if self.volume != 1.0:
            for k in range(n):
                out[k] = int(out[k] * self.volume)
        if self.music is not None:
            m, L = self.music, len(self.music)
            for k in range(n):
                self.duck += (target - self.duck) * 0.0008      # ~50 ms glide
                g = self.music_volume * (1 - 0.7 * self.duck)
                v = out[k] + int(m[self.mpos] * g)
                out[k] = 32767 if v > 32767 else -32768 if v < -32768 else v
                self.mpos += 1
                if self.mpos >= L:
                    self.mpos = 0
        # loudness of the voice for the waveform (cheap: every 8th sample)
        if voice:
            acc = 0
            for k in range(0, n, 8):
                acc += out[k] * out[k]
            self.level = math.sqrt(acc / max(1, n // 8)) / 32768
        else:
            self.level *= 0.6
        if finished:
            self._finish()
        return out.tobytes()


def ffmpeg_args(width: int, height: int, fps: int, bitrate: int, preset: str, target: str, ffmpeg: str = "ffmpeg",
                audio_port: int = 0) -> list[str]:
    """The same encoder settings as EscapeArenaLive's stream.js."""
    out = (["-movflags", "+faststart", "-y", target] if not target.startswith(("rtmp://", "rtmps://"))
           else ["-f", "flv", target])
    return [ffmpeg, "-hide_banner", "-loglevel", "warning",
            # both inputs are raw with known formats: no probing, or ffmpeg would wait for seconds of audio
            # before reading any video (and the two pipes would wait on each other)
            "-probesize", "32", "-analyzeduration", "0", "-thread_queue_size", "64",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-framerate", str(fps), "-i", "pipe:0",
            "-probesize", "32", "-analyzeduration", "0", "-thread_queue_size", "512",
            "-f", "s16le", "-ar", str(RATE), "-ac", "1", "-i", f"tcp://127.0.0.1:{audio_port}",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", preset, "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-b:v", f"{bitrate}k", "-maxrate", f"{bitrate}k", "-bufsize", f"{bitrate * 2}k",
            "-g", str(fps * 2), "-keyint_min", str(fps * 2), "-sc_threshold", "0",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2", *out]


class Streamer:
    """The real-time loop: one video frame and one frame's worth of audio at a time, into ffmpeg."""

    def __init__(self, renderer, mixer: Mixer, *, target: str, key: str = "", fps: int = 30, scale: float = 1.0,
                 bitrate: int | None = None, preset: str = "veryfast", ffmpeg: str = "ffmpeg", seconds: float = 0):
        self.r, self.mixer = renderer, mixer
        self.key = key
        self.target = f"{target.rstrip('/')}/{key}" if key and target.startswith(("rtmp://", "rtmps://")) else target
        self.fps, self.scale = fps, scale
        self.width, self.height = int(round(1080 * scale / 2) * 2), int(round(1920 * scale / 2) * 2)
        self.bitrate = bitrate or (4500 if scale >= 1 else 3000)
        self.preset, self.ffmpeg, self.seconds = preset, ffmpeg, seconds
        self.frames = 0
        self.stopped = threading.Event()
        self.error: str | None = None
        self.status = "starting"

    def redact(self, s: str) -> str:
        return s.replace(self.key, "****") if self.key else s

    def run(self) -> None:
        """Blocking; run it in a thread. Returns when stopped, or when --seconds is reached."""
        srv = socket.socket()
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        args = ffmpeg_args(self.width, self.height, self.fps, self.bitrate, self.preset, self.target, self.ffmpeg,
                           srv.getsockname()[1])
        log.info("%s · %dx%d @ %dfps · %d kbps · preset %s", "streaming to YouTube" if self.key else f"recording {self.target}",
                 self.width, self.height, self.fps, self.bitrate, self.preset)
        try:
            ff = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except OSError as exc:
            self.error = f"could not start ffmpeg ({exc}). Is it installed?"
            log.error(self.error)
            return
        threading.Thread(target=self._pipe_log, args=(ff,), daemon=True).start()
        # ffmpeg opens its inputs one after the other and reads each before opening the next, so video and audio
        # are written by two threads with small queues: neither can block the other (stream.js gets the same
        # from Node's async writes).
        vq: queue.Queue = queue.Queue(maxsize=12)
        aq: queue.Queue = queue.Queue(maxsize=600)
        failed = threading.Event()

        def write_video():
            try:
                while True:
                    buf = vq.get()
                    if buf is None:
                        break
                    ff.stdin.write(buf)
            except (BrokenPipeError, OSError, ValueError):
                failed.set()

        def write_audio():
            srv.settimeout(30)
            try:
                sock, _ = srv.accept()
            except OSError:
                failed.set()
                return
            finally:
                srv.close()
            try:
                while True:
                    buf = aq.get()
                    if buf is None:
                        break
                    sock.sendall(buf)
            except OSError:
                failed.set()
            finally:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                sock.close()

        writers = [threading.Thread(target=write_video, daemon=True), threading.Thread(target=write_audio, daemon=True)]
        for w in writers:
            w.start()
        spf = RATE / self.fps
        frame_s = 1 / self.fps
        start = time.monotonic()
        carry, last_report, report_frames, render_ms, slow = 0.0, start, 0, 0.0, 0
        cached, cached_at = b"", -1.0
        self.status = "on air" if self.key else "recording"
        try:
            while not self.stopped.is_set():
                if failed.is_set() or ff.poll() is not None:
                    raise ConnectionResetError("ffmpeg stopped")
                t = time.monotonic() - start
                r0 = time.perf_counter()
                carry += spf
                n = int(carry)
                carry -= n
                pcm = self.mixer.render(n)
                if t - cached_at >= 0.1 or not cached:     # recompose ~10 times a second, reuse in between
                    cached, cached_at = self.r.frame(t, self.mixer.level, self.scale), t
                render_ms += (time.perf_counter() - r0) * 1000
                aq.put(pcm, timeout=30)
                vq.put(cached, timeout=30)
                self.frames += 1
                report_frames += 1
                if self.seconds and self.frames >= self.seconds * self.fps:
                    break
                # always real time (a test recording too), so the conductor's timing matches what is heard
                wait = start + self.frames * frame_s - time.monotonic()
                if wait > 0:
                    time.sleep(wait)
                elif wait < -3:          # the machine stalled: re-sync instead of bursting
                    start = time.monotonic() - self.frames * frame_s
                    slow += 1
                now = time.monotonic()
                if now - last_report >= (60 if self.key else 5):
                    fps = report_frames / (now - last_report)
                    log.info("%.1f fps · %.1f ms/frame%s", fps, render_ms / max(1, report_frames),
                             f" · {slow} slow-downs (try SCALE=0.6667)" if slow else "")
                    last_report, report_frames, render_ms = now, 0, 0.0
        except (ConnectionResetError, queue.Full) as exc:
            self.error = f"ffmpeg stopped ({type(exc).__name__}, video queue {vq.qsize()}, audio queue {aq.qsize()})"
            log.error("%s; exiting so it restarts", self.error)
        finally:
            self.status = "stopped"
            for q_ in (vq, aq):
                try:
                    q_.put(None, timeout=5)
                except queue.Full:
                    pass
            writers[0].join(timeout=30)
            try:
                ff.stdin.close()
            except OSError:
                pass
            writers[1].join(timeout=10)
            try:
                ff.wait(timeout=30)
            except subprocess.TimeoutExpired:
                ff.kill()
            if ff.returncode not in (0, None) and not self.error and not self.stopped.is_set():
                self.error = f"ffmpeg exited with code {ff.returncode}"

    def _pipe_log(self, ff) -> None:
        for line in iter(ff.stderr.readline, b""):
            msg = self.redact(line.decode(errors="replace").strip())
            if msg and "Guessed Channel Layout" not in msg:
                log.warning("ffmpeg: %s", msg)


class LocalPlayer:
    """What the conductor's Hub uses in cloud mode instead of an overlay page: shows the item on the renderer
    and plays its voice through the mixer, then reports that it has finished."""

    def __init__(self, renderer, mixer: Mixer, cache_dir: Path):
        self.r, self.mixer, self.cache_dir = renderer, mixer, cache_dir

    def clips(self, item: dict) -> list[array.array]:
        out = []
        for url in item.get("audio") or []:
            name = url.rsplit("/", 1)[-1]
            try:
                out.append(load_wav(self.cache_dir / name))
            except (OSError, ValueError, EOFError, wave.Error) as exc:
                log.warning("voice %s unreadable: %s", name, exc)
        return out

    async def play(self, item: dict, seconds: float) -> None:
        await asyncio.to_thread(self.r.build_scene, item)
        if item.get("type") == "asking":
            return
        clips = self.clips(item)
        if not clips:
            await asyncio.sleep(seconds)
            return
        loop = asyncio.get_running_loop()
        done = asyncio.Event()
        self.mixer.play(clips, lambda: loop.call_soon_threadsafe(done.set))
        total = sum(len(c) for c in clips) / RATE
        try:
            await asyncio.wait_for(done.wait(), total + 10)
        except asyncio.TimeoutError:
            log.warning("voice for %s did not finish in time; moving on", item.get("id"))
        await asyncio.sleep(0.8)   # a breath between items
