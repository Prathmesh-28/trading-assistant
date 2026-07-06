"""FastAPI backend for the live dashboard.

    uvicorn server:app --reload --port 8000        # dev
    uvicorn server:app --host 0.0.0.0 --port 8000  # prod (Render sets $PORT)

Wraps the exact same RecommendEngine used by recommend_engine.py / Telegram —
this is a second front door onto the same state, not a parallel implementation.
Every mutation (buy/sell/skip/watch/pause/resume) goes through
engine.handle_command(), so the phone (Telegram) and the web dashboard always
agree, and every state change is broadcast to all connected browsers over the
websocket in real time.
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import Settings
from events import EventBus
from recommend_engine import RecommendEngine

log = logging.getLogger("server")

bus = EventBus()
settings = Settings()
engine = RecommendEngine(settings, event_bus=bus)
_engine_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine_task
    _engine_task = asyncio.create_task(engine.run())
    log.info("engine started")
    try:
        yield
    finally:
        _engine_task.cancel()
        try:
            await _engine_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 — shutdown must not hang
            pass


app = FastAPI(title="Trading Assistant API", lifespan=lifespan)

# CORS_ORIGINS="https://your-app.vercel.app,http://localhost:5173" in .env / Render env
_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ------------------------------------------------------------------ REST API

@app.get("/api/health")
async def health():
    return {"ok": True}


@app.get("/api/status")
async def status():
    return engine.snapshot()


@app.get("/api/history")
async def history(limit: int = 200):
    return {"rows": engine.journal.history(limit=limit)}


class QtyPrice(BaseModel):
    qty: Optional[int] = None
    price: Optional[float] = None


class SellBody(BaseModel):
    price: Optional[float] = None


class WatchBody(BaseModel):
    qty: int
    price: float
    stop: float
    target: Optional[float] = None


async def _run_command(cmd: str, args: list[str]) -> dict:
    reply = await engine.handle_command(cmd, args)
    return {"reply": reply, "status": engine.snapshot()}


@app.post("/api/ideas/{symbol}/buy")
async def buy_idea(symbol: str, body: QtyPrice = QtyPrice()):
    args = [symbol]
    if body.qty is not None:
        args.append(str(body.qty))
    if body.price is not None:
        args.append(str(body.price))
    return await _run_command("bought", args)


@app.post("/api/ideas/{symbol}/skip")
async def skip_idea(symbol: str):
    return await _run_command("skip", [symbol])


@app.post("/api/positions/{symbol}/sell")
async def sell_position(symbol: str, body: SellBody = SellBody()):
    args = [symbol] + ([str(body.price)] if body.price is not None else [])
    return await _run_command("sold", args)


@app.post("/api/positions/{symbol}/watch")
async def watch_position(symbol: str, body: WatchBody):
    args = [symbol, str(body.qty), str(body.price), str(body.stop)]
    if body.target is not None:
        args.append(str(body.target))
    return await _run_command("watch", args)


@app.post("/api/pause")
async def pause():
    return await _run_command("pause", [])


@app.post("/api/resume")
async def resume():
    return await _run_command("resume", [])


# ------------------------------------------------------------------ WebSocket

@app.websocket("/ws")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    queue = bus.subscribe()
    try:
        await websocket.send_json({"type": "snapshot", "data": engine.snapshot()})
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001 — a broken socket must not crash the server
        log.warning("ws client dropped: %s", e)
    finally:
        bus.unsubscribe(queue)


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)-10s %(levelname)-7s %(message)s")
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
