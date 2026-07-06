import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { BacktestJob, Snapshot } from "../types";
import { Sparkline } from "./Sparkline";
import { StatTile } from "./StatTile";

const inr = (v: number) => `₹${v.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;

/** Run the production backtester (same on_bar / scan_symbol code the live
 * engine uses) against Groww history and inspect the results. */
export function BacktestPanel({ snapshot }: { snapshot: Snapshot }) {
  const [strategy, setStrategy] = useState<"intraday" | "positional">("positional");
  const [symbols, setSymbols] = useState(snapshot.watchlist.join(", "));
  const [days, setDays] = useState(strategy === "intraday" ? "60" : "730");
  const [indexGate, setIndexGate] = useState(true);
  const [job, setJob] = useState<BacktestJob | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  const run = async () => {
    setBusy(true);
    setJob(null);
    try {
      const started = await api.startBacktest({
        strategy,
        symbols: symbols.split(",").map((s) => s.trim()).filter(Boolean),
        days: Number(days) || 365,
        use_index_gate: indexGate,
      });
      setJob(started);
      if (started.status === "running" && started.job_id) {
        const id = started.job_id;
        pollRef.current = setInterval(async () => {
          try {
            const j = await api.backtestJob(id);
            setJob(j);
            if (j.status !== "running" && pollRef.current) {
              clearInterval(pollRef.current);
              pollRef.current = null;
            }
          } catch { /* keep polling */ }
        }, 2500);
      }
    } catch (e) {
      setJob({ job_id: null, status: "error", message: String(e) });
    } finally {
      setBusy(false);
    }
  };

  const s = job?.result?.summary;
  const curve = job?.result?.equity_curve ?? [];

  return (
    <div className="backtest-panel">
      <div className="backtest-form card">
        <div className="bt-field">
          <label>Strategy</label>
          <div className="bt-toggle">
            {(["intraday", "positional"] as const).map((k) => (
              <button
                key={k}
                className={`btn btn-ghost ${strategy === k ? "active" : ""}`}
                onClick={() => {
                  setStrategy(k);
                  setDays(k === "intraday" ? "60" : "730");
                }}
              >
                {k === "intraday" ? "Intraday ORB+VWAP" : "Positional cascade"}
              </button>
            ))}
          </div>
        </div>
        <div className="bt-field">
          <label>Symbols (comma-separated NSE)</label>
          <input className="num-input bt-symbols" value={symbols} onChange={(e) => setSymbols(e.target.value)} />
        </div>
        <div className="bt-row">
          <div className="bt-field">
            <label>Days of history</label>
            <input className="num-input" type="number" value={days} onChange={(e) => setDays(e.target.value)} />
          </div>
          {strategy === "positional" && (
            <label className="bt-check">
              <input type="checkbox" checked={indexGate} onChange={(e) => setIndexGate(e.target.checked)} />
              Faber 200-DMA index gate
            </label>
          )}
          <button className="btn btn-good bt-run" disabled={busy || job?.status === "running"} onClick={run}>
            {job?.status === "running" ? "Running…" : "Run backtest"}
          </button>
        </div>
        <p className="text-muted bt-note">
          Replays the exact production strategy code on Groww history — next-bar-open fills, stop-wins on
          ambiguous bars, PnL net of Indian transaction costs.
        </p>
      </div>

      {job?.status === "unavailable" && <p className="empty-note warning">{job.message}</p>}
      {job?.status === "error" && <p className="empty-note critical">Backtest failed — {job.message}</p>}
      {job?.status === "running" && <p className="empty-note text-muted">Running… fetching history and replaying bars (can take a minute for long windows).</p>}

      {s && (
        <>
          <div className="stat-row bt-stats">
            <StatTile label="Trades" value={s.n_trades} />
            <StatTile label="Win rate" value={`${s.win_rate_pct}%`} />
            <StatTile label="Profit factor" value={s.profit_factor ?? "—"} />
            <StatTile label="Avg R" value={s.avg_r_multiple} />
          </div>
          <div className="stat-row bt-stats">
            <StatTile
              label="Total PnL (net)"
              value={inr(s.total_pnl)}
              valueColor={s.total_pnl >= 0 ? "var(--good)" : "var(--critical)"}
            />
            <StatTile label="Return" value={`${s.total_return_pct}%${s.cagr_pct != null ? ` · CAGR ${s.cagr_pct}%` : ""}`} />
            <StatTile label="Max drawdown" value={inr(s.max_drawdown)} valueColor="var(--critical)" />
            <StatTile label="Costs paid" value={inr(s.total_costs)} />
          </div>

          {curve.length >= 2 && (
            <div className="card bt-curve">
              <div className="stat-label">Equity curve — {inr(s.starting_capital)} → {inr(s.ending_capital)}</div>
              <Sparkline values={curve} width={640} height={120} />
            </div>
          )}

          {(s.diagnostics.length > 0 || s.warnings.length > 0) && (
            <div className="card bt-flags">
              {s.diagnostics.map((d, i) => (
                <p key={`d${i}`} className="warning">🔎 {d}</p>
              ))}
              {s.warnings.map((w, i) => (
                <p key={`w${i}`} className="text-muted">⚠️ {w}</p>
              ))}
              <p className="text-muted">
                Ambiguous-bar exits: {s.ambiguous_bar_exits} ({s.ambiguous_bar_rate_pct}%) — stop-wins convention.
              </p>
            </div>
          )}

          {job?.result && job.result.trades.length > 0 && (
            <div className="table-scroll bt-trades">
              <table className="history-table">
                <thead>
                  <tr>
                    <th>Date</th><th>Symbol</th><th>Side</th><th>Entry</th><th>Exit</th>
                    <th>Reason</th><th>Qty</th><th>PnL</th><th>R</th>
                  </tr>
                </thead>
                <tbody>
                  {job.result.trades.slice().reverse().map((t, i) => (
                    <tr key={i}>
                      <td>{t.entry_date}</td>
                      <td>{t.symbol}</td>
                      <td className={t.side === "BUY" ? "good" : "critical"}>{t.side}</td>
                      <td className="tabular">₹{t.entry.toLocaleString("en-IN")}</td>
                      <td className="tabular">₹{t.exit.toLocaleString("en-IN")}</td>
                      <td>{t.exit_reason}</td>
                      <td className="tabular">{t.qty}</td>
                      <td className={`tabular ${t.pnl >= 0 ? "good" : "critical"}`}>₹{t.pnl.toLocaleString("en-IN")}</td>
                      <td className="tabular">{t.r_multiple}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
