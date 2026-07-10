import { useMemo, useState } from "react";
import { downloadHistoryCsv } from "../api";
import { rupees } from "../lang";
import { toast } from "../toast";
import type { HistoryRow } from "../types";

const FILTERS = ["All", "Wins", "Losses", "Open", "Skipped"] as const;
type Filter = (typeof FILTERS)[number];

/** Your trade record, readable at a glance: filter pills, one card per
 * trade in plain words, CSV export for tax time. */
export function Journal({ rows }: { rows: HistoryRow[] }) {
  const [filter, setFilter] = useState<Filter>("All");

  const filtered = useMemo(() => {
    switch (filter) {
      case "Wins":
        return rows.filter((r) => r.status === "CLOSED" && (r.pnl ?? 0) > 0);
      case "Losses":
        return rows.filter((r) => r.status === "CLOSED" && (r.pnl ?? 0) <= 0);
      case "Open":
        return rows.filter((r) => r.status === "ACTIVE");
      case "Skipped":
        return rows.filter((r) => r.status === "SKIPPED" || r.status === "EXPIRED");
      default:
        return rows;
    }
  }, [rows, filter]);

  const closed = rows.filter((r) => r.status === "CLOSED");
  const total = closed.reduce((s, r) => s + (r.pnl ?? 0), 0);
  const wins = closed.filter((r) => (r.pnl ?? 0) > 0).length;

  return (
    <div className="journal">
      <div className="journal-stats">
        <div>
          <span className="sum-label">All-time booked</span>
          <strong className={total >= 0 ? "good" : "critical"}>
            {total >= 0 ? "+" : ""}
            {rupees(total, 0)}
          </strong>
        </div>
        <div>
          <span className="sum-label">Closed trades</span>
          <strong>{closed.length}</strong>
        </div>
        <div>
          <span className="sum-label">Winners</span>
          <strong>{closed.length ? Math.round((100 * wins) / closed.length) : 0}%</strong>
        </div>
      </div>

      <div className="filter-row">
        {FILTERS.map((f) => (
          <button key={f} className={`filter-pill ${filter === f ? "active" : ""}`} onClick={() => setFilter(f)}>
            {f}
          </button>
        ))}
        <button
          className="filter-pill"
          onClick={() => downloadHistoryCsv().catch(() => toast("danger", "Export failed — try again."))}
        >
          ⬇ CSV
        </button>
      </div>

      {filtered.length === 0 ? (
        <p className="text-muted empty-note">Nothing here yet.</p>
      ) : (
        filtered.map((r) => {
          const closedRow = r.status === "CLOSED";
          const won = (r.pnl ?? 0) > 0;
          return (
            <div key={r.id} className="journal-row">
              <div className="journal-main">
                <strong>{r.symbol}</strong>
                <span className="journal-date">{r.created_at.slice(0, 10)}</span>
              </div>
              <div className="journal-detail">
                {closedRow ? (
                  <>
                    <span>
                      {rupees(r.fill_price, 0)} → {rupees(r.exit_price, 0)} × {r.fill_qty}
                    </span>
                    <strong className={won ? "good" : "critical"}>
                      {won ? "+" : ""}
                      {rupees(r.pnl ?? 0, 0)}
                    </strong>
                  </>
                ) : (
                  <span className="text-muted">
                    {r.status === "ACTIVE"
                      ? `holding ${r.fill_qty} @ ${rupees(r.fill_price, 0)}`
                      : r.status === "SKIPPED"
                        ? "you ignored this idea"
                        : r.status === "EXPIRED"
                          ? "idea lapsed untaken"
                          : "waiting for your decision"}
                  </span>
                )}
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}
