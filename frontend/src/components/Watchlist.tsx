import type { Quote, Snapshot } from "../types";

interface Props {
  snapshot: Snapshot;
  prices: Record<string, number>; // live tick prices, override snapshot quotes
  selected: string;
  onSelect: (symbol: string) => void;
}

function liveQuote(sym: string, quotes: Record<string, Quote>, prices: Record<string, number>): Quote {
  const q = quotes[sym] ?? { ltp: null, prev_close: null, change_pct: null };
  const ltp = prices[sym] ?? q.ltp;
  const change_pct =
    ltp != null && q.prev_close ? Math.round(((ltp - q.prev_close) / q.prev_close) * 10000) / 100 : q.change_pct;
  return { ltp, prev_close: q.prev_close, change_pct };
}

/** Groww/Zerodha-style watchlist: live LTP + day change, click to chart. */
export function Watchlist({ snapshot, prices, selected, onSelect }: Props) {
  const pendingSyms = new Set(snapshot.pending.map((i) => i.symbol));
  const positionSyms = new Set(snapshot.positions.map((i) => i.symbol));

  return (
    <div className="watchlist">
      <div className="watchlist-head">
        <h2>Watchlist</h2>
        <span className="text-muted watchlist-count">{snapshot.watchlist.length}</span>
      </div>
      <ul className="watchlist-rows">
        {snapshot.watchlist.map((sym) => {
          const q = liveQuote(sym, snapshot.quotes ?? {}, prices);
          const up = (q.change_pct ?? 0) >= 0;
          return (
            <li key={sym}>
              <button
                className={`watchlist-row ${sym === selected ? "active" : ""}`}
                onClick={() => onSelect(sym)}
              >
                <span className="wl-symbol">
                  {sym}
                  {positionSyms.has(sym) && <span className="wl-flag good" title="open position">▮</span>}
                  {pendingSyms.has(sym) && <span className="wl-flag warning" title="pending idea">●</span>}
                </span>
                <span className="wl-quote tabular">
                  <span className="wl-ltp">{q.ltp != null ? q.ltp.toLocaleString("en-IN", { minimumFractionDigits: 2 }) : "—"}</span>
                  <span className={`wl-chg ${up ? "good" : "critical"}`}>
                    {q.change_pct != null ? `${up ? "+" : ""}${q.change_pct.toFixed(2)}%` : ""}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
