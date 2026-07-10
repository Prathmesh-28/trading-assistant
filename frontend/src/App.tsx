import { useEffect, useState } from "react";
import "./index.css";
import "./app.css";
import { API_BASE, api, clearToken, getToken } from "./api";
import { Landing } from "./Landing";
import { marketLine } from "./lang";
import { onToast } from "./toast";
import { AlertBanner } from "./components/AlertBanner";
import { Markets } from "./views/Markets";
import { Journal } from "./views/Journal";
import { More } from "./views/More";
import { Today } from "./views/Today";
import type { AlertLevel, HistoryRow } from "./types";
import { useLive } from "./useLive";

type Tab = "today" | "chart" | "journal" | "more";

const TABS: { key: Tab; icon: string; label: string }[] = [
  { key: "today", icon: "🏠", label: "Today" },
  { key: "chart", icon: "📈", label: "Markets" },
  { key: "journal", icon: "📒", label: "Journal" },
  { key: "more", icon: "☰", label: "More" },
];

function App() {
  const [authed, setAuthed] = useState(() => Boolean(getToken()));
  if (!authed) {
    return <Landing onLogin={() => setAuthed(true)} />;
  }
  return <Dashboard onLogout={() => { clearToken(); setAuthed(false); }} />;
}

function Dashboard({ onLogout }: { onLogout: () => void }) {
  const { snapshot, connected, alerts, dismissAlert, prices, market } = useLive();
  const [clientAlerts, setClientAlerts] = useState<
    { id: number; level: AlertLevel; message: string; at: number }[]
  >([]);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [tab, setTab] = useState<Tab>("today");
  const [slowConnect, setSlowConnect] = useState(false);

  useEffect(() => {
    let seq = 100000;
    return onToast((t) => {
      const id = ++seq;
      setClientAlerts((prev) => [...prev, { id, at: Date.now(), ...t }]);
      setTimeout(() => setClientAlerts((prev) => prev.filter((a) => a.id !== id)), 6000);
    });
  }, []);

  useEffect(() => {
    if (snapshot) return;
    const t = setTimeout(() => setSlowConnect(true), 6000);
    return () => clearTimeout(t);
  }, [snapshot]);

  useEffect(() => {
    api.history(200).then((r) => setHistory(r.rows)).catch(() => {});
  }, [snapshot?.day_stats.closed_today, snapshot?.day_stats.realised_pnl]);

  if (!snapshot) {
    return (
      <div className="loading-screen">
        <div className="loading-box">
          <p>Connecting to your bot…</p>
          {slowConnect && (
            <p className="loading-hint">
              Can't reach the engine at <code>{API_BASE}</code>.
              {API_BASE.includes("localhost")
                ? " This deployed app points at localhost — set VITE_API_URL in Vercel."
                : " It may be waking from sleep (about a minute) — this page will connect by itself."}
            </p>
          )}
        </div>
      </div>
    );
  }

  const m = market ?? snapshot.market;
  const live = snapshot.mode === "LIVE";

  return (
    <>
      <AlertBanner
        alerts={[...alerts, ...clientAlerts]}
        onDismiss={(id) => {
          dismissAlert(id);
          setClientAlerts((prev) => prev.filter((a) => a.id !== id));
        }}
      />

      <header className="topbar">
        <span className="topbar-title">Trading Assistant</span>
        <span className={`status-pill ${live ? "pill-live" : "pill-demo"}`}>
          <span className={`conn-dot ${connected ? "conn-on" : "conn-off"}`} />
          {live ? "LIVE" : "DEMO"} · {marketLine(m).replace("Market is ", "").replace("Market ", "")}
        </span>
      </header>

      {!connected && (
        <p className="thin-banner thin-danger">Reconnecting… data is paused.</p>
      )}
      {!live && (
        <p className="thin-banner thin-warn">
          Practice mode — these are fake prices so you can explore safely.
        </p>
      )}
      {snapshot.paused && (
        <p className="thin-banner thin-warn">New ideas are paused — resume under More.</p>
      )}

      <main className="app-main">
        {tab === "today" && <Today snapshot={snapshot} market={market} />}
        {tab === "chart" && <Markets snapshot={snapshot} prices={prices} />}
        {tab === "journal" && <Journal rows={history} />}
        {tab === "more" && (
          <More
            snapshot={snapshot}
            onLogout={onLogout}
            paused={snapshot.paused}
            onTogglePause={() => (snapshot.paused ? api.resume() : api.pause())}
          />
        )}
      </main>

      <nav className="bottom-nav" aria-label="Main">
        {TABS.map((t) => (
          <button
            key={t.key}
            className={`nav-btn ${tab === t.key ? "active" : ""}`}
            onClick={() => setTab(t.key)}
            aria-current={tab === t.key ? "page" : undefined}
          >
            <span className="nav-icon" aria-hidden>
              {t.icon}
            </span>
            {t.label}
          </button>
        ))}
      </nav>
    </>
  );
}

export default App;
