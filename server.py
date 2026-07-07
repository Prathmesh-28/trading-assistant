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
import hashlib
import hmac
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backtest import backtest_intraday, backtest_positional
from config import IST, Settings
from events import EventBus
from indicators import SessionVWAP, ema
from recommend_engine import RecommendEngine

log = logging.getLogger("server")

bus = EventBus()
settings = Settings()
engine = RecommendEngine(settings, event_bus=bus)
_engine_task: asyncio.Task | None = None


def _engine_died(task: asyncio.Task) -> None:
    """create_task swallows exceptions until awaited — surface them NOW.
    With per-loop supervision inside engine.run() this should never fire,
    but if it does, the traceback must land in the server log."""
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        log.critical("ENGINE TASK DIED — API is up but no ideas/monitoring!", exc_info=exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _engine_task
    _engine_task = asyncio.create_task(engine.run())
    _engine_task.add_done_callback(_engine_died)
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


# ------------------------------------------------------------------ auth

# Signed, expiring session tokens: "<issued_at>.<hmac(creds, issued_at)>".
# No session store needed — tokens survive restarts, rotate the moment the
# password changes, and expire after AUTH_TTL_DAYS (env, default 30).
_CREDS_KEY = f"{settings.auth_username}:{settings.auth_password}".encode()
_TOKEN_TTL = float(os.getenv("AUTH_TTL_DAYS", "30")) * 86400


def _sign(issued_at: str) -> str:
    return hmac.new(_CREDS_KEY, f"session-v2:{issued_at}".encode(), hashlib.sha256).hexdigest()


def _issue_token() -> str:
    ts = str(int(time.time()))
    return f"{ts}.{_sign(ts)}"


def _token_ok(token: str) -> bool:
    try:
        issued_at, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, _sign(issued_at)):
            return False
        return (time.time() - float(issued_at)) < _TOKEN_TTL
    except (ValueError, AttributeError):
        return False


# Paths reachable without a token: health (uptime checks / wake-up pings)
# and login itself.
_PUBLIC_PATHS = {"/api/health", "/api/login"}

_failed_logins: dict = {}   # ip -> [timestamps], simple brute-force damper
_LOCKOUT_ATTEMPTS = 5
_LOCKOUT_WINDOW = 300.0

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
    "Cache-Control": "no-store",  # API responses carry live position data
}


@app.middleware("http")
async def require_auth(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api") or path in _PUBLIC_PATHS or request.method == "OPTIONS":
        response = await call_next(request)
    else:
        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:] if auth_header.lower().startswith("bearer ") else ""
        if not _token_ok(token):
            response = JSONResponse({"detail": "unauthorized"}, status_code=401)
        else:
            response = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        response.headers.setdefault(k, v)
    return response


class LoginBody(BaseModel):
    username: str
    password: str


def _notify_owner(text: str) -> None:
    """Fire-and-forget Telegram note to the owner — login security events."""
    try:
        asyncio.get_running_loop().create_task(engine.notifier.send(text))
    except RuntimeError:
        pass


@app.post("/api/login")
async def login(body: LoginBody, request: Request):
    ip = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _failed_logins.get(ip, []) if now - t < _LOCKOUT_WINDOW]
    if len(recent) >= _LOCKOUT_ATTEMPTS:
        raise HTTPException(429, "too many attempts — try again in a few minutes")
    user_ok = hmac.compare_digest(body.username.strip(), settings.auth_username)
    pass_ok = hmac.compare_digest(body.password, settings.auth_password)
    if not (user_ok and pass_ok):
        recent.append(now)
        _failed_logins[ip] = recent
        log.warning("failed login from %s (%d recent)", ip, len(recent))
        if len(recent) == 3:
            _notify_owner(f"🔐 3 failed dashboard logins from {ip} in the last "
                          f"{int(_LOCKOUT_WINDOW / 60)} min — if this isn't you, "
                          "rotate AUTH_PASSWORD.")
        raise HTTPException(401, "wrong username or password")
    _failed_logins.pop(ip, None)
    log.info("dashboard login from %s", ip)
    _notify_owner(f"🔓 Dashboard login from {ip} "
                  f"({request.headers.get('user-agent', '?')[:60]})")
    return {
        "token": _issue_token(),
        "mode": "SYNTHETIC" if getattr(engine.feed, "synthetic", False) else "LIVE",
    }


