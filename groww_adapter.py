"""Groww SDK wrapper: quotes, daily history, (execute mode) orders.

No GROWW_API_KEY / GROWW_TOTP_SECRET in .env -> SyntheticFeed, a random-walk
generator so the whole Telegram pipeline can be tested end to end. Positional
scanning is skipped in synthetic mode (no real daily candles).

⚠️  VERIFY AGAINST YOUR INSTALLED growwapi VERSION before live use:
    - the access-token flow (get_access_token signature)
    - the daily candle-interval constant (CANDLE_INTERVAL_DAY below)
    - response key names in get_quote / get_historical_candle_data
The wrapper is defensive — any Groww failure degrades to "no data this tick",
never a crash.
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from config import Settings

log = logging.getLogger("groww")

# README flag: confirm against your growwapi version.
CANDLE_INTERVAL_DAY = 1440  # minutes; some versions use the string "1d"


@dataclass
class Tick:
    symbol: str
    ltp: float
    day_volume: float  # cumulative volume for the day (0 if unknown)


class GrowwAdapter:
    """Real feed via the official growwapi SDK."""

    def __init__(self, settings: Settings):
        import pyotp
        from growwapi import GrowwAPI

        totp = pyotp.TOTP(settings.groww_totp_secret).now()
        # Newer SDKs: GrowwAPI.get_access_token(api_key=..., secret=...|totp=...)
        try:
            token = GrowwAPI.get_access_token(
                api_key=settings.groww_api_key, totp=totp
            )
        except TypeError:
            token = GrowwAPI.get_access_token(
                settings.groww_api_key, settings.groww_api_secret, totp
            )
        self.api = GrowwAPI(token)
        self.synthetic = False
        log.info("Groww connected")

    def get_tick(self, symbol: str) -> Tick | None:
        try:
            q = self.api.get_quote(
                exchange=self.api.EXCHANGE_NSE,
                segment=self.api.SEGMENT_CASH,
                trading_symbol=symbol,
            )
            ltp = float(q.get("last_price") or q.get("ltp") or 0)
            vol = float(q.get("volume") or q.get("total_traded_volume") or 0)
            if ltp <= 0:
                return None
            return Tick(symbol, ltp, vol)
        except Exception as e:
            log.warning("quote %s failed: %s", symbol, e)
            return None

    def get_daily_candles(self, symbol: str, days: int = 120) -> list[dict]:
        """-> [{date, open, high, low, close, volume}] oldest first."""
        try:
            end = int(time.time() * 1000)
            start = end - days * 86_400_000
            data = self.api.get_historical_candle_data(
                trading_symbol=symbol,
                exchange=self.api.EXCHANGE_NSE,
                segment=self.api.SEGMENT_CASH,
                start_time=start,
                end_time=end,
                interval_in_minutes=CANDLE_INTERVAL_DAY,
            )
            candles = data.get("candles") or []
            out = []
            for c in candles:
                # candle rows: [epoch, open, high, low, close, volume]
                out.append({
                    "date": datetime.fromtimestamp(float(c[0]), tz=timezone.utc).date().isoformat(),
                    "open": float(c[1]), "high": float(c[2]),
                    "low": float(c[3]), "close": float(c[4]),
                    "volume": float(c[5]) if len(c) > 5 else 0.0,
                })
            return out
        except Exception as e:
            log.warning("daily candles %s failed: %s", symbol, e)
            return []

    def get_intraday_candles(self, symbol: str, days: int = 14,
                             interval_minutes: int = 5) -> list[dict]:
        """-> [{ts, open, high, low, close, volume}] oldest first. Used pre-open
        to compute the paper's RVOL (today's first 5-min bar vs 14-day average)."""
        try:
            end = int(time.time() * 1000)
            start = end - days * 86_400_000
            data = self.api.get_historical_candle_data(
                trading_symbol=symbol,
                exchange=self.api.EXCHANGE_NSE,
                segment=self.api.SEGMENT_CASH,
                start_time=start,
                end_time=end,
                interval_in_minutes=interval_minutes,
            )
            out = []
            for c in data.get("candles") or []:
                out.append({
                    "ts": float(c[0]),
                    "open": float(c[1]), "high": float(c[2]),
                    "low": float(c[3]), "close": float(c[4]),
                    "volume": float(c[5]) if len(c) > 5 else 0.0,
                })
            return out
        except Exception as e:
            log.warning("intraday candles %s failed: %s", symbol, e)
            return []

    def place_order(self, symbol: str, side: str, qty: int, product: str) -> str | None:
        """Execute mode only. Returns order id or None."""
        try:
            resp = self.api.place_order(
                trading_symbol=symbol,
                quantity=qty,
                exchange=self.api.EXCHANGE_NSE,
                segment=self.api.SEGMENT_CASH,
                product=product,          # MIS / CNC constant per SDK version
                order_type=self.api.ORDER_TYPE_MARKET,
                transaction_type=side,    # BUY / SELL
                validity=self.api.VALIDITY_DAY,
            )
            return str(resp.get("groww_order_id") or resp.get("order_id"))
        except Exception as e:
            log.error("order %s %s x%s failed: %s", side, symbol, qty, e)
            return None


class SyntheticFeed:
    """Deterministic-ish random walk so the pipeline is testable without creds."""

    BASE_PRICES = {
        "RELIANCE": 2940.0, "HDFCBANK": 1690.0, "ICICIBANK": 1230.0,
        "INFY": 1580.0, "TCS": 3860.0, "SBIN": 830.0, "TATAMOTORS": 990.0,
        "LT": 3630.0, "AXISBANK": 1140.0, "BHARTIARTL": 1520.0,
    }

    def __init__(self, settings: Settings, seed: int | None = None):
        self.synthetic = True
        self._rng = random.Random(seed)
        self._state: dict[str, dict] = {}
        for sym in settings.watchlist:
            px = self.BASE_PRICES.get(sym, 1000.0)
            self._state[sym] = {"px": px, "vol": 0.0, "drift": self._rng.uniform(-0.4, 0.6)}
        log.info("SyntheticFeed active (no Groww credentials) — test mode only")

    def get_tick(self, symbol: str) -> Tick | None:
        s = self._state.get(symbol)
        if not s:
            return None
        step = self._rng.gauss(s["drift"], 1.0) * s["px"] * 0.0006
        s["px"] = max(1.0, s["px"] + step)
        s["vol"] += abs(self._rng.gauss(25_000, 8_000))
        return Tick(symbol, round(s["px"], 2), math.floor(s["vol"]))

    def get_daily_candles(self, symbol: str, days: int = 120) -> list[dict]:
        return []  # positional scan is skipped in synthetic mode

    def get_intraday_candles(self, symbol: str, days: int = 14,
                             interval_minutes: int = 5) -> list[dict]:
        return []

    def place_order(self, *args, **kwargs) -> None:
        return None


def make_feed(settings: Settings):
    if settings.has_groww:
        try:
            return GrowwAdapter(settings)
        except Exception as e:
            log.error("Groww init failed (%s) — falling back to synthetic feed", e)
    return SyntheticFeed(settings)
