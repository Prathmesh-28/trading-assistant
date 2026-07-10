import { useState } from "react";
import { api } from "../api";
import { BacktestPanel } from "../components/BacktestPanel";
import { SettingsPanel } from "../components/SettingsPanel";
import type { Snapshot } from "../types";

type Section = "menu" | "settings" | "backtest";

/** Everything that isn't daily trading lives here, one level deep. */
export function More({
  snapshot,
  onLogout,
  paused,
  onTogglePause,
}: {
  snapshot: Snapshot;
  onLogout: () => void;
  paused: boolean;
  onTogglePause: () => void;
}) {
  const [section, setSection] = useState<Section>("menu");

  if (section === "settings" || section === "backtest") {
    return (
      <div className="more">
        <button className="back-link" onClick={() => setSection("menu")}>
          ‹ Back
        </button>
        {section === "settings" ? <SettingsPanel /> : <BacktestPanel snapshot={snapshot} />}
      </div>
    );
  }

  return (
    <div className="more">
      <button className="more-item" onClick={() => setSection("settings")}>
        <span>⚙️ Settings</span>
        <span className="more-hint">Stocks to scan, money at risk</span>
      </button>
      <button className="more-item" onClick={() => setSection("backtest")}>
        <span>🧪 Test a strategy</span>
        <span className="more-hint">Run it on past data before trusting it</span>
      </button>
      <button className="more-item" onClick={onTogglePause}>
        <span>{paused ? "▶️ Resume new ideas" : "⏸ Pause new ideas"}</span>
        <span className="more-hint">
          {paused ? "Idea scanning is currently off" : "Existing positions stay watched"}
        </span>
      </button>
      <button className="more-item" onClick={() => { api.logout(); onLogout(); }}>
        <span>🚪 Sign out</span>
        <span className="more-hint">On shared devices, always do this</span>
      </button>

      <p className="more-foot">
        {snapshot.mode === "LIVE" ? "Live NSE data" : "Demo data (synthetic)"} · you place every
        trade yourself · not investment advice
      </p>
    </div>
  );
}
