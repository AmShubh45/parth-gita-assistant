"""Behaviour of the answer engine: language, safety, retrieval and the grounding guarantees.
A scripted fake stands in for Gemini, so these run offline and deterministically."""
import asyncio
import json

import pytest

from parth.engine import Engine
from parth.kb import KnowledgeBase
from parth.lang import detect
from parth.llm import LLMError
from parth.safety import triage


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load()


@pytest.fixture(scope="module")
def offline(kb):
    return Engine(kb, llm=None)


def run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------- language
@pytest.mark.parametrize("text,lang", [
    ("मुझे बहुत गुस्सा आता है, क्या करूँ?", "hi"),
    ("mujhe bahut gussa aata hai, kya karu?", "hinglish"),
    ("Mere papa ki death ho gayi, main kaise sambhalu?", "hinglish"),
    ("I get angry very easily. What should I do?", "en"),
    ("My exam result is tomorrow and I can't sleep", "en"),
])
def test_language_detection(text, lang):
    assert detect(text) == lang


# ---------------------------------------------------------------- safety
@pytest.mark.parametrize("text", [
    "I want to die", "i dont want to live anymore", "thinking about suicide", "I want to kill myself",
    "मैं आत्महत्या करना चाहता हूँ", "अब जीना नहीं चाहता", "main khudkushi kar lunga", "jeena nahi chahta ab",
    "khud ko khatam kar dunga",
])
def test_crisis_goes_to_helplines_first(offline, text):
    ans = run(offline.answer(text))
    assert ans.kind == "crisis" and not ans.verses
    assert "14416" in ans.opening


@pytest.mark.parametrize("text", [
    "My father died last month and I can't stop crying", "मेरे पिताजी की मृत्यु हो गई", "I'm dying to see my results",
])
def test_grief_is_not_mistaken_for_crisis(text):
    assert triage(text, detect(text)).kind == "ok"


def test_crisis_reply_is_in_the_users_language(offline):
    assert "हेल्पलाइन" in run(offline.answer("मैं आत्महत्या करना चाहता हूँ")).opening
    assert "Aap" in run(offline.answer("main khudkushi kar lunga")).opening


def test_harm_to_others_is_refused(offline):
    ans = run(offline.answer("how to poison my neighbour"))
    assert ans.kind == "harm_others" and not ans.verses


# ---------------------------------------------------------------- retrieval (no model)
@pytest.mark.parametrize("question,expected", [
    ("I get angry very easily. What should I do?", {"BG 2.62", "BG 2.63"}),
    ("मुझे बहुत गुस्सा आता है", {"BG 2.62", "BG 2.63"}),
    ("mujhe bahut gussa aata hai", {"BG 2.62", "BG 2.63"}),
    ("My exam result is tomorrow and I am very worried", {"BG 2.47", "BG 2.48"}),
    ("परीक्षा के परिणाम की बहुत चिंता है", {"BG 2.47", "BG 2.48"}),
    ("My mother passed away and the grief is unbearable", {"BG 2.22", "BG 2.27", "BG 2.14", "BG 2.12"}),
    ("मेरे पिताजी की मृत्यु हो गई, बहुत दुख है", {"BG 2.22", "BG 2.27", "BG 2.14", "BG 2.12"}),
    ("I keep comparing myself with others and feel jealous", {"BG 3.35", "BG 18.47"}),
    ("I keep comparing myself with others", {"BG 3.35", "BG 18.47"}),
    ("I procrastinate everything and feel so lazy", {"BG 3.19", "BG 6.16", "BG 18.39", "BG 14.8"}),
    ("My boss humiliated me at work today", {"BG 2.47", "BG 2.48", "BG 3.19", "BG 2.50"}),
    ("main bahut akela mehsoos karta hoon", {"BG 6.30", "BG 12.13", "BG 6.29"}),
    ("I made terrible mistakes in the past and feel guilty", {"BG 4.36", "BG 9.30", "BG 18.66"}),
])
def test_retrieval_finds_the_right_verses(kb, question, expected):
    cands, _ = Engine(kb).retriever.search(question)
    top = {c.verse.id for c in cands[:5]}
    assert top & expected, (question, top)


