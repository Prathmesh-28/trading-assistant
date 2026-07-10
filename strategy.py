"""Intraday engine on 5-minute bars, plus the shared MarketContext filter.

Math sourced from the best-evidenced public implementations (see the repo
survey in the project notes):

PRIMARY — Opening Range Breakout, Zarattini/Barbon/Aziz variant
(SSRN 4729284 / 4416622; backtested Sharpe 2.81 on stocks-in-play 2016-23):
  - Opening range  = first ORB_MINUTES (default: the first 5-min bar, per paper)
  - Direction      = only long if the first bar closed up (close > open)
  - Participation  = RVOL: today's first-bar volume / 14-day avg first-bar
                     volume must be > 1.0 (skipped when history unavailable)
  - Entry          = a later 5-min bar CLOSES above the OR high
                     AND close > session VWAP        (QuantConnect port filter)
                     AND Supertrend(10,3) on 5-min not explicitly down
  - Stop           = max(OR low, entry − 0.10 · dailyATR14)   (paper's number)
  - Target         = entry + RISK_REWARD · risk (default 2R); square off by close
  - Eligibility    = price > ₹100, 14d avg volume ≥ 1M sh, dailyATR ≥ 0.5% of
                     price (paper's stocks-in-play screen, ported to NSE)

SECONDARY — LazyBear/TTM Squeeze Momentum release (BB 20/2.0 inside KC 20/1.5):
  fires on mid-day volatility compressions the ORB misses. Entry when a squeeze
  that lasted ≥ 6 bars releases with momentum positive and rising, above VWAP.
  Stop = entry − 2 · ATR14(5m); same R:R target.

One idea per symbol per day.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime, timedelta

from config import IST, Settings
from indicators import SessionVWAP, atr, squeeze_momentum, supertrend
from recommendation import Horizon, Side

log = logging.getLogger("strategy")

# NSE trading holidays 2026 (edit yearly; weekends handled separately)
NSE_HOLIDAYS_2026 = {
    "2026-01-26", "2026-02-17", "2026-03-04", "2026-03-26", "2026-04-01",
    "2026-04-03", "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26",
    "2026-08-15", "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-10",
    "2026-11-11", "2026-12-25",
}

MARKET_OPEN = dtime(9, 15)
MARKET_CLOSE = dtime(15, 30)
SQUARE_OFF_WARN = dtime(15, 10)
LAST_ENTRY = dtime(14, 30)
PRE_OPEN_START = dtime(9, 0)   # NSE pre-open session 09:00–09:15

MIN_PRICE = 100.0          # ₹ port of the paper's $5 floor
MIN_ADV = 1_000_000        # 14-day average daily volume, shares
MIN_ATR_PCT = 0.5          # daily ATR must be ≥ 0.5% of price
STOP_ATR_FRACTION = 0.10   # stop distance = 10% of daily ATR (paper's exact number)
RVOL_MIN = 1.0
SQUEEZE_MIN_BARS = 6
GAP_GO_MIN_PCT = 2.0       # open gap vs prev close for the Gap-and-Go variant
GAP_GO_RVOL_MIN = 2.0      # gap days need real participation, not just a mark-up open


def is_trading_day(now: datetime) -> bool:
    return now.weekday() < 5 and now.date().isoformat() not in NSE_HOLIDAYS_2026


def market_is_open(now: datetime) -> bool:
    if not is_trading_day(now):
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def _next_weekday(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5 or d.isoformat() in NSE_HOLIDAYS_2026:
        d += timedelta(days=1)
    return d


def market_phase(now: datetime) -> dict:
    """NSE session phase for the dashboard header. Weekend-aware but
    holiday-naive (exchange holidays show as a normal weekday). All
    timestamps ISO with tz so the client can render live countdowns."""
    tz = now.tzinfo

    def at(d: date, t: dtime) -> str:
        return datetime.combine(d, t, tzinfo=tz).isoformat()

    d = now.date()
    if now.weekday() < 5 and now.time() < MARKET_OPEN:
        if now.time() >= PRE_OPEN_START:
            return {"phase": "pre-open", "next_open": at(d, MARKET_OPEN), "next_close": None}
        return {"phase": "closed", "next_open": at(d, MARKET_OPEN), "next_close": None}
    if market_is_open(now):
        return {"phase": "open", "next_open": None, "next_close": at(d, MARKET_CLOSE)}
    nd = _next_weekday(d)
    return {"phase": "closed", "next_open": at(nd, MARKET_OPEN), "next_close": None}


@dataclass
class MarketContext:
    """Deterministic session context (indicators.market_regime on the index
    proxy, plus any manual avoid-list) — read by the strategies as a filter."""
    regime: str = "unknown"          # trending / choppy / volatile / unknown
    bias: str = "neutral"            # long / short / neutral
    confidence: str = "LOW"
    avoid_symbols: set = field(default_factory=set)
    notes: str = ""
    updated_at: datetime | None = None

    def allows(self, symbol: str, side: Side) -> bool:
        if symbol in self.avoid_symbols:
            return False
        if side == Side.BUY and self.bias == "short":
            return False
        if side == Side.SELL and self.bias == "long":
            return False
        return True


@dataclass
class DailyStats:
    """Pre-open numbers from daily/intraday history (None = unknown, fail open)."""
    atr_daily: float | None = None
    avg_first_bar_vol: float | None = None
    adv_14d: float | None = None
    prev_close: float | None = None   # yesterday's close, for gap detection

    def eligible(self, price: float) -> bool:
        if price < MIN_PRICE:
            return False
        if self.adv_14d is not None and self.adv_14d < MIN_ADV:
            return False
        if self.atr_daily is not None and self.atr_daily < price * MIN_ATR_PCT / 100.0:
            return False
        return True


@dataclass
class Bar:
    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class BarAggregator:
    """Turns polled (ltp, cumulative day volume) ticks into fixed-minute bars."""

    def __init__(self, minutes: int):
        self._minutes = minutes
        self._cur: Bar | None = None
        self._last_day_vol = 0.0

    def _bucket(self, ts: datetime) -> datetime:
        m = (ts.minute // self._minutes) * self._minutes
        return ts.replace(minute=m, second=0, microsecond=0)

    def update(self, ts: datetime, ltp: float, day_volume: float) -> Bar | None:
        """Feed a tick; returns the COMPLETED bar when a new bucket opens."""
        vol_delta = max(0.0, day_volume - self._last_day_vol) if day_volume else 0.0
        self._last_day_vol = max(self._last_day_vol, day_volume)
        bucket = self._bucket(ts)
        if self._cur is None:
            self._cur = Bar(bucket, ltp, ltp, ltp, ltp, vol_delta)
            return None
        if bucket > self._cur.start:
            done = self._cur
            self._cur = Bar(bucket, ltp, ltp, ltp, ltp, vol_delta)
            return done
        c = self._cur
        c.high = max(c.high, ltp)
        c.low = min(c.low, ltp)
        c.close = ltp
        c.volume += vol_delta
        return None

    def reset_day(self) -> None:
        self._cur = None
        self._last_day_vol = 0.0


@dataclass
class Signal:
    symbol: str
    side: Side
    horizon: Horizon
    entry: float
    stop: float
    target: float
    confidence: str
    reason: str


class _SymbolState:
    def __init__(self, bar_minutes: int):
        self.agg = BarAggregator(bar_minutes)
        self.bars: list[Bar] = []
        self.vwap = SessionVWAP()
        self.vwap_value: float | None = None
        self.or_high: float | None = None
        self.or_low: float | None = None
        self.first_bar_up: bool = False
        self.rvol_ok: bool = True
        self.rvol: float | None = None    # opening-range volume / 14d avg (None = unknown)
        self.gap_pct: float | None = None  # today's open vs prev close (None = unknown)
        self.squeeze_run = 0     # consecutive bars with squeeze on
        self.fired = False


class ORBVWAPStrategy:
    ST_PERIOD = 10
    ST_MULT = 3.0
    ATR_PERIOD = 14

    def __init__(self, settings: Settings):
        self._settings = settings
        self._orb_bars = max(1, settings.orb_minutes // settings.bar_minutes)
        self._state: dict[str, _SymbolState] = {}
        self._daily: dict[str, DailyStats] = {}

    def set_daily_stats(self, stats: dict[str, DailyStats]) -> None:
        self._daily = stats

    def _st(self, symbol: str) -> _SymbolState:
        if symbol not in self._state:
            self._state[symbol] = _SymbolState(self._settings.bar_minutes)
        return self._state[symbol]

    def reset_day(self) -> None:
        self._state.clear()

    def on_tick(self, symbol: str, ts: datetime, ltp: float, day_volume: float,
                ctx: MarketContext) -> Signal | None:
        st = self._st(symbol)
        bar = st.agg.update(ts, ltp, day_volume)
        if bar is None:
            return None
        return self.on_bar(symbol, bar, ctx)

    def on_bar(self, symbol: str, bar: Bar, ctx: MarketContext) -> Signal | None:
        st = self._st(symbol)
        daily = self._daily.get(symbol, DailyStats())
        st.bars.append(bar)
        st.vwap_value = st.vwap.update(bar.high, bar.low, bar.close, bar.volume)

        n = len(st.bars)
        if n == self._orb_bars:  # opening range just completed
            st.or_high = max(b.high for b in st.bars)
            st.or_low = min(b.low for b in st.bars)
            first = st.bars[0]
            st.first_bar_up = first.close > first.open
            or_vol = sum(b.volume for b in st.bars)
            if daily.avg_first_bar_vol and or_vol > 0:
                st.rvol = or_vol / daily.avg_first_bar_vol
                st.rvol_ok = st.rvol > RVOL_MIN
            if daily.prev_close:
                st.gap_pct = (first.open - daily.prev_close) / daily.prev_close * 100.0
            log.info("%s OR %.2f/%.2f first_up=%s rvol_ok=%s gap=%s",
                     symbol, st.or_high, st.or_low, st.first_bar_up, st.rvol_ok,
                     f"{st.gap_pct:+.1f}%" if st.gap_pct is not None else "n/a")
        if st.fired or st.or_high is None or n <= self._orb_bars:
            return None
        if bar.start.astimezone(IST).time() >= LAST_ENTRY:
            return None
        if not daily.eligible(bar.close):
            return None

        highs = [b.high for b in st.bars]
        lows = [b.low for b in st.bars]
        closes = [b.close for b in st.bars]
        _, st_dir = supertrend(highs, lows, closes, self.ST_PERIOD, self.ST_MULT)
        atr5 = atr(highs, lows, closes, self.ATR_PERIOD)
        vwap_v = st.vwap_value or bar.close

        sig = self._orb_signal(symbol, st, bar, daily, ctx, st_dir[-1], atr5[-1], vwap_v)
        if sig is None:
            sig = self._squeeze_signal(symbol, st, bar, ctx, highs, lows, closes,
                                       atr5[-1], vwap_v)
        if sig:
            st.fired = True
        return sig

    # -- primary: paper ORB ---------------------------------------------------

    def _orb_signal(self, symbol: str, st: _SymbolState, bar: Bar, daily: DailyStats,
                    ctx: MarketContext, st_dir: int, atr5: float | None,
                    vwap_v: float) -> Signal | None:
        if not st.rvol_ok:
            return None

        def stop_for(entry: float, is_long: bool) -> float:
            fallback = 1.0 * atr5 if atr5 else (st.or_high - st.or_low)  # type: ignore[operator]
            dist = STOP_ATR_FRACTION * daily.atr_daily if daily.atr_daily else fallback
            if is_long:
                return max(st.or_low, entry - dist)  # type: ignore[arg-type]
            return min(st.or_high, entry + dist)     # type: ignore[arg-type]

        # Gap-and-Go: the ORB on a true gap day — open gapped >2% above prev
        # close AND participation is heavy (RVOL>2). Same trigger machinery,
        # higher-conviction label (the paper's companion setup).
        gap_go = (
            st.gap_pct is not None and st.gap_pct >= GAP_GO_MIN_PCT
            and st.rvol is not None and st.rvol >= GAP_GO_RVOL_MIN
        )

        long_ok = (
            st.first_bar_up and bar.close > st.or_high and bar.close > vwap_v
            and st_dir != -1 and ctx.allows(symbol, Side.BUY)
        )
        if long_ok:
            entry = bar.close
            stop = stop_for(entry, True)
            risk = entry - stop
            if risk <= 0:
                return None
            if gap_go:
                return Signal(symbol, Side.BUY, Horizon.INTRADAY, round(entry, 2),
                              round(stop, 2), round(entry + self._settings.risk_reward * risk, 2),
                              "HIGH",
                              f"Gap-and-Go: +{st.gap_pct:.1f}% gap, RVOL {st.rvol:.1f}x, "
                              "OR break above VWAP")
            conf = "HIGH" if ctx.regime in ("trending", "bull_trend") and ctx.bias == "long" else "MEDIUM"
            return Signal(symbol, Side.BUY, Horizon.INTRADAY, round(entry, 2),
                          round(stop, 2), round(entry + self._settings.risk_reward * risk, 2),
                          conf, "ORB breakout above VWAP (RVOL ok, Supertrend up)")

        short_ok = (
            self._settings.allow_shorts and not st.first_bar_up
            and bar.close < st.or_low and bar.close < vwap_v
            and st_dir != 1 and ctx.allows(symbol, Side.SELL)
        )
        if short_ok:
            entry = bar.close
            stop = stop_for(entry, False)
            risk = stop - entry
            if risk <= 0:
                return None
            conf = "HIGH" if ctx.regime == "trending" and ctx.bias == "short" else "MEDIUM"
            return Signal(symbol, Side.SELL, Horizon.INTRADAY, round(entry, 2),
                          round(stop, 2), round(entry - self._settings.risk_reward * risk, 2),
                          conf, "ORB breakdown below VWAP (RVOL ok, Supertrend down)")
        return None

    # -- secondary: squeeze release -------------------------------------------

    def _squeeze_signal(self, symbol: str, st: _SymbolState, bar: Bar,
                        ctx: MarketContext, highs, lows, closes,
                        atr5: float | None, vwap_v: float) -> Signal | None:
        on, mom = squeeze_momentum(highs, lows, closes)
        if not on or mom[-1] is None:
            return None
        was_on_run = st.squeeze_run
        st.squeeze_run = st.squeeze_run + 1 if on[-1] else 0
        released = (not on[-1]) and was_on_run >= SQUEEZE_MIN_BARS
        if not released or atr5 is None:
            return None
        rising = mom[-2] is not None and mom[-1] > mom[-2]
        if not (mom[-1] > 0 and rising and bar.close > vwap_v
                and ctx.allows(symbol, Side.BUY)):
            return None
        entry = bar.close
        stop = entry - 2.0 * atr5
        risk = entry - stop
        target = entry + self._settings.risk_reward * risk
        return Signal(symbol, Side.BUY, Horizon.INTRADAY, round(entry, 2),
                      round(stop, 2), round(target, 2), "MEDIUM",
                      "Squeeze release with rising momentum above VWAP")
