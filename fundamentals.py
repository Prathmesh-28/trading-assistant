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

        base = {
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
        base.update(_derive(info, years))

        # Prefer screener.in for Indian names when the operator enabled it;
        # overlay its fields (more reliable NSE fundamentals) over yfinance,
        # keep yfinance for anything screener didn't provide.
        if market == "IN":
            try:
                import screener_adapter
                sc = screener_adapter.fetch(symbol)
                if sc:
                    for k in ("pe", "roe_pct", "debt_to_equity", "dividend_yield_pct",
                              "roce_pct", "opm_pct", "npm_pct", "interest_coverage",
                              "payout_ratio_pct", "fcf", "fcf_yield_pct", "debtor_days",
                              "inventory_days", "revenue_cagr_pct", "pat_cagr_pct",
                              "sales_cagr_5y", "pat_cagr_5y", "piotroski_score",
                              "altman_z", "eps", "market_cap"):
                        if sc.get(k) is not None:
                            base[k] = sc[k]
                    if sc.get("pros"):
                        base["pros"] = sc["pros"]
                    if sc.get("cons"):
                        base["cons"] = sc["cons"]
                    if sc.get("years"):
                        base["years"] = [
                            {"year": y["year"], "revenue": y["revenue"],
                             "net_income": y["net_income"], "revenue_growth_pct": None}
                            for y in reversed(sc["years"])
                        ]
                    base["source"] = "screener.in + yfinance"
                    base.update(_derive({**info,
                        "returnOnEquity": (sc["roe_pct"] / 100 if sc.get("roe_pct") else info.get("returnOnEquity")),
                        "debtToEquity": sc.get("debt_to_equity", info.get("debtToEquity")),
                        "trailingPE": sc.get("pe", info.get("trailingPE")),
                    }, base["years"]))
            except Exception as e:  # noqa: BLE001 — screener is best-effort
                log.warning("screener overlay %s skipped: %s", symbol, e)
        base.setdefault("source", "yfinance")
        return base
    except Exception as e:  # noqa: BLE001 — never break the app for a card
        log.warning("fundamentals %s failed: %s", symbol, e)
        return None


def _cagr(first: float, last: float, periods: int):
    if not (first and last) or first <= 0 or last <= 0 or periods <= 0:
        return None
    return round(((last / first) ** (1 / periods) - 1) * 100, 1)


def _derive(info: dict, years: list) -> dict:
    """Valuation & quality metrics computed IN-HOUSE from the raw numbers, so
    they don't depend on any site's derived column (screener.in section D/B).
    All deterministic arithmetic; each fails soft to None."""
    out: dict = {}
    eps = info.get("trailingEps")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    bvps = info.get("bookValue")
    pe = info.get("trailingPE")

    # earnings yield = inverse P/E; the number Graham compares to the bond rate
    out["earnings_yield_pct"] = round(100 / pe, 2) if isinstance(pe, (int, float)) and pe else None

    # PEG = P/E / earnings-growth% (uses Yahoo's growth if present)
    g = info.get("earningsGrowth")
    out["peg"] = (round(pe / (g * 100), 2)
                  if isinstance(pe, (int, float)) and isinstance(g, (int, float)) and g > 0 else None)

    # Graham number = sqrt(22.5 * EPS * book value) — classic defensive fair value
    if isinstance(eps, (int, float)) and isinstance(bvps, (int, float)) and eps > 0 and bvps > 0:
        gn = (22.5 * eps * bvps) ** 0.5
        out["graham_number"] = round(gn, 2)
        out["graham_upside_pct"] = (round((gn / price - 1) * 100, 1)
                                    if isinstance(price, (int, float)) and price else None)
    else:
        out["graham_number"] = None
        out["graham_upside_pct"] = None

    # free cash flow & FCF yield
    fcf = info.get("freeCashflow")
    mcap = info.get("marketCap")
    out["fcf_yield_pct"] = (round(fcf / mcap * 100, 1)
                            if isinstance(fcf, (int, float)) and isinstance(mcap, (int, float)) and mcap else None)

    # dividend payout ratio
    out["payout_ratio_pct"] = _pct(info.get("payoutRatio"))

    # interest coverage & current ratio straight from Yahoo where present
    out["current_ratio"] = _num(info.get("currentRatio"))
    out["quick_ratio"] = _num(info.get("quickRatio"))

    # revenue / profit CAGR from the parsed statement years (oldest→newest)
    rev = [y["revenue"] for y in years if y.get("revenue")]
    pat = [y["net_income"] for y in years if y.get("net_income")]
    # years came in newest-first for display; reverse for chronological CAGR
    rev_chrono, pat_chrono = list(reversed(rev)), list(reversed(pat))
    if len(rev_chrono) >= 2:
        out["revenue_cagr_pct"] = _cagr(rev_chrono[0], rev_chrono[-1], len(rev_chrono) - 1)
    if len(pat_chrono) >= 2:
        out["pat_cagr_pct"] = _cagr(pat_chrono[0], pat_chrono[-1], len(pat_chrono) - 1)

    # deterministic quality read + pros/cons (screener.in "pros & cons" idea,
    # built from numbers not scraped text)
    pros, cons = [], []
    roe = info.get("returnOnEquity")
    de = info.get("debtToEquity")
    pm = info.get("profitMargins")
    if isinstance(roe, (int, float)):
        (pros if roe >= 0.15 else cons).append(
            f"ROE {round(roe*100,1)}% ({'strong' if roe >= 0.15 else 'weak'})")
    if isinstance(de, (int, float)):
        (pros if de < 50 else cons).append(
            f"Debt/equity {round(de,0)} ({'low' if de < 50 else 'high'})")
    if out.get("revenue_cagr_pct") is not None:
        (pros if out["revenue_cagr_pct"] >= 10 else cons).append(
            f"Revenue CAGR {out['revenue_cagr_pct']}%")
    if isinstance(pm, (int, float)):
        (pros if pm >= 0.1 else cons).append(f"Net margin {round(pm*100,1)}%")
    if out.get("graham_upside_pct") is not None:
        (pros if out["graham_upside_pct"] > 0 else cons).append(
            f"{'Below' if out['graham_upside_pct'] > 0 else 'Above'} Graham fair value")
    out["pros"] = pros
    out["cons"] = cons

    # 0-100 fundamental quality score (arithmetic, no model)
    score = 50
    if isinstance(roe, (int, float)):
        score += 12 if roe >= 0.15 else (-10 if roe < 0.05 else 0)
    if isinstance(de, (int, float)):
        score += 10 if de < 50 else (-12 if de > 150 else 0)
    if out.get("revenue_cagr_pct") is not None:
        score += 10 if out["revenue_cagr_pct"] >= 10 else (-8 if out["revenue_cagr_pct"] < 0 else 0)
    if isinstance(pm, (int, float)):
        score += 8 if pm >= 0.1 else (-6 if pm < 0 else 0)
    if out.get("graham_upside_pct") is not None and out["graham_upside_pct"] > 0:
        score += 8
    out["fundamental_score"] = max(0, min(100, score))
    return out