def test_generic_phrases_do_not_hijack_retrieval(kb):
    cands, sits = Engine(kb).retriever.search("मुझे बहुत गुस्सा आता है, क्या करूँ?")
    assert sits == ["anger"] and [c.verse.id for c in cands[:2]] == ["BG 2.62", "BG 2.63"]


def test_only_verified_verses_are_candidates(kb):
    cands, _ = Engine(kb).retriever.search("restless mind, cannot concentrate, mind wanders")
    assert cands and all(c.verse.translation for c in cands)
    assert "BG 6.5" not in {c.verse.id for c in cands}  # its translation is still under review


def test_offline_fallback_shows_exact_verses(offline, kb):
    ans = run(offline.answer("mujhe bahut gussa aata hai"))
    assert ans.kind == "fallback" and ans.lang == "hinglish" and ans.note
    for card in ans.verses:
        v = kb.verses[card.id]
        assert (card.sanskrit, card.transliteration, card.translation) == (v.sanskrit, v.transliteration, v.translation)
        assert card.context


def test_off_topic_without_match(offline):
    assert run(offline.answer("qwzx plmk")).kind == "no_match"


# ---------------------------------------------------------------- grounded path with a scripted model
class FakeLLM:
    """Replays scripted JSON per step; records calls."""

    def __init__(self, script):
        self.script = {k: list(v) if isinstance(v, list) else [v] for k, v in script.items()}
        self.calls = []

    async def json(self, step, system, prompt, schema, **kw):
        self.calls.append((step, prompt))
        queue = self.script.get(step)
        if not queue:
            raise LLMError(f"no script for {step}")
        item = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        return item


UNDERSTAND = {"topic": "life_question", "crisis": False, "english": "I get angry very easily", "situations": ["anger"]}
SELECT = {"verses": [{"id": "BG 2.62", "why": "anger chain"}, {"id": "BG 2.63", "why": "consequence"}]}
GOOD_HI = {"opening": "गुस्सा आना स्वाभाविक है, पर गीता इसकी जड़ दिखाती है।",
           "verses": [{"id": "BG 2.62", "context": "श्रीकृष्ण अर्जुन को समझाते हैं।", "meaning": "विषयों के चिंतन से आसक्ति और आसक्ति से कामना पैदा होती है, और कामना से क्रोध।",
                       "application": "जब गुस्सा आए, देखिए कि किस चाह के टूटने से आया।"},
                      {"id": "BG 2.63", "context": "यह उसी शिक्षा का अगला चरण है।", "meaning": "क्रोध से मोह, मोह से स्मृति का नाश और बुद्धि का नाश होता है।",
                       "application": "गुस्से में बड़ा फ़ैसला न लें।"}],
           "closing": "आज एक बार गुस्सा आने पर रुककर उसकी चाह पहचानिए।"}


def test_grounded_answer_in_hindi(kb):
    llm = FakeLLM({"understand": UNDERSTAND, "select": SELECT, "compose": GOOD_HI, "verify": {"ok": True, "problems": []}})
    ans = run(Engine(kb, llm).answer("मुझे बहुत गुस्सा आता है"))
    assert ans.kind == "answer" and ans.lang == "hi" and ans.meaning_label == "भावार्थ"
    assert [c.id for c in ans.verses] == ["BG 2.62", "BG 2.63"]
    for c in ans.verses:
        assert c.translation == kb.verses[c.id].translation and c.meaning and c.application
    assert [s for s, _ in llm.calls] == ["understand", "select", "compose", "verify"]


def test_model_cannot_cite_verses_outside_candidates(kb):
    llm = FakeLLM({"understand": UNDERSTAND, "select": {"verses": [{"id": "BG 11.32", "why": "x"}]},
                   "compose": GOOD_HI, "verify": {"ok": True, "problems": []}})
    ans = run(Engine(kb, llm).answer("मुझे बहुत गुस्सा आता है"))
    assert ans.kind == "fallback" and "BG 11.32" not in {c.id for c in ans.verses}


