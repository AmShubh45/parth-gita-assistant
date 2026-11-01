"""End-to-end check of the voice page against a mock Gemini Live server (no API key needed).

    python scripts/e2e_voice_mock.py [screenshot.png]

Starts the real Parth app with the token step pointed at a local WebSocket server that speaks the
Live API protocol, then drives the page in Chromium with a fake microphone:
greeting -> user speech transcript -> find_verses tool call -> tool response -> spoken answer.
Fails loudly if any step does not happen.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import struct
import sys
import threading
import time

import uvicorn
import websockets

WS_PORT, APP_PORT = 8765, 8301
log: dict = {"setup": None, "audio_in": 0, "tool_response": None, "greeting": None}
events: list[str] = []


def tone(seconds: float = 0.4) -> str:
    n = int(24000 * seconds)
    return base64.b64encode(b"".join(struct.pack("<h", int(8000 * math.sin(2 * math.pi * 330 * i / 24000))) for i in range(n))).decode()


async def live(ws):
    async for raw in ws:
        m = json.loads(raw)
        if "setup" in m:
            log["setup"] = m["setup"]
            await ws.send(json.dumps({"setupComplete": {}}))
        elif "realtimeInput" in m and "text" in m["realtimeInput"] and log["greeting"] is None:
            log["greeting"] = m["realtimeInput"]
            await ws.send(json.dumps({"serverContent": {"outputTranscription": {"text": "नमस्ते! आपके मन में क्या है?"},
                                                        "modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": tone()}}]}}}))
            await ws.send(json.dumps({"serverContent": {"turnComplete": True}}))
            await asyncio.sleep(0.6)
            await ws.send(json.dumps({"serverContent": {"inputTranscription": {"text": "मुझे बहुत गुस्सा आता है"}}}))
            await ws.send(json.dumps({"toolCall": {"functionCalls": [{"id": "call-1", "name": "find_verses", "args": {"query": "anger"}}]}}))
        elif "realtimeInput" in m and "audio" in m["realtimeInput"]:
            log["audio_in"] += 1
        elif "toolResponse" in m:
            log["tool_response"] = m["toolResponse"]
            await ws.send(json.dumps({"serverContent": {"outputTranscription": {"text": "गीता के दूसरे अध्याय में श्रीकृष्ण बताते हैं कि क्रोध कहाँ से आता है।"},
                                                        "modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000", "data": tone(0.8)}}]}}}))
            await ws.send(json.dumps({"serverContent": {"turnComplete": True}}))


def run_app():
    sys.path.insert(0, ".")
    import logging
    from parth import app as appmod, live as livemod

    class Capture(logging.Handler):
        def emit(self, record):
            msg = record.getMessage()
            if msg.startswith("live_event"):
                events.append(msg.split("event=")[1].split()[0])

    logging.getLogger("parth").addHandler(Capture())
    appmod._gemini.key = "mock-key"
    livemod.mint_token = lambda key, model: "mock-token"
    livemod.WS_URL = f"ws://127.0.0.1:{WS_PORT}/ws"
    uvicorn.run(appmod.app, host="127.0.0.1", port=APP_PORT, log_level="warning")


async def main(shot: str | None) -> int:
    from playwright.async_api import async_playwright
    server = await websockets.serve(live, "127.0.0.1", WS_PORT)
    threading.Thread(target=run_app, daemon=True).start()
    time.sleep(2.5)
    errors: list[str] = []
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome",
                                    args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
        # no autoplay override: audio must start from the tap, exactly as on a phone
        ctx = await b.new_context(viewport={"width": 1280, "height": 900}, permissions=["microphone"])
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: m.type == "error" and errors.append(m.text))
        await page.goto(f"http://127.0.0.1:{APP_PORT}/", wait_until="networkidle")
        await page.click("#orb")
        await page.wait_for_selector(".card", timeout=15000)
        await page.wait_for_function("document.querySelectorAll('.msg.parth').length >= 2", timeout=10000)
        await page.wait_for_timeout(1500)
        result = {
            "setup_model": (log["setup"] or {}).get("model"),
            "greeting_sent": bool(log["greeting"]),
            "mic_chunks_sent": log["audio_in"],
            "tool_verses": [v["id"] for v in (log["tool_response"] or {}).get("functionResponses", [{}])[0].get("response", {}).get("result", {}).get("verses", [])],
            "cards_on_page": await page.eval_on_selector_all(".card .card-head b", "els => els.map(e => e.textContent)"),
            "you_bubbles": await page.eval_on_selector_all(".msg.you .txt", "els => els.map(e => e.textContent)"),
            "parth_bubbles": await page.eval_on_selector_all(".msg.parth .txt", "els => els.map(e => e.textContent)"),
            "state": await page.evaluate("document.body.dataset.state"),
            "errors": errors,
            "events": list(dict.fromkeys(events)),
        }
        if shot:
            await page.screenshot(path=shot, full_page=True)
        await page.click("#end")
        result["state_after_end"] = await page.evaluate("document.body.dataset.state")
        await b.close()
    server.close()
    print(json.dumps(result, ensure_ascii=False, indent=1))
    ok = (result["setup_model"] == "models/" + "gemini-3.8-live" and result["greeting_sent"] and result["mic_chunks_sent"] > 5
          and result["tool_verses"] and result["cards_on_page"][:1] == result["tool_verses"][:1]
          and result["you_bubbles"] and len(result["parth_bubbles"]) >= 2 and not errors and result["state_after_end"] == "idle"
          and {"token_ok", "setup_complete", "first_audio_sent", "first_server_content", "tool_call"} <= set(result["events"]))
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None)))
