import { useEffect, useState } from "react";
import { api } from "../api";
import { toast } from "../toast";

type Screen = { key: string; label: string; desc: string; expr: string };
type Match = {
  symbol: string; name: string; score: number | null; fundamental_score: number | null;
  pe: number | null; roe_pct: number | null; debt_to_equity: number | null; mom_3m_pct: number | null;
};

/** Rule-based stock screener — pick a prebuilt screen, scan the group, get
 * ranked matches. Deterministic; the expression is shown so it's never a
 * black box. Tap a result to open its chart + fundamentals. */
export function ScreenerPanel({ onOpen }: { onOpen?: (s: string) => void }) {
  const [screens, setScreens] = useState<Screen[]>([]);
  const [group, setGroup] = useState("nifty50");
  const [active, setActive] = useState<string>("");
  const [matches, setMatches] = useState<Match[] | null>(null);
  const [scanned, setScanned] = useState(0);
  const [busy, setBusy] = useState(false);
  const [expr, setExpr] = useState("");

  useEffect(() => {
    api.screens().then((r) => setScreens(r.prebuilt)).catch(() => {});
  }, []);

  const run = async (key?: string, customExpr?: string) => {
    setBusy(true);
    setMatches(null);
    setActive(key ?? "custom");
    try {
      const r = await api.runScreen({ group, key, expr: customExpr });
      setMatches(r.matches);
      setScanned(r.scanned);
      setExpr(r.expr);
    } catch (e) {
      toast("warning", `Screen failed: ${String(e).slice(0, 80)}`);
      setMatches([]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="screener">
      <div className="group-toggle" style={{ alignSelf: "flex-start" }}>
        {(["watchlist", "nifty50", "nasdaq100"] as const).map((g) => (
          <button key={g} className={group === g ? "active" : ""} onClick={() => setGroup(g)}>
            {g === "watchlist" ? "My stocks" : g === "nifty50" ? "NIFTY 50" : "US"}
          </button>
        ))}
      </div>

      <div className="screen-chips">
        {screens.map((s) => (
          <button
            key={s.key}
            className={`screen-chip ${active === s.key ? "active" : ""}`}
            disabled={busy}
            onClick={() => run(s.key)}
            title={s.desc}
          >
            <strong>{s.label}</strong>
            <span>{s.desc}</span>
          </button>
        ))}
      </div>

      {busy && <p className="text-muted empty-note">Scanning {group}… (fundamentals load can take a few seconds)</p>}

      {matches && !busy && (
        <>
          <p className="screen-expr">
            <code>{expr}</code> · scanned {scanned}, matched {matches.length}
          </p>
          {matches.length === 0 ? (
            <p className="text-muted empty-note">No stocks pass this screen right now.</p>
          ) : (
            <div className="stock-list">
              {matches.map((m) => (
                <button key={m.symbol} className="stock-row" onClick={() => onOpen?.(m.symbol)}>
                  <div className="stock-id">
                    <strong>{m.symbol}</strong>
                    <span>
                      {m.roe_pct != null ? `ROE ${m.roe_pct}%` : ""}
                      {m.pe != null ? ` · PE ${m.pe}` : ""}
                      {m.debt_to_equity != null ? ` · D/E ${m.debt_to_equity}` : ""}
                    </span>
                  </div>
                  <div className="stock-quote">
                    {m.score != null && <strong className="pick-score">{m.score}</strong>}
                    {m.mom_3m_pct != null && (
                      <span className={m.mom_3m_pct >= 0 ? "good" : "critical"}>
                        {m.mom_3m_pct >= 0 ? "+" : ""}
                        {m.mom_3m_pct}%
                      </span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </>
      )}
      <p className="more-foot">Rule-based screen over real fundamentals — a filter, not advice.</p>
    </div>
  );
}
