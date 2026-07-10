import { useState } from "react";
import { ChartPanel } from "../components/ChartPanel";
import type { Snapshot } from "../types";

/** Charts, uncluttered: pick a stock from a chip row, see its chart.
 * Change-% rides on each chip so the row doubles as a mini watchlist. */
export function ChartView({ snapshot, prices }: { snapshot: Snapshot; prices: Record<string, number> }) {
  const [selected, setSelected] = useState(
    snapshot.positions[0]?.symbol ?? snapshot.watchlist[0] ?? "",
  );

  return (
    <div className="chart-view">
      <div className="symbol-chips">
        {snapshot.watchlist.map((sym) => {
          const q = snapshot.quotes?.[sym];
          const chg = q?.change_pct;
          return (
            <button
              key={sym}
              className={`symbol-chip ${selected === sym ? "active" : ""}`}
              onClick={() => setSelected(sym)}
            >
              {sym}
              {chg !== null && chg !== undefined && (
                <span className={chg >= 0 ? "good" : "critical"}>
                  {chg >= 0 ? "+" : ""}
                  {chg}%
                </span>
              )}
            </button>
          );
        })}
      </div>
      {selected && <ChartPanel symbol={selected} snapshot={snapshot} prices={prices} />}
    </div>
  );
}
