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

export interface Quote {
  ltp: number | null;
  prev_close: number | null;
  change_pct: number | null;
}

export interface MarketStatus {
  phase: "open" | "pre-open" | "closed";
  next_open: string | null;
  next_close: string | null;
}

export interface Snapshot {
  mode: "LIVE" | "SYNTHETIC";
  paused: boolean;
  watchlist: string[];
  context: MarketContext;
  pending: Idea[];
  positions: Idea[];
  day_stats: DayStats;
  market: MarketStatus;
  quotes: Record<string, Quote>;
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
  | { type: "tick"; data: { prices: Record<string, number>; market?: MarketStatus; server_time: string } };

/* ---------- charts ---------- */

export interface ChartCandle {
  time: number | string; // epoch seconds (5m) or "YYYY-MM-DD" (1d)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ChartData {
  symbol: string;
  interval: "5m" | "1d";
  synthetic: boolean;
  candles: ChartCandle[];
  overlays: Record<string, (number | null)[]>; // aligned to candles
}

/* ---------- backtests ---------- */

export interface BacktestTrade {
  symbol: string;
  side: Side;
  entry_date: string;
  entry: number;
  stop: number;
  target: number;
  qty: number;
  exit: number;
  exit_reason: string;
  pnl: number;
  r_multiple: number;
  costs: number;
}

export interface BacktestSummary {
  strategy: string;
  n_trades: number;
  win_rate_pct: number;
  profit_factor: number | null;
  avg_r_multiple: number;
  stdev_r: number;
  total_pnl: number;
  total_costs: number;
  total_return_pct: number;
  cagr_pct: number | null;
  max_drawdown: number;
  recovery_factor: number | null;
  calmar_ratio: number | null;
  monte_carlo: { p50_max_dd: number; p95_max_dd: number } | null;
  by_exit_reason: Record<string, { count: number; total_pnl: number; win_rate_pct: number }>;
  buy_hold_return_pct: Record<string, number>;
  ambiguous_bar_exits: number;
  ambiguous_bar_rate_pct: number;
  starting_capital: number;
  ending_capital: number;
  diagnostics: string[];
  warnings: string[];
}

export interface BacktestJob {
  job_id: string | null;
  status: "running" | "done" | "error" | "unavailable";
  strategy?: string;
  symbols?: string[];
  days?: number;
  message?: string;
  started_at?: string;
  finished_at?: string;
  result?: { summary: BacktestSummary; equity_curve: number[]; trades: BacktestTrade[] };
}

/* ---------- runtime settings ---------- */

export interface TunableSettings {
  watchlist: string[];
  risk_per_trade_pct: number;
  capital: number;
  max_position_value: number;
  max_open_positions: number;
  max_portfolio_risk_pct: number;
}

/* ---------- markets ---------- */

export interface MarketQuote {
  ltp: number;
  prev_close: number | null;
  change_pct: number | null;
  name?: string;
}

export interface MarketData {
  group: string;
  quotes: Record<string, MarketQuote>;
  synthetic: boolean;
}

export interface IndexQuote {
  symbol: string;
  label: string;
  ltp: number;
  prev_close: number | null;
  change_pct: number | null;
}
