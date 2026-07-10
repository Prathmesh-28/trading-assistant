"""Rule-based stock screener — screener.in-style query engine, deterministic
and LLM-free. Screens are boolean expressions over a metrics dict (quant +
fundamentals merged). The DSL is a SAFE tokenizer/evaluator: only whitelisted
field names, numeric literals, comparison operators and and/or/not — never
Python eval, so a user-typed screen can't execute code.

    roe_pct > 15 and debt_to_equity < 50 and score >= 60
"""

from __future__ import annotations

import re

# Fields a screen may reference (merged quant + fundamentals). Anything else
# in an expression is rejected at parse time.
FIELDS = {
    # quant.py
    "score", "ann_vol_pct", "sharpe_1y", "beta", "mom_1m_pct", "mom_3m_pct",
    "mom_12_1_pct", "from_52w_high_pct", "from_52w_low_pct", "rsi14", "max_dd_1y_pct",
    # fundamentals.py
    "pe", "forward_pe", "pb", "roe_pct", "debt_to_equity", "dividend_yield_pct",
    "profit_margin_pct", "revenue_growth_pct", "revenue_cagr_pct", "pat_cagr_pct",
    "earnings_yield_pct", "peg", "graham_upside_pct", "fcf_yield_pct",
    "payout_ratio_pct", "current_ratio", "fundamental_score", "market_cap",
    "roce_pct", "opm_pct", "npm_pct", "interest_coverage", "debtor_days",
    "inventory_days", "sales_cagr_5y", "pat_cagr_5y", "piotroski_score", "altman_z",
}

_TOKEN = re.compile(r"\s*(>=|<=|==|!=|>|<|\(|\)|and|or|not|[A-Za-z_][A-Za-z0-9_]*|-?\d+\.?\d*)")

PREBUILT = {
    "quality": {
        "label": "Quality",
        "desc": "High ROE, low debt, consistent growth",
        "expr": "roe_pct >= 15 and debt_to_equity < 60 and revenue_cagr_pct >= 8",
    },
    "coffee_can": {
        "label": "Coffee Can",
        "desc": "High ROCE + steady sales growth (Saurabh Mukherjea style)",
        "expr": "roce_pct >= 15 and sales_cagr_5y >= 10",
    },
    "piotroski_strong": {
        "label": "Piotroski 7+",
        "desc": "Fundamentally improving (F-Score 7-9)",
        "expr": "piotroski_score >= 7",
    },
    "safe_balance_sheet": {
        "label": "Fortress balance sheet",
        "desc": "Low debt, strong interest cover, Altman-safe",
        "expr": "debt_to_equity < 40 and interest_coverage >= 5 and altman_z >= 3",
    },
    "value": {
        "label": "Value",
        "desc": "Cheap vs earnings & book, still profitable",
        "expr": "pe > 0 and pe < 20 and pb < 3 and roe_pct >= 10",
    },
    "momentum_quality": {
        "label": "Momentum + Quality",
        "desc": "Trending up with a sound balance sheet",
        "expr": "score >= 65 and roe_pct >= 12 and debt_to_equity < 80",
    },
    "high_dividend": {
        "label": "High Dividend",
        "desc": "Yield with a sustainable payout",
        "expr": "dividend_yield_pct >= 2 and payout_ratio_pct < 80 and roe_pct >= 10",
    },
    "breakout_strong": {
        "label": "Breakout + Strong books",
        "desc": "Near 52w high, fundamentally healthy",
        "expr": "from_52w_high_pct > -5 and fundamental_score >= 60",
    },
    "graham_value": {
        "label": "Below Graham value",
        "desc": "Trading under the defensive fair-value line",
        "expr": "graham_upside_pct > 0 and pe > 0 and debt_to_equity < 100",
    },
}


class ScreenError(ValueError):
    pass


def _tokenize(expr: str) -> list:
    tokens, pos = [], 0
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            raise ScreenError(f"bad syntax near: {expr[pos:pos+12]!r}")
        tok = m.group(1)
        pos = m.end()
        low = tok.lower()
        if low in ("and", "or", "not") or tok in (">=", "<=", "==", "!=", ">", "<", "(", ")"):
            tokens.append(low if low in ("and", "or", "not") else tok)
        elif re.fullmatch(r"-?\d+\.?\d*", tok):
            tokens.append(float(tok))
        elif tok in FIELDS:
            tokens.append(("field", tok))
        else:
            raise ScreenError(f"unknown field '{tok}' (allowed: {', '.join(sorted(FIELDS))})")
    return tokens


# Recursive-descent parser -> callable(metrics) -> bool. A missing/None field
# makes its comparison False (the stock simply doesn't qualify), never a crash.

def compile_screen(expr: str):
    tokens = _tokenize(expr)
    pos = 0

    def peek():
        return tokens[pos] if pos < len(tokens) else None

    def parse_or():
        nonlocal pos
        node = parse_and()
        while peek() == "or":
            pos += 1
            rhs = parse_and()
            a, b = node, rhs
            node = (lambda m, a=a, b=b: a(m) or b(m))
        return node

    def parse_and():
        nonlocal pos
        node = parse_not()
        while peek() == "and":
            pos += 1
            rhs = parse_not()
            a, b = node, rhs
            node = (lambda m, a=a, b=b: a(m) and b(m))
        return node

    def parse_not():
        nonlocal pos
        if peek() == "not":
            pos += 1
            inner = parse_not()
            return lambda m, inner=inner: not inner(m)
        return parse_atom()

    def parse_atom():
        nonlocal pos
        if peek() == "(":
            pos += 1
            node = parse_or()
            if peek() != ")":
                raise ScreenError("unbalanced parentheses")
            pos += 1
            return node
        # comparison: field OP number
        tok = peek()
        if not (isinstance(tok, tuple) and tok[0] == "field"):
            raise ScreenError("expected a field name")
        field = tok[1]
        pos += 1
        op = peek()
        if op not in (">=", "<=", "==", "!=", ">", "<"):
            raise ScreenError(f"expected comparison after '{field}'")
        pos += 1
        num = peek()
        if not isinstance(num, (int, float)):
            raise ScreenError(f"expected a number after '{field} {op}'")
        pos += 1

        def cmp(m, field=field, op=op, num=num):
            v = m.get(field)
            if not isinstance(v, (int, float)):
                return False
            return {">=": v >= num, "<=": v <= num, ">": v > num,
                    "<": v < num, "==": v == num, "!=": v != num}[op]
        return cmp

    node = parse_or()
    if pos != len(tokens):
        raise ScreenError("trailing tokens after expression")
    return node


def run_screen(expr: str, metrics_by_symbol: dict) -> list:
    """metrics_by_symbol: {symbol: merged-metrics-dict}. Returns matches sorted
    by score desc, each with the fields that make it screener-readable."""
    test = compile_screen(expr)
    out = []
    for sym, m in metrics_by_symbol.items():
        try:
            if test(m):
                out.append({
                    "symbol": sym, "name": m.get("name", sym),
                    "score": m.get("score"), "fundamental_score": m.get("fundamental_score"),
                    "pe": m.get("pe"), "roe_pct": m.get("roe_pct"),
                    "debt_to_equity": m.get("debt_to_equity"),
                    "mom_3m_pct": m.get("mom_3m_pct"),
                })
        except Exception:  # noqa: BLE001 — a bad metrics dict skips that symbol
            continue
    out.sort(key=lambda x: -(x.get("score") or 0))
    return out
