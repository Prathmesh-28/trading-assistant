"""Positional (CNC) swing scan on daily candles.

Five long-only strategies, tried in priority order per symbol — the first to
fire wins, so at most one idea per symbol per day (same invariant the engine
already relies on). Cascade order follows the published evidence, strongest
first: Donchian-55 and RSI-dip-in-uptrend hold up best in equity backtests,
Golden Cross is drawdown-friendly but shows no significant edge over passive
in academic tests, and MACD-alone tests weakest (win rate <50% on US indices,
arXiv:2206.12282) so it runs last at LOW confidence.

Two gates run before any strategy fires:

INDEX GATE (Faber's 200-DMA timing rule, SSRN — halves max drawdown on
1927-2022 US data for near-identical CAGR): new positional entries are only
taken while the index proxy (NIFTYBEES ETF by default — an NSE cash
instrument, so it flows through the normal equity data path) closes above its
own 200-day SMA. Fails open when index history is unavailable.

REGIME GATE (deterministic, indicators.market_regime): per-symbol thresholds
on EMA10/30 gap, ATR%, and Kaufman efficiency bucket the tape into
bull_trend / bear_trend / range / high_volatility / transition. Trend
strategies only fire in bull_trend/transition; the RSI dip-buy also fires in
range. Nothing fires long in bear_trend or high_volatility. Fails open on
"unknown" (insufficient history).

1. EMA20/50 cross — most parameter-robust trend package in the public-repo
   survey; heavily filtered (EMA200 regime + ADX14>25 + RSI14<70), so when it
   fires it outranks everything below.
2. Donchian 55-day breakout (Turtle System 2) — close breaks the highest high
   of the preceding 55 sessions; the breakout IS the trend confirmation.
3. RSI dip-buy in an uptrend — close > EMA200 but RSI14 dipped under 32 and
   is turning back up; a pullback entry, tighter stop.
4. Golden Cross (SMA50/SMA200) — textbook long-horizon trend entry.
5. MACD(12,26,9) cross above EMA200 — loosest filter, LOW confidence.

Long only (delivery). Scanned once per day from Groww daily history; skipped
on the synthetic feed. Needs ~220 daily candles for EMA200; with less history
the EMA200 filter is skipped (logged).
"""

from __future__ import annotations

import logging

from indicators import (adx, atr, chandelier_stop, donchian, ema, macd,
                        market_regime, rsi, sma)
from recommendation import Horizon, Side
from strategy import MarketContext, Signal

log = logging.getLogger("positional")

EMA_FAST = 20
EMA_SLOW = 50
EMA_REGIME = 200
CROSS_LOOKBACK = 5
ADX_MIN = 25.0
RSI_MAX = 70.0
RSI_DIP = 32.0
ATR_STOP_MULT = 2.0
ATR_TARGET_MULT = 3.0
CHANDELIER_PERIOD = 22
CHANDELIER_MULT = 3.0
DONCHIAN_PERIOD = 55
GOLDEN_SMA_FAST = 50
GOLDEN_SMA_SLOW = 200
GOLDEN_LOOKBACK = 10
MIN_HISTORY = EMA_SLOW + CROSS_LOOKBACK + 5


def _fresh_cross_up(fast: list, slow: list, lookback: int) -> bool:
    return any(
        fast[-i] is not None and slow[-i] is not None
        and fast[-i - 1] is not None and slow[-i - 1] is not None
        and fast[-i] > slow[-i] and fast[-i - 1] <= slow[-i - 1]
        for i in range(1, lookback + 1)
    )


def _atr_levels(close: float, atr_v: float, stop_mult: float, target_mult: float) -> tuple[float, float]:
    return round(close - stop_mult * atr_v, 2), round(close + target_mult * atr_v, 2)


