"""screener.in adapter — isolated data source (mirrors the groww_adapter
import boundary). OFF by default (SCREENER_SCRAPE_ENABLED); the operator of
this personal tool owns the terms-of-use decision for their own account.

Built defensively per the feature spec:
  - hard rate limit (1 req / SCREENER_MIN_INTERVAL s) + jitter, process-wide
  - disk cache with long TTL (fundamentals are quarterly facts, not live)
  - optional user-supplied session cookie (your own logged-in session)
  - HTML-structure drift detector: selectors gone -> fail soft to None
  - 403/429 backoff: on a block, disable for a cooldown and let callers fall
    back to the yfinance path in fundamentals.py
  - provenance stamp so the UI can show every value came from screener.in

Nothing here is imported unless SCREENER_SCRAPE_ENABLED is true.
"""

from __future__ import annotations

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

_last_request = [0.0]        # process-wide throttle
_blocked_until = [0.0]       # cooldown after a 403/429


def enabled() -> bool:
    on = os.getenv("SCREENER_SCRAPE_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
    if on:
        log.info("screener.in scraping ENABLED — operator-owned ToS decision; "
                 "rate-limited to 1 req / %.0fs, %.0fh cache", _MIN_INTERVAL, _TTL / 3600)
    return on


def _cache_path(symbol: str, variant: str) -> Path:
    return _CACHE_DIR / f"{symbol.upper()}_{variant}.json"


def _read_cache(symbol: str, variant: str) -> dict | None:
    p = _cache_path(symbol, variant)
    try:
        if p.exists() and time.time() - p.stat().st_mtime < _TTL:
            return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        pass
    return None


def _write_cache(symbol: str, variant: str, data: dict) -> None:
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(symbol, variant).write_text(json.dumps(data))
    except Exception:  # noqa: BLE001
        pass


def _throttle() -> None:
    wait = _MIN_INTERVAL - (time.time() - _last_request[0])
    if wait > 0:
        time.sleep(wait + random.uniform(0.2, 0.8))   # jitter
    _last_request[0] = time.time()


def _num(text: str):
    """'1,234.5 Cr' / '12.3%' / '1.23' -> float, else None."""
    if not text:
        return None
    t = text.replace(",", "").replace("%", "").replace("₹", "").strip()
    m = re.search(r"-?\d+\.?\d*", t)
    return float(m.group()) if m else None


def _parse(html: str, symbol: str, variant: str) -> dict | None:
    """Parse a screener.in company page. Any missing landmark -> None (drift
    detector), so a layout change degrades to the yfinance fallback."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    top = soup.select_one("#top-ratios")
    if top is None:
        log.warning("screener drift: #top-ratios missing for %s — failing soft", symbol)
        return None

    ratios = {}
    for li in top.select("li"):
        name_el = li.select_one(".name")
        val_el = li.select_one(".value") or li.select_one(".number")
        if name_el and val_el:
            ratios[name_el.get_text(strip=True).lower()] = val_el.get_text(" ", strip=True)

    def r(*keys):
        for k in keys:
            for key, v in ratios.items():
                if k in key:
                    return _num(v)
        return None

    # pros & cons (screener's auto-generated blocks)
    pros = [li.get_text(" ", strip=True) for li in soup.select(".pros li")][:6]
    cons = [li.get_text(" ", strip=True) for li in soup.select(".cons li")][:6]

    # annual P&L table (Sales / Net Profit rows) for CAGR
    years = []
    for section in soup.select("section#profit-loss table, table.data-table"):
        rows = {tr.select_one("td")
                and tr.select_one("td").get_text(strip=True).lower(): tr
                for tr in section.select("tr") if tr.select_one("td")}
        if any("sales" in (k or "") for k in rows):
            header = [th.get_text(strip=True) for th in section.select("thead th")][1:]
            sales_tr = next((rows[k] for k in rows if k and "sales" in k), None)
            np_tr = next((rows[k] for k in rows if k and "net profit" in k), None)
            if sales_tr:
                svals = [_num(td.get_text()) for td in sales_tr.select("td")][1:]
                nvals = ([_num(td.get_text()) for td in np_tr.select("td")][1:]
                         if np_tr else [None] * len(svals))
                for i, yr in enumerate(header):
                    if i < len(svals):
                        years.append({"year": yr, "revenue": svals[i],
                                      "net_income": nvals[i] if i < len(nvals) else None,
                                      "revenue_growth_pct": None})
            break

    return {
        "source": "screener.in",
        "variant": variant,
        "pe": r("stock p/e", "p/e"),
        "pb": r("price to book", "book value") and None,  # book value is not P/B; skip
        "market_cap": r("market cap"),
        "roe_pct": r("roe"),
        "roce_pct": r("roce"),
        "debt_to_equity": r("debt to equity"),
        "dividend_yield_pct": r("dividend yield"),
        "face_value": r("face value"),
        "high_52w": r("high"),
        "low_52w": r("low"),
        "pros": pros,
        "cons": cons,
        "years": years[-6:],
    }


def fetch(symbol: str, consolidated: bool = True) -> dict | None:
    """Cached, throttled fetch of one company's screener.in page. Returns the
    parsed dict (provenance-stamped) or None (disabled / blocked / drift /
    error) so fundamentals.py falls back cleanly."""
    if not enabled():
        return None
    variant = "consolidated" if consolidated else "standalone"
    cached = _read_cache(symbol, variant)
    if cached is not None:
        return cached
    if time.time() < _blocked_until[0]:
        return None
    try:
        import httpx

        url = f"{_BASE}/company/{symbol.upper()}/{'consolidated/' if consolidated else ''}"
        headers = {"User-Agent": _UA}
        cookie = os.getenv("SCREENER_COOKIE", "").strip()
        if cookie:
            headers["Cookie"] = cookie
        _throttle()
        resp = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
        if resp.status_code in (403, 429):
            _blocked_until[0] = time.time() + 1800  # 30-min cooldown, fall back
            log.warning("screener %s -> %s; backing off 30min, using fallback",
                        symbol, resp.status_code)
            return None
        if resp.status_code != 200:
            log.warning("screener %s -> HTTP %s", symbol, resp.status_code)
            return None
        data = _parse(resp.text, symbol, variant)
        if data:
            _write_cache(symbol, variant, data)
        return data
    except Exception as e:  # noqa: BLE001 — never break the fundamentals card
        log.warning("screener fetch %s failed: %s", symbol, e)
        return None
