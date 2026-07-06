import { useEffect, useRef, useState } from "react";
import { health, login } from "./api";

type EngineState = "checking" | "waking" | "demo" | "live" | "down";

const ENGINE_LABEL: Record<EngineState, string> = {
  checking: "Checking engine…",
  waking: "Waking the engine (free-tier cold start, ~1 min)…",
  demo: "Engine online — DEMO DATA (synthetic feed)",
  live: "Engine online — LIVE market data",
  down: "Engine unreachable — try again in a minute",
};

export function Landing({ onLogin }: { onLogin: () => void }) {
  const [engine, setEngine] = useState<EngineState>("checking");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const tries = useRef(0);

  useEffect(() => {
    let cancelled = false;
    const probe = async () => {
      while (!cancelled && tries.current < 30) {
        try {
          const h = await health();
          if (cancelled) return;
          setEngine(h.mode === "LIVE" ? "live" : "demo");
          return;
        } catch {
          tries.current += 1;
          if (cancelled) return;
          setEngine(tries.current > 12 ? "down" : "waking");
          await new Promise((r) => setTimeout(r, 5000));
        }
      }
    };
    probe();
    return () => {
      cancelled = true;
    };
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await login(username.trim(), password);
      onLogin();
    } catch (err) {
      const msg = String(err);
      setError(
        msg.includes("429")
          ? "Too many attempts — wait a few minutes."
          : msg.includes("401") || msg.includes("unauthorized")
            ? "Wrong username or password."
            : "Can't reach the engine yet — wait for it to wake, then retry.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="landing">
      <div className="landing-inner">
        <header className="landing-hero">
          <div className="landing-logo" aria-hidden>
            📈
          </div>
          <h1>Trading Assistant</h1>
          <p className="landing-tag">
            Your personal NSE trading bot — it finds the trades, watches your stops, and tells
            you when to sell. You place every order yourself.
          </p>
        </header>

        <ul className="landing-features">
          <li>
            <strong>Rule-based ideas</strong> — opening-range breakouts intraday, a five-strategy
            swing cascade + monthly momentum rotation on daily candles. No AI guesswork.
          </li>
          <li>
            <strong>Exit intelligence</strong> — trailed stops, break-even locks at +1R,
            give-back warnings, and a daily hold / tighten / exit review of every position.
          </li>
          <li>
            <strong>Risk first</strong> — position sizing off your risk %, portfolio heat caps,
            regime and index gates before any idea reaches you.
          </li>
        </ul>

        <form className="login-card" onSubmit={submit}>
          <h2>Sign in</h2>
          <label>
            Username
            <input
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </label>
          {error && <p className="login-error">{error}</p>}
          <button className="btn btn-primary login-btn" disabled={busy} type="submit">
            {busy ? "Signing in…" : "Enter dashboard"}
          </button>
          <p className={`engine-status engine-${engine}`}>
            <span className="engine-dot" aria-hidden />
            {ENGINE_LABEL[engine]}
          </p>
        </form>

        <footer className="landing-foot">
          Signals are hypotheses, not advice. The bot never places orders — every trade is
          yours. Personal tool; not SEBI-registered advice.
        </footer>
      </div>
    </div>
  );
}
