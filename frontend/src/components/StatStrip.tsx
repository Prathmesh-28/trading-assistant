import { useEffect, useState } from "react";
import { api } from "../api";
import { rupees } from "../lang";
import type { Analytics, Snapshot } from "../types";

/** Control-center stat row: P&L today, unrealized, win rate (30d), capital
 * deployed, open positions. All real numbers from the engine + journal. */
export function StatStrip({ snapshot }: { snapshot: Snapshot }) {
  const [a, setA] = useState<Analytics | null>(null);

  useEffect(() => {
    api.analytics(90).then(setA).catch(() => {});
  }, [snapshot.day_stats.closed_today]);

  const w = snapshot.wallet;
  const dayPnl = snapshot.day_stats.realised_pnl;
  const openPnl = w?.open_pnl ?? 0;
  const deployed = w?.invested ?? 0;
  const total = w?.current_value ?? 0;
  const intraday = snapshot.positions.filter((p) => p.horizon === "intraday").length;
  const positional = snapshot.positions.length - intraday;

  const cells: { label: string; value: string; cls?: string; sub?: string; subCls?: string }[] = [
    {
      label: "P&L today",
      value: `${dayPnl >= 0 ? "+" : "−"}${rupees(Math.abs(dayPnl), 0)}`,
      cls: dayPnl >= 0 ? "good" : "critical",
      sub: `${snapshot.day_stats.closed_today} closed`,
    },
    {
      label: "Unrealized",
      value: `${openPnl >= 0 ? "+" : "−"}${rupees(Math.abs(openPnl), 0)}`,
      cls: openPnl >= 0 ? "good" : "critical",
      sub: deployed > 0 ? `${((openPnl / deployed) * 100).toFixed(2)}%` : "—",
      subCls: openPnl >= 0 ? "good" : "critical",
    },
    {
      label: "Win rate (30d)",
      value: a?.win_rate_30d_pct != null ? `${a.win_rate_30d_pct}%` : "—",
      sub: a && a.closed_trades > 0 ? `${a.closed_trades} trades / ${a.days}d` : "no closed trades yet",
    },
    {
      label: "Capital deployed",
      value: rupees(deployed, 0),
      sub: total > 0 ? `of ${rupees(total, 0)}` : "—",
    },
    {
      label: "Open positions",
      value: String(snapshot.positions.length),
      sub: `${intraday} intraday · ${positional} swing`,
    },
  ];

  return (
    <div className="stats-row">
      {cells.map((c) => (
        <div className="stat-card" key={c.label}>
          <div className="stat-label">{c.label}</div>
          <div className={`stat-value ${c.cls ?? ""}`}>{c.value}</div>
          {c.sub && <div className={`stat-sub ${c.subCls ?? ""}`}>{c.sub}</div>}
        </div>
      ))}
    </div>
  );
}
