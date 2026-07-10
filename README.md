# Trading Assistant — personal NSE trading bot (you place the trades)

Generates **intraday** and **positional ("normal"/delivery)** trade ideas for
NSE equities, monitors your open positions live, trails stops, and tells you
**what to sell, when, and why**. Ideas reach you two ways: **Telegram** (reply
from your phone) and a **live web dashboard** (buy/sell with a tap, live
charts, watch positions update in real time). Everything is **100%
deterministic rules** — no LLM, no ML in the loop — so every signal is
backtestable and explainable. Orders happen ONE of two ways, always your call: you place them yourself in your broker app, or you tap ⚡ and the bot places that one order for you through Groww (off by default; demo mode always paper-fills).

## Wallet & how orders happen
One pool of capital, like a broker wallet: deposit money (practice money in
demo), every buy debits it, every sell credits it, and the bot sizes ideas off
live equity so gains compound. Three ways to trade, strictest first:
- **You trade manually** (default) — ideas arrive, you place orders in your
  broker app and confirm with /bought /sold or a tap.
- **⚡ Bot trades when told** — set `EXECUTE_ENABLED=true` (or the Settings
  toggle): tapping ⚡ on an idea/position or the Markets buy ticket makes the
  bot place THAT one market order via Groww. Never on its own initiative.
- **execute mode** (`orchestrator.py`) — full auto-placement of every signal
  (`LIVE=false` dry-runs). Separate entrypoint, separate decision.

## Strategies
- **Intraday (MIS):** opening-range breakout (SSRN 4729284 rules) with
  Gap-and-Go variant on >2% gap days, VWAP + Supertrend + RVOL filters, on
  live 5-min bars; square-off reminder before close.
- **Positional (CNC):** evidence-ranked cascade on daily candles — EMA20/50
  cross, Donchian-55 breakout, Connors RSI(2) mean-reversion, RSI dip-buy,
  Golden Cross, MACD — plus a **monthly 12-1 momentum rotation** across the
  watchlist. Held days–weeks with Chandelier-trailed stops.
- **Gates before any entry:** a deterministic per-symbol regime classifier
  (no longs in bear/high-volatility tape), the Faber 200-DMA index gate, and
  portfolio heat caps (max positions + total open risk).

## Exit intelligence (which stock to sell, when)
The bot watches every position you confirm and pushes: stop/target hits,
"approaching stop — get ready", break-even locks at +1R (stop auto-moves to
entry), profit give-back warnings, daily Chandelier stop trails ("raise your
stop to ₹X"), thesis-broken alerts (trend structure reversed), stagnant-trade
time stops, and a 15:10 hold/tighten/exit review of every open positional —
each with the reason spelled out.

## Architecture
```
Groww API ── quotes (5-min bars) ─► ORBVWAPStrategy (ORB / Gap-and-Go / squeeze) ┐
          └─ daily candles ──┬────► Positional cascade + 12-1 rotation           ├─► size + heat caps ─┬─► Telegram ─► your phone
                             └────► market_regime() ─► MarketContext (filter) ───┘         │           └─► EventBus ─► WebSocket ─► dashboard
                                                                                           └─► monitor + trail + exit reviews ─► sell alerts
                                                                                               Journal (SQLite) records every idea/outcome;
                                                                                               state restored from it after any restart
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

## Login & demo vs live

The dashboard opens on a **landing page with sign-in**. Default credentials
(override with `AUTH_USERNAME` / `AUTH_PASSWORD` env vars — do this in
production): username `prathmesh`, password `trade@2026`. All API routes and
the WebSocket require the session token; failed logins are rate-limited.

The app runs in one of two clearly-labelled data modes:
- **DEMO** (yellow badge + banner) — no Groww credentials on the server; all
  prices are a synthetic random walk so you can try every feature safely.
  Nothing is a real quote.
- **LIVE** (green badge) — Groww credentials present; real NSE quotes and
  history. The landing page shows which mode the engine is in before you even
  sign in, and also shows when the engine is waking from a free-tier sleep.

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
- Run `backtest.py` on real Groww historical data before trusting either
  strategy with real money.