@app.get("/api/settings")
async def get_settings():
    return {"settings": engine.settings_view(), "editable": sorted(engine.TUNABLE)}


class SettingsPatch(BaseModel):
    settings: dict


@app.patch("/api/settings")
async def patch_settings(body: SettingsPatch):
    errors = {}
    applied = {}
    for key, value in body.settings.items():
        err = engine.update_setting(key, value)
        if err:
            errors[key] = err
        else:
            applied[key] = getattr(engine.s, key)
    if errors and not applied:
        raise HTTPException(400, "; ".join(f"{k}: {v}" for k, v in errors.items()))
    return {"applied": applied, "errors": errors, "settings": engine.settings_view()}


@app.post("/api/logout")
async def logout():
    # Tokens are stateless — logout is client-side (drop the token). This
    # endpoint exists so the UI action hits an auditable server event.
    log.info("dashboard logout")
    return {"ok": True}


# ------------------------------------------------------------------ REST API

VERSION = os.getenv("RENDER_GIT_COMMIT", "dev")[:12]


@app.get("/api/health")
async def health():
    """Public: uptime pings, wake-up probes, and the landing page's mode
    display. Reports engine liveness so 'API up but engine dead' is visible."""
    tick_age = round(time.time() - engine.last_tick_at, 1) if engine.last_tick_at else None
    return {
        "ok": True,
        "mode": "SYNTHETIC" if getattr(engine.feed, "synthetic", False) else "LIVE",
        "version": VERSION,
        "engine": {
            "last_tick_age_s": tick_age,
            "positions": len(engine.active),
            "pending": len(engine.pending),
            "paused": engine.paused,
        },
    }


@app.get("/api/history.csv")
async def history_csv(limit: int = 1000):
    """Journal export for spreadsheets / tax prep."""
    import csv
    import io

    rows = engine.journal.history(limit=limit)
    buf = io.StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    from fastapi.responses import Response
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trading-journal.csv"},
    )


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


# ------------------------------------------------------------------ chart data

_chart_cache: dict = {}  # (symbol, interval, days) -> (fetched_at, payload)


def _fetch_chart(symbol: str, interval: str, days: int) -> dict:
    """Sync (feed calls block) — run in a thread. Read-only view of the feed;
    fails soft to an empty candle list like every other feed consumer."""
    feed = engine.feed
    synthetic = bool(getattr(feed, "synthetic", False))
    interval_minutes = 1440 if interval == "1d" else engine.s.bar_minutes
    try:
        raw = feed.get_chart_candles(symbol, interval_minutes, days)
    except Exception as e:  # noqa: BLE001 — chart must fail soft
        log.warning("chart %s %s failed: %s", symbol, interval, e)
        raw = []

    candles, overlays = [], {}
    if interval == "1d":
        for c in raw:
            candles.append({"time": c["date"], "open": c["open"], "high": c["high"],
                            "low": c["low"], "close": c["close"], "volume": c["volume"]})
        closes = [c["close"] for c in candles]
        overlays = {
            "ema20": [round(v, 2) if v is not None else None for v in ema(closes, 20)],
            "ema50": [round(v, 2) if v is not None else None for v in ema(closes, 50)],
        }
    else:
        vwap_vals: list = []
        vwap = None
        last_day = None
        for c in raw:
            ts = int(c["ts"] / 1000)
            day = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(IST).date()
            if day != last_day:  # VWAP resets each session
                vwap, last_day = SessionVWAP(), day
            v = vwap.update(c["high"], c["low"], c["close"], c["volume"])
            vwap_vals.append(round(v, 2) if v is not None else None)
            candles.append({"time": ts, "open": c["open"], "high": c["high"],
                            "low": c["low"], "close": c["close"], "volume": c["volume"]})
        closes = [c["close"] for c in candles]
        overlays = {
            "vwap": vwap_vals,
            "ema20": [round(v, 2) if v is not None else None for v in ema(closes, 20)],
        }
    return {"symbol": symbol, "interval": interval, "synthetic": synthetic,
            "candles": candles, "overlays": overlays}


