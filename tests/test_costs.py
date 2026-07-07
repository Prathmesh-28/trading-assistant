"""costs.py — Indian transaction-cost model.

Bands below are sanity rails, not exact-statute assertions: a CNC round trip
(incl. the default 0.05%/side slippage) on a ~₹40k trade should land around
0.3-0.45% of the trade value; MIS should be cheaper. Component tests pin the
side asymmetries: STT both sides on CNC but sell-only on MIS, stamp duty
buy-only, DP charge only on a CNC sell, brokerage only on MIS.
"""

from costs import DP_CHARGE_SELL, round_trip_costs, side_costs

PRICE = 400.0
QTY = 100          # ₹40,000 trade value
TRADE_VALUE = PRICE * QTY


# ------------------------------------------------------------ round trips

def test_cnc_round_trip_in_expected_band():
    total = round_trip_costs("CNC", PRICE, PRICE, QTY)  # default 0.05%/side slippage
    pct_of_trade = 100.0 * total / TRADE_VALUE
    assert 0.30 <= pct_of_trade <= 0.45, f"CNC round trip {pct_of_trade:.3f}% out of band"


def test_mis_round_trip_cheaper_than_cnc():
    mis = round_trip_costs("MIS", PRICE, PRICE, QTY)
    cnc = round_trip_costs("CNC", PRICE, PRICE, QTY)
    assert mis < cnc
    pct_of_trade = 100.0 * mis / TRADE_VALUE
    assert 0.10 <= pct_of_trade <= 0.30, f"MIS round trip {pct_of_trade:.3f}% out of band"


def test_round_trip_is_buy_plus_sell():
    buy = side_costs("CNC", True, PRICE, QTY).total
    sell = side_costs("CNC", False, PRICE, QTY).total
    assert abs(round_trip_costs("CNC", PRICE, PRICE, QTY) - (buy + sell)) < 0.02


# ------------------------------------------------------------ CNC sides

def test_cnc_buy_side_components():
    c = side_costs("CNC", True, PRICE, QTY)
    assert c.brokerage == 0.0                       # delivery is brokerage-free
    assert abs(c.stt - TRADE_VALUE * 0.001) < 1e-9  # STT on the buy too (CNC)
    assert c.stamp > 0.0                            # stamp duty is buy-side
    assert c.dp == 0.0                              # DP charge never on a buy
    assert c.exchange > 0.0 and c.gst > 0.0


def test_cnc_sell_side_components():
    c = side_costs("CNC", False, PRICE, QTY)
    assert abs(c.stt - TRADE_VALUE * 0.001) < 1e-9  # STT on the sell too (CNC)
    assert c.stamp == 0.0                           # no stamp on a sell
    assert c.dp == DP_CHARGE_SELL                   # flat DP charge, CNC sell only


# ------------------------------------------------------------ MIS sides

def test_mis_buy_side_components():
    c = side_costs("MIS", True, PRICE, QTY)
    assert c.stt == 0.0                             # MIS STT is sell-only
    assert c.stamp > 0.0
    assert c.dp == 0.0
    assert abs(c.brokerage - min(20.0, TRADE_VALUE * 0.0003)) < 1e-9


def test_mis_sell_side_components():
    c = side_costs("MIS", False, PRICE, QTY)
    assert abs(c.stt - TRADE_VALUE * 0.00025) < 1e-9
    assert c.stamp == 0.0
    assert c.dp == 0.0                              # DP charge is CNC-only


def test_mis_brokerage_caps_at_20():
    big = side_costs("MIS", True, 2000.0, 1000)     # ₹20L turnover: 0.03% would be 600
    assert big.brokerage == 20.0


# ------------------------------------------------------------ slippage

def test_slippage_scales_with_turnover_and_can_be_zeroed():
    c = side_costs("CNC", True, PRICE, QTY, slippage_pct=0.05)
    assert abs(c.slippage - TRADE_VALUE * 0.0005) < 1e-9
    assert side_costs("CNC", True, PRICE, QTY, slippage_pct=0.0).slippage == 0.0
