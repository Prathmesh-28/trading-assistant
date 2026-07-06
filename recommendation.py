"""The trade-idea object and its phone-friendly Telegram formatting."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from config import IST

_seq = itertools.count(1)


class Horizon(str, Enum):
    INTRADAY = "intraday"      # MIS — square off same day
    POSITIONAL = "positional"  # CNC — hold days–weeks


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"  # short (intraday only)


class Status(str, Enum):
    SUGGESTED = "SUGGESTED"    # pushed to phone, awaiting user
    ACTIVE = "ACTIVE"          # user confirmed with /bought
    SKIPPED = "SKIPPED"        # user replied /skip
    CLOSED = "CLOSED"          # user replied /sold
    EXPIRED = "EXPIRED"        # never taken, day ended


@dataclass
class Recommendation:
    symbol: str
    side: Side
    horizon: Horizon
    entry: float
    stop: float
    target: float
    qty: int
    confidence: str            # LOW / MEDIUM / HIGH
    reason: str                # rule-based trigger description
    why: str = ""              # optional extra context line (currently unused)
    status: Status = Status.SUGGESTED
    created_at: datetime = field(default_factory=lambda: datetime.now(IST))
    idea_id: int = field(default_factory=lambda: next(_seq))

    # filled in when the user confirms / closes the trade
    fill_qty: int = 0
    fill_price: float = 0.0
    exit_price: float = 0.0

    @property
    def risk_reward(self) -> float:
        risk = abs(self.entry - self.stop)
        reward = abs(self.target - self.entry)
        return round(reward / risk, 2) if risk > 0 else 0.0

    @property
    def is_long(self) -> bool:
        return self.side == Side.BUY

    def pnl(self, ltp: float) -> float:
        """Open PnL for a confirmed position at the given last price."""
        if self.fill_qty <= 0:
            return 0.0
        direction = 1 if self.is_long else -1
        ref = self.fill_price or self.entry
        return round((ltp - ref) * self.fill_qty * direction, 2)

    @classmethod
    def from_journal_row(cls, row: dict) -> "Recommendation":
        """Rebuild a live Recommendation from a journal row (state restore
        after an engine restart)."""
        created = datetime.now(IST)
        try:
            created = datetime.fromisoformat(row["created_at"])
        except (KeyError, TypeError, ValueError):
            pass
        rec = cls(
            symbol=row["symbol"], side=Side(row["side"]), horizon=Horizon(row["horizon"]),
            entry=row["entry"], stop=row["stop"], target=row["target"], qty=row["qty"],
            confidence=row.get("confidence") or "—", reason=row.get("reason") or "",
            why=row.get("why") or "", status=Status(row["status"]),
        )
        rec.created_at = created
        rec.fill_qty = row.get("fill_qty") or 0
        rec.fill_price = row.get("fill_price") or 0.0
        rec.exit_price = row.get("exit_price") or 0.0
        return rec

    def to_dict(self, ltp: float | None = None) -> dict:
        """JSON-serializable view for the web dashboard (REST + websocket)."""
        live_ltp = ltp if ltp is not None else (self.fill_price or self.entry)
        return {
            "idea_id": self.idea_id,
            "symbol": self.symbol,
            "side": self.side.value,
            "horizon": self.horizon.value,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "qty": self.qty,
            "confidence": self.confidence,
            "reason": self.reason,
            "why": self.why,
            "status": self.status.value,
            "risk_reward": self.risk_reward,
            "created_at": self.created_at.isoformat(),
            "fill_qty": self.fill_qty,
            "fill_price": self.fill_price,
            "exit_price": self.exit_price,
            "ltp": live_ltp,
            "pnl": self.pnl(live_ltp) if self.fill_qty > 0 else 0.0,
        }

    def format_telegram(self) -> str:
        tag = "Intraday (MIS)" if self.horizon == Horizon.INTRADAY else "Positional (CNC)"
        tail = (
            "square off same day"
            if self.horizon == Horizon.INTRADAY
            else "hold days–weeks"
        )
        ts = self.created_at.strftime("%H:%M IST")
        lines = [
            f"{'🟢' if self.is_long else '🔻'} {self.side.value} {self.symbol} — {tag}",
            f"Entry ~ ₹{self.entry:,.2f}",
            f"Stop ₹{self.stop:,.2f} | Target ₹{self.target:,.2f} (R:R {self.risk_reward})",
            f"Suggested qty ~ {self.qty} | Confidence: {self.confidence}",
        ]
        if self.why:
            lines.append(f"Why: {self.why}")
        elif self.reason:
            lines.append(f"Why: {self.reason}")
        lines.append(f"{tail} · {ts}")
        lines.append(f"Reply: /bought {self.symbol} [qty] [price] · /skip {self.symbol}")
        return "\n".join(lines)
