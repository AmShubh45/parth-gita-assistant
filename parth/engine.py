"""The answer pipeline: safety → understand → retrieve → select → compose → verify → render.

Guarantees, enforced in code rather than left to prompts:
- verse text (Sanskrit, transliteration, translation) is copied from the knowledge base by ID;
  the model only chooses IDs and writes the explanation around them;
- the model can only cite verses that retrieval offered, and only ones with a verified translation;
- long quotations in model text are rejected, so it cannot invent scripture;
- a second model checks the explanation against the same sources; if the answer still fails after
  one rewrite, or any model step fails, Parth falls back to showing the verses with their context.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import asdict, dataclass, field

from .kb import SPEAKER_HI, KnowledgeBase, Verse
from .lang import detect
from .llm import LLM, LLMError
from .retrieve import Candidate, Retriever
from .safety import triage

logger = logging.getLogger(__name__)

LANG_NAME = {"hi": "Hindi in Devanagari script", "hinglish": "Hinglish (Hindi written in Roman letters)", "en": "English"}
MEANING_LABEL = {"hi": "भावार्थ", "hinglish": "Bhavarth (meaning)", "en": "Meaning"}

FALLBACK_TEXT = {
    "opening": {
        "en": "These are the verses of the Gita that speak most directly to what you're going through.",
        "hi": "आप जो महसूस कर रहे हैं, उस पर गीता के ये श्लोक सबसे सीधे बात करते हैं।",
        "hinglish": "Aap jo mehsoos kar rahe hain, us par Gita ke ye shlok sabse seedhe baat karte hain.",
    },
    "note": {
        "en": "A detailed explanation isn't available right now, so the verses are shown on their own.",
        "hi": "अभी विस्तार से व्याख्या उपलब्ध नहीं है, इसलिए केवल श्लोक दिखाए जा रहे हैं।",
        "hinglish": "Abhi detail mein explanation available nahi hai, isliye sirf shlok dikhaye ja rahe hain.",
    },
    "no_match": {
        "en": "I couldn't find verses in the Gita that speak directly to this. Could you tell me a little more about what you're feeling or facing?",
        "hi": "मुझे गीता में ऐसे श्लोक नहीं मिले जो सीधे इस बारे में बात करते हों। क्या आप थोड़ा और बताएँगे कि आप क्या महसूस कर रहे हैं या किस स्थिति में हैं?",
        "hinglish": "Mujhe Gita mein aise shlok nahi mile jo seedhe is baare mein baat karte hon. Kya aap thoda aur batayenge ki aap kya mehsoos kar rahe hain?",
    },
    "off_topic": {
        "en": "I'm Gita Sarathi, and I answer life's questions through the Bhagavad Gita. Tell me what's on your mind: a worry, a decision, a loss, anything you're carrying.",
        "hi": "मैं गीता सारथी हूँ, और मैं भगवद्गीता के माध्यम से जीवन के प्रश्नों का उत्तर देता हूँ। बताइए, आपके मन में क्या है: कोई चिंता, कोई निर्णय, कोई दुख?",
        "hinglish": "Main Gita Sarathi hoon, aur main Bhagavad Gita ke through zindagi ke sawalon ke jawab deta hoon. Bataiye, aapke man mein kya hai: koi chinta, koi faisla, koi dukh?",
    },
}


@dataclass
class VerseCard:
    id: str
    ref: str
    chapter: int
    chapter_name: str
    chapter_name_sanskrit: str
    speaker: str
    addressed_to: str
    sanskrit: str
    transliteration: str
    translation: str
    translation_source: str
    context: str = ""
    meaning: str = ""
    application: str = ""


@dataclass
class Answer:
    kind: str  # answer | fallback | crisis | harm_others | no_match | off_topic
    lang: str
    opening: str = ""
    verses: list[VerseCard] = field(default_factory=list)
    closing: str = ""
    note: str = ""
    meaning_label: str = ""
    situations: list[str] = field(default_factory=list)
    trace: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ schemas
def _understand_schema(situation_ids: list[str]) -> dict:
    return {"type": "OBJECT", "properties": {
        "topic": {"type": "STRING", "enum": ["life_question", "gita_question", "off_topic"]},
        "crisis": {"type": "BOOLEAN"},
        "english": {"type": "STRING"},
        "situations": {"type": "ARRAY", "items": {"type": "STRING", "enum": situation_ids}}},
        "required": ["topic", "crisis", "english", "situations"]}


_SELECT_SCHEMA = {"type": "OBJECT", "properties": {"verses": {"type": "ARRAY", "items": {
    "type": "OBJECT", "properties": {"id": {"type": "STRING"}, "why": {"type": "STRING"}}, "required": ["id", "why"]}}},
    "required": ["verses"]}
_COMPOSE_SCHEMA = {"type": "OBJECT", "properties": {
    "opening": {"type": "STRING"},
    "verses": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "id": {"type": "STRING"}, "context": {"type": "STRING"}, "meaning": {"type": "STRING"},
        "application": {"type": "STRING"}}, "required": ["id", "context", "meaning", "application"]}},
    "closing": {"type": "STRING"}}, "required": ["opening", "verses", "closing"]}
_VERIFY_SCHEMA = {"type": "OBJECT", "properties": {"ok": {"type": "BOOLEAN"},
                                                   "problems": {"type": "ARRAY", "items": {"type": "STRING"}}},
                  "required": ["ok", "problems"]}

# ------------------------------------------------------------------ prompts
def _history_note(history: list[str] | None) -> str:
    recent = [h.strip()[:300] for h in (history or []) if h and h.strip()][-2:]
    return ("Earlier in this conversation the person said: " + " | ".join(recent) + "\nNow they say: ") if recent else ""


_UNDERSTAND_SYSTEM = """You read one message sent to Gita Sarathi, an app that answers life questions through the Bhagavad Gita.
The message may be in Hindi, Hinglish or English. Return:
- topic: "life_question" (a feeling, problem, decision, relationship, work, loss...), "gita_question" (about the Gita,
  its characters or teachings), or "off_topic" (unrelated requests: news, code, trivia, homework...).
