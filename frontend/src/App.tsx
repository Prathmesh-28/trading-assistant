import { useEffect, useState } from "react";
import "./index.css";
import "./app.css";
import { API_BASE, api, clearToken, getToken } from "./api";
import { Landing } from "./Landing";
import { AlertBanner } from "./components/AlertBanner";
import { BacktestPanel } from "./components/BacktestPanel";
import { ChartPanel } from "./components/ChartPanel";
import { HistoryTable } from "./components/HistoryTable";
import { IdeaCard } from "./components/IdeaCard";
import { MarketStatusBadge } from "./components/MarketStatusBadge";
import { PositionCard } from "./components/PositionCard";
import { RegimeCard } from "./components/RegimeCard";
import { StatTile } from "./components/StatTile";
import { Watchlist } from "./components/Watchlist";
import type { HistoryRow } from "./types";
import { useLive } from "./useLive";

type Tab = "trade" | "backtest" | "history";

function App() {
  const [authed, setAuthed] = useState(() => Boolean(getToken()));
  if (!authed) {
    return <Landing onLogin={() => setAuthed(true)} />;
  }
  return <Dashboard onLogout={() => { clearToken(); setAuthed(false); }} />;
}

function Dashboard({ onLogout }: { onLogout: () => void }) {
  const { snapshot, connected, alerts, dismissAlert, prices, market } = useLive();
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [pauseBusy, setPauseBusy] = useState(false);
  const [slowConnect, setSlowConnect] = useState(false);
  const [tab, setTab] = useState<Tab>("trade");
  const [selected, setSelected] = useState("");

  useEffect(() => {
    if (snapshot) return;
    const t = setTimeout(() => setSlowConnect(true), 6000);
    return () => clearTimeout(t);
  }, [snapshot]);

  useEffect(() => {
    api.history(100).then((r) => setHistory(r.rows)).catch(() => {});
  }, [snapshot?.day_stats.closed_today, snapshot?.day_stats.realised_pnl]);

  // default chart symbol: first open position, else first pending idea, else first watchlist entry
  useEffect(() => {
    if (selected || !snapshot) return;
    setSelected(snapshot.positions[0]?.symbol ?? snapshot.pending[0]?.symbol ?? snapshot.watchlist[0] ?? "");
  }, [snapshot, selected]);

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
        <div className="loading-box">
          <p>{connected ? "Loading…" : "Connecting to engine…"}</p>
          {slowConnect && (
            <p className="loading-hint">
              Can't reach the backend at <code>{API_BASE}</code>.
              {API_BASE.includes("localhost")
                ? " This deployed dashboard is pointing at localhost — set the VITE_API_URL (and VITE_WS_URL) environment variables in Vercel to your backend's public URL and redeploy."
                : " Check that the backend is running and that its CORS_ORIGINS includes this site's URL."}
            </p>
          )}
        </div>
      </div>
    );
  }

  return (
    <>
      <AlertBanner alerts={alerts} onDismiss={dismissAlert} />
      <header className="app-header">
        <div className="header-top">
          <div className="header-brand">
            <h1>Trading Assistant</h1>
            <MarketStatusBadge market={market ?? snapshot.market} />
          </div>
          <div className="header-meta">
            <span className={`mode-badge ${snapshot.mode === "LIVE" ? "good" : "warning"}`}>
              {snapshot.mode === "LIVE" ? "LIVE" : "DEMO"}
            </span>
            <button className="btn btn-ghost pause-btn" disabled={pauseBusy} onClick={togglePause}>
              {snapshot.paused ? "▶ Resume" : "⏸ Pause"}
            </button>
            <button className="btn btn-ghost pause-btn" onClick={onLogout} title="Sign out">
              ⎋
            </button>
            <span className={`conn-dot ${connected ? "conn-on" : "conn-off"}`} title={connected ? "live" : "reconnecting"} />
          </div>
        </div>
        {snapshot.mode !== "LIVE" && (
          <p className="demo-banner">
            DEMO DATA — synthetic random-walk prices for trying the app. Nothing here is a real
            market quote. Add Groww credentials on the server to go live.
          </p>
        )}
        <nav className="tab-bar">
          {(
            [
              ["trade", "Trade"],
              ["backtest", "Backtest"],
              ["history", "History"],
            ] as [Tab, string][]
          ).map(([key, label]) => (
            <button key={key} className={`tab-btn ${tab === key ? "active" : ""}`} onClick={() => setTab(key)}>
              {label}
            </button>
          ))}
        </nav>
      </header>

      <main className="app-main">
        {tab === "trade" && (
          <div className="trade-grid">
            <div className="pane-chart">
              {selected && <ChartPanel symbol={selected} snapshot={snapshot} prices={prices} />}
            </div>

            <aside className="pane-watchlist">
              <Watchlist snapshot={snapshot} prices={prices} selected={selected} onSelect={setSelected} />
            </aside>

            <div className="pane-rail">
              <RegimeCard ctx={snapshot.context} />
              <div className="stat-row">
                <StatTile
                  label="Today's PnL"
                  value={`₹${snapshot.day_stats.realised_pnl.toLocaleString("en-IN")}`}
                  valueColor={snapshot.day_stats.realised_pnl >= 0 ? "var(--good)" : "var(--critical)"}
                  trend={pnlCurve.length >= 2 ? pnlCurve : undefined}
                />
                <StatTile label="Closed today" value={snapshot.day_stats.closed_today} />
                <StatTile label="Open" value={snapshot.positions.length} />
              </div>

              <section className="section">
                <h2>Pending ideas {snapshot.pending.length > 0 && `(${snapshot.pending.length})`}</h2>
                {snapshot.pending.length === 0 ? (
                  <p className="text-muted empty-note">No pending ideas right now.</p>
                ) : (
                  snapshot.pending.map((idea) => (
                    <div key={idea.idea_id} onClick={() => setSelected(idea.symbol)}>
                      <IdeaCard idea={idea} />
                    </div>
                  ))
                )}
              </section>

              <section className="section">
                <h2>Open positions {snapshot.positions.length > 0 && `(${snapshot.positions.length})`}</h2>
                {snapshot.positions.length === 0 ? (
                  <p className="text-muted empty-note">Nothing open — flat.</p>
                ) : (
                  snapshot.positions.map((idea) => (
                    <div key={idea.idea_id} onClick={() => setSelected(idea.symbol)}>
                      <PositionCard idea={idea} />
                    </div>
                  ))
                )}
              </section>
            </div>
          </div>
        )}

        {tab === "backtest" && <BacktestPanel snapshot={snapshot} />}

        {tab === "history" && (
          <section className="section">
            <h2>Trade history</h2>
            {history.length === 0 ? (
              <p className="text-muted empty-note">No journaled trades yet.</p>
            ) : (
              <HistoryTable rows={history} />
            )}
          </section>
        )}

        <footer className="app-footer text-muted">
          Ideas only — you place every trade yourself. Watchlist: {snapshot.watchlist.join(", ")}
        </footer>
      </main>
    </>
  );
}

export default App;
