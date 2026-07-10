import { useState } from "react";
import { api } from "../api";
import { confidenceLabel, horizonLabel, riskLine, rupees } from "../lang";
import { toast } from "../toast";
import type { Idea } from "../types";

/** A new trade idea, redesigned to read top-to-bottom like a sentence:
 * what to buy → at what levels → what it costs/risks → confirm or ignore. */
export function IdeaCard({ idea }: { idea: Idea }) {
  const [qty, setQty] = useState(String(idea.qty));
  const [price, setPrice] = useState(String(idea.entry));
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const buy = async () => {
    const q = Number(qty);
    const p = Number(price);
    if (!Number.isFinite(q) || q <= 0 || !Number.isInteger(q)) {
      toast("warning", "Shares must be a positive whole number.");
      return;
    }
    if (!Number.isFinite(p) || p <= 0) {
      toast("warning", "Price must be a positive number.");
      return;
    }
    if (Math.abs(p - idea.entry) / idea.entry > 0.2) {
      toast("warning", `That price is far from the suggested ${rupees(idea.entry)} — double-check it.`);
      return;
    }
    setBusy(true);
    try {
      await api.buyIdea(idea.symbol, q, p);
      toast("success", `Got it — watching ${idea.symbol} for you now.`);
    } catch {
      toast("danger", `Couldn't save that — check your connection and tap again.`);
    } finally {
      setBusy(false);
    }
  };

  const skip = async () => {
    setBusy(true);
    try {
      await api.skipIdea(idea.symbol);
      toast("info", `${idea.symbol} ignored for today.`);
    } catch {
      toast("danger", `Couldn't ignore ${idea.symbol} — tap again.`);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="idea-card">
      <div className="idea-headline">
        <span className="idea-action">BUY</span>
        <span className="idea-symbol">{idea.symbol}</span>
        <span className="idea-price">~{rupees(idea.entry)}</span>
      </div>
      <p className="idea-sub">
        {horizonLabel(idea.horizon)}
        {idea.confidence && confidenceLabel(idea.confidence) ? ` · ${confidenceLabel(idea.confidence)}` : ""}
      </p>

      <div className="level-strip">
        <div className="level">
          <span className="level-tag critical">If it falls, sell at</span>
          <strong>{rupees(idea.stop)}</strong>
        </div>
        <div className="level">
          <span className="level-tag good">Profit goal</span>
          <strong>{rupees(idea.target)}</strong>
        </div>
        <div className="level">
          <span className="level-tag">Suggested</span>
          <strong>{idea.qty} shares</strong>
        </div>
      </div>

      <p className="idea-risk">{riskLine(idea)}</p>
      {(idea.why || idea.reason) && <p className="idea-why">{idea.why || idea.reason}</p>}

      {!confirming ? (
        <div className="idea-buttons">
          <button className="btn-big btn-buy" onClick={() => setConfirming(true)}>
            I bought this
          </button>
          <button className="btn-big btn-ignore" disabled={busy} onClick={skip}>
            Ignore
          </button>
        </div>
      ) : (
        <div className="confirm-box">
          <p className="confirm-title">Tell me your actual fill:</p>
          <div className="confirm-fields">
            <label>
              Shares bought
              <input type="number" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} />
            </label>
            <label>
              At price (₹)
              <input type="number" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} />
            </label>
          </div>
          <div className="idea-buttons">
            <button className="btn-big btn-buy" disabled={busy} onClick={buy}>
              {busy ? "Saving…" : "Start watching it"}
            </button>
            <button className="btn-big btn-ignore" disabled={busy} onClick={() => setConfirming(false)}>
              Back
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
