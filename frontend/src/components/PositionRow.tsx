import { useState } from "react";
import { api } from "../api";
import { entryMark, horizonLabel, progressToTarget, rupees } from "../lang";
import { toast } from "../toast";
import type { Idea } from "../types";

/** One position you hold: name, live PnL in big type, and a visual bar
 * showing where price sits between your sell-stop and your profit goal. */
export function PositionRow({ idea, execute }: { idea: Idea; execute?: { enabled: boolean; paper: boolean } }) {
  const [expanded, setExpanded] = useState(false);
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);

  const pnl = idea.pnl;
  const up = pnl >= 0;
  const pct = progressToTarget(idea) * 100;
  const entryPct = entryMark(idea) * 100;
  const hitStop = idea.ltp <= idea.stop;
  const hitTarget = idea.ltp >= idea.target;

  const botSell = async () => {
    setBusy(true);
    try {
      const r = await api.exitPosition(idea.symbol);
      toast(r.ok ? "success" : "warning", r.reply);
    } catch {
      toast("danger", "Sell order failed — retry.");
    } finally {
      setBusy(false);
    }
  };

  const sell = async () => {
    const p = price ? Number(price) : undefined;
    if (p !== undefined && (!Number.isFinite(p) || p <= 0)) {
      toast("warning", "Price must be a positive number — or leave it blank.");
      return;
    }
    setBusy(true);
    try {
      await api.sellPosition(idea.symbol, p);
      toast("success", `${idea.symbol} closed — saved to your journal.`);
    } catch {
      toast("danger", `Couldn't save the sale — tap again.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`pos-row ${hitStop ? "pos-alarm" : ""}`}>
      <button className="pos-main" onClick={() => setExpanded((e) => !e)} aria-expanded={expanded}>
        <div className="pos-name">
          <strong>{idea.symbol}</strong>
          <span className="pos-sub">
            {idea.fill_qty} shares · in at {rupees(idea.fill_price || idea.entry)}
          </span>
        </div>
        <div className={`pos-pnl ${up ? "good" : "critical"}`}>
          {up ? "+" : ""}
          {rupees(pnl, 0)}
        </div>
      </button>

      <div className="pos-bar" aria-hidden>
        <div className="pos-bar-fill" style={{ width: `${pct}%` }} />
        <div className="pos-bar-entry" style={{ left: `${entryPct}%` }} />
      </div>
      <div className="pos-bar-labels">
        <span className="critical">sell if {rupees(idea.stop, 0)}</span>
        <span className="pos-ltp">now {rupees(idea.ltp, 0)}</span>
        <span className="good">goal {rupees(idea.target, 0)}</span>
      </div>

      {(hitStop || hitTarget) && (
        <p className={`pos-callout ${hitStop ? "critical" : "good"}`}>
          {hitStop
            ? "⚠ Below your sell level — open your broker app and sell, then confirm below."
            : "🎯 Profit goal reached — sell to book it, or keep riding with the raised stop."}
        </p>
      )}

      {expanded && (
        <div className="pos-actions">
          <p className="pos-detail">{horizonLabel(idea.horizon)}</p>
          <div className="confirm-fields">
            <label>
              Sold at (₹) — blank = last price
              <input
                type="number"
                inputMode="decimal"
                placeholder={String(idea.ltp)}
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </label>
          </div>
          {execute?.enabled && (
            <label className="toggle-row" style={{ marginBottom: 8 }}>
              <div>
                <strong>🛡 Auto-sell at stop</strong>
                <p className="text-muted" style={{ margin: 0, fontSize: 11 }}>
                  Bot fires the sell order the instant ₹{idea.stop.toLocaleString("en-IN")} is touched
                </p>
              </div>
              <input
                type="checkbox"
                checked={Boolean(idea.auto_exit)}
                onChange={async (e) => {
                  const r = await api.armPosition(idea.symbol, e.target.checked).catch(() => null);
                  if (r) toast(r.ok ? "success" : "warning", r.reply);
                }}
              />
            </label>
          )}
          {execute?.enabled && (
            <button className="btn-big btn-bot" disabled={busy} onClick={botSell}>
              ⚡ Sell now with bot{execute.paper ? " (practice)" : ""}
            </button>
          )}
          <button className="btn-big btn-sell" disabled={busy} onClick={sell}>
            {busy ? "Saving…" : "I sold it myself — book it"}
          </button>
        </div>
      )}
    </div>
  );
}
