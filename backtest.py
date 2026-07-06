"""Hand-rolled bar-by-bar backtester for both strategies, run against Groww
historical data before trusting either strategy with real money.

    python backtest.py intraday RELIANCE TCS --days 60
    python backtest.py positional RELIANCE TCS INFY --days 730

Why hand-rolled instead of a framework (backtesting.py / vectorbt / etc.):
this project has exactly two fully-specified, imperative rule sets, not a
strategy-search workload — a small event loop gives full, auditable control
over the one decision that actually swings results (see below), at zero new
dependencies, and it replays the *exact* production code paths
(`ORBVWAPStrategy.on_bar` / `positional.scan_symbol`) so a backtest and a
live day can never silently diverge in signal logic.

THE SAME-BAR AMBIGUITY — the one thing that matters most here:
When a single bar's high/low range contains BOTH the stop and the target, OHLC
data alone cannot tell you which was actually hit first intraday (only tick
data can). Public backtesting libraries converge on one convention:
vectorbt's `ohlc_stop_choice_nb` docstring says it plainly — "we pessimistically
assume that SL comes before TP" — and backtesting.py and freqtrade both default
the same way. This code follows that convention (STOP WINS on an ambiguous
bar) and reports the ambiguous-bar rate as a first-class metric: if it's high,
treat the backtest's edge with proportionally less confidence.

No look-ahead: intraday signals are generated bar-by-bar via the same
`on_bar()` the live engine uses, so a signal at bar i can only ever see bars
0..i. Positional signals are computed from `candles[:t+1]` (truncated to day
t) but FILLED at day t+1's open — the live engine treats a positional
"close" as "current intraday price" (fine when a human sees the alert live),
but a backtest replaying only daily OHLC cannot claim a fill at a price that
was only known once the market had already closed.
"""

from __future__ import annotations

import argparse
import logging
import random
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone

from config import IST, Settings
from costs import round_trip_costs
from groww_adapter import make_feed
from indicators import atr as atr_indicator
from indicators import chandelier_stop, sma
from positional import MIN_HISTORY, scan_symbol
from recommendation import Side
from risk_manager import suggested_qty
from strategy import MARKET_CLOSE, Bar, DailyStats, MarketContext, ORBVWAPStrategy

log = logging.getLogger("backtest")

MIN_TRUSTWORTHY_TRADES = 100  # per public backtest-methodology consensus (see module docstring's research)


@dataclass
class Trade:
    symbol: str
    side: Side
    entry_date: str
    entry: float
    stop: float
    target: float
    qty: int
    exit: float
    exit_reason: str      # "stop" | "target" | "stop_ambiguous" | "eod_close" | "time_stop"
    pnl: float             # NET of transaction costs + slippage (see costs.py)
    r_multiple: float      # net pnl per unit of initial risk — size-independent
    costs: float = 0.0     # ₹ round-trip charges + slippage deducted from pnl


def _clean_candles(candles: list[dict], label: str, warnings: list[str]) -> list[dict]:
    """OHLC sanity gate at the loader boundary: drop bars where high < low,
    high/low don't bracket open/close, or prices are non-positive."""
    clean = [
        c for c in candles
        if c["low"] > 0
        and c["high"] >= c["low"]
        and c["high"] >= max(c["open"], c["close"])
        and c["low"] <= min(c["open"], c["close"])
    ]
    dropped = len(candles) - len(clean)
    if dropped:
        warnings.append(f"{label}: dropped {dropped} malformed OHLC bars at load")
    return clean


