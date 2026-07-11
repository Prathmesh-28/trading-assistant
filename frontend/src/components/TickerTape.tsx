import { useEffect, useState } from "react";
import { api } from "../api";

type Quote = { ltp: number; change_pct: number | null };

/** Scrolling tape of the user's watchlist — real quotes, refreshed with the
 * market cache. Pure decoration on top of real data; hidden if quotes fail. */
export function TickerTape({ prices }: { prices: Record<string, number> }) {
  const [quotes, setQuotes] = useState<Record<string, Quote>>({});

  useEffect(() => {
    let dead = false;
    const load = () =>
      api.market("watchlist").then((r) => !dead && setQuotes(r.quotes as Record<string, Quote>)).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => { dead = true; clearInterval(t); };
  }, []);

  const items = Object.entries(quotes);
  if (items.length === 0) return null;
  const cell = ([sym, q]: [string, Quote], dup: boolean) => {
    const ltp = prices[sym] ?? q.ltp;
    const up = (q.change_pct ?? 0) >= 0;
    return (
      <span className="tick" key={dup ? `d-${sym}` : sym}>
        <b>{sym}</b>
        <span className={up ? "good" : "critical"}>
          {ltp.toLocaleString("en-IN", { maximumFractionDigits: 2 })} {up ? "▲" : "▼"}
        </span>
      </span>
    );
  };

  return (
    <div className="ticker-wrap" aria-hidden>
      <div className="ticker-track">
        {items.map((it) => cell(it, false))}
        {items.map((it) => cell(it, true))}
      </div>
    </div>
  );
}
