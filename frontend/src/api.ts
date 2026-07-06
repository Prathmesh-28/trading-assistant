import type { BacktestJob, ChartData, HistoryRow, Snapshot } from "./types";

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
};
