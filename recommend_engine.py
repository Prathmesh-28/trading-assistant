"""Primary entrypoint — ideas → your phone; you place the trades.

    python recommend_engine.py            # live loop (synthetic feed if no Groww creds)
    python recommend_engine.py --smoke    # offline end-to-end pipeline test

Your workflow from the phone:
  1. Idea arrives on Telegram.
  2. You buy it (or don't) in your broker app.
  3. Reply  /bought RELIANCE [qty] [price]  — the engine now tracks it LIVE and
     pushes 🔴 SELL alerts the moment stop/target is touched, plus the 15:10
     square-off reminder for intraday.
  4. When you exit, reply  /sold RELIANCE [price]  — PnL is booked to the journal.
  Bought something the engine never suggested?  /watch SYMBOL QTY PRICE STOP [TARGET]
"""

from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta

from config import IST, Settings
from events import EventBus
from groww_adapter import make_feed
from journal import Journal
from notifier import Notifier
from positional import momentum_rotation_scan
from positional import scan as positional_scan
from recommendation import Horizon, Recommendation, Side, Status
from risk_manager import portfolio_allows, suggested_qty
from indicators import atr as atr_indicator
from strategy import (MARKET_CLOSE, SQUARE_OFF_WARN, DailyStats, MarketContext,
                      ORBVWAPStrategy, Signal, market_is_open, market_phase)

log = logging.getLogger("engine")


@dataclass
class Position:
    rec: Recommendation
    row_id: int
    alerted_stop: bool = False
    alerted_target: bool = False
    alerted_approach: bool = False   # price within 10% of stop distance
    alerted_breakeven: bool = False  # +1R reached: stop can move to entry
    alerted_giveback: bool = False   # winner gave back >50% of its peak
    alerted_timestop: bool = False   # stagnant positional past the time stop
    peak_pnl: float = 0.0
    auto_exit: bool = False   # armed: bot sells INSTANTLY when stop is touched
    # R-unit for the alerts above — captured at tracking start, BEFORE any
    # trailing: once the stop moves to break-even, entry-to-stop is 0 and
    # every risk-based threshold would silently die with it
    initial_risk_ps: float = 0.0


