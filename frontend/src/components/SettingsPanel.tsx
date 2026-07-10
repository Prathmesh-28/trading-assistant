import { useEffect, useState } from "react";
import { api } from "../api";
import { toast } from "../toast";
import type { TunableSettings } from "../types";

const NUM_FIELDS: { key: keyof TunableSettings; label: string; step: string; hint: string }[] = [
  { key: "capital", label: "Capital (₹)", step: "1000", hint: "Total capital sizing is based on" },
  { key: "risk_per_trade_pct", label: "Risk per trade (%)", step: "0.05", hint: "Of capital, entry-to-stop" },
  { key: "max_position_value", label: "Max position value (₹)", step: "1000", hint: "Cap on any single position" },
  { key: "max_open_positions", label: "Max open positions", step: "1", hint: "Ideas stop when reached" },
  { key: "max_portfolio_risk_pct", label: "Max portfolio heat (%)", step: "0.5", hint: "Total open risk cap" },
];

export function SettingsPanel() {
  const [settings, setSettings] = useState<TunableSettings | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [newSymbol, setNewSymbol] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .getSettings()
      .then((r) => setSettings(r.settings))
      .catch(() => setError("Couldn't load settings — check the connection and retry."));
  }, []);

  if (error) return <p className="text-muted empty-note">{error}</p>;
  if (!settings) return <p className="text-muted empty-note">Loading settings…</p>;

  const save = async (patch: Partial<TunableSettings>) => {
    setBusy(true);
    try {
      const r = await api.patchSettings(patch);
      setSettings(r.settings);
      const errs = Object.entries(r.errors);
      if (errs.length) {
        toast("warning", errs.map(([k, v]) => `${k}: ${v}`).join("; "));
      } else {
        toast("success", "Settings saved — applied immediately, survives restarts.");
      }
    } catch (e) {
      toast("danger", `Save failed: ${String(e).slice(0, 80)}`);
    } finally {
      setBusy(false);
    }
  };

  const removeSymbol = (sym: string) => {
    if (settings.watchlist.length <= 1) {
      toast("warning", "Watchlist needs at least one symbol.");
      return;
    }
    if (!window.confirm(`Remove ${sym} from the watchlist? Open positions in it stay monitored.`)) return;
    save({ watchlist: settings.watchlist.filter((s) => s !== sym) });
  };

  const addSymbol = () => {
    const sym = newSymbol.trim().toUpperCase();
    if (!sym) return;
    if (settings.watchlist.includes(sym)) {
      toast("warning", `${sym} is already on the watchlist.`);
      return;
    }
    setNewSymbol("");
    save({ watchlist: [...settings.watchlist, sym] });
  };

  return (
    <div className="settings-panel">
      <section className="section">
        <h2>Watchlist ({settings.watchlist.length})</h2>
        <p className="text-muted settings-hint">
          Symbols the engine scans for intraday and positional ideas. NSE codes, e.g. RELIANCE.
        </p>
        <div className="chip-row">
          {settings.watchlist.map((sym) => (
            <span key={sym} className="chip">
              {sym}
              <button className="chip-x" onClick={() => removeSymbol(sym)} aria-label={`Remove ${sym}`}>
                ×
              </button>
            </span>
          ))}
        </div>
        <div className="idea-actions">
          <input
            className="num-input"
            placeholder="Add symbol (e.g. WIPRO)"
            value={newSymbol}
            onChange={(e) => setNewSymbol(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && addSymbol()}
            aria-label="Add watchlist symbol"
          />
          <button className="btn btn-ghost" disabled={busy || !newSymbol.trim()} onClick={addSymbol}>
            Add
          </button>
        </div>
      </section>

      <section className="section">
        <h2>Bot trading</h2>
        <label className="toggle-row">
          <div>
            <strong>Bot places orders</strong>
            <p className="text-muted settings-hint" style={{ margin: 0 }}>
              When ON, the ⚡ buttons and the Markets buy ticket send real orders through
              Groww (in demo mode they're always practice fills).
            </p>
          </div>
          <input
            type="checkbox"
            checked={Boolean(settings.execute_enabled)}
            disabled={busy}
            onChange={(e) => save({ execute_enabled: e.target.checked })}
          />
        </label>
      </section>

      <section className="section">
        <h2>Risk</h2>
        {NUM_FIELDS.map((f) => (
          <label key={f.key} className="settings-field">
            <span>
              {f.label} <em className="text-muted">— {f.hint}</em>
            </span>
            <div className="idea-actions">
              <input
                className="num-input"
                type="number"
                step={f.step}
                value={draft[f.key] ?? String(settings[f.key])}
                onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                aria-label={f.label}
              />
              <button
                className="btn btn-ghost"
                disabled={busy || draft[f.key] === undefined || draft[f.key] === String(settings[f.key])}
                onClick={() => {
                  const v = Number(draft[f.key]);
                  if (!Number.isFinite(v)) {
                    toast("warning", `${f.label}: not a number`);
                    return;
                  }
                  save({ [f.key]: v } as Partial<TunableSettings>);
                  setDraft((d) => {
                    const next = { ...d };
                    delete next[f.key];
                    return next;
                  });
                }}
              >
                Save
              </button>
            </div>
          </label>
        ))}
        <p className="text-muted settings-hint">
          Changes apply to the next idea the engine generates — existing positions keep their
          original size and levels.
        </p>
      </section>
    </div>
  );
}
