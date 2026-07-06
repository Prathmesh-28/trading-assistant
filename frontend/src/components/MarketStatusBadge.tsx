import { useEffect, useState } from "react";
import type { MarketStatus } from "../types";

function fmtCountdown(ms: number): string {
  if (ms <= 0) return "now";
  const m = Math.floor(ms / 60000);
  if (m >= 48 * 60) return `${Math.round(m / 1440)}d`;
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m`;
  if (m >= 1) return `${m}m`;
  return `${Math.floor(ms / 1000)}s`;
}

const PHASE: Record<MarketStatus["phase"], { label: string; cls: string }> = {
  open: { label: "MARKET OPEN", cls: "phase-open" },
  "pre-open": { label: "PRE-OPEN", cls: "phase-preopen" },
  closed: { label: "MARKET CLOSED", cls: "phase-closed" },
};

/** NSE session badge with a live countdown to the next open/close (IST). */
export function MarketStatusBadge({ market }: { market: MarketStatus | null }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(t);
  }, []);

  if (!market) return null;
  const p = PHASE[market.phase];
  const targetIso = market.phase === "open" ? market.next_close : market.next_open;
  const verb = market.phase === "open" ? "closes in" : "opens in";
  const remaining = targetIso ? new Date(targetIso).getTime() - Date.now() : null;

  return (
    <span className={`market-badge ${p.cls}`}>
      <span className="market-dot" />
      {p.label}
      {remaining !== null && remaining > 0 && (
        <span className="market-countdown">
          · {verb} {fmtCountdown(remaining)}
        </span>
      )}
    </span>
  );
}
