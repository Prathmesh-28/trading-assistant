import { useState } from "react";
import { api } from "../api";
import { toast } from "../toast";
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
    const p = price ? Number(price) : undefined;
    if (p !== undefined && (!Number.isFinite(p) || p <= 0)) {
      toast("warning", "Exit price must be a positive number (or leave blank for last price).");
      return;
    }
    if (p !== undefined && idea.ltp > 0 && Math.abs(p - idea.ltp) / idea.ltp > 0.2) {
      toast("warning", `Exit price ₹${p} is >20% from LTP ₹${idea.ltp} — double-check it.`);
      return;
    }
    if (!window.confirm(`Mark ${idea.symbol} as SOLD${p ? ` @ ₹${p}` : " at last price"}? This books the PnL.`)) return;
    setBusy(true);
    try {
      await api.sellPosition(idea.symbol, p);
      toast("success", `${idea.symbol} closed — PnL journaled.`);
    } catch {
      toast("danger", `Couldn't close ${idea.symbol} — check the connection and retry.`);
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
