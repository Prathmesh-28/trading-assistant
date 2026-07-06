"""Positional (CNC) swing scan on daily candles.

The most parameter-robust trend package in the public-repo survey
(freqtrade EMA variants, backtesting.py examples, published rolling backtests):

  - Trigger: EMA20 crossed above EMA50 within the last CROSS_LOOKBACK days
  - Regime:  close > EMA200 (only trade longs in a long-term uptrend)
  - Trend:   ADX14 > 25 (Wilder; the consensus "tradeable trend" threshold)
  - Guard:   RSI14 < 70 (don't chase a blow-off)
  - Stop:    tighter of close − 2·ATR14 and the Chandelier Exit (22, 3.0);
             trail with the Chandelier as the position ages
  - Target:  close + 3·ATR14 (1.5R on the ATR stop) — trend legs often run
             further; the alert suggests trailing instead of hard-booking

Long only (delivery). Scanned once per day from Groww daily history; skipped
on the synthetic feed. Needs ~220 daily candles for EMA200; with less history
the EMA200 filter is skipped (logged).
"""

from __future__ import annotations

import logging

from config import Settings
from indicators import adx, atr, chandelier_stop, ema, rsi
from recommendation import Horizon, Side
from strategy import MarketContext, Signal

log = logging.getLogger("positional")

EMA_FAST = 20
EMA_SLOW = 50
EMA_REGIME = 200
CROSS_LOOKBACK = 5
ADX_MIN = 25.0
RSI_MAX = 70.0
ATR_STOP_MULT = 2.0
ATR_TARGET_MULT = 3.0
CHANDELIER_PERIOD = 22
CHANDELIER_MULT = 3.0
MIN_HISTORY = EMA_SLOW + CROSS_LOOKBACK + 5


def scan_symbol(symbol: str, candles: list[dict], ctx: MarketContext) -> Signal | None:
    """candles: [{open, high, low, close, volume}] oldest first, daily."""
    if len(candles) < MIN_HISTORY:
        return None
    if not ctx.allows(symbol, Side.BUY):
        return None

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

    fresh_cross = any(
        fast[-i] is not None and slow[-i] is not None
        and fast[-i - 1] is not None and slow[-i - 1] is not None
        and fast[-i] > slow[-i] and fast[-i - 1] <= slow[-i - 1]
        for i in range(1, CROSS_LOOKBACK + 1)
    )
    if not fresh_cross:
        return None
    if adx_v[-1] < ADX_MIN or rsi_v[-1] > RSI_MAX:
        return None

    atr_stop = close - ATR_STOP_MULT * atr_v[-1]
    chand = chandelier_stop(highs, lows, closes, CHANDELIER_PERIOD, CHANDELIER_MULT)
    stop = max(atr_stop, chand) if chand is not None else atr_stop
    if stop >= close:
        return None
    target = close + ATR_TARGET_MULT * atr_v[-1]
    conf = "HIGH" if adx_v[-1] >= 30 and ctx.bias == "long" else "MEDIUM"
    return Signal(
        symbol, Side.BUY, Horizon.POSITIONAL,
        round(close, 2), round(stop, 2), round(target, 2), conf,
        f"Fresh EMA{EMA_FAST}/{EMA_SLOW} cross above EMA{EMA_REGIME}, "
        f"ADX {adx_v[-1]:.0f}; trail with Chandelier(22,3)",
    )


def scan(feed, watchlist: list[str], ctx: MarketContext) -> list[Signal]:
    if getattr(feed, "synthetic", False):
        log.info("synthetic feed — positional scan skipped")
        return []
    signals = []
    for sym in watchlist:
        candles = feed.get_daily_candles(sym, days=320)
        sig = scan_symbol(sym, candles, ctx)
        if sig:
            signals.append(sig)
    return signals