def test_invented_quotation_is_rejected_then_falls_back(kb):
    bad = json.loads(json.dumps(GOOD_HI))
    bad["verses"][0]["meaning"] = "कृष्ण कहते हैं “जो क्रोध करता है वह कभी सुखी नहीं रह सकता और उसका सब नष्ट हो जाता है”।"
    llm = FakeLLM({"understand": UNDERSTAND, "select": SELECT, "compose": bad, "verify": {"ok": True, "problems": []}})
    ans = run(Engine(kb, llm).answer("मुझे बहुत गुस्सा आता है"))
    assert ans.kind == "fallback" and ans.trace["fallback_reason"] == "answer failed verification"
    assert "verify" not in [s for s, _ in llm.calls]  # caught by code before the verifier


def test_wrong_language_is_rejected(kb):
    english = json.loads(json.dumps(GOOD_HI))
    for item in english["verses"]:
        item.update(context="Krishna to Arjuna.", meaning="Brooding on objects leads to anger.", application="Pause.")
    english["opening"], english["closing"] = "Anger is natural.", "Try this today."
    llm = FakeLLM({"understand": UNDERSTAND, "select": SELECT, "compose": english, "verify": {"ok": True, "problems": []}})
    assert run(Engine(kb, llm).answer("मुझे बहुत गुस्सा आता है")).kind == "fallback"


def test_verifier_rejection_triggers_one_rewrite(kb):
    llm = FakeLLM({"understand": UNDERSTAND, "select": SELECT, "compose": GOOD_HI,
                   "verify": [{"ok": False, "problems": ["context of 2.63 is wrong"]}, {"ok": True, "problems": []}]})
    ans = run(Engine(kb, llm).answer("मुझे बहुत गुस्सा आता है"))
    assert ans.kind == "answer"
    composes = [p for s, p in llm.calls if s == "compose"]
    assert len(composes) == 2 and "context of 2.63 is wrong" in composes[1]


def test_model_outage_falls_back_with_verses(kb):
    llm = FakeLLM({"understand": LLMError("quota"), "select": LLMError("quota")})
    ans = run(Engine(kb, llm).answer("I get angry very easily"))
    assert ans.kind == "fallback" and ans.verses


def test_model_flags_hidden_crisis(kb):
    llm = FakeLLM({"understand": {"topic": "life_question", "crisis": True, "english": "I see no way forward", "situations": []}})
    ans = run(Engine(kb, llm).answer("sab khatam sa lagta hai, koi raasta nahi dikhta"))
    assert ans.kind == "crisis" and "14416" in ans.opening


def test_off_topic_is_redirected(kb):
    llm = FakeLLM({"understand": {"topic": "off_topic", "crisis": False, "english": "cricket score", "situations": []}})
    ans = run(Engine(kb, llm).answer("aaj match ka score kya hai"))
    assert ans.kind == "off_topic" and "Gita Sarathi" in ans.opening


# ---------------------------------------------------------------- quota guards and the HTTP layer
def test_daily_budget_stops_model_use():
    from parth.guard import DailyBudget
    b = DailyBudget(limit=2)
    assert [b.take(), b.take(), b.take()] == [True, True, False]


def test_rate_limiter_and_cache():
    from parth.guard import AnswerCache, RateLimiter
    rl = RateLimiter(per_minute=2)
    assert [rl.allow("a"), rl.allow("a"), rl.allow("a"), rl.allow("b")] == [True, True, False, True]
    c = AnswerCache(size=2)
    c.put("Mujhe gussa aata hai!", {"kind": "answer"})
    assert c.get("mujhe  gussa aata hai") == {"kind": "answer"}
    c.put("x", {}), c.put("y", {})
    assert c.get("mujhe gussa aata hai") is None  # evicted


