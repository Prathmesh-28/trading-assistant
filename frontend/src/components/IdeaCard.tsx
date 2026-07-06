import { useState } from "react";
import { api } from "../api";
import type { Idea } from "../types";

export function IdeaCard({ idea }: { idea: Idea }) {
  const [qty, setQty] = useState(String(idea.qty));
  const [price, setPrice] = useState(String(idea.entry));
  const [busy, setBusy] = useState(false);
  const long = idea.side === "BUY";

  const buy = async () => {
    setBusy(true);
    try {
      await api.buyIdea(idea.symbol, Number(qty) || undefined, Number(price) || undefined);
    } finally {
      setBusy(false);
    }
  };
  const skip = async () => {
    setBusy(true);
    try {
      await api.skipIdea(idea.symbol);
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
        <span className="confidence">{idea.confidence}</span>
      </div>
      <div className="levels">
        <span>Entry ₹{idea.entry.toLocaleString("en-IN")}</span>
        <span className="critical">Stop ₹{idea.stop.toLocaleString("en-IN")}</span>
        <span className="good">Target ₹{idea.target.toLocaleString("en-IN")}</span>
        <span className="text-muted">R:R {idea.risk_reward}</span>
      </div>
      {(idea.why || idea.reason) && <p className="why">{idea.why || idea.reason}</p>}
      <div className="idea-actions">
        <input
          className="num-input"
          type="number"
          value={qty}
          onChange={(e) => setQty(e.target.value)}
          aria-label="Quantity bought"
        />
        <input
          className="num-input"
          type="number"
          value={price}
          onChange={(e) => setPrice(e.target.value)}
          aria-label="Fill price"
        />
        <button className="btn btn-good" disabled={busy} onClick={buy}>
          Bought
        </button>
        <button className="btn btn-ghost" disabled={busy} onClick={skip}>
          Skip
        </button>
      </div>
    </div>
  );
}
