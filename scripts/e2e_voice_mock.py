"""End-to-end check of Gita Sarathi's voice in a real browser, with Gemini mocked (no API key needed).

    python scripts/e2e_voice_mock.py [screenshot-prefix]

1. Spoken answers (the default mode). Chromium's fake microphone plays a short "question" followed by
   silence. The page must record it, stop by itself when the person pauses, send it to /api/voice, show
   the transcript and verse cards, play every piece of the spoken answer through Gemini TTS (mocked),
   then, in conversation mode, listen again and carry the conversation into the second question.
2. Live (beta). The page talks to a local WebSocket server that speaks the Gemini Live protocol. While
   Gita Sarathi's audio plays the page must send only silence (half duplex), must ignore an echo
   `interrupted`, must report a turn_summary, and must relay the find_verses tool call.

No autoplay override is used: audio has to start from the tap, as on a phone. Fails loudly.
"""
from __future__ import annotations

import asyncio
import base64
import json
import math
import struct
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

import uvicorn
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WS_PORT, APP_PORT = 8765, 8301
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
events: list[str] = []
live_log: dict = {"setup": None, "greeting": None, "tool_response": None, "audio_at": None, "chunks": []}


def write_wav(path: Path, pieces: list[tuple[float, bool]], rate: int = 48000) -> None:
    """pieces: (seconds, voiced). Voiced parts are syllable-like bursts of a moving tone, so the
    browser's noise suppression keeps them, like speech."""
    frames = bytearray()
    t = 0
    for seconds, voiced in pieces:
        for _ in range(int(rate * seconds)):
            x = t / rate
            v = 0.0
            if voiced:
                env = max(0.0, math.sin(2 * math.pi * 3.2 * x)) ** 0.6           # ~3 syllables a second
                v = 0.35 * env * math.sin(2 * math.pi * (180 + 60 * math.sin(2 * math.pi * 0.7 * x)) * x)
            frames += struct.pack("<h", int(v * 32767))
            t += 1
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate), w.writeframes(bytes(frames))


def tone(seconds: float, rate: int = 24000) -> bytes:
    return b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 330 * i / rate))) for i in range(int(rate * seconds)))


# ---------------------------------------------------------------- mock Gemini Live
async def greet(ws):
    live_log["audio_at"] = time.monotonic()
    await ws.send(json.dumps({"serverContent": {"outputTranscription": {"text": "नमस्ते! आपके मन में क्या है?"},
                                                "modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000",
                                                                                        "data": base64.b64encode(tone(1.4)).decode()}}]}}}))
    await asyncio.sleep(0.3)
    await ws.send(json.dumps({"serverContent": {"interrupted": True}}))   # what a phone's echo used to cause
    await asyncio.sleep(1.4)
    await ws.send(json.dumps({"serverContent": {"generationComplete": True}}))
    await ws.send(json.dumps({"serverContent": {"turnComplete": True}}))
    await asyncio.sleep(0.4)
    await ws.send(json.dumps({"serverContent": {"inputTranscription": {"text": "मुझे बहुत गुस्सा आता है"}}}))
    await ws.send(json.dumps({"toolCall": {"functionCalls": [{"id": "call-1", "name": "find_verses", "args": {"query": "anger"}}]}}))


async def live(ws):
    async for raw in ws:
        m = json.loads(raw)
        if "setup" in m:
            live_log["setup"] = m["setup"]
            await ws.send(json.dumps({"setupComplete": {}}))
        elif "realtimeInput" in m and "text" in m["realtimeInput"] and live_log["greeting"] is None:
            live_log["greeting"] = m["realtimeInput"]
            asyncio.create_task(greet(ws))  # keep reading the microphone stream meanwhile
        elif "realtimeInput" in m and "audio" in m["realtimeInput"]:
            pcm = base64.b64decode(m["realtimeInput"]["audio"]["data"])
            live_log["chunks"].append((time.monotonic(), any(pcm)))
        elif "toolResponse" in m:
            live_log["tool_response"] = m["toolResponse"]
            await ws.send(json.dumps({"serverContent": {"outputTranscription": {"text": "गीता के दूसरे अध्याय में श्रीकृष्ण बताते हैं कि क्रोध कहाँ से आता है।"},
                                                        "modelTurn": {"parts": [{"inlineData": {"mimeType": "audio/pcm;rate=24000",
                                                                                                "data": base64.b64encode(tone(0.8)).decode()}}]}}}))
            await ws.send(json.dumps({"serverContent": {"turnComplete": True}}))


