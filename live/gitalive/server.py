"""The local web server OBS reads from (127.0.0.1 only).

GET  /overlay       the 1920x1080 page OBS shows as a Browser Source
GET  /preview       the overlay in a normal browser, with a box to ask test questions
POST /preview/ask   {"name", "text"} -> treated like a chat message
WS   /ws            the conductor <-> overlay pages
GET  /audio/<file>  cached voices
GET  /music         optional background music (live/assets/music.mp3)
GET  /status        what is on air, chat, OBS, quota (JSON)
GET  /frame.jpg     cloud mode: the frame being streamed right now
"""
from __future__ import annotations

import re
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

STATIC = Path(__file__).resolve().parent / "static"


class PreviewAsk(BaseModel):
    name: str = Field(default="Preview viewer", max_length=40)
    text: str = Field(min_length=1, max_length=400)


def make_app(conductor, cache_dir: Path, music: Path, status_extra=lambda: {}, renderer=None) -> FastAPI:
    app = FastAPI(title="Gita Sarathi Live", docs_url=None, redoc_url=None)
    hub = conductor.hub
    trigger = conductor.mod.triggers[0] if conductor.mod.triggers else ""
    hub.config = {"type": "config", "music": music.exists(), "trigger": trigger or "@gitalive"}

    @app.get("/overlay")
    def overlay() -> FileResponse:
        return FileResponse(STATIC / "overlay.html", headers={"Cache-Control": "no-cache"})

    @app.get("/preview")
    def preview() -> FileResponse:
        return FileResponse(STATIC / "preview.html", headers={"Cache-Control": "no-cache"})

    @app.post("/preview/ask")
    async def preview_ask(body: PreviewAsk) -> dict:
        text = body.text if trigger in body.text.lower() else f"{trigger} {body.text}"
        ok = conductor.offer({"id": uuid.uuid4().hex, "author": body.name, "channel": f"preview-{body.name}",
                              "text": text, "staff": True})
        return {"queued": ok, "waiting": conductor.mod.waiting(), "rejected": conductor.mod.rejected}

    @app.websocket("/ws")
    async def ws(sock: WebSocket) -> None:
        await sock.accept()
        await hub.join(sock)
        try:
            while True:
                msg = await sock.receive_json()
                if msg.get("type") == "done" and isinstance(msg.get("id"), str):
                    hub.page_done(msg["id"])
        except (WebSocketDisconnect, RuntimeError, ValueError):
            pass
        finally:
            hub.clients.discard(sock)

    @app.get("/audio/{name}")
    def audio(name: str) -> FileResponse:
        if not re.fullmatch(r"[0-9a-f]{24}\.wav", name) or not (cache_dir / name).exists():
            raise HTTPException(404)
        return FileResponse(cache_dir / name, media_type="audio/wav", headers={"Cache-Control": "max-age=31536000"})

    @app.get("/music")
    def music_file():
        if not music.exists():
            raise HTTPException(404)
        return FileResponse(music)

    @app.get("/frame.jpg")
    async def frame() -> Response:
        if renderer is None:
            raise HTTPException(404)
        import asyncio
        data = await asyncio.to_thread(renderer.jpeg, 78, time.monotonic())
        return Response(data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/status")
    def status() -> JSONResponse:
        return JSONResponse({**conductor.snapshot(), **status_extra(), "rendered": renderer is not None,
                             "time": time.strftime("%Y-%m-%d %H:%M:%S")})

    return app
