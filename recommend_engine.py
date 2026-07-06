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
from fable_analyst import FableAnalyst
from groww_adapter import make_feed
from journal import Journal
from notifier import Notifier
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


class RecommendEngine:
    def __init__(self, settings: Settings, event_bus: EventBus | None = None):
        self.s = settings
        self.bus = event_bus
        self.notifier = Notifier(settings)
        self.feed = make_feed(settings)
        self.journal = Journal(settings)
        self.analyst = FableAnalyst(settings)
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
        self.notifier.on_command(self.handle_command)

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
            "positions": [pos.rec.to_dict(self.last_ltp.get(sym))
                         for sym, pos in self.active.items()],
            "day_stats": self.journal.day_stats(),
            "market": market_phase(datetime.now(IST)),
            "quotes": self._quotes(),
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
        qty = suggested_qty(sig.entry, sig.stop, self.s)
        if qty <= 0:
            log.info("%s signal skipped — qty 0 under current risk settings", sig.symbol)
            return
        ok, reason = portfolio_allows(
            len(self.active) + len(self.pending),
            self._open_risk(),
            abs(sig.entry - sig.stop) * qty,
            self.s,
        )
        if not ok:
            log.info("%s signal skipped — %s", sig.symbol, reason)
            return
        rec = Recommendation(
            symbol=sig.symbol, side=sig.side, horizon=sig.horizon,
            entry=sig.entry, stop=sig.stop, target=sig.target,
            qty=qty, confidence=sig.confidence, reason=sig.reason,
        )
        try:
            rec.why = await asyncio.wait_for(self.analyst.why_line(rec, self.ctx), 30)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001 — idea must still go out
            rec.why = ""
        row = self.journal.record(rec)
        self.pending[rec.symbol] = (rec, row)
        await self.notifier.send(rec.format_telegram())
        self._emit("alert", {"level": "info", "message": f"New idea: {rec.side.value} {rec.symbol}"})
        self._emit_snapshot()
        log.info("idea pushed: %s %s @%.2f", rec.side.value, rec.symbol, rec.entry)

    # ------------------------------------------------------------- monitoring

    async def monitor(self) -> None:
        for sym, pos in list(self.active.items()):
            ltp = self.last_ltp.get(sym)
            if ltp is None:
                continue
            r = pos.rec
            hit_stop = ltp <= r.stop if r.is_long else ltp >= r.stop
            hit_target = ltp >= r.target if r.is_long else ltp <= r.target
            if hit_stop and not pos.alerted_stop:
                pos.alerted_stop = True
                await self.notifier.send(
                    f"🔴 SELL {sym} NOW — stop ₹{r.stop:,.2f} hit (LTP ₹{ltp:,.2f})\n"
                    f"Open PnL ₹{r.pnl(ltp):,.2f} on {r.fill_qty} qty\n"
                    f"Reply /sold {sym} [price] once you exit."
                )
                self._emit("alert", {
                    "level": "danger", "symbol": sym,
                    "message": f"SELL {sym} NOW — stop ₹{r.stop:,.2f} hit (LTP ₹{ltp:,.2f})",
                })
            elif hit_target and not pos.alerted_target:
                pos.alerted_target = True
                await self.notifier.send(
                    f"🟢 {sym} TARGET ₹{r.target:,.2f} hit (LTP ₹{ltp:,.2f}) — book profit "
                    f"or trail your stop to ₹{r.entry:,.2f} (entry).\n"
                    f"Open PnL ₹{r.pnl(ltp):,.2f} on {r.fill_qty} qty\n"
                    f"Reply /sold {sym} [price] once you exit."
                )
                self._emit("alert", {
                    "level": "success", "symbol": sym,
                    "message": f"{sym} TARGET ₹{r.target:,.2f} hit (LTP ₹{ltp:,.2f}) — book profit",
                })

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

    # ------------------------------------------------------------- commands

    # Commands that change state — the ones that must push a fresh snapshot to
    # every connected dashboard client (and, symmetrically, are reachable from
    # either Telegram or the web UI so both surfaces always agree).
    _MUTATING = {"pause", "resume", "bought", "skip", "sold", "watch"}

    async def handle_command(self, cmd: str, args: list[str]) -> str:
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
        if cmd in ("bought", "skip", "sold", "watch"):
            if not args:
                return f"Usage: /{cmd} SYMBOL …"
            sym = args[0].upper()
            if cmd == "bought":
                return await self._cmd_bought(sym, args[1:])
            if cmd == "skip":
                return self._cmd_skip(sym)
            if cmd == "sold":
                return self._cmd_sold(sym, args[1:])
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
        row = self.journal.record(rec)
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
        for sym in self.s.watchlist:
            ds = DailyStats()
            daily = self.feed.get_daily_candles(sym, days=40)
            if len(daily) >= 15:
                a = atr_indicator([c["high"] for c in daily], [c["low"] for c in daily],
                                  [c["close"] for c in daily], 14)
                ds.atr_daily = a[-1]
                vols = [c["volume"] for c in daily[-14:] if c.get("volume")]
                ds.adv_14d = sum(vols) / len(vols) if vols else None
            intraday = self.feed.get_intraday_candles(sym, days=14, interval_minutes=5)
            first_vols: dict = {}
            for c in intraday:
                ts = datetime.fromtimestamp(c["ts"] / 1000, tz=timezone.utc).astimezone(IST)
                day = ts.date()
                if day not in first_vols and ts.time().hour == 9 and ts.time().minute == 15:
                    first_vols[day] = c["volume"]
            today = datetime.now(IST).date()
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

    async def fable_loop(self) -> None:
        while True:
            now = datetime.now(IST)
            if market_is_open(now) or self.ctx.updated_at is None:
                snapshot = dict(list(self.last_ltp.items())[:10])
                try:
                    new = await asyncio.wait_for(
                        self.analyst.market_context(self.s.watchlist, snapshot, self.ctx),
                        120,
                    )
                except asyncio.TimeoutError:
                    new = None
                if new:
                    changed = (new.regime, new.bias) != (self.ctx.regime, self.ctx.bias)
                    self.ctx = new
                    if changed:
                        await self.notifier.send(
                            f"🧭 Context update — regime: {new.regime}, bias: {new.bias}\n{new.notes}"
                        )
                        self._emit("alert", {
                            "level": "info",
                            "message": f"Context: regime={new.regime}, bias={new.bias} — {new.notes}",
                        })
                    self._emit_snapshot()
            await asyncio.sleep(self.s.fable_refresh_minutes * 60)

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
                for sig in signals:
                    if sig.symbol not in self.active and sig.symbol not in self.pending:
                        await self.publish(sig)
            await asyncio.sleep(1800)

    async def _supervise(self, name: str, factory) -> None:
        """Run a loop forever, restarting it after unexpected crashes. One sick
        loop must never take down the others — or close the journal while the
        web server is still answering requests (the exact failure we shipped
        once: a leaked exception in fable_loop closed the DB under FastAPI)."""
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

    async def run(self) -> None:
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
            self._supervise("fable_loop", self.fable_loop),
            self._supervise("positional_loop", self.positional_loop),
        ]
        if self.notifier.enabled:
            tasks.append(self._supervise("command_loop", self.notifier.command_loop))
        try:
            await asyncio.gather(*tasks)
        finally:
            await self.analyst.close()
            await self.notifier.close()
            self.journal.close()


# ----------------------------------------------------------------- smoke test

async def smoke() -> None:
    """Offline pipeline check: fabricated bars -> idea -> /bought -> target alert."""
    import os
    os.environ["FABLE_ENABLED"] = "false"
    from strategy import Bar
    s = Settings()
    s.fable_enabled = False
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
