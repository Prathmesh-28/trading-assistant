"""indicators.py — pure-function TA math.

Contract under test (per CLAUDE.md): plain lists in, output aligned to input
length, None during warmup, deterministic regime buckets from gentle
synthetic series.
"""

import math

from indicators import (atr, donchian, efficiency_ratio, ema, macd,
                        market_regime, rsi, sma)


def _trend_series(drift: float, n: int = 60, amp: float = 0.004):
    """Geometric drift per bar with a fixed high/low band around the close."""
    closes = [100.0 * ((1.0 + drift) ** i) for i in range(n)]
    highs = [c * (1.0 + amp) for c in closes]
    lows = [c * (1.0 - amp) for c in closes]
    return highs, lows, closes


def _range_series(n: int = 60, amp: float = 0.3):
    """Flat tape oscillating ±amp around 100 — no drift, low ATR."""
    closes = [100.0 + amp * math.sin(i * 0.9) for i in range(n)]
    highs = [c + 0.15 for c in closes]
    lows = [c - 0.15 for c in closes]
    return highs, lows, closes


# ------------------------------------------------------------ sma / ema

def test_sma_warmup_and_alignment():
    values = [float(i) for i in range(1, 11)]
    out = sma(values, 3)
    assert len(out) == len(values)
    assert out[:2] == [None, None]
    assert out[2] == 2.0                     # mean(1,2,3)
    assert out[-1] == 9.0                    # mean(8,9,10)
    assert all(v is not None for v in out[2:])


def test_ema_warmup_seeded_with_sma():
    values = [float(i) for i in range(1, 21)]
    out = ema(values, 5)
    assert len(out) == len(values)
    assert all(v is None for v in out[:4])
    assert out[4] == 3.0                     # seed = SMA of first 5
    assert all(v is not None for v in out[4:])


def test_ema_shorter_than_period_is_all_none():
    assert ema([1.0, 2.0, 3.0], 5) == [None, None, None]


# ------------------------------------------------------------ rsi / atr

def test_rsi_bounds_and_warmup():
    closes = [100.0 + 3.0 * math.sin(i * 0.7) + 0.1 * i for i in range(80)]
    out = rsi(closes, 14)
    assert len(out) == len(closes)
    assert out[0] is None                    # needs a prior close
    dense = [v for v in out if v is not None]
    assert dense, "rsi never warmed up"
    assert all(0.0 <= v <= 100.0 for v in dense)


def test_rsi_extremes():
    up = [100.0 + i for i in range(30)]
    down = [130.0 - i for i in range(30)]
    assert rsi(up, 14)[-1] == 100.0          # no losses => pinned at 100
    assert rsi(down, 14)[-1] == 0.0          # no gains  => pinned at 0


def test_atr_positive_after_warmup():
    highs, lows, closes = _trend_series(0.001, n=50)
    out = atr(highs, lows, closes, 14)
    assert len(out) == len(closes)
    assert all(v is None for v in out[:13])
    assert out[13] is not None
    assert all(v > 0 for v in out[13:])


# ------------------------------------------------------------ market_regime

def test_market_regime_bull_trend():
    highs, lows, closes = _trend_series(+0.003)   # +0.3%/day, ±0.4% band
    assert market_regime(highs, lows, closes) == "bull_trend"


def test_market_regime_bear_trend():
    highs, lows, closes = _trend_series(-0.003)   # -0.3%/day, ±0.4% band
    assert market_regime(highs, lows, closes) == "bear_trend"


def test_market_regime_range():
    highs, lows, closes = _range_series()         # flat ±0.3
    assert market_regime(highs, lows, closes) == "range"


def test_market_regime_unknown_below_35_candles():
    highs, lows, closes = _trend_series(+0.003, n=34)
    assert market_regime(highs, lows, closes) == "unknown"


# ------------------------------------------------------------ efficiency_ratio

def test_efficiency_ratio_bounds_and_extremes():
    clean = [100.0 + i for i in range(30)]        # straight line => ER 1
    er_clean = efficiency_ratio(clean, 20)
    assert er_clean is not None and abs(er_clean - 1.0) < 1e-9

    churn = [100.0, 101.0] * 15                   # pure zigzag => ER ~ 0
    er_churn = efficiency_ratio(churn, 20)
    assert er_churn is not None and 0.0 <= er_churn <= 0.2

    for series in (clean, churn):
        er = efficiency_ratio(series, 20)
        assert 0.0 <= er <= 1.0


def test_efficiency_ratio_needs_period_plus_one():
    assert efficiency_ratio([100.0] * 20, 20) is None


# ------------------------------------------------------------ macd / donchian shapes

def test_macd_shapes_and_warmup():
    closes = [100.0 + 2.0 * math.sin(i * 0.3) + 0.05 * i for i in range(80)]
    line, sig, hist = macd(closes)                # 12/26/9
    assert len(line) == len(sig) == len(hist) == len(closes)
    assert all(v is None for v in line[:25])      # EMA26 warms up at index 25
    assert line[25] is not None
    assert all(v is None for v in sig[:33])       # signal EMA9 of the line
    assert sig[33] is not None
    assert hist[32] is None and hist[33] is not None
    for l, s, h in zip(line, sig, hist):
        if h is not None:
            assert abs(h - (l - s)) < 1e-9


def test_donchian_shapes_and_values():
    highs = [10.0, 12.0, 11.0, 15.0, 13.0, 14.0, 20.0]
    lows = [9.0, 10.0, 8.0, 12.0, 11.0, 12.0, 18.0]
    upper, lower = donchian(highs, lows, 5)
    assert len(upper) == len(lower) == len(highs)
    assert upper[:4] == [None] * 4 and lower[:4] == [None] * 4
    assert upper[4] == 15.0 and lower[4] == 8.0   # window = bars 0..4
    assert upper[6] == 20.0 and lower[6] == 8.0   # window = bars 2..6
    for u, l in zip(upper, lower):
        if u is not None:
            assert u >= l
