# Engineering Onboarding — Trading Assistant

This doc is the code tour. The [README](README.md) covers what the product does
and how to set it up as a *user*; this covers how it works so you can change it
safely as an *engineer*. Read this top to bottom once (~15 min), then keep the
Invariants and Gotchas sections handy.

---

## 1. The one-paragraph mental model

A deterministic rule engine watches NSE stocks through the Groww API and emits
**trade ideas** (entry / stop / target / qty). A human receives each idea on
their phone (Telegram and/or the React dashboard), places the trade manually in
their broker app, and tells the engine (`/bought`, `/sold`). The engine then
monitors the live price and alerts the human when the stop or target is
touched. Claude (Fable 5) runs **beside** the rules as an analyst — it
classifies the session (regime/bias) and writes one-line rationales, but it
never triggers, sizes, or places anything. A hand-rolled backtester replays
the *exact same* strategy code against historical data.

```
Groww API ── quotes (5-min bars) ─► ORBVWAPStrategy ┐
          └─ daily candles ───────► Positional scan ┤
                                                     ├─► enrich (size + Fable "why") ─┬─► Telegram ─► phone
   FableAnalyst (Fable 5) ──► MarketContext ─────────┘        │                       └─► EventBus ─► WebSocket ─► dashboard
     • pre-market plan  • regime refresh                       └─► monitor stops/targets ─► follow-up alerts
                                                                    Journal (SQLite) records every idea/outcome
```

## 2. Repository map

### Backend (Python 3.9+, asyncio, no framework except FastAPI for the web API)

| File | Responsibility | Depends on |
|---|---|---|
| `config.py` | **All** env/config. No other module reads `os.environ`. | — |
| `indicators.py` | Pure-function TA math (SMA/EMA/ATR/RSI/ADX/Supertrend/VWAP/MACD/Donchian/squeeze/Chandelier) + the deterministic `market_regime()` classifier. Plain lists, no numpy. | — |
| `recommendation.py` | The `Recommendation` object (an idea + its lifecycle) and its Telegram/JSON formatting. | config |
| `strategy.py` | Intraday engine: `Bar`, `BarAggregator` (ticks→5-min bars), `ORBVWAPStrategy`, the shared `MarketContext`, market-hours helpers. | indicators |
| `positional.py` | Daily-candle swing scan: 5-strategy cascade + regime gate + Faber index gate. | indicators, strategy |
| `risk_manager.py` | Per-trade sizing (`suggested_qty`), portfolio heat caps (`portfolio_allows`), execute-mode `KillSwitch`. | config |
| `costs.py` | Indian transaction-cost model (CNC/MIS: STT, stamp, exchange, GST, DP, brokerage, slippage). | — |
| `groww_adapter.py` | The only file that touches the Groww SDK. `make_feed()` returns `GrowwAdapter` (real) or `SyntheticFeed` (no creds — random walk for pipeline testing). | config |
| `fable_analyst.py` | The only file that touches the Anthropic SDK. Produces `MarketContext` + one-line "why". Every method fails soft. | config, strategy |
| `notifier.py` | The only file that touches Telegram. Push + long-poll command loop. Console fallback when unconfigured. | config |
| `journal.py` | SQLite audit trail of every idea and outcome. | config, recommendation |
| `events.py` | 20-line asyncio pub/sub (`EventBus`) connecting the engine to WebSocket clients. | — |
| `recommend_engine.py` | **The heart.** Wires everything: data loop, Fable loop, positional loop, monitoring, and `handle_command()` — the single mutation path. Entrypoint for Telegram-only use. | everything above |
| `server.py` | FastAPI wrapper: REST + WebSocket around the same engine. Entrypoint for dashboard use. | recommend_engine, events |
| `orchestrator.py` | Optional execute mode: subclasses the engine, auto-places orders (`LIVE=false` = dry run). | recommend_engine |
| `backtest.py` | Hand-rolled bar-by-bar backtester replaying the production strategy code. | strategy, positional, costs, risk_manager |

