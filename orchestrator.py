"""OPTIONAL auto-execution entrypoint (execute mode).

Same signal flow as recommend_engine, but orders are placed through Groww.
LIVE=false (default) is a dry run — orders are logged + alerted, not sent.

⚠️ SEBI note: automated order placement above exchange thresholds needs an
Algo-ID registered through your broker. Recommend mode has no such issue.
Run recommend_engine.py unless you have explicitly decided otherwise.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from config import Settings
from recommend_engine import RecommendEngine
from recommendation import Horizon, Status
from risk_manager import KillSwitch
from strategy import Signal

log = logging.getLogger("orchestrator")


class Orchestrator(RecommendEngine):
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.kill = KillSwitch(settings)

    async def publish(self, sig: Signal) -> None:
        """Instead of waiting for /bought, place (or dry-run) the order directly."""
        if not self.kill.ok_to_trade:
            await self.notifier.send("🛑 Kill switch tripped — no more auto-orders today.")
            return
        await super().publish(sig)  # journal + Telegram, idea lands in pending
        if sig.symbol not in self.pending:
            return
        rec, row = self.pending.pop(sig.symbol)
        product = "MIS" if rec.horizon == Horizon.INTRADAY else "CNC"
        if self.s.live:
            order_id = self.feed.place_order(rec.symbol, rec.side.value, rec.qty, product)
            placed = order_id is not None
            note = f"order {order_id}" if placed else "ORDER FAILED"
        else:
            placed, note = True, "DRY RUN — set LIVE=true to send real orders"
        if placed:
            rec.status = Status.ACTIVE
            rec.fill_qty = rec.qty
            rec.fill_price = rec.entry
            self.journal.update(row, rec)
            from recommend_engine import Position
            self.active[rec.symbol] = Position(rec, row)
        await self.notifier.send(f"⚙️ {rec.side.value} {rec.symbol} x{rec.qty} ({product}) — {note}")


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)-10s %(levelname)-7s %(message)s")
    settings = Settings()
    if settings.live and not settings.has_groww:
        sys.exit("LIVE=true but Groww credentials are missing — refusing to start.")
    try:
        asyncio.run(Orchestrator(settings).run())
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()
