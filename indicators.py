"""Indicator math used by both strategies.

Formulas follow the canonical public definitions (Wilder 1978 smoothing for
ATR/RSI/ADX; Olivier Seban's Supertrend band-flip; session-anchored VWAP) as
implemented across the major open-source engines (freqtrade, backtesting.py,
TradingView ports). Pure functions over plain lists — no numpy needed at this
scale.
"""

from __future__ import annotations


def sma(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    run = 0.0
    for i, v in enumerate(values):
        run += v
        if i >= period:
            run -= values[i - period]
        if i >= period - 1:
            out[i] = run / period
    return out


def ema(values: list[float], period: int) -> list[float | None]:
    """Standard EMA seeded with the SMA of the first `period` values."""
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    prev = sum(values[:period]) / period
    out[period - 1] = prev
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def _wilder(values: list[float | None], period: int) -> list[float | None]:
    """Wilder's RMA: seed = mean of first `period`, then rma = (prev*(n-1)+x)/n."""
    out: list[float | None] = [None] * len(values)
    xs = [v for v in values if v is not None]
    if len(xs) < period:
        return out
    start = next(i for i, v in enumerate(values) if v is not None)
    seed_end = start + period
    prev = sum(values[start:seed_end]) / period  # type: ignore[arg-type]
    out[seed_end - 1] = prev
    for i in range(seed_end, len(values)):
        prev = (prev * (period - 1) + values[i]) / period  # type: ignore[operator]
        out[i] = prev
    return out


def true_range(high: list[float], low: list[float], close: list[float]) -> list[float | None]:
    out: list[float | None] = [None] * len(high)
    for i in range(len(high)):
        if i == 0:
            out[i] = high[i] - low[i]
        else:
            out[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )
    return out


def atr(high: list[float], low: list[float], close: list[float], period: int = 14) -> list[float | None]:
    return _wilder(true_range(high, low, close), period)


def rsi(close: list[float], period: int = 14) -> list[float | None]:
    gains: list[float | None] = [None]
    losses: list[float | None] = [None]
    for i in range(1, len(close)):
        d = close[i] - close[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag = _wilder(gains, period)
    al = _wilder(losses, period)
    out: list[float | None] = [None] * len(close)
    for i in range(len(close)):
        if ag[i] is None or al[i] is None:
            continue
        out[i] = 100.0 if al[i] == 0 else 100.0 - 100.0 / (1.0 + ag[i] / al[i])
    return out


def adx(high: list[float], low: list[float], close: list[float], period: int = 14) -> list[float | None]:
    """Wilder ADX. Values > ~20-25 = trending market."""
    n = len(high)
    plus_dm: list[float | None] = [None]
    minus_dm: list[float | None] = [None]
    for i in range(1, n):
        up = high[i] - high[i - 1]
        dn = low[i - 1] - low[i]
        plus_dm.append(up if up > dn and up > 0 else 0.0)
        minus_dm.append(dn if dn > up and dn > 0 else 0.0)
    tr_s = _wilder(true_range(high, low, close), period)
    pdm_s = _wilder(plus_dm, period)
    mdm_s = _wilder(minus_dm, period)
    dx: list[float | None] = [None] * n
    for i in range(n):
        if tr_s[i] and pdm_s[i] is not None and mdm_s[i] is not None:
            pdi = 100.0 * pdm_s[i] / tr_s[i]
            mdi = 100.0 * mdm_s[i] / tr_s[i]
            denom = pdi + mdi
            dx[i] = 100.0 * abs(pdi - mdi) / denom if denom else 0.0
    return _wilder(dx, period)


def supertrend(
    high: list[float], low: list[float], close: list[float],
    period: int = 10, multiplier: float = 3.0,
) -> tuple[list[float | None], list[int]]:
    """Returns (line, direction) — direction +1 while price rides above the lower
    band (uptrend), -1 below the upper band. Standard band-tightening rules:
    bands only ratchet in the trend direction until price closes through them.
    """
    n = len(close)
    atr_v = atr(high, low, close, period)
    line: list[float | None] = [None] * n
    direction = [0] * n
    ub = lb = None  # final upper / lower bands
    for i in range(n):
        if atr_v[i] is None:
            continue
        mid = (high[i] + low[i]) / 2.0
        basic_ub = mid + multiplier * atr_v[i]
        basic_lb = mid - multiplier * atr_v[i]
        ub = basic_ub if ub is None or basic_ub < ub or close[i - 1] > ub else ub
        lb = basic_lb if lb is None or basic_lb > lb or close[i - 1] < lb else lb
        prev_dir = direction[i - 1] if i > 0 else 1
        if prev_dir == 1:
            direction[i] = -1 if close[i] < lb else 1
        else:
            direction[i] = 1 if close[i] > ub else -1
        if direction[i] != prev_dir:  # trend flipped: reset the opposite band
            if direction[i] == 1:
                lb = basic_lb
            else:
                ub = basic_ub
        line[i] = lb if direction[i] == 1 else ub
    return line, direction


def stdev(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1: i + 1]
        m = sum(window) / period
        out[i] = (sum((x - m) ** 2 for x in window) / period) ** 0.5
    return out


def linreg_endpoint(values: list[float], period: int) -> float | None:
    """Endpoint of the least-squares line over the last `period` values —
    LazyBear's `linreg(x, period, 0)`."""
    if len(values) < period:
        return None
    ys = values[-period:]
    n = float(period)
    xs = range(period)
    sx, sy = sum(xs), sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    if denom == 0:
        return None
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    return a + b * (period - 1)


def squeeze_momentum(
    high: list[float], low: list[float], close: list[float],
    bb_period: int = 20, bb_mult: float = 2.0,
    kc_period: int = 20, kc_mult: float = 1.5,
) -> tuple[list[bool], list[float | None]]:
    """LazyBear / TTM Squeeze. Returns (squeeze_on, momentum).
    squeeze_on: Bollinger(20, 2.0) fully inside Keltner(20, 1.5·SMA(TR,20)) —
    volatility compressed. momentum: linreg endpoint of close minus the mid of
    (donchian mid, SMA close) over 20 bars. Trade the release: first bar where
    the squeeze turns off with momentum positive and rising."""
    n = len(close)
    basis = sma(close, bb_period)
    dev = stdev(close, bb_period)
    tr = [v if v is not None else 0.0 for v in true_range(high, low, close)]
    rangema = sma(tr, kc_period)
    on: list[bool] = [False] * n
    mom: list[float | None] = [None] * n
    for i in range(n):
        if basis[i] is None or dev[i] is None or rangema[i] is None:
            continue
        ubb, lbb = basis[i] + bb_mult * dev[i], basis[i] - bb_mult * dev[i]
        ukc, lkc = basis[i] + kc_mult * rangema[i], basis[i] - kc_mult * rangema[i]
        on[i] = lbb > lkc and ubb < ukc
    period = bb_period
    for i in range(period * 2 - 1, n):
        hh = max(high[i - period + 1: i + 1])
        ll = min(low[i - period + 1: i + 1])
        mid = ((hh + ll) / 2 + basis[i]) / 2 if basis[i] is not None else None
        if mid is None:
            continue
        series = [
            close[j] - ((max(high[j - period + 1: j + 1]) + min(low[j - period + 1: j + 1])) / 2
                        + basis[j]) / 2
            for j in range(i - period + 1, i + 1)
            if basis[j] is not None
        ]
        if len(series) == period:
            mom[i] = linreg_endpoint(series, period)
    return on, mom


def efficiency_ratio(close: list[float], period: int = 20) -> float | None:
    """Kaufman's Efficiency Ratio: |net change| / sum of |bar-to-bar changes|
    over `period` bars. ~1 = clean directional move, ~0 = churn."""
    if len(close) < period + 1:
        return None
    window = close[-(period + 1):]
    net = abs(window[-1] - window[0])
    path = sum(abs(window[i] - window[i - 1]) for i in range(1, len(window)))
    return net / path if path > 0 else 0.0


def market_regime(high: list[float], low: list[float], close: list[float]) -> str:
    """Deterministic regime bucket from daily candles — no ML, pure thresholds
    (pattern adapted from QuantDinger's rule-based regime classifier: EMA gap,
    ATR%, and Kaufman efficiency).

    Returns one of: bull_trend / bear_trend / range / high_volatility /
    transition / unknown (insufficient data — callers should fail open)."""
    if len(close) < 35:
        return "unknown"
    e_fast = ema(close, 10)
    e_slow = ema(close, 30)
    atr_v = atr(high, low, close, 14)
    er = efficiency_ratio(close, 20)
    if e_fast[-1] is None or e_slow[-1] is None or atr_v[-1] is None or er is None:
        return "unknown"
    px = close[-1]
    ema_gap_pct = (e_fast[-1] - e_slow[-1]) / e_slow[-1] * 100.0
    atr_pct = atr_v[-1] / px * 100.0

    if atr_pct > 4.0:
        return "high_volatility"
    if ema_gap_pct > 0.5 and er > 0.3:
        return "bull_trend"
    if ema_gap_pct < -0.5 and er > 0.3:
        return "bear_trend"
    if abs(ema_gap_pct) <= 0.5 and atr_pct < 2.0:
        return "range"
    return "transition"


def macd(
    close: list[float], fast: int = 12, slow: int = 26, signal: int = 9,
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Standard MACD: EMA(fast) - EMA(slow), signal = EMA(signal) of that line,
    histogram = line - signal. Returns (line, signal, histogram)."""
    ema_fast, ema_slow = ema(close, fast), ema(close, slow)
    line: list[float | None] = [
        (a - b) if a is not None and b is not None else None
        for a, b in zip(ema_fast, ema_slow)
    ]
    start = next((i for i, v in enumerate(line) if v is not None), len(line))
    dense = [v for v in line[start:] if v is not None]  # type: ignore[misc]
    sig_dense = ema(dense, signal)
    sig: list[float | None] = [None] * len(line)
    sig[start:start + len(sig_dense)] = sig_dense
    hist: list[float | None] = [
        (a - b) if a is not None and b is not None else None for a, b in zip(line, sig)
    ]
    return line, sig, hist


def donchian(high: list[float], low: list[float], period: int) -> tuple[list[float | None], list[float | None]]:
    """Rolling (highest high, lowest low) over `period` bars — Turtle-style
    channel. Index i's value uses bars [i-period+1, i], never the current bar
    alone, so it's the channel as of the CLOSE of bar i."""
    n = len(high)
    upper: list[float | None] = [None] * n
    lower: list[float | None] = [None] * n
    for i in range(period - 1, n):
        upper[i] = max(high[i - period + 1: i + 1])
        lower[i] = min(low[i - period + 1: i + 1])
    return upper, lower


def chandelier_stop(high: list[float], low: list[float], close: list[float],
                    period: int = 22, mult: float = 3.0) -> float | None:
    """Le Beau's Chandelier Exit (long side): highest high of last `period`
    bars minus mult·ATR(period). Ratchet it upward while in a position."""
    if len(close) < period + 1:
        return None
    atr_v = atr(high, low, close, period)
    if atr_v[-1] is None:
        return None
    return max(high[-period:]) - mult * atr_v[-1]


class SessionVWAP:
    """Volume-weighted average price anchored to the trading day. Feed it bars;
    falls back to a cumulative typical-price mean when the feed has no volume."""

    def __init__(self):
        self._pv = 0.0
        self._vol = 0.0
        self._tp_sum = 0.0
        self._bars = 0

    def update(self, high: float, low: float, close: float, volume: float) -> float:
        tp = (high + low + close) / 3.0
        self._tp_sum += tp
        self._bars += 1
        if volume > 0:
            self._pv += tp * volume
            self._vol += volume
        if self._vol > 0:
            return self._pv / self._vol
        return self._tp_sum / self._bars  # SMA fallback (no volume in feed)

    def reset(self) -> None:
        self.__init__()
