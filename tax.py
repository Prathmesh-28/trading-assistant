"""Indian capital-gains reporting — deterministic, over the journal's closed
trades. Splits realised gains by financial year (Apr 1 – Mar 31) and by
holding period (STCG ≤ 12 months, LTCG > 12 months for listed equity),
nets each trade against costs.py charges. LLM-free; pure arithmetic.

Not tax advice — a working sheet for your CA. Delivery (CNC) trades are the
capital-gains universe; intraday (MIS) is speculative business income and is
reported separately, not as STCG/LTCG.
"""

from __future__ import annotations

from datetime import datetime

from costs import round_trip_costs

# Listed-equity long-term threshold: held strictly more than 12 months.
LTCG_DAYS = 365


def financial_year(dt: datetime) -> str:
    """Indian FY label for a date: 2025-04-01..2026-03-31 -> 'FY2025-26'."""
    y = dt.year if dt.month >= 4 else dt.year - 1
    return f"FY{y}-{str(y + 1)[-2:]}"


def _parse(ts) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts)[:19])
    except ValueError:
        return None


def compute(closed_rows: list, slippage_pct: float = 0.05) -> dict:
    """closed_rows: journal history rows with status CLOSED. Returns per-FY
    breakdown with STCG/LTCG (delivery) + intraday speculative, each net of
    charges, plus a flat trade list for CSV export."""
    years: dict = {}
    trades: list = []

    for r in closed_rows:
        if r.get("status") != "CLOSED":
            continue
        qty = r.get("fill_qty") or r.get("qty") or 0
        entry = r.get("fill_price") or r.get("entry") or 0.0
        exit_ = r.get("exit_price") or 0.0
        if qty <= 0 or entry <= 0 or exit_ <= 0:
            continue
        opened = _parse(r.get("created_at"))
        closed = _parse(r.get("updated_at"))
        if not opened or not closed:
            continue

        horizon = (r.get("horizon") or "").lower()
        intraday = horizon == "intraday"
        product = "MIS" if intraday else "CNC"
        gross = (exit_ - entry) * qty            # long-only book
        charges = round_trip_costs(product, entry, exit_, int(qty), slippage_pct)
        net = round(gross - charges, 2)
        held_days = (closed - opened).days

        if intraday:
            bucket = "intraday"
        elif held_days > LTCG_DAYS:
            bucket = "ltcg"
        else:
            bucket = "stcg"

        fy = financial_year(closed)
        y = years.setdefault(fy, {
            "fy": fy,
            "stcg": {"trades": 0, "gross": 0.0, "charges": 0.0, "net": 0.0},
            "ltcg": {"trades": 0, "gross": 0.0, "charges": 0.0, "net": 0.0},
            "intraday": {"trades": 0, "gross": 0.0, "charges": 0.0, "net": 0.0},
            "total_charges": 0.0, "total_net": 0.0,
        })
        b = y[bucket]
        b["trades"] += 1
        b["gross"] = round(b["gross"] + gross, 2)
        b["charges"] = round(b["charges"] + charges, 2)
        b["net"] = round(b["net"] + net, 2)
        y["total_charges"] = round(y["total_charges"] + charges, 2)
        y["total_net"] = round(y["total_net"] + net, 2)

        trades.append({
            "symbol": r.get("symbol"), "fy": fy, "category": bucket.upper(),
            "buy_date": opened.date().isoformat(), "sell_date": closed.date().isoformat(),
            "held_days": held_days, "qty": int(qty),
            "buy_price": round(entry, 2), "sell_price": round(exit_, 2),
            "gross_pnl": round(gross, 2), "charges": round(charges, 2), "net_pnl": net,
        })

    return {
        "years": [years[k] for k in sorted(years, reverse=True)],
        "trades": sorted(trades, key=lambda t: t["sell_date"], reverse=True),
    }


def to_csv(report: dict) -> str:
    """Flat per-trade CSV for the CA / ITR schedule 112A prep."""
    import csv
    import io

    buf = io.StringIO()
    cols = ["symbol", "fy", "category", "buy_date", "sell_date", "held_days",
            "qty", "buy_price", "sell_price", "gross_pnl", "charges", "net_pnl"]
    w = csv.DictWriter(buf, fieldnames=cols)
    w.writeheader()
    for t in report["trades"]:
        w.writerow(t)
    return buf.getvalue()
