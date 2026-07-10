import { useState } from "react";

const STEPS = [
  {
    icon: "👋",
    title: "Welcome! Here's the 30-second tour",
    body: "This bot finds NSE trades, watches your exits, and can even place orders when you tap. You approve everything — it never acts alone.",
  },
  {
    icon: "🏠",
    title: "Home — start here every day",
    body: "Your wallet on top, then anything needing a decision, then positions being watched — each with a bar showing how close price is to your sell level or profit goal.",
  },
  {
    icon: "📈",
    title: "Markets — browse & buy anything",
    body: "NIFTY, SENSEX, all NIFTY 50 and US stocks. Tap any stock for its chart, score, full financials (who owns it, quarterly results), and a buy ticket.",
  },
  {
    icon: "🔎",
    title: "Screener — find your next stock",
    body: "Ten ready-made lenses — Quality, Value, Coffee Can, Promoter skin-in-game… The engine scans real fundamentals and ranks what passes. Tap a match to open it.",
  },
  {
    icon: "💰",
    title: "Your wallet is the money",
    body: "Add money on Home (practice money in demo). Every buy uses it, every sell returns it with profit or loss. The bot can never spend more than what's in it.",
  },
] as const;

const KEY = "ta_tour_done";

export function Welcome() {
  const [step, setStep] = useState(() => (localStorage.getItem(KEY) ? -1 : 0));
  if (step < 0) return null;
  const s = STEPS[step];
  const last = step === STEPS.length - 1;

  const finish = () => {
    localStorage.setItem(KEY, "1");
    setStep(-1);
  };

  return (
    <div className="tour-scrim" role="dialog" aria-label="Welcome tour">
      <div className="tour-card">
        <div className="tour-icon" aria-hidden>{s.icon}</div>
        <h2>{s.title}</h2>
        <p>{s.body}</p>
        <div className="tour-dots" aria-hidden>
          {STEPS.map((_, i) => (
            <span key={i} className={i === step ? "on" : ""} />
          ))}
        </div>
        <button className="btn-big btn-buy" onClick={() => (last ? finish() : setStep(step + 1))}>
          {last ? "Let's go" : "Next"}
        </button>
        {!last && (
          <button className="tour-skip" onClick={finish}>
            Skip tour
          </button>
        )}
      </div>
    </div>
  );
}
