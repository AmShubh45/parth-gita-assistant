"""Keeping OBS on air, over its built-in WebSocket server (OBS 28+: Tools > WebSocket Server Settings).

Gita Sarathi Live uses its own OBS profile and scene collection, both named "GitaLive", so it never touches
other setups on the same laptop (such as another channel's scenes). Setup creates them if missing, adds the
overlay page as a 1920x1080 Browser Source with its audio routed through OBS, and sets the YouTube stream
key. The watchdog then keeps the stream running and starts OBS again if it closes."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import subprocess
import uuid
from pathlib import Path
from typing import Any

log = logging.getLogger("gitalive.obs")
PROFILE = COLLECTION = SCENE = "GitaLive"
SOURCE = "Gita Sarathi overlay"


class ObsError(Exception):
    pass


class ObsClient:
    """Tiny obs-websocket v5 client (the same handshake as the cricket commentary's clip saver)."""

    def __init__(self, url: str, password: str) -> None:
        self.url, self.password = url, password

    async def call(self, *requests: tuple[str, dict[str, Any]]) -> list[dict[str, Any]]:
        import websockets

        try:
            async with websockets.connect(self.url, open_timeout=4, close_timeout=1) as ws:
                hello = json.loads(await asyncio.wait_for(ws.recv(), 4))["d"]
                ident: dict[str, Any] = {"rpcVersion": 1, "eventSubscriptions": 0}
                auth = hello.get("authentication")
                if auth:
                    secret = base64.b64encode(hashlib.sha256((self.password + auth["salt"]).encode()).digest())
                    ident["authentication"] = base64.b64encode(
                        hashlib.sha256(secret + auth["challenge"].encode()).digest()).decode()
                await ws.send(json.dumps({"op": 1, "d": ident}))
                json.loads(await asyncio.wait_for(ws.recv(), 4))   # Identified (OBS closes on a bad password)
                out = []
                for kind, data in requests:
                    rid = uuid.uuid4().hex
                    await ws.send(json.dumps({"op": 6, "d": {"requestType": kind, "requestId": rid, "requestData": data}}))
                    while True:
                        msg = json.loads(await asyncio.wait_for(ws.recv(), 10))
                        if msg.get("op") == 7 and msg["d"].get("requestId") == rid:
                            out.append(msg["d"])
                            break
                return out
        except (OSError, asyncio.TimeoutError, KeyError, ValueError) as exc:
            raise ObsError(f"OBS not reachable at {self.url} ({type(exc).__name__})") from exc
        except Exception as exc:  # websockets raises its own closed/invalid-status errors (e.g. a bad password)
            raise ObsError(f"OBS refused the connection: {exc}") from exc

    async def one(self, kind: str, data: dict | None = None, ok_codes: tuple[int, ...] = ()) -> dict:
        res = (await self.call((kind, data or {})))[0]
        st = res.get("requestStatus", {})
        if not st.get("result") and st.get("code") not in ok_codes:
            raise ObsError(f"{kind}: {st.get('comment') or st.get('code')}")
        return res.get("responseData") or {}


class Obs:
    def __init__(self, client: ObsClient, overlay_url: str, stream_key: str, exe: str = ""):
        self.c, self.overlay_url, self.stream_key, self.exe = client, overlay_url, stream_key, exe
        self.want_live = False
        self.status = "not connected"
        self._proc: subprocess.Popen | None = None
        self._failures = 0

    def launch(self) -> bool:
        """Start OBS (minimised) if we know where it is."""
        if not self.exe or not Path(self.exe).exists():
            return False
        if self._proc and self._proc.poll() is None:
            return True
        args = [self.exe, "--minimize-to-tray", "--disable-shutdown-check", "--disable-updater",
                "--profile", PROFILE, "--collection", COLLECTION, "--scene", SCENE]
        log.info("starting OBS")
        self._proc = subprocess.Popen(args, cwd=str(Path(self.exe).parent))
        return True

    async def setup(self) -> None:
        """Make sure the GitaLive profile, scene collection, scene, overlay source and stream key exist."""
        c = self.c
        if (await c.one("GetStreamStatus")).get("outputActive"):
            return  # never reshuffle OBS while it is on air
        profiles = await c.one("GetProfileList")
        if PROFILE not in profiles.get("profiles", []):
            await c.one("CreateProfile", {"profileName": PROFILE})        # also switches to it
        elif profiles.get("currentProfileName") != PROFILE:
            await c.one("SetCurrentProfile", {"profileName": PROFILE})
        cols = await c.one("GetSceneCollectionList")
        if COLLECTION not in cols.get("sceneCollections", []):
            await c.one("CreateSceneCollection", {"sceneCollectionName": COLLECTION})
        elif cols.get("currentSceneCollectionName") != COLLECTION:
            await c.one("SetCurrentSceneCollection", {"sceneCollectionName": COLLECTION})
        await asyncio.sleep(1.5)   # OBS reloads after switching collections
        for kind, data in (   # best effort: 1080p30, simple output at a bitrate a mostly still page needs
                ("SetVideoSettings", {"baseWidth": 1920, "baseHeight": 1080, "outputWidth": 1920,
                                      "outputHeight": 1080, "fpsNumerator": 30, "fpsDenominator": 1}),
                ("SetProfileParameter", {"parameterCategory": "Output", "parameterName": "Mode", "parameterValue": "Simple"}),
                ("SetProfileParameter", {"parameterCategory": "SimpleOutput", "parameterName": "VBitrate", "parameterValue": "3000"}),
                ("SetProfileParameter", {"parameterCategory": "SimpleOutput", "parameterName": "ABitrate", "parameterValue": "160"})):
            try:
                await c.one(kind, data)
            except ObsError as exc:
                log.info("OBS setting skipped: %s", exc)
        scenes = [s["sceneName"] for s in (await c.one("GetSceneList")).get("scenes", [])]
        if SCENE not in scenes:
            await c.one("CreateScene", {"sceneName": SCENE})
        settings = {"url": self.overlay_url, "width": 1920, "height": 1080, "fps": 30, "reroute_audio": True,
                    "restart_when_active": False, "shutdown": False}
        inputs = [i["inputName"] for i in (await c.one("GetInputList")).get("inputs", [])]
        if SOURCE in inputs:
            await c.one("SetInputSettings", {"inputName": SOURCE, "inputSettings": settings, "overlay": True})
        else:
            await c.one("CreateInput", {"sceneName": SCENE, "inputName": SOURCE, "inputKind": "browser_source",
                                        "inputSettings": settings, "sceneItemEnabled": True})
        await c.one("SetCurrentProgramScene", {"sceneName": SCENE})
        if self.stream_key:
            await c.one("SetStreamServiceSettings", {"streamServiceType": "rtmp_custom", "streamServiceSettings": {
                "server": "rtmps://a.rtmps.youtube.com:443/live2", "key": self.stream_key, "use_auth": False}})
        log.info("OBS ready: profile, scene and overlay set up")

    async def start(self) -> None:
        self.want_live = True
        if not (await self.c.one("GetStreamStatus")).get("outputActive"):
            await self.c.one("StartStream", ok_codes=(500,))   # 500: already starting
            log.info("stream started")

    async def stop(self) -> None:
        self.want_live = False
        await self.c.one("StopStream", ok_codes=(501, 500))

    async def watchdog(self, sleep=asyncio.sleep, every: float = 30.0) -> None:
        """Keep OBS running and on air. Backs off when something keeps failing."""
        ready = False
        while True:
            try:
                st = await self.c.one("GetStreamStatus")
                if not ready:
                    await self.setup()
                    ready = True
                if self.want_live and not st.get("outputActive"):
                    log.warning("stream is down; starting it again")
                    await self.c.one("StartStream", ok_codes=(500,))
                self.status = ("on air · " + str(st.get("outputTimecode", ""))[:8]) if st.get("outputActive") else "connected, not streaming"
                self._failures = 0
            except ObsError as exc:
                self._failures += 1
                ready = False
                self.status = str(exc)
                if self._failures in (1, 4) or self._failures % 20 == 0:
                    log.warning("%s", exc)
                if self._failures in (2, 10) and self.launch():
                    await sleep(20)   # give OBS time to open
            await sleep(every if self._failures < 6 else min(300, every * self._failures / 3))