def _ema_cross_signal(symbol: str, candles: list[dict]) -> Signal | None:
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]

    fast = ema(closes, EMA_FAST)
    slow = ema(closes, EMA_SLOW)
    adx_v = adx(highs, lows, closes, 14)
    rsi_v = rsi(closes, 14)
    atr_v = atr(highs, lows, closes, 14)
    if None in (fast[-1], slow[-1], adx_v[-1], rsi_v[-1], atr_v[-1]):
        return None

    close = closes[-1]
    if not (fast[-1] > slow[-1] and close > fast[-1]):
        return None

    regime = ema(closes, EMA_REGIME)
    if regime[-1] is not None:
        if close < regime[-1]:
            return None
    else:
        log.info("%s: <%d candles, EMA200 regime filter skipped", symbol, EMA_REGIME)

    if not _fresh_cross_up(fast, slow, CROSS_LOOKBACK):
        return None
    if adx_v[-1] < ADX_MIN or rsi_v[-1] > RSI_MAX:
        return None

    atr_stop = close - ATR_STOP_MULT * atr_v[-1]
    chand = chandelier_stop(highs, lows, closes, CHANDELIER_PERIOD, CHANDELIER_MULT)
    stop = max(atr_stop, chand) if chand is not None else atr_stop
    if stop >= close:
        return None
    target = close + ATR_TARGET_MULT * atr_v[-1]
    conf = "HIGH" if adx_v[-1] >= 30 else "MEDIUM"
    return Signal(
        symbol, Side.BUY, Horizon.POSITIONAL, round(close, 2), round(stop, 2), round(target, 2), conf,
        f"Fresh EMA{EMA_FAST}/{EMA_SLOW} cross above EMA{EMA_REGIME}, "
        f"ADX {adx_v[-1]:.0f}; trail with Chandelier(22,3)",
    )


def _golden_cross_signal(symbol: str, candles: list[dict]) -> Signal | None:
    if len(candles) < GOLDEN_SMA_SLOW + GOLDEN_LOOKBACK:
        return None
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]

    fast = sma(closes, GOLDEN_SMA_FAST)
    slow = sma(closes, GOLDEN_SMA_SLOW)
    atr_v = atr(highs, lows, closes, 14)
    if None in (fast[-1], slow[-1], atr_v[-1]):
        return None
    close = closes[-1]
    if not (close > fast[-1] > slow[-1]):
        return None
    if not _fresh_cross_up(fast, slow, GOLDEN_LOOKBACK):
        return None

    stop, target = _atr_levels(close, atr_v[-1], ATR_STOP_MULT, ATR_TARGET_MULT)
    if stop >= close:
        return None
    return Signal(
        symbol, Side.BUY, Horizon.POSITIONAL, round(close, 2), stop, target, "HIGH",
        f"Golden Cross: SMA{GOLDEN_SMA_FAST} crossed above SMA{GOLDEN_SMA_SLOW}",
    )


def _donchian_breakout_signal(symbol: str, candles: list[dict]) -> Signal | None:
    if len(candles) < DONCHIAN_PERIOD + 1:
        return None
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]

    # channel built from everything BEFORE today, so today's close can be
    # compared against a level that was already fixed at yesterday's close
    upper, _ = donchian(highs[:-1], lows[:-1], DONCHIAN_PERIOD)
    atr_v = atr(highs, lows, closes, 14)
    if upper[-1] is None or atr_v[-1] is None:
        return None
    close = closes[-1]
    if close <= upper[-1]:
        return None

    stop, target = _atr_levels(close, atr_v[-1], ATR_STOP_MULT, ATR_TARGET_MULT)
    if stop >= close:
        return None
    return Signal(
        symbol, Side.BUY, Horizon.POSITIONAL, round(close, 2), stop, target, "MEDIUM",
        f"Donchian {DONCHIAN_PERIOD}-day breakout (Turtle-style); trail the stop as it runs",
    )


