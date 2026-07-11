import { rupees } from "../lang";
import type { Snapshot } from "../types";

/** Daily-loss circuit-breaker gauge: today's loss vs the limit the breaker
 * trips at. Green when profitable, amber filling as losses approach the cap. */
export function RiskStrip({ snapshot }: { snapshot: Snapshot }) {
  const w = snapshot.wallet;
  const limitPct = (snapshot.settings?.daily_loss_limit_pct as number) ?? 3;
  const equity = w?.current_value ?? 0;
  const limit = (equity * limitPct) / 100;
  if (limit <= 0) return null;
  const dayPnl = snapshot.day_stats.realised_pnl + (w?.open_pnl ?? 0);
  const used = Math.max(0, -dayPnl);
  const frac = Math.min(1, used / limit);

  return (
    <div className="risk-strip">
      <div className="risk-label">Daily loss limit used</div>
      <div className="risk-track">
        <div
          className="risk-fill"
          style={{ width: `${Math.round(frac * 100)}%`, background: frac > 0.8 ? "var(--critical)" : "var(--warning)" }}
        />
      </div>
      <div className="risk-value" style={frac > 0.8 ? { color: "var(--critical)" } : undefined}>
        {rupees(used, 0)} / {rupees(limit, 0)}
      </div>
    </div>
  );
}