### Frontend (`frontend/` — Vite + React + TypeScript, mobile-first)

| File | Responsibility |
|---|---|
| `src/api.ts` | REST client. `VITE_API_URL` / `VITE_WS_URL` env. |
| `src/useLive.ts` | The WebSocket hook: connects, auto-reconnects (2s), folds `snapshot`/`tick`/`alert` events into React state. |
| `src/types.ts` | Mirrors the backend's JSON shapes (`Snapshot`, `Idea`, `WsEvent`…). Keep in sync with `recommendation.to_dict()` and `engine.snapshot()`. |
| `src/App.tsx` | Layout: header, regime card, stat tiles, pending ideas, open positions, history. |
| `src/components/` | One file per card/tile. `IdeaCard` = pending idea with Bought/Skip; `PositionCard` = open position with live PnL + Sold. |
| `src/index.css`, `src/app.css` | Design tokens (dark default + light) and component styles. No CSS framework. |

### `reference/`

Third-party source files (Apache-2.0/MIT) preserved from four studied repos —
**nothing imports them**; they're the originals behind several adapted features.
See `reference/README.md` for the provenance map.

## 3. Invariants — do not break these

1. **The LLM never trades.** Fable writes `MarketContext` (regime, bias,
   avoid-list) and cosmetic "why" lines. Strategies *read* the context as a
   veto filter (`ctx.allows()`). If you find yourself passing an LLM output
   into an entry price, stop.
2. **Every state mutation goes through `engine.handle_command()`.** Telegram
   and the web UI are two front doors to the same function. That's why they
   can't disagree. New surfaces (CLI, cron, whatever) must call it too —
   never mutate `engine.active` / `engine.pending` directly.
3. **One idea per symbol at a time.** A symbol in `pending` or `active` is
   skipped by both strategy loops. The positional cascade returns at most one
   signal per symbol per day (first strategy to fire wins).
4. **Fail open, fail soft.** No Groww creds → synthetic feed. No Telegram →
   console. No Anthropic → neutral context. Missing history → gates pass.
   A dead WebSocket client → dropped events, not a dead engine. Any new
   integration must degrade the same way: the idea flow must survive every
   dependency being down.
5. **The backtester replays production code.** `backtest.py` calls the same
   `ORBVWAPStrategy.on_bar()` and `positional.scan_symbol()` the live engine
   uses. If you fork strategy logic into the backtester "just for testing,"
   backtests stop meaning anything.
