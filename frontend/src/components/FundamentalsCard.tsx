import { useEffect, useState } from "react";
import { api } from "../api";

/** screener.in-style company card: profile, key ratios, computed pros/cons,
 * and revenue/profit history. Real data via yfinance even in demo mode. */
export function FundamentalsCard({ symbol }: { symbol: string }) {
  const [f, setF] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setF(null);
    api.fundamentals(symbol).then((d) => { setF(d); setLoading(false); }).catch(() => setLoading(false));
  }, [symbol]);

  if (loading) return <p className="text-muted empty-note">Loading fundamentals…</p>;
  if (!f || f.error || !f.name) return null;

  const cur = f.currency === "USD" ? "$" : "₹";
  const rows: [string, any][] = [
    ["P/E", f.pe], ["P/B", f.pb], ["ROE", f.roe_pct != null ? `${f.roe_pct}%` : null],
    ["Debt/Equity", f.debt_to_equity], ["Net margin", f.profit_margin_pct != null ? `${f.profit_margin_pct}%` : null],
    ["Rev CAGR", f.revenue_cagr_pct != null ? `${f.revenue_cagr_pct}%` : null],
    ["Div yield", f.dividend_yield_pct != null ? `${f.dividend_yield_pct}%` : null],
    ["Earnings yield", f.earnings_yield_pct != null ? `${f.earnings_yield_pct}%` : null],
  ];

  return (
    <div className="fund-card">
      <div className="fund-head">
        <div>
          <strong>{f.name}</strong>
          {f.sector && <span className="fund-sector">{f.sector}{f.industry ? ` · ${f.industry}` : ""}</span>}
        </div>
        {f.fundamental_score != null && (
          <span className="fund-score" title="In-house fundamental quality score">
            {f.fundamental_score}<em>/100</em>
          </span>
        )}
      </div>

      <div className="fund-grid">
        {rows.filter(([, v]) => v != null).map(([k, v]) => (
          <div key={k} className="fund-row"><span>{k}</span><strong>{v}</strong></div>
        ))}
      </div>

      {(f.pros?.length || f.cons?.length) && (
        <div className="fund-proscons">
          {f.pros?.length > 0 && (
            <div><span className="good">Pros</span><ul>{f.pros.map((p: string) => <li key={p}>{p}</li>)}</ul></div>
          )}
          {f.cons?.length > 0 && (
            <div><span className="critical">Cons</span><ul>{f.cons.map((c: string) => <li key={c}>{c}</li>)}</ul></div>
          )}
        </div>
      )}

      {f.years?.length > 0 && (
        <div className="fund-years">
          <div className="fund-years-head"><span>Year</span><span>Revenue</span><span>Profit</span></div>
          {f.years.slice(0, 4).map((y: any) => (
            <div key={y.year} className="fund-years-row">
              <span>{y.year}</span>
              <span>{y.revenue != null ? `${cur}${(y.revenue / 1e7).toFixed(0)}Cr` : "—"}</span>
              <span>{y.net_income != null ? `${cur}${(y.net_income / 1e7).toFixed(0)}Cr` : "—"}</span>
            </div>
          ))}
        </div>
      )}
      <p className="fund-foot text-muted">Fundamentals via Yahoo Finance{f.market === "US" ? "" : " (NSE)"} — quarterly facts, not live.</p>
    </div>
  );
}
