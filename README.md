# Trading Assistant — Groww + Fable 5

Generates **intraday** and **positional ("normal"/delivery)** trade ideas for
NSE equities. Ideas reach you two ways: **Telegram** (reply from your phone)
and a **live web dashboard** (buy/sell with a tap, watch positions update in
real time). A deterministic, rule-based core makes the calls; **Claude
Fable 5** runs alongside as an analyst (regime, directional bias, watchlist,
news flags, and a one-line rationale on every idea). The LLM never pulls the
trigger and never places an order.

## Two modes
- **recommend** (default) — `recommend_engine.py` / `server.py`. Ideas are
  pushed to you; **the app places no orders**. This is the "I trade manually"
  model.
- **execute** (optional) — `orchestrator.py`. The app auto-places orders
  (`LIVE=false` is a dry run). Only for when you want full automation.

## Two horizons
- **Intraday (MIS):** opening-range breakout, VWAP-filtered, on live 5-min bars;
  reminds you to square off before the close.
- **Positional (CNC):** EMA trend + fresh crossover with ATR/Chandelier stops,
  scanned on **daily candles** from Groww history; ideas are meant to be held
  days–weeks.

## Why the LLM sits beside the strategy, not inside it
An entry/exit trigger must be fast, deterministic, and backtestable. So Fable
runs on a timer (pre-market once, then a regime/news refresh every ~15 min) and
writes into a shared `MarketContext` that the rules read as a filter. If the API
is slow or down, the engine keeps working on neutral defaults.

## Architecture
```
Groww API ── quotes (5-min bars) ─► ORBVWAPStrategy ┐
          └─ daily candles ───────► Positional scan ┤
                                                     ├─► enrich (size + Fable "why") ─┬─► Telegram ─► your phone
   FableAnalyst (Fable 5) ──► MarketContext ─────────┘        │                       └─► EventBus ─► WebSocket ─► web dashboard
     • pre-market plan  • regime refresh  • news flags         └─► monitor stops/targets ─► follow-up alerts
                                                                    Journal (SQLite/Postgres) records every idea/outcome
```

`server.py` wraps the exact same `RecommendEngine` used by the Telegram
entrypoint — it's a second front door onto the same state, not a parallel
implementation. Every action (buy/sell/skip/watch/pause/resume), whether it
came from your phone via Telegram or a tap in the browser, goes through
`engine.handle_command()`, so both surfaces always agree and both update live.

| File | Role |
|------|------|
| `recommend_engine.py` | Telegram-only entrypoint — ideas → phone, monitors, commands |
| `server.py` | FastAPI backend for the web dashboard (REST + WebSocket), wraps the same engine |
| `frontend/` | Vite + React + TypeScript mobile dashboard — live ideas/positions/PnL |
| `backtest.py` | Hand-rolled bar-by-bar backtester for both strategies against Groww history |
| `orchestrator.py` | Optional auto-execution entrypoint |
| `strategy.py` | Intraday ORB+VWAP, `MarketContext`, bar aggregation |
| `positional.py` | Daily-candle swing strategy + scanner |
| `fable_analyst.py` | Fable 5 layer (structured outputs + narration) |
| `notifier.py` | Telegram push + `/status` `/pause` `/resume` |
| `events.py` | Tiny pub/sub so the dashboard gets a live feed of engine activity |
| `recommendation.py` | The idea object + phone/dashboard-friendly formatting |
| `groww_adapter.py` | Groww SDK: quotes, history, positions, orders |
| `risk_manager.py` | Suggested sizing + (execute mode) kill switch |
| `journal.py` | SQLite/Postgres audit trail |
| `config.py` | All settings from `.env` |

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # fill in keys
```

**Groww** (data + optional orders): a Trading API subscription (~₹499+tax/mo).
`GROWW_TOTP_SECRET` comes from the Groww Cloud API keys page ("Generate TOTP").

**Telegram** (phone alerts), one time:
1. Message `@BotFather` → `/newbot` → copy the bot **token**.
2. Message your new bot once ("hi").
3. Open `https://api.telegram.org/bot<TOKEN>/getUpdates` → copy the numeric
   `chat.id` → that's your **chat id**.
4. Put both in `.env`. (Leave blank to print alerts to the console instead.)

