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
    assert ans.kind == "off_topic" and "Parth" in ans.opening
