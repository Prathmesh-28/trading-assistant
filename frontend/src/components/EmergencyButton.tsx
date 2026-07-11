import { useState } from "react";
import { api } from "../api";
import { toast } from "../toast";

/** One-tap emergency exit: closes every open position and pauses new ideas.
 * Two-step confirm so it can't fire on a mis-tap. */
export function EmergencyButton({ openCount }: { openCount: number }) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  if (openCount === 0) return null;

  const flatten = async () => {
    setBusy(true);
    try {
      const r = await api.flattenAll();
      toast(r.ok ? "success" : "warning", r.reply);
    } catch {
      toast("danger", "Flatten failed — exit manually on Groww and check the app.");
    } finally {
      setBusy(false);
      setArmed(false);
    }
  };

  return armed ? (
    <div className="emergency-confirm">
      <span>Exit all {openCount} positions & pause?</span>
      <button className="btn-danger" disabled={busy} onClick={flatten}>
        {busy ? "Exiting…" : "Yes, flatten"}
      </button>
      <button className="btn-ghost" disabled={busy} onClick={() => setArmed(false)}>Cancel</button>
    </div>
  ) : (
    <button className="emergency-btn" onClick={() => setArmed(true)}>
      🛑 Exit all positions
    </button>
  );
}
