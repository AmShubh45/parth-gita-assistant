"""Gita Sarathi Live (live/): chat moderation, YouTube quota, the on-air conductor, OBS control, and the
server endpoints the stream uses. YouTube, OBS and the Gita Sarathi server are all faked."""
import asyncio
import base64
import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "live"))

from gitalive.audio import AudioCache, wav_seconds  # noqa: E402
from gitalive.conductor import Conductor, Hub  # noqa: E402
from gitalive.moderation import Moderator  # noqa: E402
from gitalive.obs import Obs, ObsClient, ObsError  # noqa: E402
from gitalive.youtube import PACIFIC, ChatReader, QuotaGovernor, parse  # noqa: E402


def run(coro):
    return asyncio.run(coro)


def tiny_wav(seconds=0.05, rate=24000):
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1), w.setsampwidth(2), w.setframerate(rate), w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


# ---------------------------------------------------------------- moderation
class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_only_triggered_messages_become_questions():
    m = Moderator(clock=Clock())
    assert m.offer("1", "Asha", "c1", "hello everyone") is None
    q = m.offer("2", "Asha", "c1", "@GitaLive mujhe gussa bahut aata hai, kya karu?")
    assert q and q.text == "mujhe gussa bahut aata hai, kya karu?" and q.author == "Asha"
    assert m.offer("3", "Ravi", "c2", "!gita मैं परीक्षा से डरता हूँ").text == "मैं परीक्षा से डरता हूँ"


@pytest.mark.parametrize("text,why", [
    ("@gitalive hi", "length"),
    ("@gitalive check www.spam.com for answers", "link"),
    ("@gitalive what is this shit", "abuse"),
    ("@gitalive तुम चूतिया हो", "abuse"),
    ("@gitalive ???? !!!!", "no_words"),
])
def test_bad_messages_are_dropped_quietly(text, why):
    m = Moderator(clock=Clock())
    assert m.offer("1", "X", "c1", text) is None and m.rejected == {why: 1} and not m.queue


def test_cooldown_repeats_priority_and_hourly_cap():
    clock = Clock()
    m = Moderator(per_author_s=300, per_hour=2, clock=clock)
    assert m.offer("1", "Asha", "c1", "@gitalive how do I stop overthinking?")
    assert m.offer("2", "Asha", "c1", "@gitalive and how do I sleep better?") is None       # one at a time
    assert m.offer("3", "Ravi", "c2", "@gitalive how do I stop overthinking?") is None       # repeat
    assert m.offer("4", "Mod", "c3", "@gitalive what does Krishna say about duty?", staff=True)
    sc = m.offer("5", "Fan", "c4", "@gitalive I lost my job, please guide me", superchat=True)
    assert [q.author for q in m.queue] == ["Fan", "Mod", "Asha"] and sc.priority == 2
    assert m.next().author == "Fan" and m.next().author == "Mod"
    assert m.next() is None                                                                  # 2 per hour
    clock.t += 3601
    assert m.next().author == "Asha"
    assert m.offer("6", "Asha", "c1", "@gitalive and how do I sleep better?")                # cooldown over
    assert m.rejected == {"cooldown": 1, "repeat": 1}


# ---------------------------------------------------------------- YouTube quota and chat
def test_quota_spreads_the_day_and_speeds_up_when_people_ask():
    now = [dt.datetime(2026, 11, 2, 0, 0, tzinfo=PACIFIC)]
    gov = QuotaGovernor(9000, now=lambda: now[0])
    assert 45 <= gov.interval(5, mono=lambda: 1e9) <= 50          # 86400 s * 5 units / 9000 units
    gov.last_question = 1e9 - 30
    assert 20 <= gov.interval(5, mono=lambda: 1e9) <= 25          # someone just asked: read twice as often
    gov.spend(8998)
    assert gov.interval(5, mono=lambda: 1e9) > 80000              # out of units: wait for the reset
    now[0] += dt.timedelta(days=1)
    assert gov.left() == 9000                                      # new Pacific day


def test_chat_messages_are_parsed():
    text = {"id": "a", "snippet": {"type": "textMessageEvent", "textMessageDetails": {"messageText": "@gitalive hi there"}},
            "authorDetails": {"displayName": "Asha", "channelId": "UC1", "isChatModerator": True}}
    sc = {"id": "b", "snippet": {"type": "superChatEvent", "superChatDetails": {"userComment": "@gitalive help"}},
          "authorDetails": {"displayName": "Fan", "channelId": "UC2"}}
    assert parse(text) == {"id": "a", "author": "Asha", "channel": "UC1", "text": "@gitalive hi there", "superchat": False, "staff": True}
    assert parse(sc)["superchat"] is True
    assert parse({"snippet": {"type": "memberMilestoneChatEvent"}}) is None


