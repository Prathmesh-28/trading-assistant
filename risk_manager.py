"""Suggested position sizing + (execute mode) daily-loss kill switch."""

from __future__ import annotations

import math

from config import Settings


def suggested_qty(entry: float, stop: float, settings: Settings) -> int:
    """Risk-based size: risk RISK_PER_TRADE_PCT of capital between entry and stop,
    capped so the position never exceeds MAX_POSITION_VALUE."""
    per_share_risk = abs(entry - stop)
    if per_share_risk <= 0 or entry <= 0:
        return 0
    risk_budget = settings.capital * settings.risk_per_trade_pct / 100.0
    qty = math.floor(risk_budget / per_share_risk)
    qty = min(qty, math.floor(settings.max_position_value / entry))
    return max(qty, 0)


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