- crisis: true if the person may be at risk of harming themselves, even if said indirectly.
- english: the message restated in plain English, keeping its emotional meaning.
- situations: the matching situation ids from the allowed list (zero to three)."""

_SELECT_SYSTEM = """You choose which Bhagavad Gita verses best answer a person's question.
You are given candidate verses with their speaker, listener, chapter and an authentic translation.
Pick 1 to 3 verses that speak most directly to the person's situation when read in their real context.
Prefer verses where Krishna teaches. Choose only from the candidate IDs. For each, say in one sentence why it fits."""

_COMPOSE_SYSTEM = """You are Gita Sarathi. You help people with real problems through what the Bhagavad Gita actually says.

Write the whole answer in {lang}. Be warm, simple and respectful, like an elder who has studied the Gita closely.

For each verse you are given:
- context: 1–2 sentences on who is speaking to whom and the moment in the dialogue (use the speaker, chapter and the
  neighbouring verses provided). Krishna speaks to Arjuna on the battlefield of Kurukshetra.
- meaning: what the verse says, faithful to the provided translation and the classical commentaries
  (Shankara, Ramanuja, Sridhara). This is an explanation, not a translation.
- application: how this teaching applies to this person's situation, concretely.
Also write a short opening that shows you understood them, and a closing with one practical step.

