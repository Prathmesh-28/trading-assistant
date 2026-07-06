import type { HistoryRow } from "../types";

export function HistoryTable({ rows }: { rows: HistoryRow[] }) {
  const closed = rows.filter((r) => r.status === "CLOSED");
  if (!closed.length) {
    return <p className="text-muted empty-note">No closed trades yet.</p>;
  }
  return (
    <div className="table-scroll">
      <table className="history-table">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Side</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>PnL</th>
          </tr>
        </thead>
        <tbody>
          {closed.map((r) => (
            <tr key={r.id}>
              <td>{r.symbol}</td>
              <td>{r.side}</td>
              <td className="tabular">₹{r.fill_price.toLocaleString("en-IN")}</td>
              <td className="tabular">₹{r.exit_price.toLocaleString("en-IN")}</td>
              <td className="tabular" style={{ color: (r.pnl ?? 0) >= 0 ? "var(--good)" : "var(--critical)" }}>
                {(r.pnl ?? 0) >= 0 ? "+" : ""}
                {(r.pnl ?? 0).toLocaleString("en-IN")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
