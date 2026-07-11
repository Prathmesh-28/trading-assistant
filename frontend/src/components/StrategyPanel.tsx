import { useEffect, useState } from "react";
import { api } from "../api";
import { rupees } from "../lang";
import { toast } from "../toast";
import type { StrategyInfo } from "../types";

/** Strategy manager: every playbook the engine runs, with its live record and
 * an on/off switch (off = the engine skips those ideas, everything else runs). */
export function StrategyPanel() {
  const [rows, setRows] = useState<StrategyInfo[]>([]);
  const [busy, setBusy] = useState("");

  const load = () => api.strategies().then((r) => setRows(r.strategies)).catch(() => {});
  useEffect(() => { load(); }, []);

  const toggle = async (s: StrategyInfo) => {
    setBusy(s.key);
    try {
      const r = await api.toggleStrategy(s.key, !s.enabled);
      if (r.reply) toast("warning", r.reply);
      else toast("success", `${s.name} ${s.enabled ? "paused" : "back on"}`);
      load();
    } catch {
      toast("danger", "Could not update the strategy — try again.");
    } finally {
      setBusy("");
    }
  };

  if (rows.length === 0) return <p className="text-muted empty-note">Loading strategies…</p>;

  const groups: [string, StrategyInfo[]][] = [
    ["Intraday (square off same day)", rows.filter((r) => r.horizon === "intraday")],
    ["Positional (hold days–weeks)", rows.filter((r) => r.horizon === "positional")],
  ];

  return (
    <div className="strategy-panel">
      {groups.map(([title, list]) => (
        <section key={title}>
          <h3 className="fund-sec-title">{title}</h3>
          {list.map((s) => (
            <div className="strategy-row" key={s.key}>
              <div className="strategy-id">
                <strong>{s.name}</strong>
                <span>{s.desc}</span>
                <span className="strategy-stats mono">
                  {s.signals} signals
                  {s.closed > 0 && (
                    <>
                      {" · "}{s.win_rate_pct}% wins ·{" "}
                      <em className={s.pnl >= 0 ? "good" : "critical"}>
                        {s.pnl >= 0 ? "+" : "−"}{rupees(Math.abs(s.pnl), 0)}
                      </em>
                    </>
                  )}
                </span>
              </div>
              <button
                className={`toggle ${s.enabled ? "on" : ""}`}
                disabled={busy === s.key}
                onClick={() => toggle(s)}
                aria-label={`${s.name} ${s.enabled ? "on" : "off"}`}
              >
                <span className="knob" />
              </button>
            </div>
          ))}
        </section>
      ))}
      <p className="more-foot">Off = the engine stops sending that playbook's ideas; open positions stay watched.</p>
    </div>
  );
}