def test_chat_reader_finds_the_chat_skips_history_and_refreshes_sign_in(tmp_path):
    token = tmp_path / "token.json"
    token.write_text(json.dumps({"refresh_token": "r", "client_id": "id", "client_secret": "s",
                                 "token_uri": "https://oauth2.googleapis.com/token"}))
    calls, pages = [], iter([
        {"nextPageToken": "p1", "pollingIntervalMillis": 3000, "items": [
            {"id": "old", "snippet": {"type": "textMessageEvent", "displayMessage": "@gitalive old question"},
             "authorDetails": {"displayName": "Old", "channelId": "U0"}}]},
        {"nextPageToken": "p2", "pollingIntervalMillis": 3000, "items": [
            {"id": "new", "snippet": {"type": "textMessageEvent", "displayMessage": "@gitalive new question"},
             "authorDetails": {"displayName": "New", "channelId": "U1"}}]}])

    def handler(req):
        calls.append(req.url.path)
        if req.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "A", "expires_in": 3600})
        assert req.headers["authorization"] == "Bearer A"
        if req.url.path.endswith("/liveBroadcasts"):
            return httpx.Response(200, json={"items": [{"snippet": {"liveChatId": "CHAT1"}}]})
        assert req.url.params["liveChatId"] == "CHAT1"
        return httpx.Response(200, json=next(pages))

    seen = []
    gov = QuotaGovernor(9000)
    reader = ChatReader(token, gov, lambda m: seen.append(m) or True, transport=httpx.MockTransport(handler))

    async def go():
        reader.chat_id = await reader.find_chat()
        await reader.read_once()
        await reader.read_once()
        await reader.http.aclose()
    run(go())
    assert reader.chat_id == "CHAT1" and [m["author"] for m in seen] == ["New"]       # history skipped
    assert gov.used == 1 + 5 + 5 and json.loads(token.read_text())["token"] == "A"
    assert calls[0] == "/token"


# ---------------------------------------------------------------- the Gita Sarathi server, faked
class FakeSarathi:
    def __init__(self, verses=3, voice=True):
        self.spoken, self.asked = [], []
        self.voice = voice
        self.verses = [{"id": f"BG 1.{i}", "ref": f"1.{i}", "chapter": 1, "verse": i, "chapter_name": "Arjuna Visada Yoga",
                        "chapter_name_sanskrit": "अर्जुनविषादयोग", "speaker": "Krishna", "addressed_to": "Arjuna",
                        "sanskrit": "श्लोक", "transliteration": "shloka", "translation": f"translation {i}",
                        "translation_source": "Swami Swarupananda (1909)",
                        "speech": [{"text": f"verse {i}", "lang": "en", "sig": "s"}]} for i in range(1, verses + 1)]

    async def recitation(self, cache_file=None):
        return self.verses

    async def speak(self, item, lang):
        self.spoken.append(item["text"])
        await asyncio.sleep(0.01)
        return tiny_wav() if self.voice else None

    async def ask(self, q):
        self.asked.append(q)
        return {"kind": "answer", "lang": "hi", "opening": "गुस्सा स्वाभाविक है।", "closing": "धीरे चलिए।",
                "verses": [{"id": "BG 2.62", "chapter": 2, "speaker": "Krishna", "addressed_to": "Arjuna", "sanskrit": "ध्यायतो",
                            "meaning": "अर्थ", "application": "आपके लिए"}],
                "speech": [{"text": "गुस्सा स्वाभाविक है।", "sig": "a"}, {"text": "धीरे चलिए।", "sig": "b"}]}


def test_voices_are_fetched_once_and_new_recordings_are_rationed(tmp_path):
    sar = FakeSarathi()
    cache = AudioCache(tmp_path, sar, recite_per_day=1)
    item = {"text": "verse 1", "sig": "s"}

    async def go():
        a, b = await asyncio.gather(cache.get(item, "en", recitation=True), cache.get(item, "en", recitation=True))
        assert a == b and a[0].startswith("/audio/") and 0.04 < a[1] < 0.06
        assert await cache.get({"text": "verse 2", "sig": "s"}, "en", recitation=True) is None   # today's allowance spent
        assert await cache.get({"text": "an answer", "sig": "s"}, "hi")                          # answers are not rationed
    run(go())
    assert sar.spoken == ["verse 1", "an answer"] and cache.cached(item, "en")
    assert wav_seconds(tiny_wav(1.0)) == pytest.approx(1.0)


