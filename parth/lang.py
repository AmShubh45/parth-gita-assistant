"""Which language to answer in: Hindi (Devanagari), Hinglish (Hindi in Roman letters) or English."""
from __future__ import annotations

import re

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
# Common Hindi words written in Roman letters. Two or more hits means the person is writing Hinglish.
_HINGLISH = {
    "hai", "hain", "ho", "hoon", "hu", "hun", "tha", "thi", "the", "mujhe", "mujhko", "mera", "meri", "mere", "main",
    "mai", "mein", "hum", "humko", "aap", "tum", "kya", "kyun", "kyon", "kaise", "kab", "kaha", "kahan", "nahi",
    "nahin", "mat", "bahut", "bohot", "bhi", "aur", "lekin", "par", "toh", "to", "se", "ko", "ka", "ki", "ke",
    "karu", "karun", "karoon", "karna", "karta", "karti", "raha", "rahi", "rahe", "gaya", "gayi", "gaye", "lagta",
    "lagti", "sab", "kuch", "koi", "apne", "apna", "zindagi", "jeevan", "dil", "man", "dimag", "pareshan", "batao",
    "bataiye", "chahiye", "chahta", "chahti", "ghar", "papa", "mummy", "bhai", "yaar", "accha", "theek",
    "kar", "karunga", "karungi", "lunga", "lungi", "dunga", "dungi", "jaunga", "jaungi", "hoga", "hogi", "sakta",
    "sakti", "pata", "kyunki", "phir", "abhi", "bas", "bilkul", "ab", "jeena", "marna", "khatam", "dukh", "gussa",
    "pyaar", "pyar", "akela", "akeli", "sambhalu", "samajh", "aata", "aati", "lagta", "hua", "hui", "gayi", "wala",
    "wali", "kaun", "kis", "kisi", "unka", "unki", "uska", "uski", "humesha", "hamesha", "kabhi", "zyada", "jyada",
}
_ENGLISH_ONLY = {"the", "to", "par", "man", "main"}  # also English words: never count these alone


def detect(text: str) -> str:
    """'hi', 'hinglish' or 'en'."""
    if not text:
        return "en"
    dev = len(_DEVANAGARI.findall(text))
    letters = len(re.findall(r"[A-Za-z]", text))
    if dev and dev >= letters * 0.5:
        return "hi"
    words = re.findall(r"[a-z]+", text.lower())
    hits = [w for w in words if w in _HINGLISH]
    strong = [w for w in hits if w not in _ENGLISH_ONLY]
    if len(strong) >= 2 or (words and len(strong) / len(words) > 0.25):
        return "hinglish"
    return "en"
