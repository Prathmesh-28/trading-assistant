"""positional.py — the gates around the strategy cascade.

Covers: the per-symbol regime gate (no longs in a bear tape), the
MarketContext veto, the Faber 200-DMA index gate, 12-1 momentum ranking, and
the rotation scan's refusal to buy negative-momentum names. Uses a tiny fake
feed — no network, no Groww.
"""

from indicators import market_regime
from positional import (MIN_HISTORY, index_allows_entries, momentum_rank,
                        momentum_rotation_scan, scan_symbol)
from strategy import MarketContext


def _candles(closes, amp=0.004):
    return [
        {
            "open": c,
            "high": c * (1.0 + amp),
            "low": c * (1.0 - amp),
            "close": c,
            "volume": 1_000_000,
        }
        for c in closes
    ]


def _drift_closes(start, drift, n):
    return [start * ((1.0 + drift) ** i) for i in range(n)]


class FakeFeed:
    """get_daily_candles from a canned per-symbol close series."""

    synthetic = False

    def __init__(self, series):
        self.series = series  # symbol -> list of closes, oldest first

    def get_daily_candles(self, symbol, days=400, **_):
        closes = self.series.get(symbol, [])
        return _candles(closes[-days:])


# ------------------------------------------------------------ regime gate

def test_scan_symbol_none_in_bear_regime():
    closes = _drift_closes(500.0, -0.003, 300)      # ~-0.3%/day for ~300 sessions
    candles = _candles(closes)
    # precondition: this tape really classifies as bear_trend
    assert market_regime([c["high"] for c in candles],
                         [c["low"] for c in candles],
                         [c["close"] for c in candles]) == "bear_trend"
    assert scan_symbol("BEARX", candles, MarketContext()) is None


def test_scan_symbol_none_below_min_history():
    candles = _candles(_drift_closes(500.0, 0.003, MIN_HISTORY - 1))
    assert scan_symbol("SHORTX", candles, MarketContext()) is None


def test_scan_symbol_respects_context_veto():
    candles = _candles(_drift_closes(500.0, 0.003, 300))  # healthy uptrend
    assert scan_symbol("AVOIDX", candles,
                       MarketContext(avoid_symbols={"AVOIDX"})) is None
    assert scan_symbol("BIASX", candles, MarketContext(bias="short")) is None


# ------------------------------------------------------------ index gate

def test_index_gate_true_above_200_sma():
    closes = [100.0 + 0.5 * i for i in range(250)]  # rising: last close > SMA200
    assert index_allows_entries(_candles(closes)) is True


def test_index_gate_false_below_200_sma():
    closes = [225.0 - 0.5 * i for i in range(250)]  # falling: last close < SMA200
    assert index_allows_entries(_candles(closes)) is False


def test_index_gate_fails_open_on_short_history():
    assert index_allows_entries(_candles([100.0] * 50)) is True


# ------------------------------------------------------------ 12-1 momentum

N = 300  # >= 252 + 21 sessions of history

FEED = FakeFeed({
    "WIN": _drift_closes(100.0, +0.0020, N),    # ~+65% 12-1
    "MID": _drift_closes(100.0, +0.0005, N),    # ~+13% 12-1
    "NEG": _drift_closes(100.0, -0.0010, N),    # ~-22% 12-1
    "SHORT": [100.0] * 100,                     # too little history — omitted
})


def test_momentum_rank_orders_by_12_1_return():
    ranked = momentum_rank(FEED, ["MID", "NEG", "WIN", "SHORT"])
    assert [sym for sym, _ in ranked] == ["WIN", "MID", "NEG"]
    scores = [s for _, s in ranked]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] > 0 and scores[-1] < 0
    assert "SHORT" not in {sym for sym, _ in ranked}


def test_rotation_scan_skips_negative_momentum():
    signals = momentum_rotation_scan(FEED, ["MID", "NEG", "WIN", "SHORT"],
                                     MarketContext())
    symbols = {s.symbol for s in signals}
    assert "NEG" not in symbols                 # never rotate into negative 12-1
    assert symbols == {"WIN", "MID"}
    for s in signals:
        assert s.stop < s.entry < s.target


def test_rotation_scan_skips_already_held():
    signals = momentum_rotation_scan(FEED, ["MID", "NEG", "WIN", "SHORT"],
                                     MarketContext(), held={"WIN"})
    assert {s.symbol for s in signals} == {"MID"}
