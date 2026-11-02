# Channel kit · Gita Sarathi Live

Everything here is ready to copy into YouTube Studio. The images are in `branding/` (redraw them with
`python branding.py`).

## Name and handle

| | |
|---|---|
| **Channel name** | **Gita Sarathi · गीता सारथी** |
| **Handle** | **@GitaSarathiLive** (backups: @GitaSarathi, @GitaSarathiTV, @GeetaSarathi) |
| Why | One brand across the app, your portfolio and the stream. "Sarathi" is Krishna's role for Arjuna, the charioteer who guides, which is exactly what the channel does. Bilingual, so people searching in Hindi or English both find it. "Live" in the handle tells people it is always on. |

Backup names if you prefer something more searchable: **Bhagavad Gita Live** · **Gita Live 24/7** · **गीता पाठ Live**.
Check the handle is free when you create it (YouTube Studio → Customization → Basic info).

**Make the chat trigger your handle.** Typing `@GitaSarathiLive` in chat is the most natural way to ask, and it
avoids pointing at someone else's `@gitalive` account. In `.env`:

```
CHAT_TRIGGERS=@GitaSarathiLive,@gitalive,!gita
```

The first one is shown on the stream ("चैट में लिखें @GitaSarathiLive + अपना सवाल"); all of them work.

## Images (`branding/`)

| File | Where it goes | Size |
|---|---|---|
| `avatar.png` | Profile picture (Customization → Branding) | 800×800 |
| `banner.png` | Banner image. All text sits inside the 1546×423 area every device shows | 2560×1440 |
| `thumbnail.png` | Live stream thumbnail (Go live → Edit → Thumbnail) | 1280×720 |
| `watermark.png` | Video watermark (Customization → Branding → Video watermark, "Entire video") | 150×150 |

**The logo:** a gold chariot wheel (Sarathi, the charioteer) whose hub is a peacock-feather eye (Krishna), on the
night-sky navy of the stream. It still reads at 48 px.

**Brand colours:** night navy `#0B0F2B` · gold `#F2B544` · saffron `#FF9933` · peacock teal `#5CC4CB` ·
live red `#E5202E`. **Fonts:** Tiro Devanagari Hindi (titles), Tiro Devanagari Sanskrit (shlokas), Mukta (text).

## Channel description (Customization → Basic info)

```
🕉️ गीता सारथी · Gita Sarathi — भगवद्गीता, 24 घंटे LIVE

यहाँ दिन-रात श्रीमद्भगवद्गीता के श्लोकों का पाठ चलता है: संस्कृत श्लोक, उसका अनुवाद, और किसने किससे कहा।
आपके मन में कोई सवाल है? गुस्सा, तनाव, परीक्षा की चिंता, रिश्ते, करियर, किसी अपने को खोने का दुख…
लाइव चैट में @GitaSarathiLive लिखकर अपना सवाल पूछिए। गीता सारथी गीता के असली श्लोकों से उत्तर देगा,
स्क्रीन पर दिखाकर और बोलकर।

🕉️ The Bhagavad Gita, live 24/7. Every verse in Sanskrit with its translation, recited around the clock.
Ask your life question in live chat (type @GitaSarathiLive + your question, in Hindi, Hinglish or English) and
Gita Sarathi answers on stream with the exact verses that speak to it: who said them, to whom, and what they mean
for you.

✅ Only real verses. The Sanskrit and the translation (Swami Swarupananda, 1909, public domain) are shown exactly.
🤖 The voice is an AI voice, and the explanations are AI-written and checked against the verses.
🙏 It is a guide to the text, not a guru, doctor or counsellor. If you are in distress, call Tele-MANAS 14416
(India, free, 24×7).

💬 Try it yourself, any time: https://parth-gita-assistant-1.onrender.com

#BhagavadGita #Gita #Geeta #श्रीमद्भगवद्गीता #Krishna #GitaSaar #Live
```

**Channel keywords** (Settings → Channel → Basic info):
`bhagavad gita, gita, geeta, shrimad bhagavad gita, गीता, भगवद्गीता, गीता पाठ, gita live, gita saar, krishna, arjuna, gita updesh, gita shlok, sanskrit shlok, gita in hindi, hindu scriptures, spiritual live, gita answers`