def _monte_carlo_dd(pnls: list[float], start_capital: float,
                    iters: int = 1000, seed: int = 42) -> dict:
    """Shuffle the SAME trades' order `iters` times and measure max drawdown of
    each sequence. The observed curve is one ordering among many — p95 says how
    deep 5% of equally-likely orderings drew down, i.e. sequencing luck."""
    rng = random.Random(seed)
    dds = []
    seq = list(pnls)
    for _ in range(iters):
        rng.shuffle(seq)
        eq, peak, dd = start_capital, start_capital, 0.0
        for p in seq:
            eq += p
            peak = max(peak, eq)
            dd = max(dd, peak - eq)
        dds.append(dd)
    dds.sort()
    return {
        "p50_max_dd": round(dds[len(dds) // 2], 2),
        "p95_max_dd": round(dds[int(len(dds) * 0.95)], 2),
    }


@dataclass
class BacktestResult:
    strategy: str
    trades: list[Trade] = field(default_factory=list)
    ambiguous_bars: int = 0
    starting_capital: float = 0.0
    ending_capital: float = 0.0
    equity_curve: list[float] = field(default_factory=list)  # after each trade
    warnings: list[str] = field(default_factory=list)
    buy_hold_return_pct: dict = field(default_factory=dict)  # symbol -> % over same window

    def _diagnostics(self, n: int, win_rate: float, profit_factor: float | None,
                     max_dd: float) -> list[str]:
        """Rule-based post-backtest review (thresholds per QuantDinger's
        templated strategy review) — cheap flags, not verdicts."""
        out = []
        if 0 < n < 5:
            out.append("sample far too small (<5 trades) — result is noise")
        if profit_factor is not None and profit_factor < 1.0:
            out.append(f"profit factor {profit_factor} < 1 — strategy lost money after costs")
        if n >= 5 and win_rate < 35.0:
            out.append(f"win rate {win_rate}% < 35% — verify the R:R makes this survivable")
        if self.starting_capital and max_dd >= 0.10 * self.starting_capital:
            out.append(f"max drawdown ₹{max_dd:,.0f} ≥ 10% of capital — cap position size")
        run = worst = 0
        for t in self.trades:
            run = run + 1 if t.pnl <= 0 else 0
            worst = max(worst, run)
        if worst >= 3:
            out.append(f"{worst} consecutive losses at worst — consider a cooldown after streaks")
        return out

    def summary(self) -> dict:
        n = len(self.trades)
        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]
        r_values = [t.r_multiple for t in self.trades]
        gross_win = sum(t.pnl for t in wins)
        gross_loss = -sum(t.pnl for t in losses)
        peak = self.starting_capital
        max_dd = 0.0
        for eq in self.equity_curve:
            peak = max(peak, eq)
            max_dd = max(max_dd, peak - eq)
        years = None
        if self.trades:
            try:
                d0 = datetime.fromisoformat(self.trades[0].entry_date)
                d1 = datetime.fromisoformat(self.trades[-1].entry_date)
                years = max((d1 - d0).days / 365.25, 1 / 365.25)
            except ValueError:
                years = None
        total_pnl = round(sum(t.pnl for t in self.trades), 2)
        total_return_pct = (
            (self.ending_capital / self.starting_capital - 1) * 100
            if self.starting_capital else 0.0
        )
        cagr_pct = (
            ((self.ending_capital / self.starting_capital) ** (1 / years) - 1) * 100
            if years and self.starting_capital and self.ending_capital > 0 else None
        )
        max_dd_pct = 100 * max_dd / self.starting_capital if self.starting_capital else 0.0
        win_rate = round(100 * len(wins) / n, 1) if n else 0.0
        profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else None

        by_exit: dict = {}
        for t in self.trades:
            b = by_exit.setdefault(t.exit_reason, {"count": 0, "wins": 0, "total_pnl": 0.0})
            b["count"] += 1
            b["wins"] += 1 if t.pnl > 0 else 0
            b["total_pnl"] = round(b["total_pnl"] + t.pnl, 2)
        for b in by_exit.values():
            b["win_rate_pct"] = round(100 * b.pop("wins") / b["count"], 1)

        return {
            "strategy": self.strategy,
            "n_trades": n,
            "win_rate_pct": win_rate,
            "profit_factor": profit_factor,
            "avg_r_multiple": round(statistics.mean(r_values), 2) if r_values else 0.0,
            "stdev_r": round(statistics.pstdev(r_values), 2) if len(r_values) > 1 else 0.0,
            "total_pnl": total_pnl,
            "total_costs": round(sum(t.costs for t in self.trades), 2),
            "total_return_pct": round(total_return_pct, 1),
            "cagr_pct": round(cagr_pct, 1) if cagr_pct is not None else None,
            "max_drawdown": round(max_dd, 2),
            "recovery_factor": round(total_pnl / max_dd, 2) if max_dd > 0 else None,
            "calmar_ratio": (
                round(cagr_pct / max_dd_pct, 2)
                if cagr_pct is not None and max_dd_pct > 0 else None
            ),
            "monte_carlo": (
                _monte_carlo_dd([t.pnl for t in self.trades], self.starting_capital)
                if n >= 5 else None
            ),
            "by_exit_reason": by_exit,
            "buy_hold_return_pct": self.buy_hold_return_pct,
            "ambiguous_bar_exits": self.ambiguous_bars,
            "ambiguous_bar_rate_pct": (
                round(100 * self.ambiguous_bars / n, 1) if n else 0.0
            ),
            "starting_capital": self.starting_capital,
            "ending_capital": round(self.ending_capital, 2),
            "diagnostics": self._diagnostics(n, win_rate, profit_factor, max_dd),
            "warnings": self.warnings,
        }


def _resolve_exit(is_long: bool, bar_open: float, bar_high: float, bar_low: float,
                  stop: float, target: float) -> tuple[float, str] | None:
    """One bar's worth of exit-check, gap-aware, stop-wins-on-ambiguity."""
    hit_stop = bar_low <= stop if is_long else bar_high >= stop
    hit_target = bar_high >= target if is_long else bar_low <= target
    if not hit_stop and not hit_target:
        return None
    if hit_stop and hit_target:
        # Gapped straight past both in one bar — you got whichever the open
        # cleared, at the open (can't do better than the market's own gap).
        if is_long and bar_open <= stop:
            return bar_open, "stop_ambiguous"
        if not is_long and bar_open >= stop:
            return bar_open, "stop_ambiguous"
        return stop, "stop_ambiguous"  # true same-bar ambiguity — stop wins (see docstring)
    if hit_stop:
        gapped = (is_long and bar_open <= stop) or (not is_long and bar_open >= stop)
        return (bar_open if gapped else stop), "stop"
    gapped = (is_long and bar_open >= target) or (not is_long and bar_open <= target)
    return (bar_open if gapped else target), "target"


# --------------------------------------------------------------- intraday

def backtest_intraday(feed, settings: Settings, symbols: list[str], days: int) -> BacktestResult:
    result = BacktestResult(strategy="intraday_orb_vwap", starting_capital=settings.capital)
    capital = settings.capital
    strat = ORBVWAPStrategy(settings)
    ctx = MarketContext()  # no historical Fable regime available — rules only

    for symbol in symbols:
        intraday = _clean_candles(
            feed.get_intraday_candles(symbol, days=days, interval_minutes=settings.bar_minutes),
            f"{symbol} intraday", result.warnings)
        daily = _clean_candles(feed.get_daily_candles(symbol, days=days + 30),
                               f"{symbol} daily", result.warnings)
        if len(intraday) < 50 or len(daily) < 20:
            result.warnings.append(f"{symbol}: insufficient history, skipped")
            continue
        result.buy_hold_return_pct[symbol] = round(
            (intraday[-1]["close"] / intraday[0]["close"] - 1) * 100, 1)

        by_day: dict = {}
        for c in intraday:
            ts = datetime.fromtimestamp(c["ts"] / 1000, tz=timezone.utc).astimezone(IST)
            by_day.setdefault(ts.date(), []).append((ts, c))
        trading_days = sorted(by_day)

        # trailing 14-session first-5-min-bar volume, computed once, reused with an
        # index that only ever looks at days strictly before the current one
        first_bar_vol_by_day = {}
        for day, rows in by_day.items():
            rows.sort(key=lambda r: r[0])
            first = rows[0][1]
            first_bar_vol_by_day[day] = first["volume"]

        for i, day in enumerate(trading_days):
            if i < 15:
                continue  # need trailing history for ATR14 / ADV14 / avg-first-bar-vol
            trailing_daily = [c for c in daily if c["date"] < day.isoformat()][-20:]
            stats = DailyStats()
            if len(trailing_daily) >= 15:
                a = atr_indicator([c["high"] for c in trailing_daily], [c["low"] for c in trailing_daily],
                                  [c["close"] for c in trailing_daily], 14)
                stats.atr_daily = a[-1]
                vols = [c["volume"] for c in trailing_daily[-14:] if c.get("volume")]
                stats.adv_14d = sum(vols) / len(vols) if vols else None
            past_first_vols = [v for d, v in first_bar_vol_by_day.items() if d < day and v > 0]
            if past_first_vols:
                stats.avg_first_bar_vol = sum(past_first_vols[-14:]) / len(past_first_vols[-14:])

            strat.set_daily_stats({symbol: stats})
            strat.reset_day()
            rows = sorted(by_day[day], key=lambda r: r[0])
            signal = None
            sig_idx = None
            for idx, (ts, c) in enumerate(rows):
                bar = Bar(ts, c["open"], c["high"], c["low"], c["close"], c["volume"])
                sig = strat.on_bar(symbol, bar, ctx)
                if sig:
                    signal, sig_idx = sig, idx
                    break
            if signal is None:
                continue

            is_long = signal.side == Side.BUY
            qty = suggested_qty(signal.entry, signal.stop, settings)
            if qty <= 0:
                continue
            exit_price, exit_reason = signal.entry, "eod_close"
            for ts, c in rows[sig_idx + 1:]:
                if ts.time() >= MARKET_CLOSE:
                    break
                if c["high"] == c["low"]:
                    continue  # circuit-locked bar: one-sided book, no realistic fill
                r = _resolve_exit(is_long, c["open"], c["high"], c["low"], signal.stop, signal.target)
                if r:
                    exit_price, exit_reason = r
                    break
            else:
                exit_price = rows[-1][1]["close"]  # forced square-off at day's last bar
            if exit_reason == "stop_ambiguous":
                result.ambiguous_bars += 1

            direction = 1 if is_long else -1
            gross = (exit_price - signal.entry) * qty * direction
            costs = round_trip_costs("MIS", signal.entry, exit_price, qty, settings.slippage_pct)
            pnl = round(gross - costs, 2)
            risk = abs(signal.entry - signal.stop) * qty
            capital += pnl
            result.equity_curve.append(capital)
            result.trades.append(Trade(
                symbol, signal.side, day.isoformat(), signal.entry, signal.stop,
                signal.target, qty, round(exit_price, 2), exit_reason, pnl,
                round(pnl / risk, 2) if risk > 0 else 0.0, costs,
            ))

    result.ending_capital = capital
    if len(result.trades) < MIN_TRUSTWORTHY_TRADES:
        result.warnings.append(
            f"only {len(result.trades)} trades — below the ~{MIN_TRUSTWORTHY_TRADES} "
            "commonly cited before trusting a backtest's win rate/profit factor; "
            "widen the date range or symbol list before acting on this result"
        )
    return result


# -------------------------------------------------------------- positional

def _index_entry_gate(index_candles: list[dict]) -> set:
    """Dates on which the Faber 200-DMA index gate PERMITS new entries: the
    index closed above its 200-SMA as of that date (no lookahead — each date's
    SMA uses closes up to and including that date, known by that evening).
    Empty index history -> empty set means 'gate unavailable', treated as
    fail-open by the caller."""
    closes = [c["close"] for c in index_candles]
    sma200 = sma(closes, 200)
    return {
        c["date"] for c, s in zip(index_candles, sma200)
        if s is not None and c["close"] > s
    }


def backtest_positional(feed, settings: Settings, symbols: list[str], days: int,
                        index_candles: list[dict] | None = None) -> BacktestResult:
    result = BacktestResult(strategy="positional_cascade", starting_capital=settings.capital)
    capital = settings.capital
    ctx = MarketContext()
    gate_dates = _index_entry_gate(index_candles) if index_candles else None
    if index_candles and not gate_dates:
        result.warnings.append("index gate: no dates above 200-DMA in window — no entries taken")

    for symbol in symbols:
        candles = _clean_candles(feed.get_daily_candles(symbol, days=days),
                                 f"{symbol} daily", result.warnings)
        if len(candles) < MIN_HISTORY + 20:
            result.warnings.append(f"{symbol}: insufficient daily history, skipped")
            continue
        result.buy_hold_return_pct[symbol] = round(
            (candles[-1]["close"] / candles[MIN_HISTORY]["close"] - 1) * 100, 1)

        in_position = False
        entry = stop = target = initial_risk_per_share = 0.0
        qty = 0
        entry_date = ""

        t = MIN_HISTORY
        while t < len(candles) - 1:
            if not in_position:
                # index gate first (cheap): entries only while the index proxy
                # was above its 200-DMA as of the SIGNAL day
                if gate_dates is not None and candles[t]["date"] not in gate_dates:
                    t += 1
                    continue
                sig = scan_symbol(symbol, candles[: t + 1], ctx)  # only sees days 0..t
                t += 1
                if not sig:
                    continue
                # fill at next day's open — day t's close wasn't tradeable until
                # the market had already closed, unlike the live engine which
                # reads "close" as "current intraday price" for a human watching live
                entry = candles[t]["open"]
                initial_risk_per_share = sig.entry - sig.stop
                reward_per_share = sig.target - sig.entry
                stop = entry - initial_risk_per_share
                target = entry + reward_per_share
                qty = suggested_qty(entry, stop, settings)
                if qty > 0:
                    in_position = True
                    entry_date = candles[t]["date"]
                continue

            day = candles[t]
            # trail the stop with a Chandelier level computed from days strictly
            # before today, then check *today's* low against that fixed level —
            # never derive today's trailing level from today's own high.
            prior = candles[:t]
            if len(prior) >= 22:
                highs, lows, closes = ([c["high"] for c in prior], [c["low"] for c in prior],
                                       [c["close"] for c in prior])
                chand = chandelier_stop(highs, lows, closes, 22, 3.0)
                if chand is not None:
                    stop = max(stop, chand)  # long-only trailing stop only ratchets up

            circuit_locked = day["high"] == day["low"]  # one-sided book, no realistic fill
            r = None if circuit_locked else _resolve_exit(
                True, day["open"], day["high"], day["low"], stop, target)
            if r is None and t == len(candles) - 2:
                r = (candles[t + 1]["close"], "time_stop")  # backtest window ended, mark-to-market close
            if r:
                exit_price, exit_reason = r
                if exit_reason == "stop_ambiguous":
                    result.ambiguous_bars += 1
                gross = (exit_price - entry) * qty
                trade_costs = round_trip_costs("CNC", entry, exit_price, qty, settings.slippage_pct)
                pnl = round(gross - trade_costs, 2)
                risk = initial_risk_per_share * qty
                capital += pnl
                result.equity_curve.append(capital)
                result.trades.append(Trade(
                    symbol, Side.BUY, entry_date, entry, stop, target,
                    qty, round(exit_price, 2), exit_reason, pnl,
                    round(pnl / risk, 2) if risk > 0 else 0.0, trade_costs,
                ))
                in_position = False
            t += 1

    result.ending_capital = capital
    if len(result.trades) < MIN_TRUSTWORTHY_TRADES:
        result.warnings.append(
            f"only {len(result.trades)} trades — positional strategies trade rarely "
            f"(typically 10-30/symbol/year); pool more symbols or years before trusting "
            f"this result (~{MIN_TRUSTWORTHY_TRADES}+ trades is the commonly cited floor)"
        )
    return result


# -------------------------------------------------------------------- CLI

def _print_summary(result: BacktestResult) -> None:
    s = result.summary()
    print(f"\n=== {s['strategy']} — {s['n_trades']} trades (PnL net of costs+slippage) ===")
    if s["n_trades"] == 0:
        print("No trades generated — check symbol history length / Groww credentials.")
    else:
        print(f"Win rate:        {s['win_rate_pct']}%")
        print(f"Profit factor:   {s['profit_factor']}")
        print(f"Avg R-multiple:  {s['avg_r_multiple']}  (stdev {s['stdev_r']})")
        print(f"Total PnL:       ₹{s['total_pnl']:,.2f}  (₹{s['total_costs']:,.2f} paid in costs)")
        print(f"Total return:    {s['total_return_pct']}%"
              + (f"  (CAGR {s['cagr_pct']}%)" if s['cagr_pct'] is not None else ""))
        print(f"Max drawdown:    ₹{s['max_drawdown']:,.2f}"
              + (f"  (recovery factor {s['recovery_factor']})" if s['recovery_factor'] else ""))
        if s["calmar_ratio"] is not None:
            print(f"Calmar ratio:    {s['calmar_ratio']}")
        if s["monte_carlo"]:
            mc = s["monte_carlo"]
            print(f"Sequencing risk: same trades reshuffled 1000× → median max-DD "
                  f"₹{mc['p50_max_dd']:,.0f}, 95th pct ₹{mc['p95_max_dd']:,.0f}")
        if s["by_exit_reason"]:
            print("Exit attribution:")
            for reason, b in sorted(s["by_exit_reason"].items()):
                print(f"  {reason:<16} {b['count']:>4} trades, {b['win_rate_pct']}% win, "
                      f"₹{b['total_pnl']:,.2f}")
        if s["buy_hold_return_pct"]:
            avg_bh = sum(s["buy_hold_return_pct"].values()) / len(s["buy_hold_return_pct"])
            print(f"Buy & hold:      avg {avg_bh:.1f}% over the same window "
                  f"(strategy did {s['total_return_pct']}%)")
        print(f"Ambiguous exits: {s['ambiguous_bar_exits']} ({s['ambiguous_bar_rate_pct']}% of trades) "
              "— stop-wins convention applied, see module docstring")
        print(f"Capital:         ₹{s['starting_capital']:,.0f} → ₹{s['ending_capital']:,.2f}")
    for d in s["diagnostics"]:
        print(f"🔎 {d}")
    for w in s["warnings"]:
        print(f"⚠️  {w}")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("strategy", choices=["intraday", "positional"])
    p.add_argument("symbols", nargs="+")
    p.add_argument("--days", type=int, default=60)
    p.add_argument("--no-index-gate", action="store_true",
                   help="disable the Faber 200-DMA index gate (positional only)")
    args = p.parse_args()

    settings = Settings()
    feed = make_feed(settings)
    if getattr(feed, "synthetic", False):
        print("No Groww credentials in .env — backtesting needs real historical data.")
        print("Fill GROWW_API_KEY / GROWW_TOTP_SECRET in .env and re-run.")
        sys.exit(1)

    if args.strategy == "intraday":
        result = backtest_intraday(feed, settings, [s.upper() for s in args.symbols], args.days)
    else:
        index_candles = None
        if not args.no_index_gate:
            index_candles = feed.get_daily_candles(settings.index_symbol, days=args.days + 320)
            if not index_candles:
                print(f"(index gate: no history for {settings.index_symbol} — running ungated)")
        result = backtest_positional(feed, settings, [s.upper() for s in args.symbols],
                                     args.days, index_candles)
    _print_summary(result)


if __name__ == "__main__":
    main()
