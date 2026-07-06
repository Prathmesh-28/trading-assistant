import type { MarketContext } from "../types";

const BIAS_COLOR: Record<string, string> = {
  long: "var(--good)",
  short: "var(--critical)",
  neutral: "var(--text-muted)",
};

export function RegimeCard({ ctx }: { ctx: MarketContext }) {
  const age = ctx.updated_at
    ? Math.max(0, Math.round((Date.now() - new Date(ctx.updated_at).getTime()) / 60000))
    : null;
  return (
    <div className="regime-card">
      <div className="regime-row">
        <span>
          Regime <strong>{ctx.regime}</strong>
        </span>
        <span style={{ color: BIAS_COLOR[ctx.bias] ?? "var(--text-muted)" }}>
          Bias <strong>{ctx.bias}</strong>
        </span>
        <span className="text-muted">{ctx.confidence}</span>
        {age !== null && <span className="text-muted">{age}m ago</span>}
      </div>
      {ctx.notes && <p className="regime-notes">{ctx.notes}</p>}
      {ctx.avoid_symbols.length > 0 && (
        <p className="regime-notes critical">Avoiding: {ctx.avoid_symbols.join(", ")}</p>
      )}
    </div>
  );
}