def _rsi_dip_signal(symbol: str, candles: list[dict]) -> Signal | None:
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]

    regime = ema(closes, EMA_REGIME)
    rsi_v = rsi(closes, 14)
    atr_v = atr(highs, lows, closes, 14)
    if regime[-1] is None or rsi_v[-1] is None or rsi_v[-2] is None or atr_v[-1] is None:
        return None
    close = closes[-1]
    if close <= regime[-1]:  # only buy dips inside an established uptrend
        return None
    turning_up = rsi_v[-1] > rsi_v[-2]
    if not (rsi_v[-1] < RSI_DIP and turning_up):
        return None

    stop, target = _atr_levels(close, atr_v[-1], 1.5, 2.5)  # tighter — a counter-move entry
    if stop >= close:
        return None
    return Signal(
        symbol, Side.BUY, Horizon.POSITIONAL, round(close, 2), stop, target, "MEDIUM",
        f"RSI dip-buy in an uptrend (RSI {rsi_v[-1]:.0f}, turning up, close > EMA{EMA_REGIME})",
    )


def _macd_trend_signal(symbol: str, candles: list[dict]) -> Signal | None:
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    closes = [c["close"] for c in candles]

    line, sig, _ = macd(closes)
    regime = ema(closes, EMA_REGIME)
    atr_v = atr(highs, lows, closes, 14)
    if None in (line[-1], line[-2], sig[-1], sig[-2], regime[-1], atr_v[-1]):
        return None
    close = closes[-1]
    if close <= regime[-1]:
        return None
    crossed_up = line[-2] <= sig[-2] and line[-1] > sig[-1]
    if not crossed_up:
        return None

    stop, target = _atr_levels(close, atr_v[-1], ATR_STOP_MULT, ATR_TARGET_MULT)
    if stop >= close:
        return None
    return Signal(
        symbol, Side.BUY, Horizon.POSITIONAL, round(close, 2), stop, target, "LOW",
        "MACD bullish crossover above signal line, close > EMA200",
    )


# Evidence-ranked cascade (see module docstring); first to fire wins so a
# symbol never gets two positional ideas the same day. Each entry carries the
# regimes it's allowed to fire in — "unknown" is always allowed (fail open).
_TREND_REGIMES = {"bull_trend", "transition", "unknown"}
_DIP_REGIMES = {"bull_trend", "range", "transition", "unknown"}
_STRATEGIES = [
    (_ema_cross_signal, _TREND_REGIMES),
    (_donchian_breakout_signal, _TREND_REGIMES),
    (_rsi_dip_signal, _DIP_REGIMES),
    (_golden_cross_signal, _TREND_REGIMES),
    (_macd_trend_signal, _TREND_REGIMES),
]


def scan_symbol(symbol: str, candles: list[dict], ctx: MarketContext) -> Signal | None:
    """candles: [{open, high, low, close, volume}] oldest first, daily."""
    if len(candles) < MIN_HISTORY:
        return None
    if not ctx.allows(symbol, Side.BUY):
        return None
    regime = market_regime([c["high"] for c in candles],
                           [c["low"] for c in candles],
                           [c["close"] for c in candles])
    if regime in ("bear_trend", "high_volatility"):
        log.info("%s: regime %s — no long entries", symbol, regime)
        return None
    for strat, allowed in _STRATEGIES:
        if regime not in allowed:
            continue
        sig = strat(symbol, candles)
        if sig:
            return sig
    return None


def index_allows_entries(index_candles: list[dict]) -> bool:
    """Faber 200-DMA gate on the index proxy: new positional entries only when
    the index closes above its 200-day SMA. Fails open on missing history."""
    closes = [c["close"] for c in index_candles]
    if len(closes) < 200:
        return True
    sma200 = sma(closes, 200)
    if sma200[-1] is None:
        return True
    return closes[-1] > sma200[-1]


def scan(feed, watchlist: list[str], ctx: MarketContext,
         index_symbol: str = "NIFTYBEES") -> list[Signal]:
    if getattr(feed, "synthetic", False):
        log.info("synthetic feed — positional scan skipped")
        return []
    index_candles = feed.get_daily_candles(index_symbol, days=320)
    if not index_allows_entries(index_candles):
        log.info("index gate: %s below its 200-DMA — positional entries paused",
                 index_symbol)
        return []
    signals = []
    for sym in watchlist:
        candles = feed.get_daily_candles(sym, days=320)
        sig = scan_symbol(sym, candles, ctx)
        if sig:
            signals.append(sig)
    return signals
