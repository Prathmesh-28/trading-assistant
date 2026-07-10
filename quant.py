"""Quant analytics: the per-stock mathematics a systematic desk computes from
price history — volatility, Sharpe, beta, drawdown, momentum, 52-week
positioning — plus a deterministic composite score and plain-language
suggestion lines. Pure functions over daily candles; NO models, NO LLM —
every number is reproducible arithmetic (owner's hard rule).

Works in demo too: callers feed it chart candles, which the synthetic feed
fabricates deterministically.
"""

from __future__ import annotations

import math

from indicators import atr, market_regime, rsi

TRADING_DAYS = 252


def _returns(closes: list) -> list:
    return [(closes[i] - closes[i - 1]) / closes[i - 1]
            for i in range(1, len(closes)) if closes[i - 1] > 0]


def _mean(xs: list) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _stdev(xs: list) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def quant_stats(candles: list, index_candles: list = None) -> dict:
    """All stats from daily candles [{date, open, high, low, close, volume}],
    oldest first. Needs ~60+ candles; more fields unlock with ~250+."""
    if len(candles) < 60:
        return {"error": "not enough history (need 60+ daily candles)"}

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    rets = _returns(closes)
    px = closes[-1]

    # --- volatility & risk ---
    sigma_d = _stdev(rets[-TRADING_DAYS:])
    ann_vol_pct = round(sigma_d * math.sqrt(TRADING_DAYS) * 100, 1)
    atr_v = atr(highs, lows, closes, 14)
    atr_pct = round(atr_v[-1] / px * 100, 2) if atr_v[-1] else None

    peak, max_dd = closes[0], 0.0
    for c in closes[-TRADING_DAYS:]:
        peak = max(peak, c)
        max_dd = max(max_dd, (peak - c) / peak)
    max_dd_pct = round(max_dd * 100, 1)

    # --- performance ---
    window = rets[-TRADING_DAYS:]
    sharpe = (round(_mean(window) / _stdev(window) * math.sqrt(TRADING_DAYS), 2)
              if _stdev(window) > 0 else None)

    def mom(days: int):
        if len(closes) <= days:
            return None
        return round((px / closes[-days - 1] - 1) * 100, 1)

    mom_1m, mom_3m = mom(21), mom(63)
    mom_12_1 = (round((closes[-22] / closes[-min(len(closes), 273)] - 1) * 100, 1)
                if len(closes) >= 100 else None)

    # --- positioning ---
    hi_52w = max(highs[-TRADING_DAYS:])
    lo_52w = min(lows[-TRADING_DAYS:])
    from_high_pct = round((px / hi_52w - 1) * 100, 1)
    from_low_pct = round((px / lo_52w - 1) * 100, 1)

    # --- beta vs index (overlapping tail) ---
    beta = None
    if index_candles and len(index_candles) > 80:
        iret = _returns([c["close"] for c in index_candles])
        n = min(len(rets), len(iret), TRADING_DAYS)
        a, b = rets[-n:], iret[-n:]
        vb = _stdev(b) ** 2
        if vb > 0:
            ma, mb = _mean(a), _mean(b)
            cov = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (n - 1)
            beta = round(cov / vb, 2)

    rsi14 = rsi(closes, 14)[-1]
    regime = market_regime(highs, lows, closes)

    # --- composite score 0-100: momentum-tilted, vol-penalized, trend-gated —
    # the standard cross-sectional recipe, fully deterministic ---
    score = 50.0
    for m, w in ((mom_1m, 0.6), (mom_3m, 0.9), (mom_12_1, 1.1)):
        if m is not None:
            score += max(-15, min(15, m * w * 0.5))
    if regime == "bull_trend":
        score += 10
    elif regime in ("bear_trend", "high_volatility"):
        score -= 15
    if from_high_pct is not None:
        score += 6 if from_high_pct > -5 else (-6 if from_high_pct < -25 else 0)
    if ann_vol_pct and ann_vol_pct > 45:
        score -= 8
    if rsi14 is not None and rsi14 > 78:
        score -= 6  # chase risk
    score = round(max(0, min(100, score)))

    # --- plain-language read of the numbers ---
    notes = []
    if mom_3m is not None:
        notes.append(f"{'Up' if mom_3m >= 0 else 'Down'} {abs(mom_3m)}% in 3 months")
    if from_high_pct is not None:
        notes.append(f"{abs(from_high_pct)}% {'below' if from_high_pct < 0 else 'above'} its 52-week high")
    label = {"bull_trend": "trending up", "bear_trend": "trending down",
             "range": "moving sideways", "high_volatility": "unusually volatile",
             "transition": "changing character"}.get(regime)
    if label:
        notes.append(f"currently {label}")
    if ann_vol_pct:
        notes.append(f"typical yearly swing ±{ann_vol_pct}%")

    if score >= 70:
        verdict = "Strong candidate by the numbers — momentum and trend agree."
    elif score >= 55:
        verdict = "Decent setup — some factors aligned, not all."
    elif score >= 40:
        verdict = "Neutral — the math sees no edge either way right now."
    else:
        verdict = "Weak by the numbers — momentum/trend point against buying."

    return {
        "price": round(px, 2),
        "ann_vol_pct": ann_vol_pct,
        "atr_pct": atr_pct,
        "sharpe_1y": sharpe,
        "max_dd_1y_pct": max_dd_pct,
        "beta": beta,
        "mom_1m_pct": mom_1m,
        "mom_3m_pct": mom_3m,
        "mom_12_1_pct": mom_12_1,
        "from_52w_high_pct": from_high_pct,
        "from_52w_low_pct": from_low_pct,
        "rsi14": round(rsi14, 0) if rsi14 is not None else None,
        "regime": regime,
        "score": score,
        "verdict": verdict,
        "notes": notes,
    }


def rank_suggestions(candles_by_symbol: dict, index_candles: list = None,
                     names: dict = None, top: int = 5) -> list:
    """Deterministic 'top picks': score every symbol, return the best `top`
    with their reasons. This is rule-based screening, not a prediction."""
    scored = []
    for sym, candles in candles_by_symbol.items():
        s = quant_stats(candles, index_candles)
        if "error" in s:
            continue
        scored.append({
            "symbol": sym,
            "name": (names or {}).get(sym, sym),
            "score": s["score"],
            "price": s["price"],
            "mom_3m_pct": s["mom_3m_pct"],
            "regime": s["regime"],
            "reason": "; ".join(s["notes"][:3]),
        })
    scored.sort(key=lambda x: -x["score"])
    return scored[:top]
