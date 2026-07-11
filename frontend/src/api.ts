import type { Analytics, StrategyInfo, BacktestJob, ChartData, HistoryRow, IndexQuote, MarketData, QuantStats, Snapshot, Suggestion, TunableSettings, Wallet } from "./types";

export const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const TOKEN_KEY = "ta_token";

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

export function wsUrl(): string {
  const base = import.meta.env.VITE_WS_URL ?? API_BASE.replace(/^http/, "ws") + "/ws";
  const token = getToken();
  return token ? `${base}?token=${encodeURIComponent(token)}` : base;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (res.status === 401 && path !== "/api/login") {
    // token revoked (password changed) — back to the landing page
    clearToken();
    window.location.reload();
    throw new Error("unauthorized");
  }
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} -> ${res.status}`);
  return res.json();
}

export async function login(username: string, password: string): Promise<{ mode: string }> {
  const r = await req<{ token: string; mode: string }>("/api/login", {
    method: "POST",
    body: JSON.stringify({ username, password }),
  });
  localStorage.setItem(TOKEN_KEY, r.token);
  return { mode: r.mode };
}

/** Unauthenticated — used by the landing page to wake/probe the backend. */
export async function health(): Promise<{ ok: boolean; mode?: string }> {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error(`health ${res.status}`);
  return res.json();
}

export const api = {
  status: () => req<Snapshot>("/api/status"),
  history: (limit = 100) => req<{ rows: HistoryRow[] }>(`/api/history?limit=${limit}`),
  buyIdea: (symbol: string, qty?: number, price?: number) =>
    req(`/api/ideas/${symbol}/buy`, { method: "POST", body: JSON.stringify({ qty, price }) }),
  skipIdea: (symbol: string) => req(`/api/ideas/${symbol}/skip`, { method: "POST" }),
  sellPosition: (symbol: string, price?: number) =>
    req(`/api/positions/${symbol}/sell`, { method: "POST", body: JSON.stringify({ price }) }),
  watchPosition: (symbol: string, qty: number, price: number, stop: number, target?: number) =>
    req(`/api/positions/${symbol}/watch`, {
      method: "POST",
      body: JSON.stringify({ qty, price, stop, target }),
    }),
  pause: () => req("/api/pause", { method: "POST" }),
  resume: () => req("/api/resume", { method: "POST" }),
  chart: (symbol: string, interval: "5m" | "1d", days: number) =>
    req<ChartData>(`/api/chart/${symbol}?interval=${interval}&days=${days}`),
  startBacktest: (body: { strategy: string; symbols?: string[]; days: number; use_index_gate?: boolean }) =>
    req<BacktestJob>("/api/backtest", { method: "POST", body: JSON.stringify(body) }),
  backtestJob: (jobId: string) => req<BacktestJob>(`/api/backtest/${jobId}`),
  getSettings: () => req<{ settings: TunableSettings; editable: string[] }>("/api/settings"),
  patchSettings: (settings: Partial<TunableSettings>) =>
    req<{ applied: Record<string, unknown>; errors: Record<string, string>; settings: TunableSettings }>(
      "/api/settings",
      { method: "PATCH", body: JSON.stringify({ settings }) },
    ),
  market: (group: "watchlist" | "nifty50" | "nasdaq100") => req<MarketData>(`/api/market?group=${group}`),
  indices: () => req<{ indices: IndexQuote[] }>("/api/indices"),
  executeIdea: (symbol: string) =>
    req<{ reply: string; ok: boolean }>(`/api/ideas/${symbol}/execute`, { method: "POST" }),
  exitPosition: (symbol: string) =>
    req<{ reply: string; ok: boolean }>(`/api/positions/${symbol}/exit`, { method: "POST" }),
  placeOrder: (symbol: string, qty: number, stop: number, target?: number) =>
    req<{ reply: string; ok: boolean }>(`/api/order/${symbol}`, {
      method: "POST",
      body: JSON.stringify({ qty, stop, target }),
    }),
  wallet: () => req<{ wallet: Wallet; txns: Record<string, unknown>[] }>("/api/wallet"),
  walletDeposit: (amount: number) =>
    req<{ reply: string; ok: boolean; wallet: Wallet }>("/api/wallet/deposit", {
      method: "POST",
      body: JSON.stringify({ amount }),
    }),
  walletWithdraw: (amount: number) =>
    req<{ reply: string; ok: boolean; wallet: Wallet }>("/api/wallet/withdraw", {
      method: "POST",
      body: JSON.stringify({ amount }),
    }),
  quant: (symbol: string) => req<QuantStats>(`/api/quant/${symbol}`),
  fundamentals: (symbol: string) => req<Record<string, any>>(`/api/fundamentals/${symbol}`),
  screens: () => req<{ prebuilt: { key: string; label: string; desc: string; expr: string }[] }>("/api/screens"),
  analytics: (days = 90) => req<Analytics>(`/api/analytics?days=${days}`),
  strategies: () => req<{ strategies: StrategyInfo[] }>("/api/strategies"),
  toggleStrategy: (key: string, enabled: boolean) =>
    req<{ ok: boolean; reply: string }>(`/api/strategies/${encodeURIComponent(key)}/toggle`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    }),
  telegramStatus: () =>
    req<{ configured: boolean; muted: boolean; last_sent_at: string | null; last_error: string | null }>(
      "/api/telegram/status",
    ),
  reviewTrade: (id: number, body: { notes?: string; tags?: string; rating?: number }) =>
    req<{ ok: boolean }>(`/api/journal/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  runScreen: (body: { group?: string; key?: string; expr?: string }) =>
    req<{ expr: string; scanned: number; matches: any[]; synthetic: boolean }>("/api/screen", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  armPosition: (symbol: string, on: boolean) =>
    req<{ reply: string; ok: boolean }>(`/api/positions/${symbol}/arm`, {
      method: "POST",
      body: JSON.stringify({ on }),
    }),
  suggestions: (group: string) =>
    req<{ picks: Suggestion[]; synthetic: boolean }>(`/api/suggestions?group=${group}`),
  logout: () => req("/api/logout", { method: "POST" }).catch(() => {}),
};

export function historyCsvUrl(): string {
  // CSV download needs the token in the URL since it's a plain <a> navigation;
  // acceptable for a personal tool (token already lives in localStorage)
  return `${API_BASE}/api/history.csv`;
}

export async function downloadHistoryCsv(): Promise<void> {
  const token = getToken();
  const res = await fetch(historyCsvUrl(), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`csv ${res.status}`);
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "trading-journal.csv";
  a.click();
  URL.revokeObjectURL(a.href);
}
