import { marketLine, regimeLabel, rupees } from "../lang";
import type { MarketStatus, Snapshot } from "../types";
import { IdeaCard } from "../components/IdeaCard";
import { IndexStrip } from "../components/IndexStrip";
import { PositionRow } from "../components/PositionRow";
import { WalletCard } from "../components/WalletCard";

/** The home screen. One question, answered top-to-bottom:
 * "Do I need to do anything right now?"
 * 1. New ideas waiting for a yes/no          (act)
 * 2. Positions being watched, alarms first   (watch)
 * 3. How today went                          (review)
 * Market closed? Say when it opens and what will happen. */
export function Today({ snapshot, market }: { snapshot: Snapshot; market: MarketStatus | null }) {
  const m = market ?? snapshot.market;
  const closed = m?.phase !== "open";
  const pnl = snapshot.day_stats.realised_pnl;
  const nothingOn = snapshot.pending.length === 0 && snapshot.positions.length === 0;

  // alarms (stop/target touched) float above quiet positions
  const positions = [...snapshot.positions].sort((a, b) => {
    const urgent = (i: typeof a) => (i.ltp <= i.stop || i.ltp >= i.target ? 0 : 1);
    return urgent(a) - urgent(b);
  });

  return (
    <div className="today">
      <WalletCard wallet={snapshot.wallet} paper={snapshot.execute.paper} />
      <IndexStrip />
      {closed && nothingOn && (
        <div className="closed-hero">
          <p className="closed-title">{marketLine(m)}</p>
          <p className="closed-sub">
            When it opens, the bot scans your {snapshot.watchlist.length} stocks and sends any
            trade idea here and to Telegram. You approve, it watches your exit for you.
          </p>
        </div>
      )}

      {snapshot.pending.length > 0 && (
        <section className="today-block">
          <h2 className="today-heading">
            👋 Needs your decision <span className="count-pill">{snapshot.pending.length}</span>
          </h2>
          {snapshot.pending.map((idea) => (
            <IdeaCard key={idea.idea_id} idea={idea} execute={snapshot.execute} />
          ))}
        </section>
      )}

      {positions.length > 0 && (
        <section className="today-block">
          <h2 className="today-heading">
            👁 Being watched for you <span className="count-pill">{positions.length}</span>
          </h2>
          {positions.map((idea) => (
            <PositionRow key={idea.idea_id} idea={idea} execute={snapshot.execute} />
          ))}
        </section>
      )}

      {!closed && nothingOn && (
        <div className="closed-hero">
          <p className="closed-title">All quiet 🧘</p>
          <p className="closed-sub">
            The bot is scanning. When a setup passes every check, the idea appears here — most
            show up between 9:20 and 14:30.
          </p>
        </div>
      )}

      <section className="today-block">
        <h2 className="today-heading">Today so far</h2>
        <div className="today-summary">
          <div>
            <span className="sum-label">Booked profit/loss</span>
            <strong className={pnl >= 0 ? "good" : "critical"}>
              {pnl >= 0 ? "+" : ""}
              {rupees(pnl, 0)}
            </strong>
          </div>
          <div>
            <span className="sum-label">Trades closed</span>
            <strong>{snapshot.day_stats.closed_today}</strong>
          </div>
        </div>
        {regimeLabel(snapshot.context) && <p className="mood-line">{regimeLabel(snapshot.context)}</p>}
      </section>
    </div>
  );
}
