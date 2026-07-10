import { useEffect, useState } from "react";
import { api } from "../api";
import type { IndexQuote } from "../types";

/** NIFTY 50 · SENSEX · BANK NIFTY at a glance, refreshed every 30s. */
export function IndexStrip() {
  const [indices, setIndices] = useState<IndexQuote[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api
        .indices()
        .then((r) => !cancelled && setIndices(r.indices))
        .catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  if (!indices.length) return null;

  return (
    <div className="index-strip">
      {indices.map((ix) => {
        const up = (ix.change_pct ?? 0) >= 0;
        return (
          <div key={ix.symbol} className="index-card">
            <span className="index-label">{ix.label}</span>
            <strong className="index-value">
              {ix.ltp.toLocaleString("en-IN", { maximumFractionDigits: 2 })}
            </strong>
            {ix.change_pct !== null && (
              <span className={`index-chg ${up ? "good" : "critical"}`}>
                {up ? "▲" : "▼"} {Math.abs(ix.change_pct)}%
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