# ---------------------------------------------------------------- the real app, with Gemini mocked
def run_app(state: dict):
    import logging
    from parth import app as appmod, live as livemod, speech
    from parth.engine import Engine
    from tests.test_engine import FakeLLM, GOOD_HI, SELECT, UNDERSTAND

    class Capture(logging.Handler):
        def emit(self, record):
            msg = record.getMessage()
            if msg.startswith("live_event"):
                events.append(msg.split("event=")[1].split()[0])

    logging.getLogger("parth").addHandler(Capture())
    llm = FakeLLM({"understand": [{**UNDERSTAND, "transcript": "मुझे बहुत गुस्सा आता है"}, {**UNDERSTAND, "transcript": "और बताइए"}],
                   "select": SELECT, "compose": GOOD_HI, "verify": {"ok": True, "problems": []}})
    state["llm"] = llm
    appmod._gemini.key = "mock-key"
    appmod.engine = Engine(appmod._kb, llm)

    async def fake_speak(text, lang):
        state["tts"] = state.get("tts", 0) + 1
        await asyncio.sleep(0.2)
        return speech.wav(tone(0.5))

    appmod.speaker.speak = fake_speak
    livemod.mint_token = lambda key, model: "mock-token"
    livemod.WS_URL = f"ws://127.0.0.1:{WS_PORT}/ws"
    uvicorn.run(appmod.app, host="127.0.0.1", port=APP_PORT, log_level="warning")


COUNT_AUDIO = """
// Spoken answers must play through <audio> elements (loudspeaker), never Web Audio buffers (earpiece on phones).
window.__srcs = []; window.__streams = 0; window.__webaudio = 0; window.__says = 0;
window.__pieces = () => window.__srcs.filter((u) => u !== window.__srcs[0]).length;   // the first is the silent unlock
const _play = HTMLMediaElement.prototype.play;
HTMLMediaElement.prototype.play = function (...a) {
  if (this.srcObject) window.__streams++; else if ((this.src || '').startsWith('blob:')) window.__srcs.push(this.src);
  const p = _play.apply(this, a);
  return p;
};
const _start = AudioBufferSourceNode.prototype.start;
AudioBufferSourceNode.prototype.start = function (...a) { window.__webaudio++; return _start.apply(this, a); };
if (window.speechSynthesis) { const _speak = speechSynthesis.speak.bind(speechSynthesis);
  speechSynthesis.speak = (u) => { if ((u.text || '').trim()) window.__says++; return _speak(u); }; }
"""


async def browser(p, fake_wav: Path):
    return await p.chromium.launch(executable_path=CHROME, args=[
        "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", f"--use-file-for-fake-audio-capture={fake_wav}"])


async def spoken_answers(p, tmp: Path, state: dict, shot: str | None) -> dict:
    question = tmp / "question.wav"
    write_wav(question, [(0.4, False), (1.6, True), (4.0, False)])
    b = await browser(p, question)
    ctx = await b.new_context(viewport={"width": 390, "height": 860}, permissions=["microphone"])
    page = await ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    await page.add_init_script(COUNT_AUDIO)
    await page.goto(f"http://127.0.0.1:{APP_PORT}/", wait_until="networkidle")
    await page.check("#optConvo")
    await page.click("#mic")
    await page.wait_for_selector(".turn .card", timeout=20000)
    first_state = await page.evaluate("document.body.dataset.state")
    await page.wait_for_function("window.__pieces() >= 4", timeout=15000)            # opening, 2 verses, closing
    await page.wait_for_function("document.querySelectorAll('.turn').length >= 2 && document.querySelectorAll('.turn')[1].querySelector('.card')", timeout=25000)
    await page.uncheck("#optConvo")
    await page.wait_for_function("document.body.dataset.state === 'idle'", timeout=15000)
    if shot:
        await page.screenshot(path=f"{shot}-voice-390.png", full_page=True)
    result = {
        "state_while_answer_arrived": first_state,
        "you": await page.eval_on_selector_all(".turn .you .said-text", "els => els.map(e => e.textContent)"),
        "cards": await page.eval_on_selector_all(".turn .card .card-head b", "els => els.map(e => e.textContent)"),
        "listen_buttons": await page.eval_on_selector_all(".turn .listen", "els => els.length"),
        "audio_pieces_played": await page.evaluate("window.__pieces()"),
        "web_audio_playback": await page.evaluate("window.__webaudio"),
        "browser_voice_used": await page.evaluate("window.__says"),
        "first_section": await page.eval_on_selector(".turn .card .sec h3", "e => e.textContent"),
        "english_tucked_away": await page.eval_on_selector(".turn .card details.tr-more", "e => !e.open && e.querySelector('summary').textContent"),
        "tts_calls": state.get("tts", 0),
        "second_question_saw_first": "मुझे बहुत गुस्सा आता है" in state["llm"].calls[4][1] if len(state["llm"].calls) > 4 else False,
        "errors": errors,
    }
    await b.close()
    result["ok"] = (result["you"][:2] == ["मुझे बहुत गुस्सा आता है", "और बताइए"] and result["cards"][:2] == ["BG 2.62", "BG 2.63"]
                    and result["audio_pieces_played"] >= 8 and result["browser_voice_used"] == 0 and result["listen_buttons"] >= 2
                    and result["web_audio_playback"] == 0 and result["first_section"] == "भावार्थ"
                    and str(result["english_tucked_away"]).startswith("अंग्रेज़ी अनुवाद")
                    and result["second_question_saw_first"] and not errors and "voice_error" not in events)
    return result


