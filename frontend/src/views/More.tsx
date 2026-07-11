import { useState } from "react";
import { api } from "../api";
import { BacktestPanel } from "../components/BacktestPanel";
import { SettingsPanel } from "../components/SettingsPanel";
import { StrategyPanel } from "../components/StrategyPanel";
import { TelegramPanel } from "../components/TelegramPanel";
import type { Snapshot } from "../types";

type Section = "menu" | "settings" | "backtest" | "help" | "strategies" | "telegram";

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

  if (section !== "menu") {
    return (
      <div className="more">
        <button className="back-link" onClick={() => setSection("menu")}>
          ‹ Back
        </button>
        {section === "settings" && <SettingsPanel />}
        {section === "backtest" && <BacktestPanel snapshot={snapshot} />}
        {section === "help" && <HowItWorks />}
        {section === "strategies" && <StrategyPanel />}
        {section === "telegram" && <TelegramPanel />}
      </div>
    );
  }

  return (
    <div className="more">
      <button className="more-item" onClick={() => setSection("strategies")}>
        <span>🧠 Strategies</span>
        <span className="more-hint">Every playbook, its record, on/off switches</span>
      </button>
      <button className="more-item" onClick={() => setSection("telegram")}>
        <span>📨 Phone alerts</span>
        <span className="more-hint">Telegram health & the mute switch</span>
      </button>
      <button className="more-item" onClick={() => setSection("help")}>
        <span>❓ How this works</span>
        <span className="more-hint">The daily loop, in one minute</span>
      </button>
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


function HowItWorks() {
  const steps = [
    ["1. Money in", "Add money to the wallet on Today (practice money while in demo). That's the only money the bot can ever use."],
    ["2. Ideas come to you", "During market hours the bot scans your stocks. When a setup passes every rule, a green card appears on Today (and on Telegram) with the buy price, the sell-if-falls price, and the profit goal."],
    ["3. You decide", "Tap ⚡ to have the bot place the order, tap 'I bought it myself' if you did it in your broker app, or Ignore it. Nothing happens without you."],
    ["4. It watches for you", "Every position gets a live bar from sell-level to goal. You get alerts: near your stop, goal hit, stop raised, 'this trade stopped making sense' — each says what to do."],
    ["5. You exit, it books", "Tap ⚡ to sell via the bot or confirm you sold yourself. Money returns to the wallet with the profit/loss, and the Journal keeps the record."],
  ];
  return (
    <div className="howit">
      {steps.map(([t, b]) => (
        <div key={t} className="howit-step">
          <strong>{t}</strong>
          <p>{b}</p>
        </div>
      ))}
      <p className="more-foot">
        Lost anywhere? The bottom bar always brings you back: Today = act, Markets = browse,
        Journal = history, More = everything else.
      </p>
    </div>
  );
}
