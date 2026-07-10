import { useState } from "react";

const STEPS = [
  {
    icon: "👋",
    title: "Welcome! Here's the 30-second tour",
    body: "This bot finds NSE trades, watches your exits, and can even place orders when you tap. You approve everything — it never acts alone.",
  },
  {
    icon: "🏠",
    title: "Today — start here every day",
    body: "Anything needing your decision appears at the top. Below it: positions being watched with a bar showing how close price is to your sell level or profit goal.",
  },
  {
    icon: "📈",
    title: "Markets — browse & buy anything",
    body: "NIFTY, SENSEX, all NIFTY 50 stocks with live prices. Tap a stock for its chart, and buy with your wallet right from there.",
  },
  {
    icon: "💰",
    title: "Your wallet is the money",
    body: "Add money on Today (practice money in demo). Every buy uses it, every sell returns it with profit or loss. The bot can never spend more than what's in it.",
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
