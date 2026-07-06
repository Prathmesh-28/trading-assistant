"""Indian equity transaction-cost model (NSE, discount broker — Zerodha/Groww
rates as of 2026, verified against zerodha.com/charges and groww.in/pricing).

Every backtest that ignores these is inflated: the statutory round trip alone
is ~0.15-0.2% on delivery. Slippage on top is configurable per side — breakout
entries in particular fill worse than the trigger price.

CNC (delivery):
  brokerage  ₹0
  STT        0.1%  of turnover, BOTH sides
  stamp duty 0.015% buy side only
  exchange   0.00325% + SEBI 0.0001%, both sides, +18% GST on those
  DP charge  ~₹15.93 flat, sell side only, per scrip-day

MIS (intraday):
  brokerage  min(₹20, 0.03%) per side
  STT        0.025% SELL side only
  stamp duty 0.003% buy side only
  exchange   0.00325% + SEBI 0.0001%, both sides, +18% GST on (brokerage+those)
"""

from __future__ import annotations

from dataclasses import dataclass

STT_CNC = 0.001          # both sides
STT_MIS_SELL = 0.00025   # sell only
STAMP_CNC_BUY = 0.00015
STAMP_MIS_BUY = 0.00003
EXCHANGE_TXN = 0.0000325
SEBI_FEE = 0.000001
GST = 0.18
DP_CHARGE_SELL = 15.93
MIS_BROKERAGE_CAP = 20.0
MIS_BROKERAGE_PCT = 0.0003


@dataclass
class CostBreakdown:
    brokerage: float = 0.0
    stt: float = 0.0
    stamp: float = 0.0
    exchange: float = 0.0
    gst: float = 0.0
    dp: float = 0.0
    slippage: float = 0.0

    @property
    def total(self) -> float:
        return round(self.brokerage + self.stt + self.stamp + self.exchange
                     + self.gst + self.dp + self.slippage, 2)


def side_costs(product: str, is_buy: bool, price: float, qty: int,
               slippage_pct: float = 0.05) -> CostBreakdown:
    """Costs for ONE side (a buy or a sell) of a trade.
    product: "CNC" (delivery) or "MIS" (intraday). slippage_pct is % of turnover."""
    turnover = price * qty
    c = CostBreakdown()
    if product == "MIS":
        c.brokerage = min(MIS_BROKERAGE_CAP, turnover * MIS_BROKERAGE_PCT)
        c.stt = 0.0 if is_buy else turnover * STT_MIS_SELL
        c.stamp = turnover * STAMP_MIS_BUY if is_buy else 0.0
    else:  # CNC
        c.stt = turnover * STT_CNC
        c.stamp = turnover * STAMP_CNC_BUY if is_buy else 0.0
        c.dp = 0.0 if is_buy else DP_CHARGE_SELL
    c.exchange = turnover * (EXCHANGE_TXN + SEBI_FEE)
    c.gst = (c.brokerage + c.exchange) * GST
    c.slippage = turnover * slippage_pct / 100.0
    return c


def round_trip_costs(product: str, entry_price: float, exit_price: float,
                     qty: int, slippage_pct: float = 0.05) -> float:
    """Total ₹ cost of a completed long round trip (buy then sell)."""
    buy = side_costs(product, True, entry_price, qty, slippage_pct)
    sell = side_costs(product, False, exit_price, qty, slippage_pct)
    return round(buy.total + sell.total, 2)
