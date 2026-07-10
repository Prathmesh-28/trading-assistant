"""Suggested position sizing + (execute mode) daily-loss kill switch."""

from __future__ import annotations

import math

from config import Settings


def suggested_qty(entry: float, stop: float, settings: Settings,
                  capital: float = None) -> int:
    """Risk-based size: risk RISK_PER_TRADE_PCT of capital between entry and
    stop, capped so the position never exceeds MAX_POSITION_VALUE. Pass the
    live wallet equity as `capital` so size compounds with the account;
    defaults to the static CAPITAL setting (backtests, tests)."""
    per_share_risk = abs(entry - stop)
    if per_share_risk <= 0 or entry <= 0:
        return 0
    base = capital if capital is not None else settings.capital
    risk_budget = base * settings.risk_per_trade_pct / 100.0
    qty = math.floor(risk_budget / per_share_risk)
    qty = min(qty, math.floor(settings.max_position_value / entry))
    return max(qty, 0)


def portfolio_allows(open_count: int, open_risk: float, new_risk: float,
                     settings: Settings, capital: float = None) -> tuple[bool, str]:
    """Portfolio heat check (Turtle unit caps / Van Tharp's 6-10% total-open-
    risk heuristic): a new idea is blocked when either cap would be breached.
    open_risk / new_risk are ₹ entry-to-stop amounts. Returns (ok, reason)."""
    if open_count >= settings.max_open_positions:
        return False, f"max open positions ({settings.max_open_positions}) reached"
    base = capital if capital is not None else settings.capital
    heat_cap = base * settings.max_portfolio_risk_pct / 100.0
    if open_risk + new_risk > heat_cap:
        return False, (f"portfolio heat cap: open ₹{open_risk:,.0f} + new ₹{new_risk:,.0f} "
                       f"> ₹{heat_cap:,.0f} ({settings.max_portfolio_risk_pct}% of capital)")
    return True, ""


class KillSwitch:
    """Execute-mode only: halts auto-orders once the day's realised loss exceeds
    a multiple of the per-trade risk budget. Recommend mode never places orders,
    so this is advisory there."""

    def __init__(self, settings: Settings, max_daily_r: float = 3.0):
        self._budget = settings.capital * settings.risk_per_trade_pct / 100.0
        self._max_loss = self._budget * max_daily_r
        self.realised = 0.0
        self.tripped = False

    def record(self, pnl: float) -> None:
        self.realised += pnl
        if self.realised <= -self._max_loss:
            self.tripped = True

    @property
    def ok_to_trade(self) -> bool:
        return not self.tripped
