import { marketLine, regimeLabel, rupees } from "../lang";
import type { MarketStatus, Snapshot } from "../types";
import { IdeaCard } from "../components/IdeaCard";
import { RiskStrip } from "../components/RiskStrip";
import { StatStrip } from "../components/StatStrip";
import { IndexStrip } from "../components/IndexStrip";
import { PositionRow } from "../components/PositionRow";
import { WalletCard } from "../components/WalletCard";

/** The home screen. One question, answered top-to-bottom:
 * "Do I need to do anything right now?"
 * 1. New ideas waiting for a yes/no          (act)
 * 2. Positions being watched, alarms first   (watch)
 * 3. How today went                          (review)
 * Market closed? Say when it opens and what will happen. */
export function Today({ snapshot, market, onBrowse }: { snapshot: Snapshot; market: MarketStatus | null; onBrowse?: () => void }) {
  const m = market ?? snapshot.market;
  const exec = snapshot.execute ?? { enabled: false, paper: snapshot.mode !== "LIVE" };
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
      <div className="today-top">
        <StatStrip snapshot={snapshot} />
        <RiskStrip snapshot={snapshot} />
      </div>
      <aside className="today-rail">
        {snapshot.wallet && <WalletCard wallet={snapshot.wallet} paper={exec.paper} />}
        <IndexStrip />
        <section className="today-block rail-summary">
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
      </aside>

      <div className="today-main">
      {closed && nothingOn && (
        <div className="closed-hero">
          <p className="closed-title">{marketLine(m)}</p>
          <p className="closed-sub">
            When it opens, the bot scans your {snapshot.watchlist.length} stocks and sends any
            trade idea here and to Telegram. You approve, it watches your exit for you.
          </p>
          {onBrowse && (
            <button className="btn-big btn-ignore hero-cta" onClick={onBrowse}>
              Browse the markets meanwhile →
            </button>
          )}
        </div>
      )}

      {snapshot.pending.length > 0 && (
        <section className="today-block">
          <h2 className="today-heading">
            👋 Needs your decision <span className="count-pill">{snapshot.pending.length}</span>
          </h2>
          {snapshot.pending.map((idea) => (
            <IdeaCard key={idea.idea_id} idea={idea} execute={exec} />
          ))}
        </section>
      )}

      {positions.length > 0 && (
        <section className="today-block">
          <h2 className="today-heading">
            👁 Being watched for you <span className="count-pill">{positions.length}</span>
          </h2>
          {positions.map((idea) => (
            <PositionRow key={idea.idea_id} idea={idea} execute={exec} />
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
          {onBrowse && (
            <button className="btn-big btn-ignore hero-cta" onClick={onBrowse}>
              Browse the markets meanwhile →
            </button>
          )}
        </div>
      )}

      </div>
    </div>
  );
}