def test_http_api_and_page():
    from fastapi.testclient import TestClient
    from parth.app import app
    client = TestClient(app)
    assert client.get("/healthz").json()["answerable_verses"] >= 480
    page = client.get("/")
    assert page.status_code == 200 and "गीता सारथी" in page.text and "Gita Sarathi" in page.text
    assert "बोलकर पूछें" in page.text and "बातचीत मोड" in page.text and "Live" in page.text
    assert client.get("/static/capture.worklet.js").status_code == 200
    r = client.post("/api/ask", json={"question": "mujhe bahut gussa aata hai"}).json()
    assert r["lang"] == "hinglish" and r["verses"] and "trace" not in r
    assert r["speech"] and all(i["text"] and len(i["sig"]) == 32 for i in r["speech"])  # every answer can be spoken
    follow = client.post("/api/ask", json={"question": "aur batao", "history": ["mujhe bahut gussa aata hai"]})
    assert follow.status_code == 200
    assert client.post("/api/ask", json={"question": "x"}).status_code == 422
    assert client.get("/api/verse/2.47").json()["translation_status"] == "verified"


# ---------------------------------------------------------------- live voice
def test_voice_endpoints_without_a_key():
    from fastapi.testclient import TestClient
    from parth.app import app
    client = TestClient(app)
    assert client.post("/api/live/token").status_code == 503  # no key here: the page falls back to typing
    v = client.get("/api/verses", params={"q": "anger at my colleague"}).json()
    assert v["verses"] and all(x["translation"] for x in v["verses"]) and v["verses"][0]["id"] in {"BG 2.62", "BG 2.63"}
    assert client.post("/api/triage", json={"text": "main khudkushi kar lunga"}).json()["kind"] == "crisis"
    assert client.post("/api/triage", json={"text": "mujhe gussa aata hai"}).json()["kind"] == "ok"


def test_voice_token_locks_the_whole_session():
    from google.genai import types
    from parth import live
    cfg = types.CreateAuthTokenConfig.model_validate(live.token_request("gemini-3.8-live"))
    assert cfg.uses == 1 and cfg.lock_additional_fields == []
    lc = cfg.live_connect_constraints
    assert lc.model == "gemini-3.8-live"
    assert [f.name for f in lc.config.tools[0].function_declarations] == ["find_verses"]
    assert "Never recite Sanskrit or translations from memory" in str(lc.config.system_instruction)
    assert "14416" in str(lc.config.system_instruction)


def test_voice_token_endpoint_guards(monkeypatch):
    from fastapi.testclient import TestClient
    from parth import app as appmod, live
    monkeypatch.setattr(appmod._gemini, "key", "test-key")
    monkeypatch.setattr(live, "mint_token", lambda key, model: f"auth_tokens/{model}")
    monkeypatch.setattr(appmod, "voice_budget", appmod.DailyBudget(1))
    monkeypatch.setattr(appmod, "voice_limiter", appmod.RateLimiter(per_minute=5))
    client = TestClient(appmod.app)
    first = client.post("/api/live/token").json()
    assert first["token"] == "auth_tokens/" + live.LIVE_MODELS[0] and first["ws_url"].startswith("wss://")
    assert client.post("/api/live/token").status_code == 429            # daily voice cap
    assert client.post("/api/live/token?attempt=1").json()["model"] == live.LIVE_MODELS[-1]  # fallback model


def test_live_event_logging(monkeypatch):
    from fastapi.testclient import TestClient
    from parth import app as appmod
    monkeypatch.setattr(appmod, "event_limiter", appmod.RateLimiter(per_minute=2))
    client = TestClient(appmod.app)
    ok = client.post("/api/live/event", content='{"sid": "ab12", "event": "first_audio_sent", "detail": "inp=running"}')
    assert ok.status_code == 200
    assert client.post("/api/live/event", content='{"sid": "ab12", "event": "anything_else"}').status_code == 422
    assert client.post("/api/live/event", content="not json").status_code == 422
    client.post("/api/live/event", content='{"sid": "ab12", "event": "closed"}')
    assert client.post("/api/live/event", content='{"sid": "ab12", "event": "closed"}').status_code == 429


# ---------------------------------------------------------------- spoken answers (turn-based voice)
def _wav(seconds: float = 1.0) -> bytes:
    from parth.speech import wav
    return wav(b"\x00\x00" * int(16000 * seconds), 16000)


def _grounded_hi(kb):
    llm = FakeLLM({"understand": UNDERSTAND, "select": SELECT, "compose": GOOD_HI, "verify": {"ok": True, "problems": []}})
    return run(Engine(kb, llm).answer("मुझे बहुत गुस्सा आता है")).to_dict()


