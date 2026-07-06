import { useEffect, useState } from "react";
import "./index.css";
import "./app.css";
import { api } from "./api";
import { AlertBanner } from "./components/AlertBanner";
import { HistoryTable } from "./components/HistoryTable";
import { IdeaCard } from "./components/IdeaCard";
import { PositionCard } from "./components/PositionCard";
import { RegimeCard } from "./components/RegimeCard";
import { StatTile } from "./components/StatTile";
import type { HistoryRow } from "./types";
import { useLive } from "./useLive";

function App() {
  const { snapshot, connected, alerts, dismissAlert } = useLive();
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [showHistory, setShowHistory] = useState(false);

  useEffect(() => {
    api.history(100).then((r) => setHistory(r.rows)).catch(() => {});
  }, [snapshot?.day_stats.closed_today, snapshot?.day_stats.realised_pnl]);

  const togglePause = async () => {
    if (!snapshot) return;
    setPauseBusy(true);
    try {
      await (snapshot.paused ? api.resume() : api.pause());
    } finally {
      setPauseBusy(false);
    }
  };

  const pnlCurve = history
    .filter((r) => r.status === "CLOSED")
    .slice()
    .reverse()
    .reduce<number[]>((acc, r) => {
      const prev = acc.length ? acc[acc.length - 1] : 0;
      acc.push(prev + (r.pnl ?? 0));
      return acc;
    }, []);

  if (!snapshot) {
    return (
      <div className="loading-screen">
        <p>{connected ? "Loading…" : "Connecting to engine…"}</p>
      </div>
    );
  }

  return (
    <>
      <AlertBanner alerts={alerts} onDismiss={dismissAlert} />
      <header className="app-header">
        <div className="header-top">
          <h1>Trading Assistant</h1>
          <span className={`conn-dot ${connected ? "conn-on" : "conn-off"}`} title={connected ? "live" : "reconnecting"} />
        </div>
        <div className="header-meta">
          <span className={`mode-badge ${snapshot.mode === "LIVE" ? "good" : "warning"}`}>{snapshot.mode}</span>
          <button className={`btn btn-ghost pause-btn`} disabled={pauseBusy} onClick={togglePause}>
            {snapshot.paused ? "▶ Resume" : "⏸ Pause"}
          </button>
        </div>
      </header>

      <main className="app-main">
        <RegimeCard ctx={snapshot.context} />

        <div className="stat-row">
          <StatTile
            label="Today's PnL"
            value={`₹${snapshot.day_stats.realised_pnl.toLocaleString("en-IN")}`}
            valueColor={snapshot.day_stats.realised_pnl >= 0 ? "var(--good)" : "var(--critical)"}
            trend={pnlCurve.length >= 2 ? pnlCurve : undefined}
          />
          <StatTile label="Closed today" value={snapshot.day_stats.closed_today} />
          <StatTile label="Open positions" value={snapshot.positions.length} />
        </div>

        <section className="section">
          <h2>Pending ideas {snapshot.pending.length > 0 && `(${snapshot.pending.length})`}</h2>
          {snapshot.pending.length === 0 ? (
            <p className="text-muted empty-note">No pending ideas right now.</p>
          ) : (
            snapshot.pending.map((idea) => <IdeaCard key={idea.idea_id} idea={idea} />)
          )}
        </section>

        <section className="section">
          <h2>Open positions {snapshot.positions.length > 0 && `(${snapshot.positions.length})`}</h2>
          {snapshot.positions.length === 0 ? (
            <p className="text-muted empty-note">Nothing open — flat.</p>
          ) : (
            snapshot.positions.map((idea) => <PositionCard key={idea.idea_id} idea={idea} />)
          )}
        </section>

        <section className="section">
          <button className="btn btn-ghost history-toggle" onClick={() => setShowHistory((s) => !s)}>
            {showHistory ? "Hide" : "Show"} trade history
          </button>
          {showHistory && <HistoryTable rows={history} />}
        </section>

        <footer className="app-footer text-muted">
          Watchlist: {snapshot.watchlist.join(", ")}
        </footer>
      </main>
    </>
  );
}

export default App;
