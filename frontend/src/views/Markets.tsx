import { useEffect, useMemo, useState } from "react";
import { useState as useStateReact } from "react";
import { api } from "../api";
import { toast } from "../toast";
import { ChartPanel } from "../components/ChartPanel";
import { IndexStrip } from "../components/IndexStrip";
import type { MarketData, Snapshot } from "../types";

type Group = "watchlist" | "nifty50";

/** Groww-style market browser: indices on top, then a searchable stock list
 * (My stocks / NIFTY 50), tap any row to open its chart. */
export function Markets({ snapshot, prices }: { snapshot: Snapshot; prices: Record<string, number> }) {
  const [group, setGroup] = useState<Group>("watchlist");
  const [data, setData] = useState<MarketData | null>(null);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    const load = () =>
      api
        .market(group)
        .then((r) => {
          if (!cancelled) {
            setData(r);
            setLoading(false);
          }
        })
        .catch(() => !cancelled && setLoading(false));
    load();
    const t = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, [group]);

  const rows = useMemo(() => {
    if (!data) return [];
    const q = query.trim().toUpperCase();
    return Object.entries(data.quotes)
      .filter(([sym, v]) => !q || sym.includes(q) || (v.name ?? "").toUpperCase().includes(q))
      .sort(([a], [b]) => a.localeCompare(b));
  }, [data, query]);

  const movers = useMemo(() => {
    if (!data) return { up: [], down: [] as [string, MarketData["quotes"][string]][] };
    const withChg = Object.entries(data.quotes).filter(([, v]) => v.change_pct !== null);
    const sorted = [...withChg].sort((a, b) => (b[1].change_pct ?? 0) - (a[1].change_pct ?? 0));
    return { up: sorted.slice(0, 3), down: sorted.slice(-3).reverse() };
  }, [data]);

  if (selected) {
    const q = data?.quotes[selected];
    return (
      <div className="markets">
        <button className="back-link" onClick={() => setSelected("")}>
          ‹ All stocks
        </button>
        <ChartPanel symbol={selected} snapshot={snapshot} prices={prices} />
        <OrderTicket
          symbol={selected}
          ltp={prices[selected] ?? q?.ltp ?? 0}
          execute={snapshot.execute}
          cash={snapshot.wallet.cash}
        />
      </div>
    );
  }

  return (
    <div className="markets">
      <IndexStrip />

      {movers.up.length > 0 && (
        <div className="movers">
          <div className="movers-col">
            <span className="movers-title good">Top gainers</span>
            {movers.up.map(([sym, v]) => (
              <button key={sym} className="mover" onClick={() => setSelected(sym)}>
                <span>{sym}</span>
                <span className="good">+{v.change_pct}%</span>
              </button>
            ))}
          </div>
          <div className="movers-col">
            <span className="movers-title critical">Top losers</span>
            {movers.down.map(([sym, v]) => (
              <button key={sym} className="mover" onClick={() => setSelected(sym)}>
                <span>{sym}</span>
                <span className="critical">{v.change_pct}%</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="market-controls">
        <div className="group-toggle">
          <button className={group === "watchlist" ? "active" : ""} onClick={() => setGroup("watchlist")}>
            My stocks
          </button>
          <button className={group === "nifty50" ? "active" : ""} onClick={() => setGroup("nifty50")}>
            NIFTY 50
          </button>
        </div>
        <input
          className="market-search"
          placeholder="Search stocks…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search stocks"
        />
      </div>

      {loading && !rows.length ? (
        <p className="text-muted empty-note">Loading prices…</p>
      ) : (
        <div className="stock-list">
          {rows.map(([sym, v]) => {
            const live = prices[sym] ?? v.ltp;
            const up = (v.change_pct ?? 0) >= 0;
            return (
              <button key={sym} className="stock-row" onClick={() => setSelected(sym)}>
                <div className="stock-id">
                  <strong>{sym}</strong>
                  {v.name && <span>{v.name}</span>}
                </div>
                <div className="stock-quote">
                  <strong>₹{live.toLocaleString("en-IN", { maximumFractionDigits: 2 })}</strong>
                  {v.change_pct !== null && (
                    <span className={up ? "good" : "critical"}>
                      {up ? "+" : ""}
                      {v.change_pct}%
                    </span>
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}


function OrderTicket({
  symbol,
  ltp,
  execute,
  cash,
}: {
  symbol: string;
  ltp: number;
  execute: { enabled: boolean; paper: boolean };
  cash: number;
}) {
  const [qty, setQty] = useStateReact("");
  const [stop, setStop] = useStateReact("");
  const [busy, setBusy] = useStateReact(false);
  const q = Number(qty);
  const s = Number(stop);
  const cost = Number.isFinite(q) && q > 0 && ltp > 0 ? q * ltp : 0;

  const buy = async () => {
    if (!Number.isFinite(q) || q <= 0 || !Number.isInteger(q)) {
      toast("warning", "Shares must be a positive whole number.");
      return;
    }
    if (!Number.isFinite(s) || s <= 0 || s >= ltp) {
      toast("warning", `Your sell-if-falls price must be below the current ₹${ltp}.`);
      return;
    }
    if (cost > cash) {
      toast("warning", `That costs ₹${cost.toLocaleString("en-IN")} but only ₹${cash.toLocaleString("en-IN")} is free.`);
      return;
    }
    setBusy(true);
    try {
      const r = await api.placeOrder(symbol, q, s);
      toast(r.ok ? "success" : "warning", r.reply);
      if (r.ok) {
        setQty("");
        setStop("");
      }
    } catch {
      toast("danger", "Order failed — check the connection and retry.");
    } finally {
      setBusy(false);
    }
  };

  if (!execute.enabled) {
    return (
      <p className="ticket-off text-muted">
        Want to buy {symbol} from here? Turn on "Bot places orders" under More → Settings.
      </p>
    );
  }

  return (
    <div className="order-ticket">
      <p className="ticket-title">
        Buy {symbol}
        {execute.paper ? " (practice money)" : ""} — ₹{cash.toLocaleString("en-IN")} free
      </p>
      <div className="confirm-fields">
        <label>
          Shares
          <input type="number" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} />
        </label>
        <label>
          Sell if it falls to (₹)
          <input type="number" inputMode="decimal" value={stop} onChange={(e) => setStop(e.target.value)} />
        </label>
      </div>
      {cost > 0 && (
        <p className="ticket-cost">
          Cost ~₹{cost.toLocaleString("en-IN", { maximumFractionDigits: 0 })} at ₹{ltp.toLocaleString("en-IN")}
        </p>
      )}
      <button className="btn-big btn-bot" disabled={busy} onClick={buy}>
        {busy ? "Placing…" : `⚡ Buy with wallet`}
      </button>
    </div>
  );
}
