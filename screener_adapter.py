"""screener.in adapter — isolated data source (mirrors the groww_adapter
import boundary). OFF by default (SCREENER_SCRAPE_ENABLED); the operator of
this personal tool owns the terms-of-use decision for their own account.

Uses screener.in's own **Excel export** (the robust, structured path), not
HTML scraping:
  1. GET  /api/company/search/?q=SYMBOL      -> resolve to the company URL
  2. GET  the company page                   -> warehouse id from the export
                                                form action
  3. POST /user/company/export/<id>/         -> the .xlsx report
  4. parse the "Data Sheet" tab (a stable, versioned layout) into a clean dict

Why export over HTML: the Data Sheet is a fixed schema ("LATEST VERSION 2.1"),
so it doesn't drift when the website's HTML changes. The export requires a
logged-in session, so the operator supplies their OWN cookie (SCREENER_COOKIE);
without it the POST 403s and callers fall back to yfinance.

Built defensively: process-wide rate limit + jitter, long disk cache, 403/429
cooldown, label-scan parser that fails soft to None, provenance stamp.
"""

from __future__ import annotations

import io
import json
import logging
import os
import random
import re
import time
from pathlib import Path

log = logging.getLogger("screener")

_BASE = "https://www.screener.in"
_CACHE_DIR = Path(os.getenv("SCREENER_CACHE_DIR", "/tmp/screener_cache"))
_TTL = float(os.getenv("SCREENER_CACHE_TTL_H", "18")) * 3600
_MIN_INTERVAL = float(os.getenv("SCREENER_MIN_INTERVAL", "4"))
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_last_request = [0.0]
_blocked_until = [0.0]


def enabled() -> bool:
    on = os.getenv("SCREENER_SCRAPE_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
    if on and not os.getenv("SCREENER_COOKIE", "").strip():
        log.warning("SCREENER_SCRAPE_ENABLED but no SCREENER_COOKIE — the Excel "
                    "export needs a logged-in session; will fall back to yfinance")
    return on


def _cache_path(symbol: str) -> Path:
    return _CACHE_DIR / f"{symbol.upper()}.json"


def _read_cache(symbol: str) -> dict | None:
    p = _cache_path(symbol)
    try:
        if p.exists() and time.time() - p.stat().st_mtime < _TTL:
            return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        pass
    return None


def _write_cache(symbol: str, data: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(symbol).write_text(json.dumps(data))
    except Exception:  # noqa: BLE001
        pass


def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.2, 0.8))
    _last_request[0] = time.time()


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_datasheet(xlsx_bytes: bytes) -> dict | None:
    """Parse the screener 'Data Sheet' tab (schema v2.x) into fundamentals.
    Label-scan (not hardcoded rows) so minor layout shifts still resolve.
    Returns None on drift so callers fall back to yfinance."""
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True, read_only=True)
    except Exception as e:  # noqa: BLE001 — corrupt/HTML-error body
        log.warning("screener export not a valid xlsx: %s", e)
        return None
    if "Data Sheet" not in wb.sheetnames:
        log.warning("screener drift: no 'Data Sheet' tab — failing soft")
        return None
    ds = wb["Data Sheet"]

    rows = [[c.value for c in row] for row in ds.iter_rows()]

    def label_row(label, start=0, end=None):
        end = end if end is not None else len(rows)
        lab = label.lower()
        for i in range(start, min(end, len(rows))):
            a = rows[i][0]
            if isinstance(a, str) and a.strip().lower() == lab:
                return i
        return None

    def cell(label, col=1, start=0, end=None):
        i = label_row(label, start, end)
        return _f(rows[i][col]) if i is not None and col < len(rows[i]) else None

    def series(label, start, end):
        i = label_row(label, start, end)
        if i is None:
            return []
        return [_f(v) for v in rows[i][1:] if _f(v) is not None]

    # section anchors
    pl = label_row("PROFIT & LOSS") or 0
    bs = label_row("BALANCE SHEET") or (pl + 40)
    cf = label_row("CASH FLOW:") or (bs + 25)

    name = rows[0][1] if rows and len(rows[0]) > 1 and isinstance(rows[0][1], str) else None
    face_value = cell("Face Value", 1, 0, pl)
    price = cell("Current Price", 1, 0, pl)
    mcap = cell("Market Capitalization", 1, 0, pl)

    sales = series("Sales", pl, bs)
    net_profit = series("Net profit", pl, bs)
    dividend = series("Dividend Amount", pl, bs)

    equity = series("Equity Share Capital", bs, cf)
    reserves = series("Reserves", bs, cf)
    borrowings = series("Borrowings", bs, cf)
    shares = series("No. of Equity Shares", bs, cf)

    if not sales or not net_profit:
        log.warning("screener drift: Sales/Net-profit rows empty — failing soft")
        return None

    def last(xs):
        return xs[-1] if xs else None

    latest_np = last(net_profit)
    latest_equity = (last(equity) or 0) + (last(reserves) or 0)
    latest_borrow = last(borrowings)

    def pct(n, d):
        return round(n / d * 100, 1) if n is not None and d else None

    out = {
        "source": "screener.in",
        "name": name,
        "face_value": face_value,
        "market_cap": mcap,
        "pe": (round(mcap / latest_np, 2) if mcap and latest_np else None),
        "roe_pct": pct(latest_np, latest_equity),
        "debt_to_equity": (round(latest_borrow / latest_equity, 2)
                           if latest_borrow is not None and latest_equity else None),
        "roce_pct": None,
        "dividend_yield_pct": None,
        "payout_ratio_pct": pct(last(dividend), latest_np),
        "years": [],
    }
    # revenue/profit history (align by shared length, newest last)
    n = min(len(sales), len(net_profit))
    for i in range(n):
        out["years"].append({"year": None, "revenue": sales[i],
                             "net_income": net_profit[i], "revenue_growth_pct": None})
    if price and last(shares):
        eps = latest_np * 1e7 / last(shares) if latest_np else None  # Cr->abs
        out["eps"] = round(eps, 2) if eps else None
    return out


