"""Company fundamentals — the screener.in-style view, sourced legally via
Yahoo Finance (yfinance) which serves both NSE (.NS) and US tickers.

Fundamentals are REAL even when prices run in demo mode (they're quarterly
facts, not a live feed) — the dashboard labels the distinction. Every call
fails soft to None; the UI hides the card when data is unavailable.
"""

from __future__ import annotations

import logging

log = logging.getLogger("fundamentals")

# Yahoo suffix by market: NSE symbols get .NS, US tickers pass through.
_SPECIAL = {"M&M": "M&M.NS", "BAJAJ-AUTO": "BAJAJ-AUTO.NS"}


def yahoo_symbol(symbol: str, market: str) -> str:
    if market == "US":
        return symbol
    return _SPECIAL.get(symbol, f"{symbol}.NS")


def _pct(v):
    return round(v * 100, 1) if isinstance(v, (int, float)) else None


def _num(v, digits=2):
    return round(v, digits) if isinstance(v, (int, float)) else None


def fetch_fundamentals(symbol: str, market: str = "IN") -> dict | None:
    """One company's story: profile, key ratios, and up to 4 years of
    revenue/profit with growth — everything a screener.in card shows."""
    try:
        import yfinance as yf

        t = yf.Ticker(yahoo_symbol(symbol, market))
        info = t.info or {}
        if not info.get("longName") and not info.get("shortName"):
            return None

        years = []
        try:
            inc = t.income_stmt
            if inc is not None and not inc.empty:
                rev = inc.loc["Total Revenue"] if "Total Revenue" in inc.index else None
                ni = inc.loc["Net Income"] if "Net Income" in inc.index else None
                cols = list(inc.columns)[:4]
                prev_rev = None
                rows = []
                for c in reversed(cols):  # oldest first for growth calc
                    r = float(rev[c]) if rev is not None and rev[c] == rev[c] else None
                    n = float(ni[c]) if ni is not None and ni[c] == ni[c] else None
                    growth = (round((r / prev_rev - 1) * 100, 1)
                              if r and prev_rev else None)
                    rows.append({"year": str(getattr(c, "year", c)),
                                 "revenue": r, "net_income": n,
                                 "revenue_growth_pct": growth})
                    prev_rev = r or prev_rev
                years = list(reversed(rows))  # newest first for display
        except Exception:  # noqa: BLE001 — statements are best-effort
            pass

        summary = (info.get("longBusinessSummary") or "")[:420]
        if len(summary) == 420:
            summary = summary.rsplit(" ", 1)[0] + "…"

        return {
            "symbol": symbol,
            "market": market,
            "name": info.get("longName") or info.get("shortName"),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "summary": summary,
            "currency": info.get("financialCurrency") or ("INR" if market == "IN" else "USD"),
            "market_cap": info.get("marketCap"),
            "pe": _num(info.get("trailingPE")),
            "forward_pe": _num(info.get("forwardPE")),
            "pb": _num(info.get("priceToBook")),
            "roe_pct": _pct(info.get("returnOnEquity")),
            "debt_to_equity": _num(info.get("debtToEquity")),
            "dividend_yield_pct": _num(info.get("dividendYield")),
            "profit_margin_pct": _pct(info.get("profitMargins")),
            "revenue_growth_pct": _pct(info.get("revenueGrowth")),
            "beta_yahoo": _num(info.get("beta")),
            "employees": info.get("fullTimeEmployees"),
            "years": years,
        }
    except Exception as e:  # noqa: BLE001 — never break the app for a card
        log.warning("fundamentals %s failed: %s", symbol, e)
        return None