## Run — Telegram only
```bash
python recommend_engine.py
```
- Ideas arrive on Telegram like:
  ```
  BUY RELIANCE — Intraday (MIS)
  Entry ~ ₹2,945.00
  Stop ₹2,928.00 | Target ₹2,970.50 (R:R 1.5)
  Suggested qty ~ 17 | Confidence: HIGH
  Why: ORB breakout above VWAP; trending regime, long bias.
  square off same day · 09:34 IST
  ```
- You get follow-ups when a stop/target is touched, plus an intraday
  square-off reminder before close.
- From your phone: **/status** (regime, bias, open ideas, hypothetical PnL),
  **/pause**, **/resume**.
- No Groww creds yet? It falls back to a synthetic feed so you can test the
  pipeline end to end (positional is skipped in that mode).

## Run — live web dashboard
```bash
# terminal 1 — backend (wraps the same engine, also runs the Telegram loop if configured)
uvicorn server:app --reload --port 8000

# terminal 2 — frontend
cd frontend
cp .env.example .env      # VITE_API_URL=http://localhost:8000
npm install
npm run dev                # http://localhost:5173
```
The dashboard shows live regime/bias, pending ideas with tap-to-confirm
buy/skip, open positions with live LTP/PnL ticking in over a WebSocket, a
PnL sparkline, and trade history — mobile-first so you can act on it from
your phone's browser exactly like the README's original ask: watch the
screen live, sell when you see the alert.

## Backtesting
Validate both strategies against Groww history before trusting either with
real money:
```bash
python backtest.py intraday RELIANCE TCS --days 60
python backtest.py positional RELIANCE TCS INFY --days 730
```
It replays the *exact* production strategy code (`ORBVWAPStrategy.on_bar` /
`positional.scan_symbol`) bar-by-bar with no look-ahead, resolves the
same-bar stop-vs-target ambiguity by assuming the stop wins (the convention
used by `vectorbt`/`backtesting.py`/`freqtrade`), and reports win rate,
profit factor, R-multiples, max drawdown, CAGR, and the ambiguous-bar rate —
with an explicit warning if a run has too few trades to trust (~100+ is the
commonly cited floor). Requires real Groww credentials in `.env` — the
synthetic feed has no history to replay.

## Deployment
- **Backend → Render**: `render.yaml` in the repo root defines the service
  (`uvicorn server:app`). Push to GitHub, then in the Render dashboard choose
  **New → Blueprint** and point it at the repo — it reads `render.yaml`
  automatically. Set the env vars from `.env.example` in the Render
  dashboard (never commit `.env`). Set `CORS_ORIGINS` to your Vercel URL.
- **Frontend → Vercel**: `frontend/vercel.json` configures the build. Import
  the repo in Vercel, set the project root to `frontend/`, and set
  `VITE_API_URL` / `VITE_WS_URL` to your Render backend's URL
  (`https://<service>.onrender.com`, `wss://<service>.onrender.com/ws`).

## SEBI / compliance (India)
In **recommend mode the app places no orders**, so for personal use it's a
signal tool you act on manually — not algo order-routing, and no exchange
Algo-ID is needed. Do **not** sell or broadcast these signals to others without
looking at SEBI Research Analyst / Investment Adviser rules. If you switch to
**execute mode** and your order rate crosses the exchange threshold, register
the strategy through Groww for an Algo-ID. Not legal advice — confirm with Groww.

## Safety
Suggested sizes come from your `RISK_PER_TRADE_PCT` and `MAX_POSITION_VALUE` —
they're suggestions, size to your own conviction. SEBI's own data: 90%+ of
retail F&O traders lose money. Treat every idea as a hypothesis, size small,
backtest before trusting a strategy, and only ever risk capital you can lose.

## Before serious use
- Confirm the daily candle-interval constant (`CANDLE_INTERVAL_DAY`) against your
  installed `growwapi` version (flagged in `groww_adapter.py`).
- Swap quote polling for Groww's **GrowwFeed WebSocket** for real-time LTP +
  volume (which upgrades the intraday VWAP filter from its SMA fallback):
  ```python
  from growwapi import GrowwFeed, GrowwAPI
  feed = GrowwFeed(API_KEY)
  feed.subscribe_live_data(GrowwAPI.SEGMENT_CASH, "RELIANCE")
  ltp = feed.get_stocks_ltp("RELIANCE", timeout=3)
  ```
- Wire `news_brief.txt` / a headlines feed into the Fable pre-market and news
  passes.
- Run `backtest.py` on real Groww historical data before trusting either
  strategy with real money.
