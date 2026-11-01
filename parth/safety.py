"""Safety triage that runs before anything else.

A person who may be in danger gets human help first: helplines, a short caring message, no verses
and no waiting on a model. This check is deterministic on purpose: it must work even when the AI is
down, and it errs towards caution."""
from __future__ import annotations

import re
from dataclasses import dataclass

_CRISIS = [
    # English
    r"\bsuicid", r"\bkill(ing)?\s+my\s?self\b", r"\bend\s+(it\s+all|my\s+life)\b", r"\bwant\s+to\s+die\b",
    r"\bwish\s+i\s+(was|were)\s+dead\b", r"\bdon'?t\s+want\s+to\s+(live|be\s+alive)\b", r"\bno\s+reason\s+to\s+live\b",
    r"\bself[\s-]?harm", r"\bcut(ting)?\s+my\s?self\b", r"\bhurt(ing)?\s+my\s?self\b", r"\btake\s+my\s+(own\s+)?life\b",
    r"\bbetter\s+off\s+dead\b",
    # Hindi
    r"आत्महत्या", r"ख़ुदकुशी", r"खुदकुशी", r"मरना\s+चाहत", r"जीना\s+नहीं\s+चाहत", r"जान\s+दे\s+(दूँ|दूं|दूंगा|दूँगा|दूंगी|दूँगी|दे)",
    r"ख़ुद\s+को\s+(ख़त्म|खत्म|मार)", r"खुद\s+को\s+(ख़त्म|खत्म|मार)", r"अपने\s+आप\s+को\s+(ख़त्म|खत्म|मार)", r"जीने\s+का\s+मन\s+नहीं",
    # Hinglish
    r"\bkhudkushi\b", r"\baatmahatya\b", r"\batmahatya\b", r"\bmarna\s+chaht", r"\bjeena\s+nahi\s+chaht",
    r"\bjaan\s+de\s+(du|dun|dunga|dungi|doon|dena)\b", r"\bkhud\s+ko\s+(khatam|khatm|maar)", r"\bjeene\s+ka\s+man\s+nahi\b",
    r"\bmar\s+jaana\s+chaht", r"\bmar\s+jana\s+chaht",
]
_HARM_OTHERS = [
    r"\bkill\s+(him|her|them|my\s+\w+)\b", r"\bhow\s+to\s+(hurt|kill|poison)\b", r"\bmurder\b",
    r"(उसे|उसको|उन्हें)\s+मार\s+(दूँ|दूं|डालूँ|डालूं|दूंगा|दूँगा)", r"\b(use|usko|unko)\s+maar\s+(du|dun|dunga|daalu|dalun)\b",
]
_CRISIS_RE = re.compile("|".join(_CRISIS), re.I)
_HARM_RE = re.compile("|".join(_HARM_OTHERS), re.I)

HELP = {
    "en": ("I'm really sorry you're going through this. You don't have to face it alone, and you deserve support "
           "right now from a person who can help.\n\n"
           "• India: Tele-MANAS 14416 or 1-800-891-4416 (free, 24×7) · KIRAN 1800-599-0019\n"
           "• Outside India: find a local line at findahelpline.com\n"
           "• If you are in immediate danger, call your local emergency number (112 in India).\n\n"
           "Please reach out to one of them, or to someone you trust, now. I'm here to talk too."),
    "hi": ("आप जिस दर्द से गुज़र रहे हैं, उसके लिए मुझे सच में बहुत अफ़सोस है। आप अकेले नहीं हैं, और इस समय आपको किसी ऐसे "
           "व्यक्ति से बात करनी चाहिए जो मदद कर सके।\n\n"
           "• भारत: टेली-मानस 14416 या 1-800-891-4416 (मुफ़्त, 24×7) · किरण 1800-599-0019\n"
           "• भारत के बाहर: findahelpline.com पर अपने देश की हेल्पलाइन देखें\n"
           "• अगर आप तुरंत ख़तरे में हैं, तो 112 पर कॉल करें।\n\n"
           "कृपया अभी इनमें से किसी से, या किसी ऐसे व्यक्ति से बात करें जिस पर आपको भरोसा है। मैं भी आपसे बात करने के लिए यहाँ हूँ।"),
    "hinglish": ("Aap jis dard se guzar rahe hain, uske liye mujhe sach mein bahut afsos hai. Aap akele nahi hain, aur is waqt "
                 "aapko kisi aise insaan se baat karni chahiye jo madad kar sake.\n\n"
                 "• India: Tele-MANAS 14416 ya 1-800-891-4416 (free, 24×7) · KIRAN 1800-599-0019\n"
                 "• India ke bahar: findahelpline.com par apne desh ki helpline dekhiye\n"
                 "• Agar aap turant khatre mein hain, to 112 par call kariye.\n\n"
                 "Please abhi inme se kisi se, ya kisi apne se baat kariye. Main bhi aapse baat karne ke liye yahan hoon."),
}
HARM = {
    "en": "I can't help with harming anyone. If you feel you might hurt someone, please step away and call 112 or Tele-MANAS 14416 to talk to someone now.",
    "hi": "मैं किसी को नुकसान पहुँचाने में मदद नहीं कर सकता। अगर आपको लगता है कि आप किसी को चोट पहुँचा सकते हैं, तो कृपया वहाँ से हट जाएँ और अभी 112 या टेली-मानस 14416 पर बात करें।",
    "hinglish": "Main kisi ko nuksan pahunchane mein madad nahi kar sakta. Agar aapko lagta hai ki aap kisi ko chot pahuncha sakte hain, to please wahan se hat jaiye aur abhi 112 ya Tele-MANAS 14416 par baat kariye.",
}


@dataclass
class Triage:
    kind: str  # "ok", "crisis", "harm_others"
    message: str | None = None


def triage(text: str, lang: str) -> Triage:
    if _CRISIS_RE.search(text or ""):
        return Triage("crisis", HELP.get(lang, HELP["en"]))
    if _HARM_RE.search(text or ""):
        return Triage("harm_others", HARM.get(lang, HARM["en"]))
    return Triage("ok")
