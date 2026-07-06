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
import zlib
from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta, timezone

from config import IST, Settings

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

    def get_chart_candles(self, symbol: str, interval_minutes: int, days: int) -> list[dict]:
        """Dashboard chart feed. Daily rows carry `date` (ISO str); intraday rows
        carry `ts` (epoch ms). Same defensive behaviour as the other getters."""
        if interval_minutes >= CANDLE_INTERVAL_DAY:
            return self.get_daily_candles(symbol, days=days)
        return self.get_intraday_candles(symbol, days=days, interval_minutes=interval_minutes)

    def prev_close(self, symbol: str) -> float | None:
        """Most recent completed session's close (for watchlist change-%)."""
        try:
            today = datetime.now(IST).date().isoformat()
            past = [c for c in self.get_daily_candles(symbol, days=10) if c["date"] < today]
            return past[-1]["close"] if past else None
        except Exception as e:  # noqa: BLE001 — quotes must fail soft
            log.warning("prev_close %s failed: %s", symbol, e)
            return None

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
        self._chart_cache: dict[tuple, list] = {}  # deterministic demo history
        for sym in settings.watchlist:
            px = self.BASE_PRICES.get(sym, 1000.0)
            self._state[sym] = {"px": px, "vol": 0.0, "drift": self._rng.uniform(-0.4, 0.6)}
        log.info("SyntheticFeed active (no Groww credentials) — test mode only")

    # -- demo chart history --------------------------------------------------
    # Deterministic per-symbol random walks so the dashboard's charts render
    # without creds. Served ONLY via get_chart_candles (cosmetic); the
    # strategy-facing get_daily_candles/get_intraday_candles still return []
    # so positional scanning and backtesting stay OFF synthetic data.

    @staticmethod
    def _seed(symbol: str) -> int:
        return zlib.crc32(symbol.encode())  # hash() is salted per process

    def _base(self, symbol: str) -> float:
        return self.BASE_PRICES.get(symbol, 1000.0)

    def _gen_daily(self, symbol: str) -> list[dict]:
        """~250 completed daily candles ending on the last weekday before today,
        walked backwards from the base price so the last close == prev_close ==
        the price the live tick walk starts from."""
        key = (symbol, "1d", datetime.now(IST).date())
        if key in self._chart_cache:
            return self._chart_cache[key]
        rng = random.Random(self._seed(symbol))
        d = datetime.now(IST).date() - timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        dates = []
        for _ in range(250):
            dates.append(d)
            d -= timedelta(days=1)
            while d.weekday() >= 5:
                d -= timedelta(days=1)
        dates.reverse()
        closes = [self._base(symbol)]
        for _ in range(len(dates) - 1):
            closes.append(closes[-1] / (1 + rng.gauss(0.0004, 0.012)))
        closes.reverse()
        out, prev = [], closes[0]
        for day, c in zip(dates, closes):
            hi = max(prev, c) * (1 + abs(rng.gauss(0, 0.004)))
            lo = min(prev, c) * (1 - abs(rng.gauss(0, 0.004)))
            out.append({"date": day.isoformat(), "open": round(prev, 2),
                        "high": round(hi, 2), "low": round(lo, 2), "close": round(c, 2),
                        "volume": float(int(abs(rng.gauss(2_500_000, 900_000))))})
            prev = c
        self._chart_cache[key] = out
        return out

    def _gen_intraday_past(self, symbol: str, interval_minutes: int, sessions: int) -> list[dict]:
        """Completed 09:15–15:30 sessions before today, ending at the base price."""
        key = (symbol, interval_minutes, sessions, datetime.now(IST).date())
        if key in self._chart_cache:
            return self._chart_cache[key]
        rng = random.Random(self._seed(symbol) ^ interval_minutes)
        days, d = [], datetime.now(IST).date() - timedelta(days=1)
        while len(days) < sessions:
            if d.weekday() < 5:
                days.append(d)
            d -= timedelta(days=1)
        days.reverse()
        per_session = (6 * 60 + 15) // interval_minutes
        closes = [self._base(symbol)]
        for _ in range(per_session * len(days) - 1):
            closes.append(closes[-1] / (1 + rng.gauss(0.00005, 0.0012)))
        closes.reverse()
        out, prev, i = [], closes[0], 0
        for day in days:
            t0 = datetime.combine(day, dtime(9, 15), tzinfo=IST)
            for b in range(per_session):
                c = closes[i]
                i += 1
                hi = max(prev, c) * (1 + abs(rng.gauss(0, 0.0008)))
                lo = min(prev, c) * (1 - abs(rng.gauss(0, 0.0008)))
                out.append({"ts": (t0 + timedelta(minutes=interval_minutes * b)).timestamp() * 1000,
                            "open": round(prev, 2), "high": round(hi, 2),
                            "low": round(lo, 2), "close": round(c, 2),
                            "volume": float(int(abs(rng.gauss(60_000, 20_000))))})
                prev = c
        self._chart_cache[key] = out
        return out

    def _today_partial(self, symbol: str, interval_minutes: int, prev: float) -> list[dict]:
        """Today's bars from 09:15 up to the last completed bucket, ending at the
        CURRENT walked price so live ticks continue the chart seamlessly."""
        now = datetime.now(IST)
        start = datetime.combine(now.date(), dtime(9, 15), tzinfo=IST)
        n = int((now - start).total_seconds() // (interval_minutes * 60))
        if n <= 0:
            return []
        live = self._state.get(symbol, {}).get("px", self._base(symbol))
        rng = random.Random(self._seed(symbol) ^ 0xDEAD)
        step = (live / prev) ** (1.0 / n) if prev > 0 else 1.0
        out = []
        for b in range(n):
            c = live if b == n - 1 else prev * step * (1 + rng.gauss(0, 0.0008))
            hi = max(prev, c) * (1 + abs(rng.gauss(0, 0.0006)))
            lo = min(prev, c) * (1 - abs(rng.gauss(0, 0.0006)))
            out.append({"ts": (start + timedelta(minutes=interval_minutes * b)).timestamp() * 1000,
                        "open": round(prev, 2), "high": round(hi, 2),
                        "low": round(lo, 2), "close": round(c, 2),
                        "volume": float(int(abs(rng.gauss(60_000, 20_000))))})
            prev = c
        return out

    def get_chart_candles(self, symbol: str, interval_minutes: int, days: int) -> list[dict]:
        if interval_minutes >= 1440:
            rows = max(30, int(days * 5 / 7))
            return self._gen_daily(symbol)[-rows:]
        sessions = max(1, min(days, 10))
        past = self._gen_intraday_past(symbol, interval_minutes, sessions)
        prev = past[-1]["close"] if past else self._base(symbol)
        return past + self._today_partial(symbol, interval_minutes, prev)

    def prev_close(self, symbol: str) -> float | None:
        return self._base(symbol)

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
