import { useEffect, useState } from "react";
import { api, downloadTaxCsv, downloadJournalBackup } from "../api";
import { rupees } from "../lang";
import { toast } from "../toast";
import type { TaxReport as TaxReportT } from "../types";

/** Capital-gains working sheet — per financial year, STCG / LTCG (delivery)
 * and intraday split, net of costs.py charges. Export to CSV for your CA. */
export function TaxReport() {
  const [rep, setRep] = useState<TaxReportT | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.taxReport().then((r) => { setRep(r); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-muted empty-note">Computing capital gains…</p>;
  if (!rep || rep.years.length === 0) {
    return <p className="text-muted empty-note">No closed delivery trades yet — the tax sheet fills in after your first booked exit.</p>;
  }

  const row = (label: string, b: { trades: number; gross: number; charges: number; net: number }) =>
    b.trades > 0 && (
      <div className="tax-line" key={label}>
        <span className="tax-cat">{label}</span>
        <span className="mono text-muted">{b.trades} trades</span>
        <span className="mono text-muted">− {rupees(b.charges, 0)} cost</span>
        <strong className={`mono ${b.net >= 0 ? "good" : "critical"}`}>
          {b.net >= 0 ? "+" : "−"}{rupees(Math.abs(b.net), 0)}
        </strong>
      </div>
    );

  return (
    <div className="tax-report">
      {rep.years.map((y) => (
        <section className="tax-year ana-block" key={y.fy}>
          <div className="tax-head">
            <h3>{y.fy}</h3>
            <button className="link-btn" onClick={() => downloadTaxCsv(y.fy).catch(() => toast("danger", "Export failed"))}>
              ↓ CSV
            </button>
          </div>
          {row("STCG (≤12mo)", y.stcg)}
          {row("LTCG (>12mo)", y.ltcg)}
          {row("Intraday (speculative)", y.intraday)}
          <div className="tax-total">
            <span>Net after all charges</span>
            <strong className={`mono ${y.total_net >= 0 ? "good" : "critical"}`}>
              {y.total_net >= 0 ? "+" : "−"}{rupees(Math.abs(y.total_net), 0)}
            </strong>
          </div>
        </section>
      ))}
      <div className="tax-actions">
        <button className="btn-ghost" onClick={() => downloadTaxCsv().catch(() => toast("danger", "Export failed"))}>
          ↓ Full capital-gains CSV
        </button>
        <button className="btn-ghost" onClick={() => downloadJournalBackup().catch(() => toast("danger", "Backup failed"))}>
          ↓ Backup journal DB
        </button>
      </div>
      <p className="more-foot">
        Working sheet for your CA — not tax advice. STCG/LTCG use the {">"}12-month listed-equity
        rule; intraday is speculative business income, shown separately. Charges from the
        Groww cost model.
      </p>
    </div>
  );
}
