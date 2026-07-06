# CLAUDE.md

NSE trading signal tool: 100% deterministic rule engine emits trade ideas →
human places trades manually (Telegram + React dashboard) → engine monitors
live stops/targets, trails stops, and reviews exits daily. No LLM anywhere in
the runtime (owner's explicit requirement — do not reintroduce one). Full code
tour in ONBOARDING.md — read it before structural changes.

## Commands

```bash
source .venv/bin/activate
python recommend_engine.py --smoke        # offline pipeline test — must pass before commit
uvicorn server:app --reload --port 8000   # backend (engine + REST + WS)
cd frontend && npm run dev                # dashboard (Vite, localhost:5173)
cd frontend && npm run build              # type-check + production build
python backtest.py positional RELIANCE --days 730   # needs real Groww creds
```

## Hard rules

- **Python 3.9 runtime**: pydantic/FastAPI models need `Optional[X]`, not
  `X | None` (annotations-only positions are fine — file has
  `from __future__ import annotations`).
- **No LLM in the runtime.** MarketContext comes from the deterministic
  `indicators.market_regime()` classifier (engine's `context_loop`). The owner
  removed the LLM analyst deliberately — don't add model calls to the bot.
- All state mutations go through `RecommendEngine.handle_command()` — never
  poke `engine.active`/`engine.pending` from a new surface.
- backtest.py must keep replaying the real `ORBVWAPStrategy.on_bar` /
  `positional.scan_symbol` — never fork strategy logic for tests.
- Backtest conventions: next-bar-open fills, stop-wins-on-ambiguous-bar,
  trailing stops from prior bars only, PnL net of costs.py.
- Only config.py reads `os.environ`; only groww_adapter.py imports growwapi;
  only notifier.py talks to Telegram.
- Everything must fail soft: missing creds/data → degraded mode, never a crash
  in the idea flow.
- indicators.py is pure functions over plain lists (no numpy), `None` during
  warmup, aligned to input length.

## Sync points

- `recommendation.to_dict()` / `engine.snapshot()` ↔ `frontend/src/types.ts`
- `_STRATEGIES` in positional.py: (function, allowed_regimes), list order =
  priority, first hit wins, one idea per symbol per day.
- Mutating commands belong in `_MUTATING` (auto-broadcasts a snapshot to the
  dashboard).