6. **Backtest honesty rules:** signals computed on bar *i* fill no earlier
   than bar *i+1* (positional fills at next day's OPEN); when one bar contains
   both stop and target, the **stop wins** (industry pessimistic convention);
   trailing stops are computed from bars *before* today and checked against
   today; PnL is **net** of `costs.py`; circuit-locked bars (high==low) allow
   no fills.
7. **Risk is layered, and every layer can veto:** per-trade sizing
   (`suggested_qty` → 0 kills the idea) → portfolio heat caps
   (`portfolio_allows`) → per-symbol regime gate → index 200-DMA gate →
   Fable avoid-list → (execute mode only) daily-loss kill switch.
8. **`config.py` owns the environment.** Never read `os.environ` elsewhere;
   add a field to `Settings` instead (with a sane default so everything runs
   with an empty `.env`).

## 4. Life of an idea (end-to-end walkthrough)

**Intraday path:**
1. `data_loop` (recommend_engine.py) polls `feed.get_tick()` every
   `POLL_SECONDS` during market hours.
2. `ORBVWAPStrategy.on_tick()` feeds the tick to `BarAggregator`; when a 5-min
   bucket closes, `on_bar()` runs the rules: opening-range breakout + VWAP +
   Supertrend + RVOL + eligibility screen (see strategy.py docstring for the
   paper's exact rules). Returns a `Signal` or `None`.
3. `engine.publish(sig)`: sizes it (`suggested_qty`), checks portfolio heat
   (`portfolio_allows`), asks Fable for a one-liner (30s timeout, optional),
   journals it (`Status.SUGGESTED`), pushes to Telegram, emits `alert` +
   `snapshot` on the EventBus. The idea now sits in `engine.pending`.
4. You reply `/bought RELIANCE 16 2947.5` (or tap **Bought** on the dashboard,
   which POSTs `/api/ideas/RELIANCE/buy` — same handler). Idea moves
   `pending → active` (`Status.ACTIVE`), journal updated.
5. `monitor()` checks every poll: LTP vs stop/target. First touch → 🔴/🟢
   alert (once — `alerted_stop`/`alerted_target` flags prevent spam).
   15:10 IST → square-off reminder for intraday positions.
6. `/sold RELIANCE 2967` → PnL booked, `Status.CLOSED`, journaled, alert
   emitted. Position gone from `active`.
7. Untaken intraday ideas expire after close (`Status.EXPIRED`).

**Positional path:** same flow, but signals come from `positional_loop` (once
per day, daily candles, `scan()` → cascade), horizon is CNC, and there's no
square-off reminder.

**Dashboard live-ness:** the WebSocket sends a full `snapshot` on connect and
after every mutation, plus lightweight `tick` events (prices only) every poll
— `useLive.ts` recomputes open PnL client-side between snapshots.

## 5. The two strategy engines

**Intraday (`strategy.py`)** — Opening Range Breakout, per SSRN 4729284:
opening range = first 5-min bar; only long if that bar closed up; entry when a
later bar *closes* above the OR high AND above session VWAP AND Supertrend not
down AND relative volume > 1× the 14-day average first-bar volume; stop =
max(OR low, entry − 0.10·dailyATR14); target = 2R; square off by close.
A secondary LazyBear squeeze-release trigger catches mid-day compressions.
Stocks must pass the paper's screen: price > ₹100, ADV ≥ 1M shares,
dailyATR ≥ 0.5% of price. One idea per symbol per day.

**Positional (`positional.py`)** — evidence-ranked cascade, long-only, all
with ATR/Chandelier stops: ① EMA20/50 fresh cross (+EMA200 regime, ADX>25,
RSI<70) ② Donchian 55-day breakout ③ RSI dip-buy in an uptrend ④ Golden
Cross ⑤ MACD cross (LOW confidence). Two gates run first: the per-symbol
regime classifier (no longs in `bear_trend`/`high_volatility`) and the Faber
index gate (no entries while NIFTYBEES < its 200-DMA).

Both read the shared `MarketContext` from Fable as a final veto.

## 6. Running it locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # everything works with it EMPTY (synthetic mode)

python recommend_engine.py --smoke        # offline end-to-end pipeline test — must pass
python recommend_engine.py                # Telegram-only engine (synthetic feed w/o creds)

uvicorn server:app --reload --port 8000   # engine + REST + WebSocket
cd frontend && npm install && npm run dev # dashboard at localhost:5173

python backtest.py intraday RELIANCE TCS --days 60        # needs real Groww creds
python backtest.py positional RELIANCE TCS INFY --days 730
```

**Testing:** `--smoke` covers the engine pipeline (fabricated bars → signal →
publish → /bought → target alert → /sold → journal → /status). The backtester
has unit tests for the same-bar exit resolver and integration runs on a fake
feed (currently a scratch script — porting it into `tests/` with pytest is a
welcome first contribution). Frontend: `npm run build` type-checks; visual
verification was done with Playwright screenshots against a live local backend.

## 7. How to extend

**Add a positional strategy:** write `_my_signal(symbol, candles) -> Signal | None`
in positional.py (compute indicators from `candles`, return a `Signal` with
entry/stop/target), then register it in `_STRATEGIES` with its allowed regimes.
Position in the list = priority. It's automatically in the live scan AND the
backtester. Backtest it before shipping.

**Add an indicator:** pure function over plain lists in indicators.py,
returning `list[float | None]` aligned to input length (None during warmup).
Follow Wilder smoothing via `_wilder()` where the canonical definition uses it.

**Add a phone/dashboard command:** add a branch in
`engine._dispatch_command()`; add it to `_MUTATING` if it changes state (that
auto-broadcasts a snapshot); expose a REST route in server.py that calls
`_run_command()`; add a button in the frontend calling `api.ts`.

**Add a data field to the dashboard:** extend `recommendation.to_dict()` or
`engine.snapshot()` → mirror in `frontend/src/types.ts` → render.

**Swap SQLite for Postgres:** implement the `DATABASE_URL` branch in
journal.py (schema already written); everything else reads through `Journal`.

## 8. Gotchas & footguns

- **Python 3.9 runtime**: `from __future__ import annotations` makes `X | None`
  fine in *annotations*, but NOT in runtime contexts — pydantic models in
  server.py must use `Optional[X]` (this bit us once already).
- **`growwapi` SDK drift**: `CANDLE_INTERVAL_DAY` and response key names in
  groww_adapter.py are flagged `⚠️` — verify against your installed SDK version
  before live use. All Groww calls are defensive (log + return None/[]).
- **Groww API rate limits**: the pre-open `_compute_daily_stats` makes 2 calls
  per watchlist symbol; keep the watchlist modest (~10-15 names).
- **`journal.db` lands in the CWD** you launch from (`JOURNAL_PATH`). On
  Render's free tier the filesystem is **ephemeral** — history resets on
  redeploy. Move to Postgres if that matters.
- **Telegram is single-tenant**: one bot, one `chat_id`, no auth beyond that.
  The command loop ignores other chats. The web API has **no auth at all** —
  it's CORS-restricted (`CORS_ORIGINS`), which is *not* a security boundary.
  Don't expose the backend publicly without adding real auth.
- **Timezones**: everything internal is IST (`config.IST`). Groww candle
  epochs are UTC — convert at the boundary (see `_compute_daily_stats`).
- **The synthetic feed has no history**, so positional scanning and
  backtesting are skipped/refused in synthetic mode — only the intraday
  pipeline and the dashboard are testable without creds.
- **Fable 5 API quirks** (fable_analyst.py): thinking is always on (never send
  a `thinking` param), no temperature, and refusal stop-reasons are handled
  via server-side fallback to Opus. Auth failure disables the layer for the
  run rather than crashing.
- **Engine restarts lose in-memory state** (`pending`/`active` live in RAM;
  only the journal persists). After a restart, re-arm monitoring with
  `/watch SYMBOL QTY PRICE STOP [TARGET]`.

## 9. Glossary (for engineers who don't trade)

- **MIS / CNC** — broker product types: intraday (auto-squared-off same day) vs
  delivery (held in your demat account days–weeks).
- **LTP** — last traded price.
- **ORB** — opening-range breakout: trade when price escapes the first N
  minutes' high/low.
- **VWAP** — volume-weighted average price since open; intraday "fair value".
- **ATR** — average true range; a volatility unit used to size stops.
- **Stop / target** — exit prices: cut the loss / book the profit.
- **R-multiple** — PnL measured in units of initial risk (entry−stop). +2R =
  made twice what you risked. Size-independent, so comparable across trades.
- **R:R** — reward-to-risk ratio of the setup (target distance / stop distance).
- **Regime** — the market's current character (trending/choppy/volatile);
  strategies that chase trends lose money in chop, hence the gates.
- **Squaring off** — closing an intraday position before the 15:30 close.
- **STT, stamp duty, DP charge** — Indian statutory/depository charges baked
  into `costs.py`; they matter because they eat thin edges.
- **Circuit / circuit-locked** — NSE halts a stock at ±X% daily move; at the
  lock there's no counterparty, so fills there are fiction (backtester skips).
- **Portfolio heat** — total open risk (sum of entry-to-stop across positions)
  as % of capital.