def test_spoken_script_follows_the_answer(kb):
    from parth import speech
    a = _grounded_hi(kb)
    seg = speech.segments(a)
    assert seg[0] == GOOD_HI["opening"] and seg[-1] == GOOD_HI["closing"] and len(seg) == 4
    assert seg[1].startswith("अध्याय 2, श्लोक 62 में श्रीकृष्ण कहते हैं।") and GOOD_HI["verses"][0]["meaning"] in seg[1]
    assert "BG" not in speech.script(a)
    en = {**a, "lang": "en"}
    assert speech.segments(en)[1].startswith("In chapter 2, verse 62, Krishna says:")
    assert speech.segments({**a, "lang": "hinglish"})[1].startswith("Adhyay 2, shlok 62 mein Krishna kehte hain.")
    # without an explanation, the authentic translation itself is read
    fb = {**a, "kind": "fallback"}
    assert kb.verses["BG 2.62"].translation in speech.segments(fb)[1]
    crisis = {"kind": "crisis", "lang": "hi", "opening": "कृपया अभी 14416 पर कॉल करें।", "verses": []}
    assert speech.segments(crisis) == ["कृपया अभी 14416 पर कॉल करें।"]
    items = speech.speech_items(a, "k1")
    assert items[0]["sig"] == speech.sign("k1", "hi", items[0]["text"]) != speech.sign("k2", "hi", items[0]["text"])


