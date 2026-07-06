import { useState } from "react";
import { api } from "../api";
import type { Idea } from "../types";

export function PositionCard({ idea }: { idea: Idea }) {
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);
  const long = idea.side === "BUY";
  const pnlColor = idea.pnl >= 0 ? "var(--good)" : "var(--critical)";
  const distToStop = Math.abs(idea.ltp - idea.stop);
  const distToTarget = Math.abs(idea.target - idea.ltp);
  const nearStop = distToStop <= distToTarget;

  const sell = async () => {
    setBusy(true);
    try {
      await api.sellPosition(idea.symbol, price ? Number(price) : undefined);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="card">
      <div className="card-head">
        <span className={`side-badge ${long ? "good" : "critical"}`}>{idea.side}</span>
        <span className="symbol">{idea.symbol}</span>
        <span className="horizon-tag">{idea.horizon === "intraday" ? "MIS" : "CNC"}</span>
      </div>
      <div className="levels">
        <span>
          {idea.fill_qty} @ ₹{idea.fill_price.toLocaleString("en-IN")}
        </span>
        <span>
          LTP <strong>₹{idea.ltp.toLocaleString("en-IN")}</strong>
        </span>
        <span className={nearStop ? "critical" : "text-muted"}>Stop ₹{idea.stop.toLocaleString("en-IN")}</span>
        <span className={!nearStop ? "good" : "text-muted"}>Target ₹{idea.target.toLocaleString("en-IN")}</span>
      </div>
      <div className="pnl-line" style={{ color: pnlColor }}>
        {idea.pnl >= 0 ? "+" : ""}
        ₹{idea.pnl.toLocaleString("en-IN")}
      </div>
      <div className="idea-actions">
        <input
          className="num-input"
          type="number"
          placeholder={`${idea.ltp}`}
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          aria-label="Exit price"
        />
        <button className="btn btn-critical" disabled={busy} onClick={sell}>
          Sold
        </button>
      </div>
    </div>
  );
}
