import { useEffect, useState } from "react";
import { api } from "../api";
import { rupees } from "../lang";
import type { Analytics } from "../types";

/** Performance analytics from closed trades: equity curve, win metrics,
 * where the money came from (symbol / horizon / weekday), journal tags. */
export function AnalyticsPanel() {
  const [a, setA] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.analytics(90).then((r) => { setA(r); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-muted empty-note">Crunching your trades…</p>;
  if (!a || a.closed_trades === 0) {
    return <p className="text-muted empty-note">No closed trades yet — analytics appear after your first exit.</p>;
  }

  const curve = a.equity_curve;
  const min = Math.min(0, ...curve.map((c) => c.cum_pnl));
  const max = Math.max(0, ...curve.map((c) => c.cum_pnl));
  const span = max - min || 1;
  const W = 320, H = 80;
  const pts = curve.map((c, i) => {
    const x = curve.length > 1 ? (i / (curve.length - 1)) * W : W;
    const y = H - ((c.cum_pnl - min) / span) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  const last = curve[curve.length - 1]?.cum_pnl ?? 0;

  const bucketTable = (title: string, data: Record<string, { trades: number; pnl: number; wins: number }>) => {
    const rows = Object.entries(data).sort((x, y) => y[1].pnl - x[1].pnl);
    if (rows.length === 0) return null;
    return (
      <section className="ana-block" key={title}>
        <h3 className="fund-sec-title">{title}</h3>
        <div className="ana-table">
          {rows.slice(0, 8).map(([k, v]) => (
            <div className="ana-row" key={k}>
              <span className="ana-key">{k}</span>
              <span className="mono text-muted">{v.trades} trades · {v.trades ? Math.round((v.wins / v.trades) * 100) : 0}% win</span>
              <strong className={`mono ${v.pnl >= 0 ? "good" : "critical"}`}>
                {v.pnl >= 0 ? "+" : "−"}{rupees(Math.abs(v.pnl), 0)}
              </strong>
            </div>
          ))}
        </div>
      </section>
    );
  };

  return (
    <div className="analytics">
      <section className="ana-block">
        <h3 className="fund-sec-title">Equity curve · last {a.days} days</h3>
        <svg viewBox={`0 0 ${W} ${H}`} className="equity-svg" preserveAspectRatio="none">
          <line x1="0" x2={W} y1={H - ((0 - min) / span) * H} y2={H - ((0 - min) / span) * H}
                stroke="var(--baseline)" strokeDasharray="3 3" strokeWidth="1" />
          <polyline points={pts} fill="none"
                    stroke={last >= 0 ? "var(--good)" : "var(--critical)"} strokeWidth="2" />
        </svg>
        <p className={`mono ana-cum ${last >= 0 ? "good" : "critical"}`}>
          {last >= 0 ? "+" : "−"}{rupees(Math.abs(last), 0)} booked over {a.closed_trades} trades
        </p>
      </section>

      <section className="ana-block">
        <div className="ana-grid">
          <div><span className="stat-label">Win rate</span><strong className="stat-value">{a.win_rate_pct ?? "—"}%</strong></div>
          <div><span className="stat-label">Profit factor</span><strong className="stat-value">{a.profit_factor ?? "—"}</strong></div>
          <div><span className="stat-label">Avg win</span><strong className="stat-value good">{a.avg_win != null ? rupees(a.avg_win, 0) : "—"}</strong></div>
          <div><span className="stat-label">Avg loss</span><strong className="stat-value critical">{a.avg_loss != null ? rupees(Math.abs(a.avg_loss), 0) : "—"}</strong></div>
          <div><span className="stat-label">Best streak</span><strong className="stat-value">{a.best_win_streak}W</strong></div>
          <div><span className="stat-label">Worst streak</span><strong className="stat-value">{a.worst_loss_streak}L</strong></div>
        </div>
      </section>

      {bucketTable("By stock", a.by_symbol)}
      {bucketTable("By style", a.by_horizon)}
      {bucketTable("By weekday — find your worst day", a.by_weekday)}

      {Object.keys(a.tag_counts).length > 0 && (
        <section className="ana-block">
          <h3 className="fund-sec-title">Your journal tags</h3>
          <div className="sh-chips">
            {Object.entries(a.tag_counts).sort((x, y) => y[1] - x[1]).map(([t, n]) => (
              <span key={t}>{t} <strong>×{n}</strong></span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
