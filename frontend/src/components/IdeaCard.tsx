import { useState } from "react";
import { api } from "../api";
import { toast } from "../toast";
import type { Idea } from "../types";

export function IdeaCard({ idea }: { idea: Idea }) {
  const [qty, setQty] = useState(String(idea.qty));
  const [price, setPrice] = useState(String(idea.entry));
  const [busy, setBusy] = useState(false);
  const long = idea.side === "BUY";

  const buy = async () => {
    const q = Number(qty);
    const p = Number(price);
    if (!Number.isFinite(q) || q <= 0 || !Number.isInteger(q)) {
      toast("warning", "Quantity must be a positive whole number.");
      return;
    }
    if (!Number.isFinite(p) || p <= 0) {
      toast("warning", "Fill price must be a positive number.");
      return;
    }
    if (Math.abs(p - idea.entry) / idea.entry > 0.2) {
      toast("warning", `Fill price ₹${p} is >20% away from the idea's entry ₹${idea.entry} — double-check it.`);
      return;
    }
    setBusy(true);
    try {
      await api.buyIdea(idea.symbol, q, p);
      toast("success", `Tracking ${idea.symbol}: ${q} @ ₹${p}`);
    } catch {
      toast("danger", `Couldn't confirm ${idea.symbol} — check the connection and retry.`);
    } finally {
      setBusy(false);
    }
  };
  const skip = async () => {
    if (!window.confirm(`Dismiss the ${idea.symbol} idea? It won't re-fire today.`)) return;
    setBusy(true);
    try {
      await api.skipIdea(idea.symbol);
    } catch {
      toast("danger", `Couldn't skip ${idea.symbol} — retry.`);
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