Rules:
- Never quote or recite verse text, Sanskrit or translation: the app shows the exact verse beside your words.
- Never use quotation marks around long passages, and never attribute words to Krishna that are not in the translation.
- Do not add teachings, stories or claims that are not supported by the material given.
- If the classical commentators read a verse differently, say so briefly instead of picking one.
- No medical, legal or financial advice. Never use the Gita to justify harm, caste discrimination or politics.
- Keep it short: opening ≤ 2 sentences, each field ≤ 3 sentences, closing ≤ 2 sentences."""

_VERIFY_SYSTEM = """You check an answer written for a person by Gita Sarathi, an app grounded in the Bhagavad Gita.
You are given the person's question, the source material for each verse (authentic translation, speaker, chapter,
neighbouring verses, classical commentary excerpts) and the answer.
Set ok=false and list each problem if any of these is true:
- a statement about what a verse says is not supported by its translation or the commentary excerpts;
- the context (speaker, listener, situation) is wrong;
- it quotes scripture that is not in the material, or puts words in Krishna's mouth;
- it gives medical, legal or financial advice, or could encourage harm;
- it is not written in {lang}.
Small differences in wording are fine. Judge faithfulness, not style."""


class Engine:
    def __init__(self, kb: KnowledgeBase, llm: LLM | None = None):
        self.kb = kb
        self.llm = llm
        self.retriever = Retriever(kb)

    # ------------------------------------------------------------- helpers
    def _card(self, v: Verse) -> VerseCard:
        ch = self.kb.chapters[v.chapter]
        return VerseCard(id=v.id, ref=v.ref, chapter=v.chapter, chapter_name=ch["name_en"],
                         chapter_name_sanskrit=ch["name_sanskrit"], speaker=v.speaker,
                         addressed_to=v.addressed_to, sanskrit=v.sanskrit, transliteration=v.transliteration,
                         translation=v.translation or "", translation_source="Swami Swarupananda (1909)")

    def _auto_context(self, v: Verse, lang: str) -> str:
        ch = self.kb.chapters[v.chapter]
        if lang == "hi":
            return f"अध्याय {v.chapter} ({ch['name_sanskrit']}) में {SPEAKER_HI[v.speaker]} {SPEAKER_HI[v.addressed_to]} से कहते हैं।"
        if lang == "hinglish":
            return f"Adhyay {v.chapter} ({ch['name_transliterated']}) mein {v.speaker} {v.addressed_to} se kehte hain."
        return f"{v.speaker} to {v.addressed_to}, chapter {v.chapter} ({ch['name_en']})."

    def _material(self, v: Verse) -> str:
        ch = self.kb.chapters[v.chapter]
        lines = [f"[{v.id}] speaker: {v.speaker} → listener: {v.addressed_to}",
                 f"chapter {v.chapter}: {ch['name_en']} ({ch['meaning']}). {ch['summary_en'][:500]}",
                 f"translation (Swami Swarupananda, 1909): {v.translation}"]
        for n in self.kb.neighbours(v):
            if n.translation:
                lines.append(f"neighbouring verse {n.id} ({n.speaker}): {n.translation}")
        com = self.kb.commentaries.get(v.id, {})
        for key in ("shankara", "ramanuja", "sridhara"):
            if key in com:
                lines.append(f"commentary ({key}, Sanskrit): {com[key][:600]}")
        return "\n".join(lines)

    @staticmethod
    def _long_quote(text: str) -> bool:
        for m in re.finditer(r"[\"“”‘’']([^\"“”‘’']{20,})[\"“”‘’']", text):
            if len(m.group(1).split()) > 8:
                return True
        return False

    @staticmethod
    def _in_language(text: str, lang: str) -> bool:
        dev = len(re.findall(r"[ऀ-ॿ]", text))
        lat = len(re.findall(r"[A-Za-z]", text))
        if lang == "hi":
            return dev >= 0.6 * max(1, dev + lat)
        return lat >= 0.8 * max(1, dev + lat)

    def _fallback(self, lang: str, cands: list[Candidate], sits: list[str], trace: dict, reason: str) -> Answer:
        trace["fallback_reason"] = reason
        cards = []
        for c in cands[:2]:
            card = self._card(c.verse)
            card.context = self._auto_context(c.verse, lang)
            cards.append(card)
        return Answer(kind="fallback", lang=lang, opening=FALLBACK_TEXT["opening"][lang], verses=cards,
                      note=FALLBACK_TEXT["note"][lang], meaning_label=MEANING_LABEL[lang], situations=sits, trace=trace)

    # ------------------------------------------------------------- pipeline
    async def understand_audio(self, audio_wav: bytes, history: list[str] | None = None) -> dict:
        """Transcribe a spoken question and understand it in one model call."""
        schema = _understand_schema([s["id"] for s in self.kb.situations])
        schema = {**schema, "properties": {**schema["properties"], "transcript": {"type": "STRING"}},
                  "required": ["transcript", *schema["required"]]}
        prompt = (_history_note(history) + "The attached audio is the person's message. Transcribe it exactly in the "
                  "script they spoke (Devanagari for Hindi, Roman letters for Hinglish, English as English), then fill the rest.")
        return await self.llm.json("understand", _UNDERSTAND_SYSTEM, prompt, schema, max_tokens=600, timeout_s=25,
                                   audio=("audio/wav", audio_wav))

    async def answer(self, question: str, use_model: bool = True, understanding: dict | None = None,
                     history: list[str] | None = None) -> Answer:
        """use_model=False answers from the knowledge base alone (e.g. when the daily AI budget is spent).
        understanding: a result already computed (e.g. by understand_audio), so the model is not asked twice.
        history: the person's previous questions in this conversation, for follow-ups like "aur batao"."""
        t0 = time.monotonic()
        question = (question or "").strip()[:2000]
        lang = detect(question)
        trace: dict = {"steps": []}
        tri = triage(question, lang)
        if tri.kind != "ok":
            return Answer(kind=tri.kind, lang=lang, opening=tri.message or "", trace=trace)

        english, situation_ids = "", []
        llm = self.llm if use_model else None
        if llm:
            try:
                u = understanding or await llm.json("understand", _UNDERSTAND_SYSTEM, _history_note(history) + question,
                                                    _understand_schema([s["id"] for s in self.kb.situations]), max_tokens=300)
                trace["steps"].append("understand")
                if u.get("crisis"):
                    return Answer(kind="crisis", lang=lang, opening=triage("suicide", lang).message or "", trace=trace)
                if u.get("topic") == "off_topic":
                    return Answer(kind="off_topic", lang=lang, opening=FALLBACK_TEXT["off_topic"][lang], trace=trace)
                english, situation_ids = u.get("english", ""), list(u.get("situations", []))
            except LLMError as exc:
                trace["understand_error"] = str(exc)

        cands, sits = self.retriever.search(question, english=english, situation_ids=situation_ids)
        trace["candidates"] = [c.verse.id for c in cands]
        if not cands:
            return Answer(kind="no_match", lang=lang, opening=FALLBACK_TEXT["no_match"][lang], situations=sits, trace=trace)
        if not llm:
            return self._fallback(lang, cands, sits, trace, "no model configured" if not self.llm else "daily AI budget reached")

        try:
            ans = await self._grounded(_history_note(history) + question, english, lang, cands, sits, trace)
        except LLMError as exc:
            return self._fallback(lang, cands, sits, trace, f"model error: {exc}")
        trace["ms"] = int((time.monotonic() - t0) * 1000)
        return ans

    async def _grounded(self, question: str, english: str, lang: str, cands: list[Candidate], sits: list[str],
                        trace: dict) -> Answer:
        allowed = {c.verse.id: c.verse for c in cands}
        listing = "\n\n".join(self._material(c.verse).split("\ncommentary")[0] for c in cands)
        sel = await self.llm.json("select", _SELECT_SYSTEM,
                                  f"QUESTION: {question}\nIN ENGLISH: {english or '(same)'}\n\nCANDIDATES:\n{listing}",
                                  _SELECT_SCHEMA, max_tokens=400)
        trace["steps"].append("select")
        ids = list(dict.fromkeys(x.get("id") for x in sel.get("verses", []) if x.get("id") in allowed))[:3]
        chosen = [allowed[i] for i in ids]
        if not chosen:
            return self._fallback(lang, cands, sits, trace, "no valid verse selected")
        trace["selected"] = [v.id for v in chosen]

        material = "\n\n".join(self._material(v) for v in chosen)
        problems: list[str] = []
        for attempt in range(2):
            extra = ("\n\nA reviewer found these problems in your previous answer; fix them:\n- " + "\n- ".join(problems)) if problems else ""
            comp = await self.llm.json("compose", _COMPOSE_SYSTEM.format(lang=LANG_NAME[lang]),
                                       f"QUESTION: {question}\n\nVERSES:\n{material}{extra}",
                                       _COMPOSE_SCHEMA, smart=True, max_tokens=1400, timeout_s=30)
            trace["steps"].append("compose")
            problems = self._check_composition(comp, chosen, lang)
            if problems:
                continue
            ver = await self.llm.json("verify", _VERIFY_SYSTEM.format(lang=LANG_NAME[lang]),
                                      f"QUESTION: {question}\n\nSOURCE MATERIAL:\n{material}\n\nANSWER:\n{comp}",
                                      _VERIFY_SCHEMA, max_tokens=400)
            trace["steps"].append("verify")
            if ver.get("ok") and not ver.get("problems"):
                return self._render(comp, chosen, lang, sits, trace)
            problems = [str(p) for p in ver.get("problems", [])] or ["the reviewer rejected the answer"]
        trace["problems"] = problems
        return self._fallback(lang, [Candidate(v, 1.0, []) for v in chosen], sits, trace, "answer failed verification")

    def _check_composition(self, comp: dict, chosen: list[Verse], lang: str) -> list[str]:
        ids = {v.id for v in chosen}
        problems = []
        items = comp.get("verses", [])
        if not items or any(i.get("id") not in ids for i in items):
            problems.append("explain only the selected verses, using their exact IDs")
        texts = [comp.get("opening", ""), comp.get("closing", "")] + [i.get(f, "") for i in items for f in ("context", "meaning", "application")]
        if any(not t.strip() for t in texts):
            problems.append("every field must be filled in")
        if any(self._long_quote(t) for t in texts):
            problems.append("do not quote verse text or put long quotations in the answer")
        if not self._in_language(" ".join(texts), lang):
            problems.append(f"write everything in {LANG_NAME[lang]}")
        return problems

    def _render(self, comp: dict, chosen: list[Verse], lang: str, sits: list[str], trace: dict) -> Answer:
        by_id = {i["id"]: i for i in comp["verses"]}
        cards = []
        for v in chosen:
            if v.id not in by_id:
                continue
            card = self._card(v)  # verse text always from the knowledge base
            card.context, card.meaning, card.application = (by_id[v.id][f].strip() for f in ("context", "meaning", "application"))
            cards.append(card)
        return Answer(kind="answer", lang=lang, opening=comp["opening"].strip(), verses=cards,
                      closing=comp["closing"].strip(), meaning_label=MEANING_LABEL[lang], situations=sits, trace=trace)
