import type { Idea, MarketContext, MarketStatus } from "./types";

/** Plain-language helpers — every piece of trader jargon gets translated
 * once, here, so the UI reads like a human wrote it. */

export const rupees = (v: number, digits = 2): string =>
  `₹${v.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

export const horizonLabel = (h: Idea["horizon"]): string =>
  h === "intraday" ? "Intraday · exit today" : "Swing · hold days–weeks";

export const confidenceLabel = (c: string): string =>
  ({ HIGH: "Strong setup", MEDIUM: "Decent setup", LOW: "Weak setup" })[c] ?? "";

export function riskLine(idea: Idea): string {
  const qty = idea.fill_qty || idea.qty;
  const ref = idea.fill_price || idea.entry;
  const risk = Math.abs(ref - idea.stop) * qty;
  const reward = Math.abs(idea.target - ref) * qty;
  return `Risking ${rupees(risk, 0)} to make ${rupees(reward, 0)}`;
}

export const regimeLabel = (ctx: MarketContext): string =>
  ({
    bull_trend: "📈 Market mood: trending up — good for buying",
    bear_trend: "📉 Market mood: trending down — new buys are blocked",
    range: "↔️ Market mood: sideways — only dip-buys allowed",
    high_volatility: "⚡ Market mood: choppy — new buys are blocked",
    transition: "🌫 Market mood: mixed",
    trending: "📈 Market mood: trending",
    choppy: "⚡ Market mood: choppy",
  })[ctx.regime] ?? "";

export function marketLine(m: MarketStatus | null): string {
  if (!m) return "";
  if (m.phase === "open") return "Market is open";
  if (m.phase === "pre-open") return "Pre-open — trading starts 9:15";
  if (!m.next_open) return "Market is closed";
  const mins = Math.max(0, Math.round((new Date(m.next_open).getTime() - Date.now()) / 60000));
  const h = Math.floor(mins / 60);
  const rest = mins % 60;
  const inTxt = h > 0 ? `${h}h ${rest}m` : `${rest}m`;
  return `Market closed — opens in ${inTxt}`;
}

/** 0..1 position of LTP on the stop→target line (long or short). */
export function progressToTarget(idea: Idea): number {
  const span = idea.target - idea.stop;
  if (span === 0) return 0.5;
  return Math.min(1, Math.max(0, (idea.ltp - idea.stop) / span));
}

/** Same scale, where the entry sits on the bar. */
export function entryMark(idea: Idea): number {
  const span = idea.target - idea.stop;
  const ref = idea.fill_price || idea.entry;
  if (span === 0) return 0.5;
  return Math.min(1, Math.max(0, (ref - idea.stop) / span));
}