class FakeWS:
    def __init__(self, hub, autodone=True):
        self.hub, self.autodone, self.sent = hub, autodone, []

    async def send_json(self, msg):
        self.sent.append(msg)
        if self.autodone and msg.get("type") in ("verse", "answer"):
            asyncio.get_running_loop().call_soon(self.hub.page_done, msg["id"])


def make_conductor(tmp_path, sar, allowance=10):
    hub = Hub()
    c = Conductor(sar, AudioCache(tmp_path / "cache", sar, allowance), hub, Moderator(clock=Clock()),
                  tmp_path / "state.json", tmp_path / "verses.json", silent_seconds=0.01)
    return c, hub


def test_recites_in_order_and_answers_questions_between_verses(tmp_path):
    sar = FakeSarathi()
    c, hub = make_conductor(tmp_path, sar)
    page = FakeWS(hub)
    hub.clients.add(page)

    async def go():
        await c.load()
        await c.recite(c.pick())
        assert c.offer({"id": "m1", "author": "Asha", "channel": "U1", "text": "@gitalive मुझे बहुत गुस्सा आता है"})
        await asyncio.sleep(0)
        await c.answer(c.mod.next())
        await c.recite(c.pick())
    run(go())
    kinds = [m["type"] for m in page.sent]
    assert kinds == ["verse", "queue", "queue", "asking", "answer", "queue", "verse"]
    verse, answer = page.sent[0], page.sent[4]
    assert c.recent == ["Asha"]
    assert verse["verse"]["id"] == "BG 1.1" and verse["audio"] and verse["progress"] == {"index": 1, "total": 3}
    assert answer["name"] == "Asha" and answer["answer"]["verses"][0]["id"] == "BG 2.62" and len(answer["audio"]) == 2
    assert page.sent[6]["verse"]["id"] == "BG 1.2" and json.loads((tmp_path / "state.json").read_text()) == {"pos": 2}
    assert sar.asked == ["मुझे बहुत गुस्सा आता है"]


def test_verses_without_a_voice_are_skipped_while_others_have_one(tmp_path):
    sar = FakeSarathi(verses=4)
    c, hub = make_conductor(tmp_path, sar, allowance=0)

    async def go():
        await c.load()
        cache = c.audio
        (cache.folder / cache.path(sar.verses[2]["speech"][0], "en").name).write_bytes(tiny_wav())   # only BG 1.3 recorded
        assert c.pick() == 2 and c.pick() == 2                     # the recorded verse loops until more are recorded
        (cache.folder / cache.path(sar.verses[3]["speech"][0], "en").name).write_bytes(tiny_wav())
        assert c.pick() == 3 and c.pick() == 2
        for v in sar.verses:
            cache.path(v["speech"][0], "en").unlink(missing_ok=True)
        assert c.pick() == 3                                       # nothing recorded: silent, in order
    run(go())


def test_without_a_page_the_conductor_keeps_time_and_survives_no_voice(tmp_path):
    sar = FakeSarathi(voice=False)
    c, hub = make_conductor(tmp_path, sar)

    async def go():
        await c.load()
        await asyncio.wait_for(c.recite(c.pick()), 5)
    run(go())
    assert hub.current["audio"] == [] and hub.current["seconds"] == 0.01