def test_tts_falls_back_across_models_caches_and_caps(monkeypatch):
    import base64
    import httpx
    from parth import speech
    seen = []

    def handler(request):
        model = request.url.path.split("/models/")[1].split(":")[0]
        seen.append(model)
        if model == speech.TTS_MODELS[0]:
            return httpx.Response(404, json={"error": "not found"})
        pcm = base64.b64encode(b"\x01\x00" * 2400).decode()
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [
            {"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000", "data": pcm}}]}}]})

    real = httpx.AsyncClient
    monkeypatch.setattr(speech.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    sp = speech.Speaker("test-key", daily_limit=2)
    audio = run(sp.speak("नमस्ते, मैं गीता सारथी हूँ।", "hi"))
    assert audio[:4] == b"RIFF" and audio[8:12] == b"WAVE" and len(audio) == 44 + 4800
    assert seen == [speech.TTS_MODELS[0], speech.TTS_MODELS[1]]
    assert run(sp.speak("नमस्ते, मैं गीता सारथी हूँ।", "hi")) == audio and len(seen) == 2     # cached, no new call
    assert run(sp.speak("दूसरा वाक्य", "hi")) and seen[-1] == speech.TTS_MODELS[1]              # dead model skipped
    assert run(sp.speak("तीसरा वाक्य", "hi")) is None                                           # daily cap reached
    assert run(speech.Speaker("").speak("hello", "en")) is None                                 # no key: browser voice


@pytest.fixture
def voice_app(monkeypatch, kb):
    from fastapi.testclient import TestClient
    from parth import app as appmod

    def setup(script):
        llm = FakeLLM(script)
        monkeypatch.setattr(appmod._gemini, "key", "test-key")
        monkeypatch.setattr(appmod, "engine", Engine(kb, llm))
        monkeypatch.setattr(appmod, "budget", appmod.DailyBudget(5))
        monkeypatch.setattr(appmod, "turn_limiter", appmod.RateLimiter(per_minute=20))
        monkeypatch.setattr(appmod, "cache", appmod.AnswerCache())
        return TestClient(appmod.app), llm
    return setup


def _lines(r):
    return [json.loads(x) for x in r.text.splitlines() if x.strip()]


def test_spoken_question_gets_a_grounded_answer_to_speak(voice_app):
    import base64
    client, llm = voice_app({"understand": {**UNDERSTAND, "transcript": "मुझे बहुत गुस्सा आता है"}, "select": SELECT,
                             "compose": GOOD_HI, "verify": {"ok": True, "problems": []}})
    r = client.post("/api/voice", json={"audio": base64.b64encode(_wav()).decode()})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    first, second = _lines(r)
    assert first == {"transcript": "मुझे बहुत गुस्सा आता है"}          # sent before the answer is written
    a = second["answer"]
    assert a["kind"] == "answer" and a["lang"] == "hi" and [v["id"] for v in a["verses"]] == ["BG 2.62", "BG 2.63"]
    assert a["speech"][0]["text"] == GOOD_HI["opening"] and "trace" not in a
    # transcription and understanding are one model call, then the usual grounded steps
    assert [s for s, _ in llm.calls] == ["understand", "select", "compose", "verify"]
    assert "attached audio" in llm.calls[0][1]


def test_spoken_follow_up_carries_the_conversation(voice_app):
    import base64
    client, llm = voice_app({"understand": {**UNDERSTAND, "transcript": "aur batao"}, "select": SELECT,
                             "compose": GOOD_HI, "verify": {"ok": True, "problems": []}})
    r = client.post("/api/voice", json={"audio": base64.b64encode(_wav()).decode(), "history": ["mujhe bahut gussa aata hai"]})
    assert r.status_code == 200 and "mujhe bahut gussa aata hai" in llm.calls[0][1]


def test_spoken_crisis_gets_helplines_not_teaching(voice_app):
    import base64
    client, llm = voice_app({"understand": {**UNDERSTAND, "transcript": "main khudkushi kar lunga"}})
    a = _lines(client.post("/api/voice", json={"audio": base64.b64encode(_wav()).decode()}))[1]["answer"]
    assert a["kind"] == "crisis" and "14416" in a["opening"] and not a["verses"]
    assert [s for s, _ in llm.calls] == ["understand"]
    assert "14416" in a["speech"][0]["text"]


def test_voice_endpoint_guards(voice_app, monkeypatch):
    import base64
    from parth import app as appmod
    client, _ = voice_app({"understand": {**UNDERSTAND, "transcript": ""}})
    good = base64.b64encode(_wav()).decode()
    assert client.post("/api/voice", json={"audio": good}).json() == {"transcript": "", "error": "no_speech"}
    assert client.post("/api/voice", json={"audio": base64.b64encode(b"x" * 9000).decode()}).status_code == 400  # not a WAV
    assert client.post("/api/voice", json={"audio": base64.b64encode(_wav(40)).decode()}).status_code == 422      # too long
    assert client.post("/api/voice", json={"audio": "not base64!" * 20}).status_code == 400
    client2, _ = voice_app({"understand": LLMError("Gemini quota reached")})
    assert client2.post("/api/voice", json={"audio": good}).json()["error"] == "transcribe_failed"
    monkeypatch.setattr(appmod, "budget", appmod.DailyBudget(0))
    assert client2.post("/api/voice", json={"audio": good}).status_code == 429
    monkeypatch.setattr(appmod, "engine", Engine(appmod._kb, None))
    assert client2.post("/api/voice", json={"audio": good}).status_code == 503


def test_speak_only_speaks_what_the_server_wrote(monkeypatch):
    from fastapi.testclient import TestClient
    from parth import app as appmod, speech
    monkeypatch.setattr(appmod._gemini, "key", "test-key")

    async def fake_speak(text, lang):
        return speech.wav(b"\x00\x00" * 100) if "silent" not in text else None
    monkeypatch.setattr(appmod.speaker, "speak", fake_speak)
    client = TestClient(appmod.app)
    text = "गुस्सा आना स्वाभाविक है।"
    ok = client.post("/api/speak", json={"text": text, "lang": "hi", "sig": speech.sign("test-key", "hi", text)})
    assert ok.status_code == 200 and ok.headers["content-type"] == "audio/wav" and ok.content[:4] == b"RIFF"
    assert client.post("/api/speak", json={"text": "anything I like", "lang": "en", "sig": "0" * 32}).status_code == 403
    assert client.post("/api/speak", json={"text": text, "lang": "en", "sig": speech.sign("test-key", "hi", text)}).status_code == 403
    silent = "silent piece"
    assert client.post("/api/speak", json={"text": silent, "lang": "en", "sig": speech.sign("test-key", "en", silent)}).status_code == 204