class RecommendEngine:
    def __init__(self, settings: Settings, event_bus: EventBus | None = None):
        self.s = settings
        self.bus = event_bus
        self.notifier = Notifier(settings)
        self.feed = make_feed(settings)
        self.journal = Journal(settings)
        self.strategy = ORBVWAPStrategy(settings)
        self.ctx = MarketContext()
        self.pending: dict[str, tuple[Recommendation, int]] = {}   # symbol -> (rec, row)
        self.active: dict[str, Position] = {}
        self.last_ltp: dict[str, float] = {}
        self.prev_close: dict[str, float] = {}   # for watchlist change-% (fail open: empty)
        self.paused = False
        self._squareoff_warned = False
        self._session_date = None
        self._positional_done = None
        self._exit_review_done = None
        self._rotation_done_month = None
        self.last_tick_at: float = 0.0   # data_loop liveness (epoch); watchdog + /api/health read it
        self._loop = None                # event loop, for thread-safe fast ticks
        self.latency = {"fast_ticks": 0, "tick_to_decision_ms": None,
                        "order_rtt_ms": None, "source": "poll"}
        self._order_times: list = []      # OPS/rate guard (SEBI-friendly)
        self._last_order: dict = {}       # (sym, side) -> ts, duplicate debounce
        self._breaker_tripped_on = None   # date the daily-loss breaker fired
        self._apply_setting_overrides()
        # Wallet: ONE pool of capital shared by you and the bot. First boot
        # seeds it with CAPITAL as an opening deposit; after that the ledger
        # is the truth and CAPITAL is ignored for cash.
        if not self.journal.wallet_has_txns():
            self.journal.wallet_record("deposit", self.s.capital,
                                       note="opening balance (CAPITAL)")
        self.cash: float = self.journal.wallet_balance()
        self.notifier.on_command(self.handle_command)

    # ------------------------------------------------------------- wallet

    def invested_value(self) -> float:
        """₹ locked in open positions at their fill prices."""
        return round(sum((p.rec.fill_price or p.rec.entry) * (p.rec.fill_qty or p.rec.qty)
                         for p in self.active.values()), 2)

    def equity(self) -> float:
        """Cash + invested — the bot sizes trades off this, so profits compound
        and losses shrink future size, exactly like a real account."""
        return round(self.cash + self.invested_value(), 2)

    def wallet_view(self) -> dict:
        invested = self.invested_value()
        open_pnl = round(sum(p.rec.pnl(self.last_ltp.get(s, p.rec.fill_price or p.rec.entry))
                             for s, p in self.active.items()), 2)
        return {"cash": round(self.cash, 2), "invested": invested,
                "equity": self.equity(), "open_pnl": open_pnl,
                "current_value": round(self.cash + invested + open_pnl, 2)}

    # -------------------------------------------- institutional risk layer

    def _equity_peak(self) -> float:
        try:
            peak = float(self.journal.load_setting_overrides().get("equity_peak", 0) or 0)
        except Exception:  # noqa: BLE001
            peak = 0.0
        eq = self.equity()
        if eq > peak:
            peak = eq
            try:
                self.journal.save_setting_override("equity_peak", peak)
            except Exception:  # noqa: BLE001
                pass
        return peak

    def effective_risk_pct(self) -> float:
        """Drawdown de-risking: beyond 8% equity drawdown from the all-time
        peak, cut per-trade risk in half until the account recovers — the
        standard prop-desk drawdown policy."""
        peak = self._equity_peak()
        if peak <= 0:
            return self.s.risk_per_trade_pct
        dd = 1 - self.equity() / peak
        return round(self.s.risk_per_trade_pct * (0.5 if dd > 0.08 else 1.0), 3)

    _fund_cache: dict = {}   # symbol -> (ts, merged fundamentals+quant dict)

    def _fundamentals_for(self, symbol: str) -> dict:
        """Merged fundamentals + quant for one symbol (deep-dive context on a
        positional idea). Heavy (yfinance/screener) — 6h cached, fail-soft to
        {}. Called via asyncio.to_thread so the engine loop never blocks."""
        import time as _time
        hit = self._fund_cache.get(symbol)
        if hit and _time.time() - hit[0] < 6 * 3600:
            return hit[1]
        merged = {}
        try:
            from fundamentals import fetch_fundamentals
            from universe import NASDAQ100
            us = {s for s, _ in NASDAQ100}
            f = fetch_fundamentals(symbol, "US" if symbol in us else "IN")
            if f:
                merged.update({k: v for k, v in f.items() if v is not None})
        except Exception:  # noqa: BLE001
            pass
        try:
            from quant import quant_stats
            candles = self.feed.get_chart_candles(symbol, 1440, 400)
            if len(candles) >= 60:
                idx = self.feed.get_chart_candles(self.s.index_symbol, 1440, 400)
                q = quant_stats(candles, idx)
                if "error" not in q:
                    merged.setdefault("quant_score", q.get("score"))
                    for k in ("mom_3m_pct", "ann_vol_pct", "sharpe_1y"):
                        merged.setdefault(k, q.get(k))
        except Exception:  # noqa: BLE001
            pass
        self._fund_cache[symbol] = (_time.time(), merged)
        return merged

    def _fundamental_gate(self, symbol: str, fund: dict) -> str:
        """Quality veto for positional ideas. Returns '' (pass) or a reason.
        Fails OPEN: missing data never blocks a technically-valid idea."""
        if not self.s.fundamental_gate_enabled or not fund:
            return ""
        score = fund.get("fundamental_score")
        de = fund.get("debt_to_equity")
        if score is not None and score < self.s.min_fundamental_score:
            return f"fundamental score {score} < {self.s.min_fundamental_score:.0f} min"
        if de is not None and de > self.s.max_fundamental_de:
            return f"debt/equity {de} > {self.s.max_fundamental_de:.0f} cap"
        return ""

    def _why_line(self, sig, fund: dict) -> str:
        """Deterministic one-liner blending the technical trigger with quant +
        fundamental context — the 'why' shown on the idea."""
        bits = [sig.reason]
        q = fund.get("quant_score")
        if q is not None:
            bits.append(f"quant {q}/100")
        fs = fund.get("fundamental_score")
        if fs is not None:
            roe = fund.get("roe_pct")
            de = fund.get("debt_to_equity")
            extra = []
            if roe is not None:
                extra.append(f"ROE {roe}%")
            if de is not None:
                extra.append(f"D/E {de}")
            bits.append(f"fundamentals {fs}/100" + (f" ({', '.join(extra)})" if extra else ""))
        return " · ".join(bits)

    def _ideas_today(self) -> int:
        """Count fresh ideas emitted today (pending + already-acted-on)."""
        today = datetime.now(IST).date().isoformat()
        n = sum(1 for rec, _ in self.pending.values()
                if rec.created_at.date().isoformat() == today)
        try:
            n += sum(1 for r in self.journal.history(200)
                     if (r.get("created_at") or "").startswith(today)
                     and r.get("status") in ("ACTIVE", "CLOSED", "SKIPPED"))
        except Exception:  # noqa: BLE001
            pass
        return n

    async def flatten_all(self) -> str:
        """Emergency: exit every open position at once and pause new ideas.
        Fails soft per-symbol so one bad exit can't strand the rest."""
        syms = list(self.active.keys())
        if not syms:
            self.paused = True
            return "No open positions. New ideas paused."
        done, failed = [], []
        for sym in syms:
            try:
                await self.execute_exit(sym)
                done.append(sym)
            except Exception as e:  # noqa: BLE001
                failed.append(f"{sym} ({str(e)[:30]})")
        self.paused = True
        self._emit_snapshot()
        msg = f"🛑 FLATTEN: exited {len(done)} position(s)"
        if failed:
            msg += f"; FAILED: {', '.join(failed)} — check the app"
        msg += ". New ideas paused."
        await self._alert("danger", "", msg, msg)
        return msg

    def _day_pnl(self) -> float:
        realized = self.journal.day_stats().get("realised_pnl", 0.0)
        open_pnl = sum(p.rec.pnl(self.last_ltp.get(s, p.rec.fill_price or p.rec.entry))
                       for s, p in self.active.items())
        return realized + open_pnl

    async def _check_breaker(self) -> None:
        """Daily-loss circuit breaker: auto-pause NEW ideas for the rest of the
        day once the day's total loss crosses the limit. Monitoring continues."""
        today = datetime.now(IST).date()
        if self.paused or self._breaker_tripped_on == today:
            return
        limit = self.equity() * self.s.daily_loss_limit_pct / 100.0
        pnl = self._day_pnl()
        if pnl < -limit:
            self._breaker_tripped_on = today
            self.paused = True
            await self._alert(
                "danger", "",
                f"🛑 CIRCUIT BREAKER: today's PnL ₹{pnl:,.0f} crossed the "
                f"-{self.s.daily_loss_limit_pct}% daily limit (₹{limit:,.0f}). "
                "New ideas are PAUSED for today — open positions stay monitored. "
                "/resume to override.",
                f"Circuit breaker: day PnL ₹{pnl:,.0f} — new ideas paused",
            )
            self._emit_snapshot()

    def _order_guard(self, sym: str, side: str, price: float = None) -> str:
        """Pre-trade checks every bot order passes (SEBI-friendly): rate limit
        well under the 10-orders/sec retail threshold, duplicate debounce,
        market hours (live only), and a ±10%% price-band sanity check."""
        import time as _time
        now = _time.time()
        self._order_times = [t for t in self._order_times if now - t < 60]
        if len([t for t in self._order_times if now - t < 1]) >= 2:
            return "rate limit: max 2 bot orders per second"
        if len(self._order_times) >= 10:
            return "rate limit: max 10 bot orders per minute"
        last = self._last_order.get((sym, side))
        if last and now - last < 5:
            return f"duplicate guard: {side} {sym} was ordered {now - last:.0f}s ago"
        if not self._paper() and not market_is_open(datetime.now(IST)):
            return "market is closed — live orders refused"
        pc = self.prev_close.get(sym)
        if price and pc and abs(price / pc - 1) > 0.10:
            return (f"price band: ₹{price:,.2f} is >10% from yesterday's "
                    f"₹{pc:,.2f} — refusing (circuit risk)")
        self._order_times.append(now)
        self._last_order[(sym, side)] = now
        return ""

    async def _correlation_note(self, sym: str) -> str:
        """Warn when a new idea moves with something already held (>0.8 corr
        of 60d returns) — you'd be doubling the same bet."""
        if not self.active:
            return ""
        try:
            def corr_check():
                import math
                def rets(cs):
                    xs = [c["close"] for c in cs][-61:]
                    return [(xs[i] - xs[i-1]) / xs[i-1] for i in range(1, len(xs)) if xs[i-1]]
                a = rets(self.feed.get_chart_candles(sym, 1440, 90))
                worst, worst_sym = 0.0, ""
                for held in list(self.active):
                    b = rets(self.feed.get_chart_candles(held, 1440, 90))
                    n = min(len(a), len(b))
                    if n < 30:
                        continue
                    x, y = a[-n:], b[-n:]
                    mx, my = sum(x)/n, sum(y)/n
                    sx = math.sqrt(sum((v-mx)**2 for v in x))
                    sy = math.sqrt(sum((v-my)**2 for v in y))
                    if sx and sy:
                        c = sum((x[i]-mx)*(y[i]-my) for i in range(n)) / (sx*sy)
                        if c > worst:
                            worst, worst_sym = c, held
                return worst, worst_sym
            worst, worst_sym = await asyncio.to_thread(corr_check)
            if worst > 0.8:
                return (f"\n⚠️ Moves almost identically to {worst_sym} you already "
                        f"hold (correlation {worst:.2f}) — this doubles that bet.")
        except Exception:  # noqa: BLE001 — advisory only
            pass
        return ""

    def _wallet_buy(self, symbol: str, qty: int, price: float, note: str = "") -> str:
        """Debit cash for a fill. Returns '' or the rejection reason."""
        cost = round(qty * price, 2)
        if cost > self.cash + 0.01:
            return (f"Not enough wallet cash: need ₹{cost:,.2f}, have ₹{self.cash:,.2f}. "
                    f"Add money or reduce quantity.")
        self.cash = self.journal.wallet_record("buy", -cost, symbol, qty, price, note)
        return ""

    def _wallet_sell(self, symbol: str, qty: int, price: float, note: str = "") -> None:
        self.cash = self.journal.wallet_record("sell", round(qty * price, 2),
                                               symbol, qty, price, note)

    # ---------------------------------------------------- fast path (<200ms)
    # AlphaGrep-style hot loop at personal scale: ticks arrive by push (Groww
    # WebSocket live; 1s synthetic ticker in demo), each tick is checked
    # against armed stops IMMEDIATELY, and an armed position fires a market
    # order in the same breath. Latency is measured end to end.

    def on_fast_tick(self, sym: str, ltp: float, recv_ts: float) -> None:
        """THREAD-SAFE entry: called from the feed thread. Schedules the async
        handler on the engine loop without blocking the feed."""
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self._fast_tick(sym, ltp, recv_ts), self._loop)

    async def _fast_tick(self, sym: str, ltp: float, recv_ts: float) -> None:
        import time as _time
        self.last_ltp[sym] = ltp
        self.latency["fast_ticks"] += 1
        pos = self.active.get(sym)
        if not pos or pos.alerted_stop:
            return
        r = pos.rec
        hit_stop = ltp <= r.stop if r.is_long else ltp >= r.stop
        if not hit_stop:
            return
        decided = _time.time()
        self.latency["tick_to_decision_ms"] = round((decided - recv_ts) * 1000, 1)
        if pos.auto_exit and (self._paper() or self.s.execute_enabled):
            reply = await self.execute_exit(sym)
            self.latency["order_rtt_ms"] = round((_time.time() - decided) * 1000, 1)
            log.info("AUTO-EXIT %s: decision %.1fms, order %.1fms — %s", sym,
                     self.latency["tick_to_decision_ms"], self.latency["order_rtt_ms"],
                     reply[:60])
        else:
            await self.monitor()  # normal alert path, still faster than the poll

    async def fast_loop(self) -> None:
        """Push-based ticks. Live: GrowwFeed WebSocket (real-time LTP for the
        watchlist + everything held). Demo: 1s ticker over active positions so
        the identical code path is exercised without creds."""
        import time as _time
        if self._paper():
            self.latency["source"] = "demo-1s"
            while True:
                await asyncio.sleep(1.0)
                for sym in list(self.active):
                    tick = self.feed.get_tick(sym)
                    if tick:
                        await self._fast_tick(sym, tick.ltp, _time.time())
        else:
            try:
                from growwapi import GrowwFeed
                feed = GrowwFeed(self.feed.api)
                self.latency["source"] = "groww-websocket"

                def _on_data():
                    now = _time.time()
                    try:
                        data = feed.get_ltp() or {}
                        # payload nests by segment/exchange; walk to symbol: ltp
                        for seg in data.values():
                            for exch in (seg or {}).values():
                                for sym, q in (exch or {}).items():
                                    px = (q or {}).get("ltp") or (q or {}).get("last_price")
                                    if px:
                                        self.on_fast_tick(str(sym).upper(), float(px), now)
                    except Exception:  # noqa: BLE001 — one bad frame ≠ dead feed
                        log.exception("fast feed frame failed")

                def _run():
                    symbols = sorted(set(self.s.watchlist) | set(self.active))
                    instruments = [{"exchange": "NSE", "segment": "CASH",
                                    "trading_symbol": s} for s in symbols]
                    feed.subscribe_ltp(instruments, on_data_received=_on_data)
                    feed.consume()  # blocking websocket loop

                await asyncio.to_thread(_run)
                log.warning("GrowwFeed consume() returned — restarting via supervisor")
                raise RuntimeError("feed ended")
            except ImportError:
                log.warning("GrowwFeed unavailable — fast path disabled, polling only")
                while True:
                    await asyncio.sleep(3600)

    def arm_auto_exit(self, sym: str, on: bool) -> str:
        pos = self.active.get(sym)
        if not pos:
            return f"{sym} isn't being tracked."
        if on and not self._paper() and not self.s.execute_enabled:
            return "❌ Turn on 'Bot places orders' in Settings first."
        pos.auto_exit = on
        self._emit_snapshot()
        if on:
            return (f"🛡 {sym}: ARMED — the bot sells the instant "
                    f"₹{pos.rec.stop:,.2f} is touched.")
        return f"🛡 {sym}: auto-sell off — you'll get an alert instead."

    # ---------------------------------------------------------- execution
    # The bot places an order ONLY when you explicitly tell it to (a tap or a
    # /execute command). Demo mode always paper-fills at the live demo price;
    # live mode sends a real market order through Groww. Wallet accounting is
    # identical either way — one pool of capital.

    def _paper(self) -> bool:
        return bool(getattr(self.feed, "synthetic", False))

    def _fill_price(self, symbol: str, fallback: float) -> float:
        px = self.last_ltp.get(symbol)
        if px:
            return px
        try:
            snap = self.feed.get_quote_snapshot(symbol)
            if snap and snap.get("ltp"):
                return float(snap["ltp"])
        except Exception:  # noqa: BLE001
            pass
        return fallback

    async def execute_idea(self, sym: str) -> str:
        """You tapped 'Buy via bot' on a pending idea."""
        if sym not in self.pending:
            return f"No pending idea for {sym}."
        if not self._paper() and not self.s.execute_enabled:
            return ("❌ Bot ordering is OFF. Turn on 'Bot places orders' in "
                    "Settings first (More → Settings).")
        rec, _row = self.pending[sym]
        product = "MIS" if rec.horizon == Horizon.INTRADAY else "CNC"
        price = self._fill_price(sym, rec.entry)
        guard = self._order_guard(sym, "BUY", price)
        if guard:
            return f"❌ {guard}"
        if self._paper():
            note = "PAPER order (demo)"
        else:
            order_id = await asyncio.to_thread(
                self.feed.place_order, sym, "BUY", rec.qty, product)
            if not order_id:
                return f"❌ Groww rejected the {sym} order — check the app/logs."
            note = f"Groww order {order_id}"
        reply = await self._cmd_bought(sym, [str(rec.qty), str(price)])
        if reply.startswith("❌"):
            return reply
        self._emit_snapshot()
        await self._alert("success", sym,
                          f"⚡ Bot bought {sym}: {rec.qty} @ ~₹{price:,.2f} ({note}). "
                          f"Stop ₹{rec.stop:,.2f} · target ₹{rec.target:,.2f}. I'm watching it.",
                          f"Bot bought {sym} {rec.qty} @ ~₹{price:,.2f} ({note})")
        return f"⚡ Done — bought {sym} ({note})."

    async def execute_exit(self, sym: str) -> str:
        """You tapped 'Sell now via bot' on an open position."""
        if sym not in self.active:
            return f"{sym} isn't being tracked."
        if not self._paper() and not self.s.execute_enabled:
            return ("❌ Bot ordering is OFF. Turn on 'Bot places orders' in "
                    "Settings first (More → Settings).")
        rec = self.active[sym].rec
        product = "MIS" if rec.horizon == Horizon.INTRADAY else "CNC"
        price = self._fill_price(sym, rec.fill_price or rec.entry)
        guard = self._order_guard(sym, "SELL", None)
        if guard:
            return f"❌ {guard}"
        if self._paper():
            note = "PAPER order (demo)"
        else:
            order_id = await asyncio.to_thread(
                self.feed.place_order, sym, "SELL", rec.fill_qty, product)
            if not order_id:
                return f"❌ Groww rejected the {sym} sell — check the app/logs."
            note = f"Groww order {order_id}"
        reply = self._cmd_sold(sym, [str(price)])
        self._emit_snapshot()
        await self._alert("info", sym, f"⚡ Bot sold {sym} @ ~₹{price:,.2f} ({note}).",
                          f"Bot sold {sym} @ ~₹{price:,.2f} ({note})")
        return f"⚡ {reply} ({note})"

    async def place_manual_order(self, sym: str, qty: int, stop: float,
                                 target: float = None) -> str:
        """Groww-style order ticket from the Markets tab: buy any stock with
        wallet money; the bot tracks it like any other position."""
        sym = sym.upper()
        if sym in self.active or sym in self.pending:
            return f"❌ {sym} is already open or pending."
        if qty <= 0:
            return "❌ Quantity must be positive."
        price = self._fill_price(sym, 0.0)
        if price <= 0:
            return f"❌ No price available for {sym} — is the symbol right?"
        if stop >= price:
            return f"❌ Stop ₹{stop:,.2f} must be below the price ₹{price:,.2f}."
        guard = self._order_guard(sym, "BUY", price)
        if guard:
            return f"❌ {guard}"
        if not self._paper() and not self.s.execute_enabled:
            return ("❌ Bot ordering is OFF. Turn on 'Bot places orders' in "
                    "Settings first (More → Settings).")
        if self._paper():
            note = "PAPER order (demo)"
        else:
            order_id = await asyncio.to_thread(
                self.feed.place_order, sym, "BUY", qty, "CNC")
            if not order_id:
                return f"❌ Groww rejected the {sym} order — check the app/logs."
            note = f"Groww order {order_id}"
        tgt = target if target else round(price + 2 * (price - stop), 2)
        reply = self._cmd_watch(sym, [str(qty), str(price), str(stop), str(tgt)])
        if reply.startswith("❌"):
            return reply
        self._emit_snapshot()
        await self._alert("success", sym,
                          f"⚡ Bought {sym}: {qty} @ ~₹{price:,.2f} ({note}). "
                          f"Stop ₹{stop:,.2f} · target ₹{tgt:,.2f}. I'm watching it.",
                          f"Bought {sym} {qty} @ ~₹{price:,.2f} ({note})")
        return f"⚡ {reply} ({note})"

    def wallet_deposit(self, amount: float) -> str:
        if not (1 <= amount <= 1e9):
            return "❌ Amount must be between ₹1 and ₹100 crore."
        self.cash = self.journal.wallet_record("deposit", round(amount, 2), note="user deposit")
        self._emit_snapshot()
        return f"💰 Added ₹{amount:,.2f}. Wallet cash: ₹{self.cash:,.2f}."

    def wallet_withdraw(self, amount: float) -> str:
        if amount <= 0:
            return "❌ Amount must be positive."
        if amount > self.cash:
            return f"❌ Only ₹{self.cash:,.2f} is free to withdraw (rest is invested)."
        self.cash = self.journal.wallet_record("withdraw", -round(amount, 2), note="user withdrawal")
        self._emit_snapshot()
        return f"💸 Withdrew ₹{amount:,.2f}. Wallet cash: ₹{self.cash:,.2f}."

    # Runtime-tunable settings (dashboard Settings tab). Whitelist keeps the
    # PATCH surface away from credentials and structural config.
    TUNABLE = {
        "execute_enabled": bool,
        "watchlist": list,
        "risk_per_trade_pct": float,
        "capital": float,
        "max_position_value": float,
        "max_open_positions": int,
        "max_portfolio_risk_pct": float,
        "daily_loss_limit_pct": float,
        "max_ideas_per_day": int,
        "alerts_muted": bool,
        "disabled_strategies": list,
        "fundamental_gate_enabled": bool,
        "min_fundamental_score": float,
        "max_fundamental_de": float,
    }

    def _apply_setting_overrides(self) -> None:
        """Persisted dashboard tweaks win over env defaults across restarts."""
        try:
            overrides = self.journal.load_setting_overrides()
        except Exception:  # noqa: BLE001 — never block startup on this
            return
        for key, value in overrides.items():
            caster = self.TUNABLE.get(key)
            if caster is None:
                continue
            try:
                if key == "disabled_strategies":
                    value = [str(s).strip().lower() for s in value if str(s).strip()]
                elif caster is list:
                    value = [str(s).strip().upper() for s in value if str(s).strip()]
                elif caster is bool:
                    value = bool(value)
                else:
                    value = caster(value)
                setattr(self.s, key, value)
            except (TypeError, ValueError):
                log.warning("ignoring bad persisted setting %s=%r", key, value)

    def update_setting(self, key: str, value) -> str:
        """Validate + apply + persist one tunable. Returns '' or an error."""
        caster = self.TUNABLE.get(key)
        if caster is None:
            return f"'{key}' is not editable at runtime"
        try:
            if key == "disabled_strategies":
                if not isinstance(value, list):
                    return "disabled_strategies must be a list of strategy keys"
                value = [str(s).strip().lower()[:30] for s in value if str(s).strip()]
                if len(value) > 20:
                    return "too many disabled strategies"
            elif caster is list:
                if not isinstance(value, list):
                    return "watchlist must be a list of symbols"
                value = [str(s).strip().upper() for s in value if str(s).strip()]
                if not (1 <= len(value) <= 25):
                    return "watchlist must have 1-25 symbols"
                if any(not s.replace("&", "").replace("-", "").isalnum() or len(s) > 20
                       for s in value):
                    return "symbols must be alphanumeric NSE codes"
            elif caster is bool:
                if not isinstance(value, bool):
                    return f"{key} must be true or false"
            else:
                value = caster(value)
                limits = {
                    "risk_per_trade_pct": (0.05, 5.0),
                    "capital": (1000.0, 1e9),
                    "max_position_value": (1000.0, 1e9),
                    "max_open_positions": (1, 25),
                    "max_portfolio_risk_pct": (0.5, 25.0),
                    "daily_loss_limit_pct": (0.5, 20.0),
                    "max_ideas_per_day": (0, 100),
                    "min_fundamental_score": (0.0, 100.0),
                    "max_fundamental_de": (10.0, 1000.0),
                }[key]
                if not (limits[0] <= value <= limits[1]):
                    return f"{key} must be between {limits[0]} and {limits[1]}"
        except (TypeError, ValueError):
            return f"invalid value for {key}"
        setattr(self.s, key, value)
        self.journal.save_setting_override(key, value)
        log.info("setting updated: %s=%r", key, value)
        self._emit_snapshot()
        return ""

    def settings_view(self) -> dict:
        return {k: getattr(self.s, k) for k in self.TUNABLE}

    # ------------------------------------------------------------- events

    def _emit(self, event_type: str, data=None) -> None:
        if self.bus:
            self.bus.publish(event_type, data)

    def _emit_snapshot(self) -> None:
        self._emit("snapshot", self.snapshot())

    def snapshot(self) -> dict:
        """Full state for a REST poll or a freshly-connected websocket client."""
        c = self.ctx
        return {
            "mode": "SYNTHETIC" if getattr(self.feed, "synthetic", False) else "LIVE",
            "paused": self.paused,
            "watchlist": self.s.watchlist,
            "context": {
                "regime": c.regime, "bias": c.bias, "confidence": c.confidence,
                "notes": c.notes, "avoid_symbols": sorted(c.avoid_symbols),
                "updated_at": c.updated_at.isoformat() if c.updated_at else None,
            },
            "pending": [rec.to_dict(self.last_ltp.get(rec.symbol))
                       for rec, _ in self.pending.values()],
            "positions": [{**pos.rec.to_dict(self.last_ltp.get(sym)),
                           "auto_exit": pos.auto_exit}
                         for sym, pos in self.active.items()],
            "day_stats": self.journal.day_stats(),
            "wallet": self.wallet_view(),
            "execute": {"enabled": bool(self.s.execute_enabled) or self._paper(),
                        "paper": self._paper()},
            "market": market_phase(datetime.now(IST)),
            "quotes": self._quotes(),
            "settings": self.settings_view(),
            "server_time": datetime.now(IST).isoformat(),
        }

    def _quotes(self) -> dict:
        """Watchlist quotes for the dashboard: LTP (falls back to prev close
        when the session hasn't ticked yet) + change-%. All fields may be None."""
        out = {}
        for sym in self.s.watchlist:
            pc = self.prev_close.get(sym)
            ltp = self.last_ltp.get(sym, pc)
            chg = round((ltp - pc) / pc * 100, 2) if (ltp and pc) else None
            out[sym] = {"ltp": ltp, "prev_close": pc, "change_pct": chg}
        return out

    def _load_prev_closes(self) -> None:
        """Sync (run in a thread for the real feed). Fail open per symbol."""
        for sym in self.s.watchlist:
            try:
                pc = self.feed.prev_close(sym)
            except Exception:  # noqa: BLE001 — quotes are cosmetic
                pc = None
            if pc:
                self.prev_close[sym] = pc

    # ------------------------------------------------------------- publishing

    def _open_risk(self) -> float:
        """₹ entry-to-stop risk across confirmed positions AND pending ideas —
        pending counts because the user may still take them."""
        risk = 0.0
        for pos in self.active.values():
            r = pos.rec
            risk += abs((r.fill_price or r.entry) - r.stop) * (r.fill_qty or r.qty)
        for rec, _ in self.pending.values():
            risk += abs(rec.entry - rec.stop) * rec.qty
        return risk

    async def publish(self, sig: Signal) -> None:
        muted = [k for k in self.s.disabled_strategies if k in sig.reason.lower()]
        if muted:
            log.info("%s idea skipped — strategy muted (%s)", sig.symbol, muted[0])
            return
        cap = self.s.max_ideas_per_day
        if cap and self._ideas_today() >= cap:
            log.info("%s idea skipped — daily cap of %d ideas reached", sig.symbol, cap)
            return
        qty = suggested_qty(sig.entry, sig.stop, self.s, capital=self.equity(),
                            risk_pct=self.effective_risk_pct())
        if qty <= 0:
            log.info("%s signal skipped — qty 0 under current risk settings", sig.symbol)
            return
        ok, reason = portfolio_allows(
            len(self.active) + len(self.pending),
            self._open_risk(),
            abs(sig.entry - sig.stop) * qty,
            self.s, capital=self.equity(),
        )
        if not ok:
            log.info("%s signal skipped — %s", sig.symbol, reason)
            return
        fund = {}
        if sig.horizon == Horizon.POSITIONAL:
            fund = await asyncio.to_thread(self._fundamentals_for, sig.symbol)
            gate = self._fundamental_gate(sig.symbol, fund)
            if gate:
                log.info("%s positional idea vetoed — %s", sig.symbol, gate)
                return
        rec = Recommendation(
            symbol=sig.symbol, side=sig.side, horizon=sig.horizon,
            entry=sig.entry, stop=sig.stop, target=sig.target,
            qty=qty, confidence=sig.confidence, reason=sig.reason,
            why=self._why_line(sig, fund),
        )
        corr = await self._correlation_note(rec.symbol)
        row = self.journal.record(rec)
        self.pending[rec.symbol] = (rec, row)
        await self.notifier.send(rec.format_telegram() + corr)
        self._emit("alert", {"level": "info", "message": f"New idea: {rec.side.value} {rec.symbol}"})
        self._emit_snapshot()
        log.info("idea pushed: %s %s @%.2f", rec.side.value, rec.symbol, rec.entry)

    # ------------------------------------------------------------- monitoring

    async def _alert(self, level: str, symbol: str, telegram_text: str, short: str) -> None:
        await self.notifier.send(telegram_text)
        self._emit("alert", {"level": level, "symbol": symbol, "message": short})

    async def monitor(self) -> None:
        await self._check_breaker()
        for sym, pos in list(self.active.items()):
            ltp = self.last_ltp.get(sym)
            if ltp is None:
                continue
            r = pos.rec
            direction = 1 if r.is_long else -1
            if pos.initial_risk_ps <= 0:  # memoize before any trailing shrinks it
                pos.initial_risk_ps = abs((r.fill_price or r.entry) - r.stop)
            risk_per_share = pos.initial_risk_ps
            risk_rupees = risk_per_share * (r.fill_qty or r.qty)
            pnl = r.pnl(ltp)
            pos.peak_pnl = max(pos.peak_pnl, pnl)

            hit_stop = ltp <= r.stop if r.is_long else ltp >= r.stop
            hit_target = ltp >= r.target if r.is_long else ltp <= r.target
            if hit_stop and not pos.alerted_stop:
                pos.alerted_stop = True
                await self._alert(
                    "danger", sym,
                    f"🔴 SELL {sym} NOW — stop ₹{r.stop:,.2f} hit (LTP ₹{ltp:,.2f})\n"
                    f"Open PnL ₹{pnl:,.2f} on {r.fill_qty} qty\n"
                    f"Reply /sold {sym} [price] once you exit.",
                    f"SELL {sym} NOW — stop ₹{r.stop:,.2f} hit (LTP ₹{ltp:,.2f})",
                )
                continue
            if hit_target and not pos.alerted_target:
                pos.alerted_target = True
                await self._alert(
                    "success", sym,
                    f"🟢 {sym} TARGET ₹{r.target:,.2f} hit (LTP ₹{ltp:,.2f}) — book profit "
                    f"or trail your stop to ₹{r.entry:,.2f} (entry).\n"
                    f"Open PnL ₹{pnl:,.2f} on {r.fill_qty} qty\n"
                    f"Reply /sold {sym} [price] once you exit.",
                    f"{sym} TARGET ₹{r.target:,.2f} hit (LTP ₹{ltp:,.2f}) — book profit",
                )
                continue
            if risk_per_share <= 0:
                continue

            # prepare-to-act warning: within 10% of the stop distance
            near_stop = (r.stop + 0.10 * risk_per_share * direction - ltp) * direction >= 0
            if near_stop and not pos.alerted_approach and not pos.alerted_stop:
                pos.alerted_approach = True
                await self._alert(
                    "warning", sym,
                    f"⚠️ {sym} approaching stop — LTP ₹{ltp:,.2f}, stop ₹{r.stop:,.2f}. "
                    f"Open your broker app and be ready to sell.",
                    f"{sym} approaching stop (LTP ₹{ltp:,.2f} vs ₹{r.stop:,.2f})",
                )

            # +1R: the trade can no longer lose if the stop moves to entry
            if pnl >= risk_rupees and not pos.alerted_breakeven:
                pos.alerted_breakeven = True
                ref = r.fill_price or r.entry
                r.stop = round(ref, 2)  # bot now monitors the break-even level
                self.journal.update(pos.row_id, r)
                await self._alert(
                    "success", sym,
                    f"🔒 {sym} is +1R (₹{pnl:,.2f}). Stop moved to entry ₹{ref:,.2f} — "
                    f"this trade can no longer lose. If you placed a broker SL, raise it too.",
                    f"{sym} +1R — stop moved to break-even ₹{ref:,.2f}",
                )
                self._emit_snapshot()

            # winner giving back more than half its peak
            if (pos.peak_pnl >= risk_rupees and pnl < 0.5 * pos.peak_pnl
                    and not pos.alerted_giveback):
                pos.alerted_giveback = True
                await self._alert(
                    "warning", sym,
                    f"↩️ {sym} has given back over half its peak profit "
                    f"(peak ₹{pos.peak_pnl:,.2f} → now ₹{pnl:,.2f}). "
                    f"Consider booking or tightening the stop.",
                    f"{sym} gave back >50% of peak profit (₹{pos.peak_pnl:,.0f} → ₹{pnl:,.0f})",
                )

    async def squareoff_check(self, now: datetime) -> None:
        if self._squareoff_warned or now.time() < SQUARE_OFF_WARN:
            return
        intraday = [p.rec for p in self.active.values() if p.rec.horizon == Horizon.INTRADAY]
        self._squareoff_warned = True
        if intraday:
            names = ", ".join(
                f"{r.symbol} (PnL ₹{r.pnl(self.last_ltp.get(r.symbol, r.entry)):,.2f})"
                for r in intraday
            )
            await self.notifier.send(
                f"⏰ 15:10 — square off intraday positions before close: {names}"
            )
            self._emit("alert", {
                "level": "warning",
                "message": f"15:10 — square off intraday positions before close: {names}",
            })

    def _expire_pending_intraday(self) -> None:
        for sym in list(self.pending):
            rec, row = self.pending[sym]
            if rec.horizon == Horizon.INTRADAY:
                rec.status = Status.EXPIRED
                self.journal.update(row, rec)
                del self.pending[sym]

    # ------------------------------------------------- positional exit review

    TIME_STOP_DAYS = 28          # ~20 sessions; stagnant capital is a cost too
    _REVIEW_TIME = SQUARE_OFF_WARN  # 15:10 IST — user can still act same day

    def _review_position(self, sym: str, pos: Position) -> tuple[str, list[str]]:
        """Daily rule-based verdict for one positional holding:
        returns (verdict, reasons) where verdict is hold/tighten/exit.
        Sync (feed calls) — run in a thread."""
        from indicators import chandelier_stop, ema
        r = pos.rec
        candles = self.feed.get_daily_candles(sym, days=90)
        if len(candles) < 30:
            return "hold", ["not enough daily history for a review — holding"]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        verdict, reasons = "hold", []

        # 1. trail: Chandelier(22,3) ratchets the monitored stop upward
        chand = chandelier_stop(highs, lows, closes, 22, 3.0)
        if chand is not None and r.is_long and chand > r.stop:
            old = r.stop
            r.stop = round(chand, 2)
            self.journal.update(pos.row_id, r)
            reasons.append(f"stop trailed ₹{old:,.2f} → ₹{r.stop:,.2f} (Chandelier)")
            verdict = "tighten"

        # 2. thesis reversal: trend structure the entries rely on has flipped
        e20, e50 = ema(closes, 20), ema(closes, 50)
        if (e20[-1] is not None and e50[-1] is not None
                and e20[-2] is not None and e50[-2] is not None):
            crossed_down = e20[-1] < e50[-1] and e20[-2] >= e50[-2]
            if crossed_down:
                reasons.append("EMA20 crossed BELOW EMA50 — the entry thesis is broken")
                verdict = "exit"
        if chand is not None and closes[-1] < chand:
            reasons.append(f"close ₹{closes[-1]:,.2f} is below the Chandelier stop ₹{chand:,.2f}")
            verdict = "exit"

        # 3. time stop: weeks in, going nowhere
        days_held = (datetime.now(IST) - r.created_at).days
        risk = abs((r.fill_price or r.entry) - r.stop) * (r.fill_qty or r.qty)
        pnl = r.pnl(self.last_ltp.get(sym, r.fill_price or r.entry))
        if (days_held >= self.TIME_STOP_DAYS and risk > 0 and abs(pnl) < 0.5 * risk
                and not pos.alerted_timestop):
            pos.alerted_timestop = True
            reasons.append(f"{days_held} days held for <0.5R progress — capital is idle")
            if verdict == "hold":
                verdict = "exit"

        # 4. fundamental deterioration (deep-dive): a held name whose books have
        # gone red is a tighten/exit reason even if price hasn't broken yet.
        fund = self._fundamentals_for(sym)
        roe, de = fund.get("roe_pct"), fund.get("debt_to_equity")
        if roe is not None and roe < 0:
            reasons.append(f"fundamentals: ROE now negative ({roe}%)")
            verdict = "exit"
        elif de is not None and de > self.s.max_fundamental_de:
            reasons.append(f"fundamentals: debt/equity {de} above your {self.s.max_fundamental_de:.0f} cap")
            if verdict == "hold":
                verdict = "tighten"

        if not reasons:
            reasons.append("trend intact, stop unchanged")
        return verdict, reasons

    async def positional_exit_review(self, now: datetime) -> None:
        """Once a day near the close: hold / tighten / exit verdict per open
        positional position, pushed as one message each."""
        if self._exit_review_done == now.date() or now.time() < self._REVIEW_TIME:
            return
        self._exit_review_done = now.date()
        positional = {s: p for s, p in self.active.items()
                      if p.rec.horizon == Horizon.POSITIONAL}
        if not positional:
            return
        icons = {"hold": "🟢", "tighten": "🟡", "exit": "🔴"}
        for sym, pos in positional.items():
            verdict, reasons = await asyncio.to_thread(self._review_position, sym, pos)
            ltp = self.last_ltp.get(sym, pos.rec.fill_price or pos.rec.entry)
            await self._alert(
                {"hold": "info", "tighten": "warning", "exit": "danger"}[verdict], sym,
                f"{icons[verdict]} EOD review {sym}: {verdict.upper()}\n"
                f"LTP ₹{ltp:,.2f} · PnL ₹{pos.rec.pnl(ltp):,.2f} · stop ₹{pos.rec.stop:,.2f}\n"
                + "\n".join(f"• {t}" for t in reasons),
                f"EOD {sym}: {verdict.upper()} — {reasons[0]}",
            )
        self._emit_snapshot()

    # ------------------------------------------------------------- commands

    # Commands that change state — the ones that must push a fresh snapshot to
    # every connected dashboard client (and, symmetrically, are reachable from
    # either Telegram or the web UI so both surfaces always agree).
    _MUTATING = {"pause", "resume", "bought", "skip", "sold", "watch", "flatten",
                 "execute", "exit", "deposit", "withdraw", "arm", "disarm"}

    async def handle_command(self, cmd: str, args: list[str]) -> str:
        if cmd == "flatten":
            return await self.flatten_all()
        reply = await self._dispatch_command(cmd, args)
        if cmd in self._MUTATING:
            self._emit_snapshot()
        return reply

    async def _dispatch_command(self, cmd: str, args: list[str]) -> str:
        if cmd == "help":
            return (
                "/status – regime, ideas, open positions\n"
                "/positions – open positions + live PnL\n"
                "/bought SYMBOL [qty] [price] – confirm you took an idea\n"
                "/sold SYMBOL [price] – you exited; books PnL\n"
                "/skip SYMBOL – dismiss a pending idea\n"
                "/watch SYMBOL QTY PRICE STOP [TARGET] – monitor a manual trade\n"
                "/execute SYMBOL – bot BUYS a pending idea for you\n"
                "/exit SYMBOL – bot SELLS an open position for you\n"
                "/wallet · /deposit AMT · /withdraw AMT – your capital\n"
                "/pause · /resume – stop/restart new ideas"
            )
        if cmd == "pause":
            self.paused = True
            return "⏸ Paused — no new ideas. Monitoring of open positions continues."
        if cmd == "resume":
            self.paused = False
            return "▶️ Resumed — idea generation back on."
        if cmd == "status":
            return self._status_text()
        if cmd == "positions":
            return self._positions_text()
        if cmd == "wallet":
            w = self.wallet_view()
            return (f"💰 Wallet\nCash free: ₹{w['cash']:,.2f}\n"
                    f"Invested: ₹{w['invested']:,.2f}\n"
                    f"Open PnL: ₹{w['open_pnl']:,.2f}\n"
                    f"Total value: ₹{w['current_value']:,.2f}")
        if cmd in ("deposit", "withdraw"):
            try:
                amount = float(args[0])
            except (IndexError, ValueError):
                return f"Usage: /{cmd} AMOUNT"
            return (self.wallet_deposit(amount) if cmd == "deposit"
                    else self.wallet_withdraw(amount))
        if cmd in ("arm", "disarm"):
            if not args:
                return f"Usage: /{cmd} SYMBOL"
            return self.arm_auto_exit(args[0].upper(), cmd == "arm")
        if cmd in ("bought", "skip", "sold", "watch", "execute", "exit"):
            if not args:
                return f"Usage: /{cmd} SYMBOL …"
            sym = args[0].upper()
            if cmd == "bought":
                return await self._cmd_bought(sym, args[1:])
            if cmd == "skip":
                return self._cmd_skip(sym)
            if cmd == "sold":
                return self._cmd_sold(sym, args[1:])
            if cmd == "execute":
                return await self.execute_idea(sym)
            if cmd == "exit":
                return await self.execute_exit(sym)
            return self._cmd_watch(sym, args[1:])
        return "Unknown command — /help"

    async def _cmd_bought(self, sym: str, rest: list[str]) -> str:
        if sym in self.active:
            return f"{sym} is already being monitored."
        if sym not in self.pending:
            return (f"No pending idea for {sym}. For a manual trade use:\n"
                    f"/watch {sym} QTY PRICE STOP [TARGET]")
        rec, row = self.pending.pop(sym)
        rec.fill_qty = int(float(rest[0])) if rest else rec.qty
        rec.fill_price = float(rest[1]) if len(rest) > 1 else rec.entry
        err = self._wallet_buy(sym, rec.fill_qty, rec.fill_price, "confirmed fill")
        if err:
            self.pending[sym] = (rec, row)  # idea stays pending
            return f"❌ {err}"
        rec.status = Status.ACTIVE
        self.journal.update(row, rec)
        self.active[sym] = Position(rec, row)
        return (f"✅ Tracking {sym}: {rec.fill_qty} @ ₹{rec.fill_price:,.2f}\n"
                f"I'll alert you at stop ₹{rec.stop:,.2f} / target ₹{rec.target:,.2f}"
                + (" and remind you before close." if rec.horizon == Horizon.INTRADAY else "."))

    def _cmd_skip(self, sym: str) -> str:
        if sym not in self.pending:
            return f"No pending idea for {sym}."
        rec, row = self.pending.pop(sym)
        rec.status = Status.SKIPPED
        self.journal.update(row, rec)
        return f"👌 {sym} idea dismissed."

    def _cmd_sold(self, sym: str, rest: list[str]) -> str:
        if sym not in self.active:
            return f"{sym} isn't being monitored."
        pos = self.active.pop(sym)
        rec = pos.rec
        rec.exit_price = float(rest[0]) if rest else self.last_ltp.get(sym, rec.entry)
        direction = 1 if rec.is_long else -1
        pnl = round((rec.exit_price - rec.fill_price) * rec.fill_qty * direction, 2)
        rec.status = Status.CLOSED
        self.journal.update(pos.row_id, rec, pnl)
        self._wallet_sell(sym, rec.fill_qty, rec.exit_price, "position closed")
        emoji = "🟢" if pnl >= 0 else "🔴"
        self._emit("alert", {
            "level": "success" if pnl >= 0 else "danger", "symbol": sym,
            "message": f"{sym} closed @ ₹{rec.exit_price:,.2f} — PnL ₹{pnl:,.2f}",
        })
        return f"{emoji} {sym} closed @ ₹{rec.exit_price:,.2f} — PnL ₹{pnl:,.2f}. Journaled."

    def _cmd_watch(self, sym: str, rest: list[str]) -> str:
        if len(rest) < 3:
            return f"Usage: /watch {sym} QTY PRICE STOP [TARGET]"
        qty, price, stop = int(float(rest[0])), float(rest[1]), float(rest[2])
        target = float(rest[3]) if len(rest) > 3 else round(price + 1.5 * (price - stop), 2)
        side = Side.BUY if stop < price else Side.SELL
        rec = Recommendation(
            symbol=sym, side=side, horizon=Horizon.INTRADAY,
            entry=price, stop=stop, target=target, qty=qty,
            confidence="—", reason="manual trade via /watch",
            status=Status.ACTIVE, fill_qty=qty, fill_price=price,
        )
        err = self._wallet_buy(sym, qty, price, "manual buy")
        if err:
            return f"❌ {err}"
        row = self.journal.record(rec)
        self.journal.update(row, rec)  # record() doesn't persist fill fields — a restart must restore them
        self.active[sym] = Position(rec, row)
        return (f"👁 Watching {sym}: {qty} @ ₹{price:,.2f} · "
                f"stop ₹{stop:,.2f} / target ₹{target:,.2f}")

    def _status_text(self) -> str:
        c = self.ctx
        age = ""
        if c.updated_at:
            mins = int((datetime.now(IST) - c.updated_at).total_seconds() // 60)
            age = f" ({mins}m ago)"
        stats = self.journal.day_stats()
        lines = [
            f"📊 Regime: {c.regime} · bias: {c.bias} · conf: {c.confidence}{age}",
        ]
        if c.notes:
            lines.append(f"🧠 {c.notes}")
        if c.avoid_symbols:
            lines.append(f"🚫 Avoiding: {', '.join(sorted(c.avoid_symbols))}")
        lines.append("⏸ paused" if self.paused else "▶️ generating ideas")
        if self.pending:
            lines.append("Pending: " + ", ".join(
                f"{r.side.value} {s} @₹{r.entry:,.2f}" for s, (r, _) in self.pending.items()))
        lines.append(self._positions_text())
        lines.append(f"Today: {stats['closed_today']} closed, realised ₹{stats['realised_pnl']:,.2f}")
        return "\n".join(lines)

    def _positions_text(self) -> str:
        if not self.active:
            return "Open positions: none"
        rows = []
        for sym, pos in self.active.items():
            r = pos.rec
            ltp = self.last_ltp.get(sym, r.fill_price)
            rows.append(
                f"• {sym} {r.fill_qty} @ ₹{r.fill_price:,.2f} → LTP ₹{ltp:,.2f} "
                f"(PnL ₹{r.pnl(ltp):,.2f}) stop ₹{r.stop:,.2f}"
            )
        return "Open positions:\n" + "\n".join(rows)

    # ------------------------------------------------------------- pre-open

    def _compute_daily_stats(self) -> dict[str, DailyStats]:
        """Paper's stocks-in-play screen: daily ATR14, 14-day avg volume, and the
        14-day average first-5-min-bar volume for RVOL. Sync Groww calls — run
        in a thread. All fields fail open (None) when history is unavailable."""
        stats: dict[str, DailyStats] = {}
        if getattr(self.feed, "synthetic", False):
            return stats
        from datetime import timezone
        today = datetime.now(IST).date()
        for sym in self.s.watchlist:
            ds = DailyStats()
            daily = self.feed.get_daily_candles(sym, days=40)
            if len(daily) >= 15:
                a = atr_indicator([c["high"] for c in daily], [c["low"] for c in daily],
                                  [c["close"] for c in daily], 14)
                ds.atr_daily = a[-1]
                vols = [c["volume"] for c in daily[-14:] if c.get("volume")]
                ds.adv_14d = sum(vols) / len(vols) if vols else None
                past_days = [c for c in daily if c["date"] < today.isoformat()]
                ds.prev_close = past_days[-1]["close"] if past_days else None
            intraday = self.feed.get_intraday_candles(sym, days=14, interval_minutes=5)
            first_vols: dict = {}
            for c in intraday:
                ts = datetime.fromtimestamp(c["ts"] / 1000, tz=timezone.utc).astimezone(IST)
                day = ts.date()
                if day not in first_vols and ts.time().hour == 9 and ts.time().minute == 15:
                    first_vols[day] = c["volume"]
            past = [v for d, v in first_vols.items() if d != today and v > 0]
            if past:
                ds.avg_first_bar_vol = sum(past) / len(past)
            stats[sym] = ds
            log.info("%s daily stats: ATRd=%s ADV=%s avg1stVol=%s", sym,
                     f"{ds.atr_daily:.1f}" if ds.atr_daily else "n/a",
                     f"{ds.adv_14d:,.0f}" if ds.adv_14d else "n/a",
                     f"{ds.avg_first_bar_vol:,.0f}" if ds.avg_first_bar_vol else "n/a")
        return stats

    # ------------------------------------------------------------- loops

    async def context_loop(self) -> None:
        """Deterministic market context: classify the index proxy's daily tape
        (indicators.market_regime — pure thresholds) into the shared ctx the
        strategies read. No LLM anywhere; fails open to neutral defaults."""
        from indicators import market_regime
        while True:
            try:
                candles = await asyncio.to_thread(
                    self.feed.get_daily_candles, self.s.index_symbol, 90)
            except Exception:  # noqa: BLE001 — context is a filter, never a blocker
                candles = []
            if len(candles) >= 35:
                regime = market_regime([c["high"] for c in candles],
                                       [c["low"] for c in candles],
                                       [c["close"] for c in candles])
                bias = {"bull_trend": "long", "bear_trend": "short"}.get(regime, "neutral")
                changed = (regime, bias) != (self.ctx.regime, self.ctx.bias)
                self.ctx = MarketContext(
                    regime=regime, bias=bias,
                    confidence="HIGH" if regime in ("bull_trend", "bear_trend") else "MEDIUM",
                    avoid_symbols=self.ctx.avoid_symbols,
                    notes=f"{self.s.index_symbol} daily tape: {regime}",
                    updated_at=datetime.now(IST),
                )
                if changed:
                    await self.notifier.send(
                        f"🧭 Regime update ({self.s.index_symbol}): {regime}, bias {bias}"
                    )
                    self._emit("alert", {
                        "level": "info",
                        "message": f"Regime: {regime}, bias {bias} ({self.s.index_symbol} daily)",
                    })
                self._emit_snapshot()
            await asyncio.sleep(1800)  # daily-candle input — 30 min is plenty

    async def data_loop(self) -> None:
        # Synthetic mode ticks 24/7 so the dashboard (charts, watchlist, PnL,
        # stop/target alerts) is demonstrable outside market hours. Strategy
        # time gates (LAST_ENTRY etc.) still apply unchanged — this widens
        # WHEN the demo feed flows, never what the rules do with it.
        synthetic = getattr(self.feed, "synthetic", False)
        while True:
            now = datetime.now(IST)
            if market_is_open(now) or synthetic:
                if self._session_date != now.date():
                    self._session_date = now.date()
                    self.strategy.reset_day()
                    self._squareoff_warned = False
                    log.info("new session %s — computing daily stats", now.date())
                    stats = await asyncio.to_thread(self._compute_daily_stats)
                    self.strategy.set_daily_stats(stats)
                    await asyncio.to_thread(self._load_prev_closes)
                for sym in self.s.watchlist:
                    tick = self.feed.get_tick(sym)
                    if not tick:
                        continue
                    self.last_ltp[sym] = tick.ltp
                    if self.paused or sym in self.active or sym in self.pending:
                        continue
                    sig = self.strategy.on_tick(sym, now, tick.ltp, tick.day_volume, self.ctx)
                    if sig:
                        await self.publish(sig)
                await self.monitor()
                if market_is_open(now):
                    await self.squareoff_check(now)
                    await self.positional_exit_review(now)
                import time as _time
                self.last_tick_at = _time.time()
                self._emit("tick", {"prices": dict(self.last_ltp),
                                    "market": market_phase(now),
                                    "server_time": now.isoformat()})
                await asyncio.sleep(self.s.poll_seconds)
            else:
                if now.time() > MARKET_CLOSE and self.pending:
                    self._expire_pending_intraday()
                    self._emit_snapshot()
                await asyncio.sleep(60)

    async def positional_loop(self) -> None:
        while True:
            today = datetime.now(IST).date()
            if self._positional_done != today:
                self._positional_done = today
                signals = await asyncio.to_thread(
                    positional_scan, self.feed, self.s.watchlist, self.ctx,
                    self.s.index_symbol,
                )
                # first scan of a new month: add 12-1 momentum rotation ideas
                month = (today.year, today.month)
                if self._rotation_done_month != month:
                    self._rotation_done_month = month
                    held = set(self.active) | set(self.pending)
                    rotation = await asyncio.to_thread(
                        momentum_rotation_scan, self.feed, self.s.watchlist,
                        self.ctx, held,
                    )
                    signals = signals + rotation
                for sig in signals:
                    if sig.symbol not in self.active and sig.symbol not in self.pending:
                        await self.publish(sig)
            await asyncio.sleep(1800)

    async def watchdog_loop(self) -> None:
        """Owner-facing liveness alarm: if the data loop stops ticking during
        market hours (API up, engine wedged), say so on Telegram — silence must
        never look like 'no signals today'. Re-alerts at most hourly."""
        import time as _time
        last_alerted = 0.0
        while True:
            await asyncio.sleep(120)
            now = datetime.now(IST)
            if not market_is_open(now) and not getattr(self.feed, "synthetic", False):
                continue
            stall = _time.time() - self.last_tick_at if self.last_tick_at else 0.0
            if stall > max(5 * self.s.poll_seconds, 180) and _time.time() - last_alerted > 3600:
                last_alerted = _time.time()
                await self._alert(
                    "danger", "",
                    f"🚨 WATCHDOG: no market data ticks for {int(stall)}s during "
                    "trading hours — stops are NOT being monitored. Check the "
                    "server/Groww connection.",
                    f"WATCHDOG: data loop stalled {int(stall)}s — stops unmonitored",
                )

    async def _supervise(self, name: str, factory) -> None:
        """Run a loop forever, restarting it after unexpected crashes. One sick
        loop must never take down the others — or close the journal while the
        web server is still answering requests (the exact failure we shipped
        once: a leaked exception in a loop closed the DB under FastAPI)."""
        while True:
            try:
                await factory()
                return  # a loop returning normally means shutdown
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 — log, alert once, back off, restart
                log.exception("%s crashed — restarting in 60s", name)
                self._emit("alert", {"level": "warning",
                                     "message": f"{name} crashed — restarting in 60s"})
                await asyncio.sleep(60)

    def _restore_state(self) -> str:
        """Rebuild pending/active from the journal after a restart — an engine
        reboot must NEVER silently stop monitoring open positions."""
        try:
            active_rows, pending_rows = self.journal.load_open()
        except Exception:  # noqa: BLE001 — a broken journal must not block startup
            log.exception("state restore failed — starting empty")
            return ""
        for row in active_rows:
            rec = Recommendation.from_journal_row(row)
            self.active[rec.symbol] = Position(rec, row["id"])
        for row in pending_rows:
            rec = Recommendation.from_journal_row(row)
            self.pending[rec.symbol] = (rec, row["id"])
        if not active_rows and not pending_rows:
            return ""
        return (f"♻️ Restored after restart: {len(active_rows)} open position(s) "
                f"[{', '.join(sorted(r['symbol'] for r in active_rows)) or '—'}], "
                f"{len(pending_rows)} pending idea(s). Monitoring resumed.")

    async def run(self) -> None:
        self._loop = asyncio.get_running_loop()
        restored = self._restore_state()
        if restored:
            await self.notifier.send(restored)
        try:
            await asyncio.to_thread(self._load_prev_closes)  # quotes before first session block
        except Exception:  # noqa: BLE001 — cosmetic, never block startup
            log.warning("prev-close preload failed — change-%% shows once the session loads")
        mode = "SYNTHETIC (test)" if getattr(self.feed, "synthetic", False) else "LIVE Groww data"
        await self.notifier.send(
            f"🤖 Trading assistant online — {mode}\n"
            f"Watchlist: {', '.join(self.s.watchlist)}\n"
            f"Risk/trade: {self.s.risk_per_trade_pct}% of ₹{self.s.capital:,.0f} · "
            f"ideas only, you place the trades. /help for commands."
        )
        tasks = [
            self._supervise("data_loop", self.data_loop),
            self._supervise("context_loop", self.context_loop),
            self._supervise("positional_loop", self.positional_loop),
            self._supervise("watchdog_loop", self.watchdog_loop),
            self._supervise("fast_loop", self.fast_loop),
        ]
        if self.notifier.enabled:
            tasks.append(self._supervise("command_loop", self.notifier.command_loop))
        try:
            await asyncio.gather(*tasks)
        finally:
            await self.notifier.close()
            self.journal.close()


# ----------------------------------------------------------------- smoke test

async def smoke() -> None:
    """Offline pipeline check: fabricated bars -> idea -> /bought -> target alert."""
    from strategy import Bar
    s = Settings()
    s.telegram_token = ""  # force console output
    engine = RecommendEngine(s)
    ctx = engine.ctx
    base = datetime.now(IST).replace(hour=9, minute=15, second=0, microsecond=0)

    sym = "RELIANCE"
    # Opening range: three 5-min bars around 2940
    bars = [
        Bar(base, 2940, 2946, 2936, 2941, 90_000),
        Bar(base + timedelta(minutes=5), 2941, 2945, 2938, 2943, 80_000),
        Bar(base + timedelta(minutes=10), 2943, 2947, 2940, 2944, 70_000),
    ]
    # Build enough post-OR bars for ATR/Supertrend, then a decisive breakout
    px = 2944.0
    for i in range(3, 17):
        px += 1.8
        bars.append(Bar(base + timedelta(minutes=5 * i), px - 1, px + 2.4, px - 2.2, px + 1.5, 60_000))
    bars.append(Bar(base + timedelta(minutes=5 * 17), px, px + 9, px - 1, px + 8.5, 150_000))

    sig = None
    for b in bars:
        sig = engine.strategy.on_bar(sym, b, ctx) or sig
    assert sig is not None, "smoke: breakout signal was not generated"
    await engine.publish(sig)

    print("\n--- user replies /bought ---")
    print(await engine.handle_command("bought", [sym]))

    rec = engine.active[sym].rec
    engine.last_ltp[sym] = rec.target + 1  # price runs to target
    await engine.monitor()

    print("\n--- user replies /sold ---")
    print(await engine.handle_command("sold", [sym, str(rec.target)]))
    print("\n--- /status ---")
    print(await engine.handle_command("status", []))
    engine.journal.close()
    print("\nSMOKE TEST PASSED ✅")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)-10s %(levelname)-7s %(message)s",
    )
    if "--smoke" in sys.argv:
        asyncio.run(smoke())
        return
    settings = Settings()
    engine = RecommendEngine(settings)
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()