def fetch(symbol: str) -> dict | None:
    if not enabled():
        return None
    cached = _read_cache(symbol)
    if cached is not None:
        return cached
    if time.time() < _blocked_until[0]:
        return None
    cookie = os.getenv("SCREENER_COOKIE", "").strip()
    if not cookie:
        return None  # export needs a session; fall back cleanly
    try:
        import httpx

        with httpx.Client(timeout=20, follow_redirects=True,
                          headers={"User-Agent": _UA, "Cookie": cookie}) as client:
            _throttle()
            search = client.get(f"{_BASE}/api/company/search/", params={"q": symbol})
            if search.status_code in (403, 429):
                _blocked_until[0] = time.time() + 1800
                log.warning("screener search %s -> %s; 30min cooldown", symbol, search.status_code)
                return None
            hits = search.json() if search.status_code == 200 else []
            url = next((h["url"] for h in hits
                        if h.get("url", "").upper().rstrip("/").endswith(symbol.upper())), None)
            url = url or (hits[0]["url"] if hits else None)
            if not url:
                log.warning("screener: symbol %s not found", symbol)
                return None

            _throttle()
            page = client.get(f"{_BASE}{url}")
            m = re.search(r"/user/company/export/(\d+)/", page.text)
            csrf = client.cookies.get("csrftoken", "")
            if not m:
                log.warning("screener drift: export id not found on %s page", symbol)
                return None
            wid = m.group(1)

            _throttle()
            export = client.post(
                f"{_BASE}/user/company/export/{wid}/",
                data={"csrfmiddlewaretoken": csrf, "next": url},
                headers={"Referer": f"{_BASE}{url}", "Content-Type": "application/x-www-form-urlencoded"},
            )
            if export.status_code in (403, 429):
                _blocked_until[0] = time.time() + 1800
                log.warning("screener export %s -> %s; 30min cooldown", symbol, export.status_code)
                return None
            if export.status_code != 200:
                log.warning("screener export %s -> HTTP %s", symbol, export.status_code)
                return None
            data = parse_datasheet(export.content)
            if data:
                _write_cache(symbol, data)
            return data
    except Exception as e:  # noqa: BLE001 — never break the fundamentals card
        log.warning("screener fetch %s failed: %s", symbol, e)
        return None