async def live_beta(p, tmp: Path, shot: str | None) -> dict:
    talk = tmp / "talk.wav"
    write_wav(talk, [(10.0, True)])
    b = await browser(p, talk)
    ctx = await b.new_context(viewport={"width": 1280, "height": 900}, permissions=["microphone"])
    page = await ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    await page.add_init_script(COUNT_AUDIO)
    await page.goto(f"http://127.0.0.1:{APP_PORT}/", wait_until="networkidle")
    await page.check("#optLive")
    await page.click("#mic")
    await page.wait_for_selector(".turn .card", timeout=15000)
    await page.wait_for_function("document.querySelectorAll('.said').length >= 2", timeout=10000)
    await page.wait_for_timeout(2500)
    if shot:
        await page.screenshot(path=f"{shot}-live-1280.png", full_page=True)
    await page.click("#vend")
    t0 = live_log["audio_at"] or 0
    during = [nz for t, nz in live_log["chunks"] if t0 + 0.2 < t < t0 + 1.2]          # Gita Sarathi is speaking
    after = [nz for t, nz in live_log["chunks"] if t > t0 + 1.85]                      # the person's turn again
    result = {
        "setup_model": (live_log["setup"] or {}).get("model"),
        "greeting_sent": bool(live_log["greeting"]),
        "mic_chunks_later_with_sound": sum(after),
        "mic_chunks_while_speaking": len(during),
        "mic_chunks_while_speaking_with_sound": sum(during),
        "tool_verses": [v["id"] for v in (live_log["tool_response"] or {}).get("functionResponses", [{}])[0].get("response", {}).get("result", {}).get("verses", [])],
        "cards": await page.eval_on_selector_all(".turn .card .card-head b", "els => els.map(e => e.textContent)"),
        "stream_to_audio_element": await page.evaluate("window.__streams"),
        "web_audio_playback": await page.evaluate("window.__webaudio"),
        "state_after_end": await page.evaluate("document.body.dataset.state"),
        "errors": errors,
    }
    await b.close()
    result["ok"] = (result["setup_model"] == "models/gemini-3.8-live" and result["greeting_sent"]
                    and result["mic_chunks_while_speaking"] > 5 and result["mic_chunks_while_speaking_with_sound"] == 0
                    and result["mic_chunks_later_with_sound"] > 5
                    and result["tool_verses"] and result["cards"][:1] == result["tool_verses"][:1]
                    and result["stream_to_audio_element"] >= 1 and result["web_audio_playback"] == 0
                    and not errors and result["state_after_end"] == "idle"
                    and {"echo_ignored", "turn_summary", "tool_call", "setup_complete", "first_audio_sent"} <= set(events))
    return result


async def main(shot: str | None) -> int:
    from playwright.async_api import async_playwright
    state: dict = {}
    server = await websockets.serve(live, "127.0.0.1", WS_PORT)
    threading.Thread(target=run_app, args=(state,), daemon=True).start()
    time.sleep(2.5)
    with tempfile.TemporaryDirectory() as d:
        async with async_playwright() as p:
            voice = await spoken_answers(p, Path(d), state, shot)
            beta = await live_beta(p, Path(d), shot)
    server.close()
    print(json.dumps({"spoken_answers": voice, "live_beta": beta, "events": list(dict.fromkeys(events))}, ensure_ascii=False, indent=1))
    ok = voice["ok"] and beta["ok"]
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None)))
