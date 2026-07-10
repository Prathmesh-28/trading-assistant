import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
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
    return (
      <div className="markets">
        <button className="back-link" onClick={() => setSelected("")}>
          ‹ All stocks
        </button>
        <ChartPanel symbol={selected} snapshot={snapshot} prices={prices} />
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
