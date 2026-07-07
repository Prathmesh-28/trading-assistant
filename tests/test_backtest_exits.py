"""backtest.py — the same-bar exit resolver and the Monte Carlo drawdown.

_resolve_exit conventions under test (the backtest honesty rules):
gap-aware fills at the open, stop-wins-on-ambiguous-bar, None when neither
level is touched. Long positions here use stop 95 / target 110; shorts use
stop 105 / target 90.
"""

from backtest import _monte_carlo_dd, _resolve_exit

LONG_STOP, LONG_TARGET = 95.0, 110.0
SHORT_STOP, SHORT_TARGET = 105.0, 90.0


# ------------------------------------------------------------ long exits

def test_long_clean_stop():
    r = _resolve_exit(True, 100.0, 101.0, 94.0, LONG_STOP, LONG_TARGET)
    assert r == (LONG_STOP, "stop")


def test_long_clean_target():
    r = _resolve_exit(True, 100.0, 111.0, 99.0, LONG_STOP, LONG_TARGET)
    assert r == (LONG_TARGET, "target")


def test_long_ambiguous_bar_stop_wins():
    # Bar spans both levels; open is between them => fill at the stop.
    r = _resolve_exit(True, 100.0, 111.0, 94.0, LONG_STOP, LONG_TARGET)
    assert r == (LONG_STOP, "stop_ambiguous")


def test_long_no_hit():
    assert _resolve_exit(True, 100.0, 105.0, 96.0, LONG_STOP, LONG_TARGET) is None


def test_long_gap_through_stop_fills_at_open():
    # Opened below the stop: you get the open, not the stop price.
    r = _resolve_exit(True, 90.0, 92.0, 88.0, LONG_STOP, LONG_TARGET)
    assert r == (90.0, "stop")


def test_long_gap_through_target_fills_at_open():
    # Opened above the target: you get the open, not the target price.
    r = _resolve_exit(True, 112.0, 115.0, 111.0, LONG_STOP, LONG_TARGET)
    assert r == (112.0, "target")


def test_long_gap_past_stop_on_ambiguous_bar_fills_at_open():
    # Opened through the stop AND the bar later spanned the target too.
    r = _resolve_exit(True, 94.0, 111.0, 90.0, LONG_STOP, LONG_TARGET)
    assert r == (94.0, "stop_ambiguous")


# ------------------------------------------------------------ short exits

def test_short_clean_stop():
    r = _resolve_exit(False, 100.0, 106.0, 99.0, SHORT_STOP, SHORT_TARGET)
    assert r == (SHORT_STOP, "stop")


def test_short_clean_target():
    r = _resolve_exit(False, 100.0, 101.0, 89.0, SHORT_STOP, SHORT_TARGET)
    assert r == (SHORT_TARGET, "target")


def test_short_ambiguous_bar_stop_wins():
    r = _resolve_exit(False, 100.0, 106.0, 89.0, SHORT_STOP, SHORT_TARGET)
    assert r == (SHORT_STOP, "stop_ambiguous")


def test_short_no_hit():
    assert _resolve_exit(False, 100.0, 103.0, 95.0, SHORT_STOP, SHORT_TARGET) is None


def test_short_gap_through_stop_fills_at_open():
    r = _resolve_exit(False, 107.0, 109.0, 106.0, SHORT_STOP, SHORT_TARGET)
    assert r == (107.0, "stop")


def test_short_gap_through_target_fills_at_open():
    r = _resolve_exit(False, 88.0, 89.0, 86.0, SHORT_STOP, SHORT_TARGET)
    assert r == (88.0, "target")


# ------------------------------------------------------------ Monte Carlo DD

PNLS = [120.0, -60.0, 200.0, -90.0, 45.0, -30.0, 80.0, -150.0, 60.0, 10.0]


def test_monte_carlo_p50_not_above_p95():
    out = _monte_carlo_dd(PNLS, 100_000.0)
    assert set(out) == {"p50_max_dd", "p95_max_dd"}
    assert 0.0 <= out["p50_max_dd"] <= out["p95_max_dd"]


def test_monte_carlo_deterministic_for_same_seed():
    a = _monte_carlo_dd(PNLS, 100_000.0, iters=500, seed=7)
    b = _monte_carlo_dd(PNLS, 100_000.0, iters=500, seed=7)
    assert a == b
    # and the default-seed call is reproducible too
    assert _monte_carlo_dd(PNLS, 100_000.0) == _monte_carlo_dd(PNLS, 100_000.0)