# ---------------------------------------------------------------- OBS
class FakeObs:
    """obs-websocket v5 with a password, recording requests."""

    def __init__(self, password="pw", profiles=("Untitled",), streaming=False):
        self.password, self.requests = password, []
        self.state = {"profiles": list(profiles), "collections": ["Untitled"], "scenes": ["Scene"], "inputs": [],
                      "streaming": streaming}

    async def handler(self, ws):
        salt, challenge = "salt1", "chal1"
        await ws.send(json.dumps({"op": 0, "d": {"rpcVersion": 1, "authentication": {"salt": salt, "challenge": challenge}}}))
        ident = json.loads(await ws.recv())["d"]
        secret = base64.b64encode(hashlib.sha256((self.password + salt).encode()).digest())
        if ident.get("authentication") != base64.b64encode(hashlib.sha256(secret + challenge.encode()).digest()).decode():
            await ws.close(4009, "Authentication failed")
            return
        await ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        async for raw in ws:
            d = json.loads(raw)["d"]
            kind, data = d["requestType"], d.get("requestData") or {}
            self.requests.append((kind, data))
            s, resp = self.state, {}
            if kind == "GetStreamStatus":
                resp = {"outputActive": s["streaming"], "outputTimecode": "01:00:00.000"}
            elif kind == "GetProfileList":
                resp = {"profiles": s["profiles"], "currentProfileName": s["profiles"][0]}
            elif kind == "CreateProfile":
                s["profiles"].insert(0, data["profileName"])
            elif kind == "GetSceneCollectionList":
                resp = {"sceneCollections": s["collections"], "currentSceneCollectionName": s["collections"][0]}
            elif kind == "CreateSceneCollection":
                s["collections"].insert(0, data["sceneCollectionName"])
            elif kind == "GetSceneList":
                resp = {"scenes": [{"sceneName": n} for n in s["scenes"]]}
            elif kind == "CreateScene":
                s["scenes"].append(data["sceneName"])
            elif kind == "GetInputList":
                resp = {"inputs": [{"inputName": n} for n in s["inputs"]]}
            elif kind == "CreateInput":
                s["inputs"].append(data["inputName"])
            elif kind == "StartStream":
                s["streaming"] = True
            elif kind == "GetVersion":
                resp = {"obsVersion": "31.0.0"}
            await ws.send(json.dumps({"op": 7, "d": {"requestType": kind, "requestId": d["requestId"],
                                                    "requestStatus": {"result": True, "code": 100}, "responseData": resp}}))


