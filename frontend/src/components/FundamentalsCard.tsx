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
    ["ROCE", f.roce_pct != null ? `${f.roce_pct}%` : null],
    ["OPM", f.opm_pct != null ? `${f.opm_pct}%` : null],
    ["Rev CAGR (5y)", f.sales_cagr_5y != null ? `${f.sales_cagr_5y}%` : (f.revenue_cagr_pct != null ? `${f.revenue_cagr_pct}%` : null)],
    ["Interest cover", f.interest_coverage],
    ["Piotroski", f.piotroski_score != null ? `${f.piotroski_score}/9` : null],
    ["Altman Z", f.altman_z],
    ["Div yield", f.dividend_yield_pct != null ? `${f.dividend_yield_pct}%` : null],
    ["Earnings yield", f.earnings_yield_pct != null ? `${f.earnings_yield_pct}%` : null],
    ["Book value", f.book_value != null ? `${cur}${f.book_value}` : null],
    ["Profit CAGR (5y)", f.profit_cagr_5y != null ? `${f.profit_cagr_5y}%` : null],
    ["Working cap days", f.working_capital_days],
  ];

  const qt = f.quarters;
  const docs = f.documents;
  const lastN = (a: any[] | undefined, n: number) => (a ?? []).slice(-n);

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

      {(f.pros?.length > 0 || f.cons?.length > 0) && (
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
      {f.promoter_pct != null && (
        <div className="fund-shareholding">
          <div className="fund-sec-title">Who owns it</div>
          <div className="sh-chips">
            <span>Promoters <strong>{f.promoter_pct}%</strong>{f.promoter_change_pct != null && f.promoter_change_pct !== 0 && (
              <em className={f.promoter_change_pct > 0 ? "good" : "critical"}>
                {" "}{f.promoter_change_pct > 0 ? "▲" : "▼"}{Math.abs(f.promoter_change_pct)}%
              </em>
            )}</span>
            {f.fii_pct != null && <span>FIIs <strong>{f.fii_pct}%</strong></span>}
            {f.dii_pct != null && <span>DIIs <strong>{f.dii_pct}%</strong></span>}
            {f.public_pct != null && <span>Public <strong>{f.public_pct}%</strong></span>}
          </div>
        </div>
      )}

      {qt?.headers?.length > 0 && qt.sales?.length > 0 && (
        <div className="fund-quarters">
          <div className="fund-sec-title">Recent quarters</div>
          <div className="fund-q-scroll">
            <table>
              <thead>
                <tr><th></th>{lastN(qt.headers, 5).map((h: string) => <th key={h}>{h}</th>)}</tr>
              </thead>
              <tbody>
                <tr><td>Sales</td>{lastN(qt.sales, 5).map((v: number, i: number) => <td key={i}>{v ?? "—"}</td>)}</tr>
                {qt.opm_pct?.length > 0 && (
                  <tr><td>OPM</td>{lastN(qt.opm_pct, 5).map((v: number, i: number) => <td key={i}>{v != null ? `${v}%` : "—"}</td>)}</tr>
                )}
                <tr><td>Profit</td>{lastN(qt.net_profit, 5).map((v: number, i: number) => <td key={i}>{v ?? "—"}</td>)}</tr>
                {qt.eps?.length > 0 && (
                  <tr><td>EPS</td>{lastN(qt.eps, 5).map((v: number, i: number) => <td key={i}>{v ?? "—"}</td>)}</tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {(docs?.annual_reports?.length > 0 || docs?.concalls?.length > 0) && (
        <div className="fund-docs">
          <div className="fund-sec-title">Filings</div>
          <div className="fund-doc-links">
            {(docs.annual_reports ?? []).slice(0, 3).map((d: any) => (
              <a key={d.url} href={d.url} target="_blank" rel="noreferrer">{d.label || "Annual report"}</a>
            ))}
            {(docs.concalls ?? []).slice(0, 2).map((c: any, i: number) => (
              c.transcript && <a key={i} href={c.transcript} target="_blank" rel="noreferrer">Concall {c.date}</a>
            ))}
          </div>
        </div>
      )}

      <p className="fund-foot text-muted">{f.source === "screener.in + yfinance" ? "Fundamentals via screener.in + Yahoo" : `Fundamentals via Yahoo Finance${f.market === "US" ? "" : " (NSE)"}`} — quarterly facts, not live.</p>
    </div>
  );
}