**Links** (Customization → Basic info → Links): "Ask Gita Sarathi" → https://parth-gita-assistant-1.onrender.com

## Live stream settings (Go live → Stream → Edit)

**Title** (under 100 characters; rotate every few weeks and keep whichever gets more clicks):

1. `🔴 भगवद्गीता LIVE 24/7 | अपना सवाल पूछिए, गीता से जवाब | Gita Sarathi`
2. `🔴 Bhagavad Gita LIVE 24/7 🕉️ श्लोक पाठ + Ask Your Life Question in Chat`
3. `🔴 गीता पाठ LIVE 24/7 | गुस्सा, तनाव, परीक्षा, रिश्ते — गीता क्या कहती है?`
4. `🔴 LIVE: Ask the Bhagavad Gita Anything 24/7 | Anger, Stress, Exams, Love | गीता सारथी`

**Description:**

```
🔴 श्रीमद्भगवद्गीता — 24 घंटे LIVE · Bhagavad Gita live 24/7

❓ सवाल कैसे पूछें · How to ask
चैट में लिखें: @GitaSarathiLive + अपना सवाल
Example: @GitaSarathiLive मुझे बहुत गुस्सा आता है, क्या करूँ?
Example: @GitaSarathiLive exam ke result ki chinta ho rahi hai
Example: @GitaSarathiLive how do I stop comparing myself with others?

📖 क्या होता है · What happens
• गीता का पाठ: हर श्लोक संस्कृत में, फिर अनुवाद · Every verse, in Sanskrit, then its translation
• आपका सवाल अगले श्लोक के बाद स्क्रीन पर आता है, और गीता सारथी असली श्लोकों से जवाब देता है
• Your question comes up after the current verse; the answer uses the exact verses, shown and spoken
• Super Chat questions go first · एक व्यक्ति, हर 5 मिनट में एक सवाल

🙏 नियम · Chat rules
सम्मान से बात करें। No hate, no politics, no caste talk. Links are removed.

✅ Only real verses: the Sanskrit and Swami Swarupananda's 1909 translation are shown exactly as written.
🤖 AI voice; explanations are AI-written and checked against the verses. A guide to the text, not a guru,
doctor or counsellor.
💛 In distress? Tele-MANAS 14416 (India, free, 24×7) · KIRAN 1800-599-0019

💬 Ask privately, by voice: https://parth-gita-assistant-1.onrender.com

#BhagavadGita #Gita #Geeta #गीता #Krishna #Live #GitaSaar
```

**Tags:**

```
bhagavad gita, bhagavad gita live, gita live, geeta live, shrimad bhagavad gita, गीता, भगवद्गीता, गीता पाठ, गीता सार, gita path, gita saar, gita shlok, gita updesh, krishna, krishna arjuna, krishna updesh, gita in hindi, bhagavad gita hindi, sanskrit shlok, gita for students, gita on anger, gita on stress, life questions, spiritual live, 24/7 live
```

**Other settings:**

| Setting | Value |
|---|---|
| Category | **Education** |
| Audience | **No, it's not made for kids.** "Made for kids" turns off live chat, and the questions are the whole point. |
| Visibility | Public (do the first test as **Unlisted**) |
| Live chat | On · **Slow mode 10 seconds** · Participant mode: Anyone |
| Auto-start / Auto-stop | **On / Off** |
| Latency | Normal |
| DVR | On |
| Language | **Hindi**, with an English title and description added as a translation (Subtitles → Add language) |
| Altered or synthetic content | Answer honestly if YouTube asks. The narrator is an AI voice that doesn't imitate a real person, and the description says so. |

## Pinned chat message (post it from the Live Control Room, then pin it)

```
🙏 स्वागत है! सवाल पूछने के लिए लिखें: @GitaSarathiLive + अपना सवाल (हिंदी/Hinglish/English) · Type @GitaSarathiLive + your question · सम्मान से बात करें 🙏
```

## Moderation (important for religious content)

Set this up before going public:

1. **YouTube Studio → Settings → Community → Automated filters:**
   - "Hold potentially inappropriate messages for review": **Strict**
   - **Block links: On**
   - **Blocked words:** party and leader names and political insults (for example *bjp, congress, aap, modi,
     rahul, sanghi, andhbhakt, librandu, jihadi*), plus any religious or caste slurs and abuse in Hindi, Hinglish and
     English that you see. Aim for 30–50 words and keep adding.
