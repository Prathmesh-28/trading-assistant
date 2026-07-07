"""risk_manager.py — per-trade sizing and portfolio heat caps.

Settings are pinned in-code (the dataclass is mutable) so the tests do not
depend on the shell environment: capital ₹1,00,000, 0.5% risk per trade
(₹500 budget), ₹50,000 max position value, 6 max positions, 6% heat cap
(₹6,000 of open entry-to-stop risk).
"""

import pytest

from config import Settings
from risk_manager import portfolio_allows, suggested_qty


@pytest.fixture()
def settings():
    s = Settings()
    s.capital = 100_000.0
    s.risk_per_trade_pct = 0.5
    s.max_position_value = 50_000.0
    s.max_open_positions = 6
    s.max_portfolio_risk_pct = 6.0
    return s


# ------------------------------------------------------------ suggested_qty

def test_qty_is_risk_budget_over_per_share_risk(settings):
    # ₹500 budget / ₹5 per-share risk = 100 shares (₹10k position, under the cap)
    assert suggested_qty(100.0, 95.0, settings) == 100


def test_qty_capped_by_max_position_value(settings):
    # Tiny stop distance would size ~5000 shares; the ₹50k value cap allows 500.
    assert suggested_qty(100.0, 99.9, settings) == 500


def test_qty_zero_on_bad_inputs(settings):
    assert suggested_qty(100.0, 100.0, settings) == 0   # zero risk per share
    assert suggested_qty(0.0, -5.0, settings) == 0      # non-positive entry
    assert suggested_qty(-10.0, -15.0, settings) == 0


def test_qty_uses_absolute_risk_for_shorts(settings):
    # stop above entry (short setup): same distance, same size
    assert suggested_qty(100.0, 105.0, settings) == suggested_qty(100.0, 95.0, settings)


# ------------------------------------------------------------ portfolio_allows

def test_allows_under_both_caps(settings):
    ok, reason = portfolio_allows(2, 1_000.0, 500.0, settings)
    assert ok is True and reason == ""


def test_blocks_at_max_positions(settings):
    ok, reason = portfolio_allows(6, 0.0, 500.0, settings)
    assert ok is False
    assert "max open positions" in reason


def test_blocks_at_heat_cap(settings):
    # ₹5,600 open + ₹500 new = ₹6,100 > ₹6,000 cap
    ok, reason = portfolio_allows(2, 5_600.0, 500.0, settings)
    assert ok is False
    assert "heat" in reason.lower()


def test_allows_exactly_at_heat_cap(settings):
    # cap is exclusive: 5,500 + 500 == 6,000 is still allowed
    ok, _ = portfolio_allows(2, 5_500.0, 500.0, settings)
    assert ok is True
