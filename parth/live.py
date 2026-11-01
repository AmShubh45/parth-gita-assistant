"""Real-time voice with Gemini Live.

The browser talks to Gemini Live directly over a WebSocket, so audio never passes through our
server. Our server only:
- mints a single-use ephemeral token whose session config is locked (model, system instruction,
  tools, audio output, transcription), so a visitor cannot change Parth's instructions;
- answers the model's `find_verses` tool calls (relayed by the browser) from the verified
  knowledge base, which is also what the page shows as verse cards;
- runs the same safety triage on what the person says.
"""
from __future__ import annotations

import datetime as dt
import os

SESSION_MINUTES = 10
LIVE_MODELS = tuple(m.strip() for m in os.environ.get(
    "PARTH_LIVE_MODEL", "gemini-3.8-live,gemini-3.1-flash-live-preview").split(",") if m.strip())
VOICE = os.environ.get("PARTH_LIVE_VOICE", "Charon")
WS_URL = ("wss://generativelanguage.googleapis.com/ws/"
          "google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContentConstrained")

SYSTEM = """You are Parth, a warm and wise guide who helps people with real problems through what the
Bhagavad Gita actually says. You are talking with one person, live, by voice.

Language: reply in the language the person speaks (Hindi, Hinglish or English). Keep replies short and
conversational: three to six sentences, then let them speak. Ask a gentle follow-up question when it helps.

Grounding, always:
- Before you mention, explain or apply any verse, call find_verses with a short English description of the
  person's situation. Use only the verses it returns; the person sees those exact verses on screen.
- When you quote a translation, say it exactly as returned. The first time, say it is Swami Swarupananda's translation.
- Never recite Sanskrit or translations from memory. Never invent a verse or put words in Krishna's mouth.
- Explain in this order: the context (who is speaking to whom, what was happening), what it means, and how it
  applies to this person's situation, with one practical step.
- If find_verses returns nothing that fits, say honestly that the Gita does not speak to this directly, and listen.

Safety: if the person speaks of wanting to die, harming themselves, or someone being in danger, stop teaching.
With care, ask them to call Tele-MANAS on 14416 or KIRAN on 1800 599 0019 in India, or 112 in an emergency,
and stay with them supportively. Give no medical, legal or financial advice. Never use the Gita to justify harm,
caste discrimination or politics.

Start by greeting the person briefly, in Hindi and English, and asking what is on their mind."""

FIND_VERSES = {
    "name": "find_verses",
    "description": ("Search the Bhagavad Gita for verses that speak to the person's situation. Returns verified "
                    "verses with speaker, listener, chapter and the exact translation to quote. Call this before "
                    "mentioning any verse."),
    "parameters": {
        "type": "OBJECT",
        "properties": {"query": {"type": "STRING",
                                 "description": "The person's situation or feeling in plain English, e.g. 'anger at a colleague'"}},
        "required": ["query"],
    },
}


def session_config() -> dict:
    """The Live session config, locked into every token."""
    return {
        "response_modalities": ["AUDIO"],
        "system_instruction": SYSTEM,
        "tools": [{"function_declarations": [FIND_VERSES]}],
        "input_audio_transcription": {},
        "output_audio_transcription": {},
        "speech_config": {"voice_config": {"prebuilt_voice_config": {"voice_name": VOICE}}},
        "temperature": 0.6,
    }


def token_request(model: str, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(tz=dt.timezone.utc)
    return {
        "uses": 1,
        "expire_time": (now + dt.timedelta(minutes=SESSION_MINUTES + 2)).isoformat(),
        "new_session_expire_time": (now + dt.timedelta(minutes=1)).isoformat(),
        "live_connect_constraints": {"model": model, "config": session_config()},
        "lock_additional_fields": [],  # lock every field of the setup, not only the ones listed
        "http_options": {"api_version": "v1beta"},
    }


def mint_token(api_key: str, model: str) -> str:
    """Create an ephemeral token with Google's SDK (blocking; call from a worker thread)."""
    from google import genai  # imported lazily: only needed when voice is used
    client = genai.Client(api_key=api_key, http_options={"api_version": "v1beta"})
    return client.auth_tokens.create(config=token_request(model)).name