2. **Slow mode** 10 s stops spam floods and keeps the question queue fair.
3. Make 1–2 respectful regulars **moderators** once they appear (Settings → Community → Moderators). Moderators'
   questions also go first on the stream.
4. The stream already drops links, abuse, repeats and floods from the question queue, and anyone who sounds in
   danger gets helplines instead of teaching.
5. Channel rule (in the pinned message if needed): **"सम्मान से · No hate, no politics, no caste talk."**

## Growth plan

**Week 1**
- Go live **Unlisted** for an hour. Watch it on your phone (it should fill the screen vertically) and ask 3–4
  questions yourself in Hindi and English.
- Switch to **Public**. Post the pinned message.
- Post **3–5 Shorts** (see below).

**Shorts: the main way new people find you.** Post one a day. The stream makes them for you:
```
python run_live.py --out short.mp4 --seconds 75
```
While it records, open http://127.0.0.1:8770/preview and ask the question. The clip includes the verse, the
question and the spoken answer, already vertical. Trim it to the question and answer (YouTube Studio's editor,
or CapCut), and add a Hindi title. Use the verse number the answer actually shows, for example:
- `गुस्सा क्यों आता है? गीता का जवाब (2.62) #shorts #gita`
- `Exam result की चिंता? श्रीकृष्ण कहते हैं… (गीता 2.47) #shorts`
- `किसी अपने को खो दिया? गीता 2.20 क्या कहती है #shorts`
- `दूसरों से तुलना छोड़ो — गीता 3.35 #shorts`
- `Career confusion? Krishna's answer to Arjuna (Gita 2.31) #shorts`
- `डर लगता है? गीता का एक श्लोक #shorts`

Each Short's description ends with "पूरा LIVE: @GitaSarathiLive · 24/7 अपना सवाल पूछिए".

**Playlists:** गीता के उत्तर · Gita Answers (Shorts) · परीक्षा और करियर · गुस्सा और शांति · रिश्ते और दुख ·
अध्याय अनुसार · Chapter by chapter.

**Community posts and polls** (unlock as the channel grows):
- "आज किस बात पर मन भारी है? 1) परीक्षा 2) रिश्ते 3) काम 4) गुस्सा — LIVE में पूछिए 🙏"
- "आज का श्लोक: कर्मण्येवाधिकारस्ते… (2.47). आपके लिए इसका मतलब क्या है?"

**Special days** (ask me to add a themed recitation for each):
- **Gita Jayanti** (Margashirsha Shukla Ekadashi, in December): the whole of chapter 2 with a special banner.
- **Janmashtami** (August/September).
- **Board-exam season** (February–March): "परीक्षा की चिंता" Shorts and pinned message.
- Every Monday: "इस हफ़्ते का श्लोक" community post.

**Grow chat:** say hello to regulars by name when you can, and reply to the best questions in Shorts. Live chat
activity helps the stream get recommended.

## Monetization reality check
- **YouTube Partner Program** (check Studio → Earn for current rules): 1,000 subscribers + 4,000 public watch hours
  in 12 months, or 1,000 subscribers + 10 million Shorts views in 90 days. Fan funding (Super Chat, memberships)
  opens earlier, at about 500 subscribers.
- **"Inauthentic content":** YouTube can refuse monetization for mass-produced or repetitive content. A 24/7 automated
  recitation alone is at risk. What protects this channel:
  - every viewer's question gets its own answer, by name;
  - Shorts with your own titles and edits, and ideally sometimes your own voice or face;
  - a clear identity (name, logo, the app) and an About section that says it is your original project;
  - occasional live sessions where you take questions yourself (for example, a weekly "सत्संग Q&A").
- Live streams longer than about 12 hours may not be kept as a replay. That's normal for 24/7 channels.

## Respect and policy
- The stream never speaks as Krishna or any guru. Answers say what the Gita says, with the verse shown.
- No medical, legal or financial advice. Crisis messages get helplines (Tele-MANAS 14416, KIRAN 1800-599-0019).
- The translation is public domain (Swami Swarupananda, 1909). The voice and explanations are AI and disclosed.
- Background music, if you add any, must be music you have the rights to stream (for example the YouTube Audio
  Library).