def with_obs(fake, fn):
    import websockets

    async def go():
        async with websockets.serve(fake.handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            return await fn(f"ws://127.0.0.1:{port}")
    return run(go())


def test_obs_setup_creates_its_own_profile_scene_and_overlay_then_goes_live():
    fake = FakeObs()

    async def fn(url):
        obs = Obs(ObsClient(url, "pw"), "http://127.0.0.1:8770/overlay", "abcd-key")
        await obs.setup()
        await obs.start()
    with_obs(fake, fn)
    kinds = [k for k, _ in fake.requests]
    assert {"CreateProfile", "CreateSceneCollection", "CreateScene", "CreateInput", "SetCurrentProgramScene",
            "SetStreamServiceSettings", "StartStream"} <= set(kinds)
    create = dict(fake.requests)["CreateInput"]
    assert create["inputKind"] == "browser_source" and create["inputSettings"]["url"].endswith("/overlay")
    assert create["inputSettings"]["reroute_audio"] is True and create["sceneName"] == "GitaLive"
    stream = dict(fake.requests)["SetStreamServiceSettings"]["streamServiceSettings"]
    assert stream["key"] == "abcd-key" and stream["server"].startswith("rtmps://")


def test_obs_is_never_reconfigured_while_on_air_and_bad_passwords_are_reported():
    fake = FakeObs(streaming=True)

    async def fn(url):
        await Obs(ObsClient(url, "pw"), "http://x/overlay", "k").setup()
        with pytest.raises(ObsError):
            await ObsClient(url, "wrong").one("GetVersion")
    with_obs(fake, fn)
    assert [k for k, _ in fake.requests] == ["GetStreamStatus"]


# ---------------------------------------------------------------- the server endpoints the stream uses
def test_recitation_endpoint_lists_every_verse_with_a_signed_piece(monkeypatch):
    from fastapi.testclient import TestClient
    from parth import app as appmod, speech
    j = TestClient(appmod.app).get("/api/recite").json()
    assert j["count"] == 701 and j["verses"][0]["id"] == "BG 1.1" and j["verses"][-1]["id"] == "BG 18.78"
    v = next(x for x in j["verses"] if x["id"] == "BG 2.47")
    piece = v["speech"][0]
    assert piece["text"].startswith("Chapter 2, verse 47.") and "कर्मण्येवाधिकारस्ते" in piece["text"]
    assert "Krishna says: Thy right is to work only" in piece["text"]
    assert piece["sig"] == speech.sign(appmod._sign_key(), "en", piece["text"])
    unverified = next(x for x in j["verses"] if not x["translation"])
    assert "says:" not in unverified["speech"][0]["text"]                  # no translation is read before it is verified


def test_the_stream_has_its_own_budgets(monkeypatch):
    from fastapi.testclient import TestClient
    from parth import app as appmod
    monkeypatch.setattr(appmod, "LIVE_TOKEN", "secret-live")
    monkeypatch.setattr(appmod, "live_budget", appmod.DailyBudget(5))
    monkeypatch.setattr(appmod, "budget", appmod.DailyBudget(5))
    monkeypatch.setattr(appmod.engine, "llm", object())   # pretend a model is configured; its calls fall back

    async def no_model(*a, **k):
        from parth.engine import Answer
        return Answer(kind="no_match", lang="en", opening="x")
    monkeypatch.setattr(appmod.engine, "answer", no_model)
    client = TestClient(appmod.app)
    client.post("/api/ask", json={"question": "I feel lost at work"}, headers={"X-Live-Token": "secret-live"})
    assert appmod.live_budget.used == 1 and appmod.budget.used == 0
    client.post("/api/ask", json={"question": "I feel lost at home"}, headers={"X-Live-Token": "wrong"})
    assert appmod.live_budget.used == 1 and appmod.budget.used == 1
    assert client.get("/healthz").json()["live_stream"]["enabled"] is True


def test_local_live_server_preview_and_audio(tmp_path):
    from fastapi.testclient import TestClient
    from gitalive.server import make_app
    sar = FakeSarathi()
    c, hub = make_conductor(tmp_path, sar)
    (tmp_path / "cache").mkdir(exist_ok=True)
    (tmp_path / "cache" / ("a" * 24 + ".wav")).write_bytes(tiny_wav())
    client = TestClient(make_app(c, tmp_path / "cache", tmp_path / "none.mp3"))
    assert "GITA SARATHI" in client.get("/overlay").text and "preview" in client.get("/preview").text.lower()
    r = client.post("/preview/ask", json={"name": "Tester", "text": "मन शांत कैसे करूँ?"}).json()
    assert r["queued"] and r["waiting"] == ["Tester"]
    assert client.get("/audio/" + "a" * 24 + ".wav").status_code == 200
    assert client.get("/audio/..%2F..%2Fsecret.wav").status_code == 404
    assert client.get("/music").status_code == 404
    assert client.get("/status").json()["waiting"] == ["Tester"]


# ---------------------------------------------------------------- the vertical cloud stream (the EscapeArenaLive way)
LIVE = Path(__file__).resolve().parents[1] / "live"


@pytest.fixture(scope="module")
def fonts():
    from gitalive.fonts import ensure
    from gitalive.render import Fonts
    try:
        return Fonts(ensure(LIVE / "fonts", log=lambda m: None))
    except Exception as exc:  # no network to fetch them
        pytest.skip(f"fonts unavailable: {exc}")


VERSE = {"type": "verse", "id": "v1", "progress": {"index": 84, "total": 701},
         "verse": {"id": "BG 2.47", "chapter": 2, "verse": 47, "chapter_name": "Sankhya Yoga", "chapter_name_sanskrit": "सांख्ययोग",
                   "speaker": "Krishna", "addressed_to": "Arjuna", "speaker_hindi": "श्रीकृष्ण", "listener_hindi": "अर्जुन",
                   "sanskrit": "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन।\nमा कर्मफलहेतुर्भूर्मा ते सङ्गोऽस्त्वकर्मणि।।",
                   "transliteration": "karmaṇy-evādhikāras te mā phaleṣhu kadāchana", "translation": "Thy right is to work only.",
                   "translation_source": "Swami Swarupananda (1909)"}}


def test_vertical_frames_are_drawn_with_shaped_devanagari(fonts):
    from PIL import ImageFont
    from gitalive.render import H, W, Renderer
    r = Renderer(fonts)
    idle = r.frame(0.0)
    assert len(idle) == W * H * 3 == 1080 * 1920 * 3
    assert len(r.frame(0.0, scale=0.6667)) == 720 * 1280 * 3
    r.build_scene(VERSE)
    assert r.frame(0.0) != idle and r.progress == (84, 701, 2) and r.last_fit == 1.0
    shaped = fonts("sanskrit", 60).getlength("कर्मण्येवाधिकारस्ते")
    basic = ImageFont.truetype(str(fonts.paths["sanskrit"]), 60, layout_engine=ImageFont.Layout.BASIC).getlength("कर्मण्येवाधिकारस्ते")
    assert shaped != basic                                   # conjuncts and matras are shaped (raqm/HarfBuzz)


def test_text_wraps_inside_its_box_and_long_answers_shrink(fonts):
    from gitalive.render import Renderer, wrap
    f = fonts("ui", 32)
    text = "गुस्सा आना स्वाभाविक है, पर गीता इसकी जड़ दिखाती है। " * 6
    assert all(f.getlength(line) <= 600 for line in wrap(text, f, 600)) and len(wrap(text, f, 600)) > 3
    r = Renderer(fonts)
    long = "विषयों के चिंतन से आसक्ति और आसक्ति से कामना पैदा होती है, और कामना से क्रोध। " * 4
    card = {"id": "BG 2.62", "chapter": 2, "speaker": "Krishna", "addressed_to": "Arjuna", "sanskrit": VERSE["verse"]["sanskrit"],
            "meaning": long, "application": long}
    r.build_scene({"type": "answer", "id": "q1", "name": "Asha", "question": "मुझे बहुत गुस्सा आता है " * 8,
                   "answer": {"kind": "answer", "lang": "hi", "opening": long, "closing": long, "verses": [card, card]}})
    assert r.last_fit < 1.0                                  # shrunk to fit the stage
    r.set_queue(["Asha", "Ravi"], ["Meera"])
    assert r.waiting == ["Asha", "Ravi"] and r.answered == ["Meera"]


def test_mixer_plays_voice_over_music_and_reports_the_end():
    import array
    from gitalive.broadcast import Mixer
    music = array.array("h", [1000] * 24000)
    m = Mixer(music=music, music_volume=0.12)
    quiet = array.array("h", m.render(800))
    assert len(quiet) == 800 and 100 <= max(quiet) <= 130          # music alone, at 12 %
    ended = []
    m.play([array.array("h", [8000] * 1200), array.array("h", [8000] * 1200)], lambda: ended.append(1))
    first = array.array("h", m.render(800))
    assert min(first) > 7000 and m.level > 0.2 and not ended       # the voice, with the music under it
    m.render(800)
    assert not ended
    m.render(800)
    assert ended == [1] and not m.busy                              # both clips done
    for _ in range(40):
        m.render(800)
    assert max(array.array("h", m.render(800))) < 140               # music back up once the voice ends
    replaced = []
    m.play([array.array("h", [1] * 50000)], lambda: replaced.append("old"))
    m.play([array.array("h", [1] * 10)], lambda: replaced.append("new"))
    assert replaced == ["old"]                                      # cutting an item short releases its waiter


def test_local_player_plays_through_the_mixer(tmp_path):
    import threading
    import time
    from gitalive.broadcast import LocalPlayer, Mixer
    (tmp_path / ("b" * 24 + ".wav")).write_bytes(tiny_wav(0.3))

    class FakeRenderer:
        def __init__(self):
            self.scenes, self.queues = [], []

        def build_scene(self, item):
            self.scenes.append(item["type"])

        def set_queue(self, waiting, answered=None):
            self.queues.append((waiting, answered))

    fr, mixer = FakeRenderer(), Mixer()
    stop = threading.Event()

    def pump():                       # stands in for the streaming loop: 24 kHz in real time
        while not stop.is_set():
            mixer.render(2400)
            time.sleep(0.1)
    threading.Thread(target=pump, daemon=True).start()
    hub = Hub(LocalPlayer(fr, mixer, tmp_path))

    async def go():
        t0 = time.monotonic()
        await hub.show({"type": "verse", "id": "v1", "audio": ["/audio/" + "b" * 24 + ".wav"]}, 0.3)
        voiced = time.monotonic() - t0
        await hub.announce({"type": "asking", "id": "q1", "name": "Asha", "question": "?"})
        await hub.queue(["Ravi"], ["Asha"])
        t0 = time.monotonic()
        await hub.show({"type": "verse", "id": "v2", "audio": []}, 0.2)
        return voiced, time.monotonic() - t0
    voiced, silent = run(go())
    stop.set()
    assert 0.3 <= voiced < 3 and 0.2 <= silent < 1
    assert fr.scenes == ["verse", "asking", "verse"] and fr.queues == [(["Ravi"], ["Asha"])]


def test_cloud_settings_like_escape_arena(monkeypatch, tmp_path):
    from gitalive.config import Config
    env = tmp_path / ".env"
    env.write_text("YOUTUBE_STREAM_KEY=abcd-efgh\nDATA_DIR=data\nSCALE=0.6667\n")
    for k in ("STREAM_MODE", "YT_STREAM_KEY", "DATA_DIR", "SCALE", "YOUTUBE_STREAM_KEY"):
        monkeypatch.delenv(k, raising=False)
    c = Config.load(env)
    assert c.stream_mode == "cloud" and c.yt_stream_key == "abcd-efgh" and c.scale == "0.6667"
    assert c.data_dir.name == "data" and c.cache_dir == c.data_dir / "cache" and c.token_file == c.data_dir / "token.json"
    assert c.rtmp_url.startswith("rtmps://") and c.fps == 30
    assert not any("OBS" in p for p in c.problems(need_youtube=False))   # cloud mode needs no OBS


def test_encoder_settings_match_escape_arena():
    from gitalive.broadcast import Streamer, auto_scale, ffmpeg_args
    a = ffmpeg_args(1080, 1920, 30, 4500, "veryfast", "rtmps://a.rtmps.youtube.com/live2/KEY", audio_port=5555)
    j = " ".join(a)
    assert "-s 1080x1920" in j and "-g 60" in j and "-keyint_min 60" in j and "-c:v libx264" in j and "-preset veryfast" in j
    assert "-b:v 4500k" in j and "-c:a aac" in j and a[-2:] == ["flv", "rtmps://a.rtmps.youtube.com/live2/KEY"]
    assert "-probesize 32" in j and "tcp://127.0.0.1:5555" in j
    assert ffmpeg_args(720, 1280, 30, 3000, "veryfast", "out.mp4")[-1] == "out.mp4"
    s = Streamer(object(), object(), target="rtmps://a.rtmps.youtube.com/live2", key="SECRET-KEY", scale=0.6667)
    assert s.target.endswith("/live2/SECRET-KEY") and (s.width, s.height, s.bitrate) == (720, 1280, 3000)
    assert s.redact("error at rtmps://x/live2/SECRET-KEY") == "error at rtmps://x/live2/****"
    assert auto_scale("1") == 1.0 and auto_scale("auto") in (1.0, 0.6667)


@pytest.mark.skipif(not __import__("shutil").which("ffmpeg"), reason="ffmpeg not installed")
def test_streamer_records_a_vertical_clip(fonts, tmp_path):
    import array
    import subprocess
    from gitalive.broadcast import Mixer, Streamer
    from gitalive.render import Renderer
    r, m = Renderer(fonts), Mixer()
    r.build_scene(VERSE)
    m.play([array.array("h", [3000, -3000] * 12000)], lambda: None)
    out = tmp_path / "clip.mp4"
    s = Streamer(r, m, target=str(out), fps=30, scale=0.6667, seconds=2)
    s.run()
    assert s.error is None and s.frames == 60
    info = json.loads(subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(out)],
                                     capture_output=True, text=True).stdout)
    v = next(x for x in info["streams"] if x["codec_type"] == "video")
    assert (v["width"], v["height"], v["r_frame_rate"]) == (720, 1280, "30/1")
    assert any(x["codec_type"] == "audio" and x["codec_name"] == "aac" for x in info["streams"])


