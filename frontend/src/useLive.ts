import { useEffect, useRef, useState } from "react";
import { wsUrl } from "./api";
import type { AlertEvent, MarketStatus, Snapshot, WsEvent } from "./types";

let alertSeq = 0;

function applyTick(snap: Snapshot, prices: Record<string, number>): Snapshot {
  const patch = (idea: Snapshot["positions"][number]) => {
    const ltp = prices[idea.symbol];
    if (ltp === undefined) return idea;
    const direction = idea.side === "BUY" ? 1 : -1;
    const ref = idea.fill_price || idea.entry;
    const pnl = idea.fill_qty > 0 ? Math.round((ltp - ref) * idea.fill_qty * direction * 100) / 100 : 0;
    return { ...idea, ltp, pnl };
  };
  return { ...snap, positions: snap.positions.map(patch), pending: snap.pending.map(patch) };
}

export function useLive() {
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [connected, setConnected] = useState(false);
  const [alerts, setAlerts] = useState<AlertEvent[]>([]);
  const [prices, setPrices] = useState<Record<string, number>>({});
  const [market, setMarket] = useState<MarketStatus | null>(null);
  const snapRef = useRef<Snapshot | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const connect = () => {
      ws = new WebSocket(wsUrl());
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!cancelled) retryTimer = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (ev) => {
        const msg: WsEvent = JSON.parse(ev.data);
        if (msg.type === "snapshot") {
          snapRef.current = msg.data;
          setSnapshot(msg.data);
          setMarket(msg.data.market ?? null);
        } else if (msg.type === "tick" && snapRef.current) {
          const next = applyTick(snapRef.current, msg.data.prices);
          snapRef.current = next;
          setSnapshot(next);
          setPrices((prev) => ({ ...prev, ...msg.data.prices }));
          if (msg.data.market) setMarket(msg.data.market);
        } else if (msg.type === "alert") {
          const entry: AlertEvent = { id: ++alertSeq, at: Date.now(), ...msg.data };
          setAlerts((prev) => [...prev, entry]);
          setTimeout(() => {
            setAlerts((prev) => prev.filter((a) => a.id !== entry.id));
          }, 8000);
        }
      };
    };
    connect();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
    };
  }, []);

  const dismissAlert = (id: number) => setAlerts((prev) => prev.filter((a) => a.id !== id));

  return { snapshot, connected, alerts, dismissAlert, prices, market };
}
