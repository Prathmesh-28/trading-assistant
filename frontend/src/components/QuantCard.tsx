import { useEffect, useState } from "react";
import { api } from "../api";
import type { QuantStats } from "../types";

const ROWS: { key: keyof QuantStats; label: string; fmt?: (v: number) => string }[] = [
  { key: "mom_3m_pct", label: "3-month move", fmt: (v) => `${v > 0 ? "+" : ""}${v}%` },
  { key: "mom_12_1_pct", label: "12-month momentum", fmt: (v) => `${v > 0 ? "+" : ""}${v}%` },
  { key: "from_52w_high_pct", label: "From 52-week high", fmt: (v) => `${v}%` },
  { key: "ann_vol_pct", label: "Yearly volatility", fmt: (v) => `±${v}%` },
  { key: "sharpe_1y", label: "Sharpe (1y)" },
  { key: "beta", label: "Beta vs index" },
  { key: "max_dd_1y_pct", label: "Worst drop (1y)", fmt: (v) => `−${v}%` },
  { key: "rsi14", label: "RSI (14)" },
];

/** The quant-desk read of one stock — pure arithmetic on price history,
 * scored 0-100. No AI, no prediction: a screen, not a promise. */
export function QuantCard({ symbol }: { symbol: string }) {
  const [stats, setStats] = useState<QuantStats | null>(null);

  useEffect(() => {
    setStats(null);
    api.quant(symbol).then(setStats).catch(() => {});
  }, [symbol]);

  if (!stats) return <p className="text-muted empty-note">Crunching the numbers…</p>;
  if (stats.error) return null;

  const score = stats.score ?? 0;
  const scoreColor = score >= 70 ? "var(--good)" : score >= 40 ? "var(--warning)" : "var(--critical)";

  return (
    <div className="quant-card">
      <div className="quant-head">
        <span className="quant-title">Quant score</span>
        <span className="quant-score" style={{ color: scoreColor }}>
          {score}
          <em>/100</em>
        </span>
      </div>
      <div className="quant-meter" aria-hidden>
        <div className="quant-meter-fill" style={{ width: `${score}%`, background: scoreColor }} />
      </div>
      <p className="quant-verdict">{stats.verdict}</p>
      <div className="quant-grid">
        {ROWS.map(({ key, label, fmt }) => {
          const v = stats[key];
          if (v === null || v === undefined || typeof v !== "number") return null;
          return (
            <div key={key} className="quant-row">
              <span>{label}</span>
              <strong>{fmt ? fmt(v) : v}</strong>
            </div>
          );
        })}
      </div>
      <p className="quant-foot text-muted">
        Deterministic math on {stats.synthetic ? "demo" : "real"} price history — a screen, not a
        prediction.
      </p>
    </div>
  );
}