def test_the_trigger_shown_on_screen_keeps_its_case(monkeypatch, tmp_path):
    from gitalive.config import Config
    env = tmp_path / ".env"
    env.write_text("CHAT_TRIGGERS=@GitaSarathiLive,@gitalive,!gita\n")
    monkeypatch.delenv("CHAT_TRIGGERS", raising=False)
    c = Config.load(env)
    assert c.triggers[0] == "@GitaSarathiLive"
    m = Moderator(c.triggers, clock=Clock())
    assert m.labels[0] == "@GitaSarathiLive"
    assert m.offer("1", "Asha", "c1", "@gitasarathilive मन शांत कैसे करूँ?").text == "मन शांत कैसे करूँ?"   # any case matches
    assert m.offer("2", "Ravi", "c2", "@GITALIVE how to handle exam stress?").text == "how to handle exam stress?"


def test_channel_images_have_youtube_sizes(fonts, tmp_path, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("branding", LIVE / "branding.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    assert b.avatar(fonts).size == (800, 800)
    assert b.banner(fonts).size == (2560, 1440)
    assert b.thumbnail(fonts).size == (1280, 720)
    wm = b.watermark()
    assert wm.size == (150, 150) and wm.mode == "RGBA" and wm.getpixel((0, 0))[3] == 0     # transparent corners
