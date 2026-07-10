import { useEffect, useRef, useState } from "react";
import { health, login } from "./api";

type EngineState = "checking" | "waking" | "demo" | "live" | "down" | "outdated";

const ENGINE_LABEL: Record<EngineState, string> = {
  checking: "Checking engine…",
  waking: "Waking the engine — free-tier cold start, about a minute…",
  demo: "Engine online · demo data (safe to explore)",
  live: "Engine online · live NSE data",
  down: "Engine unreachable — try again in a minute",
  outdated: "Server is running an old version — sign-in won't work until it's redeployed",
};

function LogoMark({ size = 56 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <rect x="0" y="0" width="64" height="64" rx="16" fill="var(--logo-bg, #1a1a19)" />
      <line x1="17" y1="14" x2="17" y2="50" stroke="#3987e5" strokeWidth="3" strokeLinecap="round" />
      <rect x="11" y="24" width="12" height="18" rx="3" fill="#3987e5" />
      <line x1="32" y1="10" x2="32" y2="54" stroke="#0ca30c" strokeWidth="3" strokeLinecap="round" />
      <rect x="26" y="18" width="12" height="22" rx="3" fill="#0ca30c" />
      <line x1="47" y1="6" x2="47" y2="44" stroke="#0ca30c" strokeWidth="3" strokeLinecap="round" />
      <rect x="41" y="12" width="12" height="20" rx="3" fill="#0ca30c" />
    </svg>
  );
}

const FEATURES = [
  {
    icon: "🎯",
    title: "Finds the trade",
    body: "Scans your stocks with proven breakout & swing rules — no AI guesswork.",
  },
  {
    icon: "🔔",
    title: "Tells you when to sell",
    body: "Watches every position live: stop alerts, profit goals, daily exit reviews.",
  },
  {
    icon: "🛡️",
    title: "Guards your capital",
    body: "Sizes every idea off your risk limit and blocks trades in bad markets.",
  },
] as const;

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
          // old backend builds answer /api/health but have no `mode` field —
          // and no /api/login either, so say so instead of "online"
          if (!h.mode) {
            setEngine("outdated");
            return;
          }
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
            : msg.includes("404") || msg.includes("405")
              ? "The server is running an old version without sign-in. Redeploy the backend on Render (Manual Deploy → Deploy latest commit), wait ~3 min, then retry."
              : "The engine isn't awake yet — give it a minute, then try again.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="ld">
      <div className="ld-glow" aria-hidden />
      <div className="ld-shell">
        <section className="ld-brand">
          <div className="ld-logo-row">
            <LogoMark />
            <span className="ld-wordmark">Trading Assistant</span>
          </div>
          <h1 className="ld-headline">
            Your personal trading bot.
            <br />
            <span className="ld-accent">You stay in control.</span>
          </h1>
          <p className="ld-sub">
            It finds NSE trades, watches your stops and tells you exactly when to sell —
            you place every order yourself.
          </p>

          <ul className="ld-features">
            {FEATURES.map((f) => (
              <li key={f.title}>
                <span className="ld-fi" aria-hidden>
                  {f.icon}
                </span>
                <div>
                  <strong>{f.title}</strong>
                  <p>{f.body}</p>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="ld-panel">
          <form className="ld-card" onSubmit={submit}>
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
            {error && <p className="ld-error">{error}</p>}
            <button className="ld-btn" disabled={busy} type="submit">
              {busy ? "Signing in…" : "Enter dashboard"}
            </button>
            <p className={`ld-engine ld-engine-${engine}`}>
              <span className="ld-dot" aria-hidden />
              {ENGINE_LABEL[engine]}
            </p>
          </form>
          <p className="ld-foot">
            Signals are hypotheses, not advice. The bot never places orders — every trade is
            yours. Personal tool · not SEBI-registered advice.
          </p>
        </section>
      </div>
    </div>
  );
}
