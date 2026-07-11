"""Capital-gains reporting — categorization, netting, FY split."""
from datetime import datetime, timedelta

import tax
from config import IST


def _row(sym, horizon, buy_days_ago, hold_days, entry, exit_, qty):
    opened = datetime.now(IST) - timedelta(days=buy_days_ago)
    closed = opened + timedelta(days=hold_days)
    return {
        "symbol": sym, "horizon": horizon, "status": "CLOSED",
        "created_at": opened.isoformat(), "updated_at": closed.isoformat(),
        "fill_qty": qty, "fill_price": entry, "exit_price": exit_,
    }


def test_holding_period_categories():
    rows = [
        _row("TCS", "positional", 420, 400, 3000, 3600, 10),   # LTCG
        _row("INFY", "positional", 40, 30, 1500, 1400, 20),    # STCG
        _row("SBIN", "intraday", 5, 0, 800, 820, 50),          # intraday
    ]
    rep = tax.compute(rows)
    cats = {t["symbol"]: t["category"] for t in rep["trades"]}
    assert cats == {"TCS": "LTCG", "INFY": "STCG", "SBIN": "INTRADAY"}


def test_net_is_gross_minus_charges():
    rep = tax.compute([_row("TCS", "positional", 420, 400, 3000, 3600, 10)])
    t = rep["trades"][0]
    assert t["gross_pnl"] == 6000.0
    assert t["charges"] > 0
    assert t["net_pnl"] == round(6000.0 - t["charges"], 2)


def test_fy_boundary():
    # sold 2025-03-31 -> FY2024-25 ; sold 2025-04-01 -> FY2025-26
    assert tax.financial_year(datetime(2025, 3, 31)) == "FY2024-25"
    assert tax.financial_year(datetime(2025, 4, 1)) == "FY2025-26"


def test_ignores_open_and_bad_rows():
    rows = [
        {"symbol": "X", "status": "ACTIVE", "horizon": "positional"},
        {"symbol": "Y", "status": "CLOSED", "horizon": "positional",
         "fill_qty": 0, "fill_price": 0, "exit_price": 0,
         "created_at": "2025-01-01T00:00:00", "updated_at": "2025-02-01T00:00:00"},
    ]
    rep = tax.compute(rows)
    assert rep["trades"] == []
