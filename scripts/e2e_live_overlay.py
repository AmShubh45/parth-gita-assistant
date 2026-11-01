"""End-to-end check of the YouTube live overlay in a real browser, with Gemini mocked (no keys needed).

    python scripts/e2e_live_overlay.py [screenshot-prefix]

Runs the real Gita Sarathi server (scripted model, short fake voices, a live-stream token) and the real
live/ stack in preview mode against it, then opens the 1920x1080 overlay in Chromium:
verse recited with its voice -> next verse -> a viewer question -> "asking" -> answer with verse cards and
voice -> recitation resumes. Fails loudly if any step does not happen.
"""
from __future__ import annotations

import asyncio
import json
import math
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "live"))
APP_PORT, LIVE_PORT = 8302, 8771
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
state: dict = {"tts": 0}


def tone(seconds: float, rate: int = 24000) -> bytes:
    return b"".join(struct.pack("<h", int(5000 * math.sin(2 * math.pi * 300 * i / rate))) for i in range(int(rate * seconds)))


def run_sarathi():
    from parth import app as appmod, speech
    from parth.engine import Engine
    from tests.test_engine import FakeLLM, GOOD_HI, SELECT, UNDERSTAND
    appmod._gemini.key = "mock-key"
    appmod.LIVE_TOKEN = "live-secret"
    appmod.engine = Engine(appmod._kb, FakeLLM({"understand": UNDERSTAND, "select": SELECT, "compose": GOOD_HI,
                                                "verify": {"ok": True, "problems": []}}))

    async def fake_speak(text, lang):
        state["tts"] += 1
        await asyncio.sleep(0.1)
        return speech.wav(tone(0.6))
    appmod.live_speaker.speak = fake_speak
    uvicorn.run(appmod.app, host="127.0.0.1", port=APP_PORT, log_level="warning")


async def main(shot: str | None) -> int:
    from playwright.async_api import async_playwright
    from gitalive.audio import AudioCache
    from gitalive.conductor import Conductor, Hub
    from gitalive.moderation import Moderator
    from gitalive.sarathi import Sarathi
    from gitalive.server import make_app

    threading.Thread(target=run_sarathi, daemon=True).start()
    time.sleep(2.5)
    tmp = Path(tempfile.mkdtemp())
    sar = Sarathi(f"http://127.0.0.1:{APP_PORT}", "live-secret")
    conductor = Conductor(sar, AudioCache(tmp / "cache", sar, 50), Hub(), Moderator(), tmp / "state.json",
                          tmp / "cache" / "verses.json", silent_seconds=3)
    server = uvicorn.Server(uvicorn.Config(make_app(conductor, tmp / "cache", tmp / "music.mp3"),
                                           host="127.0.0.1", port=LIVE_PORT, log_level="warning"))
    tasks = [asyncio.create_task(server.serve()), asyncio.create_task(conductor.run())]
    await asyncio.sleep(1.5)
    errors: list[str] = []
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path=CHROME, args=["--autoplay-policy=no-user-gesture-required"])  # as in OBS
        page = await b.new_page(viewport={"width": 1920, "height": 1080})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and "fonts.g" not in m.text and errors.append(m.text))
        page.on("response", lambda r: r.status >= 400 and "fonts.g" not in r.url and errors.append(f"{r.status} {r.url}"))
        await page.add_init_script("window.__plays = []; const _p = HTMLMediaElement.prototype.play;"
                                   "HTMLMediaElement.prototype.play = function (...a) { if ((this.src||'').includes('/audio/')) window.__plays.push(this.src); return _p.apply(this, a); };")
        await page.goto(f"http://127.0.0.1:{LIVE_PORT}/overlay", wait_until="domcontentloaded")
        await page.wait_for_function("document.getElementById('v-sa').textContent.length > 10", timeout=20000)
        first = await page.text_content("#v-hi")
        await page.wait_for_function("document.getElementById('v-hi').textContent !== " + json.dumps(first), timeout=20000)
        second = await page.text_content("#v-hi")
        if shot:
            await page.screenshot(path=f"{shot}-verse.png")
        async with httpx.AsyncClient() as h:
            queued = (await h.post(f"http://127.0.0.1:{LIVE_PORT}/preview/ask", json={"name": "Asha", "text": "मुझे बहुत गुस्सा आता है"})).json()
        await page.wait_for_function("document.getElementById('asking').classList.contains('on') || document.getElementById('answer').classList.contains('on')", timeout=30000)
        await page.wait_for_function("document.getElementById('answer').classList.contains('on')", timeout=30000)
        await page.wait_for_timeout(400)
        if shot:
            await page.screenshot(path=f"{shot}-answer.png")
        answer = {"name": await page.text_content("#r-name"), "question": await page.text_content("#r-q"),
                  "cards": await page.eval_on_selector_all("#r-body .card .head b", "els => els.map(e => e.textContent)")}
        await page.wait_for_function("document.getElementById('verse').classList.contains('on')", timeout=30000)
        resumed = await page.text_content("#v-hi")
        plays = await page.evaluate("window.__plays.length")
        status = json.loads(await (await page.request.get(f"http://127.0.0.1:{LIVE_PORT}/status")).text())
        await b.close()
    server.should_exit = True
    tasks[1].cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await sar.close()
    result = {"first_verse": first, "second_verse": second, "queued": queued.get("queued"), "answer": answer,
              "resumed_at": resumed, "voices_played": plays, "tts_calls": state["tts"], "status": {k: status[k] for k in ("verses", "answered", "verses_with_voice")},
              "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=1))
    ok = (first.startswith("अध्याय 1 · श्लोक") and second.startswith("अध्याय 1 · श्लोक") and first != second and queued.get("queued")
          and answer["name"] == "Asha" and answer["cards"][:2] == ["BG 2.62", "BG 2.63"] and resumed.startswith("अध्याय 1 · श्लोक")
          and plays >= 4 and status["answered"] == 1 and status["verses"] == 701 and not errors)
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None)))