@app.get("/api/chart/{symbol}")
async def chart(symbol: str, interval: str = "5m", days: int = 5):
    symbol = symbol.upper()
    if interval not in ("5m", "1d"):
        raise HTTPException(400, "interval must be 5m or 1d")
    days = max(1, min(days, 10 if interval == "5m" else 400))
    key = (symbol, interval, days)
    ttl = 30 if interval == "5m" else 120
    hit = _chart_cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    payload = await asyncio.to_thread(_fetch_chart, symbol, interval, days)
    _chart_cache[key] = (time.time(), payload)
    return payload


# ------------------------------------------------------------------ backtests

class BacktestBody(BaseModel):
    strategy: str = "positional"           # "intraday" | "positional"
    symbols: Optional[List[str]] = None    # default: the engine watchlist
    days: int = 365
    use_index_gate: bool = True            # Faber 200-DMA gate (positional)


_backtests: dict = {}                      # job_id -> {status, ..., result?}
_backtest_lock = asyncio.Lock()            # one at a time — Groww rate limits


def _run_backtest_sync(strategy: str, symbols: list, days: int, use_gate: bool) -> dict:
    """Reuses the production backtester verbatim (same on_bar/scan_symbol paths)."""
    feed, s = engine.feed, engine.s
    if strategy == "intraday":
        result = backtest_intraday(feed, s, symbols, days)
    else:
        index_candles = None
        if use_gate:
            index_candles = feed.get_daily_candles(s.index_symbol, days=days + 320)
        result = backtest_positional(feed, s, symbols, days, index_candles or None)
    return {
        "summary": result.summary(),
        "equity_curve": result.equity_curve,
        "trades": [{
            "symbol": t.symbol, "side": t.side.value, "entry_date": t.entry_date,
            "entry": t.entry, "stop": t.stop, "target": t.target, "qty": t.qty,
            "exit": t.exit, "exit_reason": t.exit_reason, "pnl": t.pnl,
            "r_multiple": t.r_multiple, "costs": t.costs,
        } for t in result.trades[-500:]],
    }


async def _backtest_job(job_id: str, strategy: str, symbols: list, days: int, use_gate: bool) -> None:
    job = _backtests[job_id]
    try:
        async with _backtest_lock:
            job["result"] = await asyncio.to_thread(
                _run_backtest_sync, strategy, symbols, days, use_gate)
        job["status"] = "done"
    except Exception as e:  # noqa: BLE001 — surface the error to the UI, not a 500
        log.exception("backtest %s failed", job_id)
        job["status"] = "error"
        job["message"] = str(e)
    job["finished_at"] = datetime.now(IST).isoformat()


@app.post("/api/backtest")
async def start_backtest(body: BacktestBody):
    if getattr(engine.feed, "synthetic", False):
        return {"job_id": None, "status": "unavailable",
                "message": "Backtesting needs real Groww historical data — set "
                           "GROWW_API_KEY / GROWW_TOTP_SECRET in .env and restart."}
    if body.strategy not in ("intraday", "positional"):
        raise HTTPException(400, "strategy must be intraday or positional")
    symbols = [s.strip().upper() for s in (body.symbols or engine.s.watchlist) if s.strip()]
    if not symbols:
        raise HTTPException(400, "no symbols")
    days = max(5, min(body.days, 1500))
    job_id = uuid.uuid4().hex[:8]
    _backtests[job_id] = {
        "job_id": job_id, "status": "running", "strategy": body.strategy,
        "symbols": symbols, "days": days, "started_at": datetime.now(IST).isoformat(),
    }
    asyncio.create_task(_backtest_job(job_id, body.strategy, symbols, days, body.use_index_gate))
    return {"job_id": job_id, "status": "running"}


@app.get("/api/backtest/{job_id}")
async def backtest_status(job_id: str):
    job = _backtests.get(job_id)
    if not job:
        raise HTTPException(404, "unknown backtest job")
    return job


# ------------------------------------------------------------------ WebSocket

@app.websocket("/ws")
async def ws_live(websocket: WebSocket):
    # browsers can't set headers on WebSockets — the token rides the query string
    if not _token_ok(websocket.query_params.get("token", "")):
        await websocket.close(code=4401, reason="unauthorized")
        return
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
