export type Side = "BUY" | "SELL";
export type Horizon = "intraday" | "positional";
export type AlertLevel = "info" | "success" | "warning" | "danger";

export interface Idea {
  idea_id: number;
  symbol: string;
  side: Side;
  horizon: Horizon;
  entry: number;
  stop: number;
  target: number;
  qty: number;
  confidence: string;
  reason: string;
  why: string;
  status: string;
  risk_reward: number;
  created_at: string;
  fill_qty: number;
  fill_price: number;
  exit_price: number;
  ltp: number;
  pnl: number;
}

export interface MarketContext {
  regime: string;
  bias: string;
  confidence: string;
  notes: string;
  avoid_symbols: string[];
  updated_at: string | null;
}

export interface DayStats {
  closed_today: number;
  realised_pnl: number;
}

export interface Snapshot {
  mode: "LIVE" | "SYNTHETIC";
  paused: boolean;
  watchlist: string[];
  context: MarketContext;
  pending: Idea[];
  positions: Idea[];
  day_stats: DayStats;
  server_time: string;
}

export interface AlertEvent {
  id: number;
  level: AlertLevel;
  symbol?: string;
  message: string;
  at: number;
}

export interface HistoryRow {
  id: number;
  created_at: string;
  symbol: string;
  side: Side;
  horizon: Horizon;
  entry: number;
  stop: number;
  target: number;
  qty: number;
  confidence: string;
  reason: string;
  why: string;
  status: string;
  fill_qty: number;
  fill_price: number;
  exit_price: number;
  pnl: number | null;
  updated_at: string;
}

export type WsEvent =
  | { type: "snapshot"; data: Snapshot }
  | { type: "alert"; data: { level: AlertLevel; symbol?: string; message: string } }
  | { type: "tick"; data: { prices: Record<string, number>; server_time: string } };
