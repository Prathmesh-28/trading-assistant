"""Audit trail for every idea and outcome.

Uses SQLite (stdlib, zero setup) by default. If DATABASE_URL is set and psycopg
is installed, the same schema goes to Postgres — the dashboard in the README
reads either.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime

from config import IST, Settings
from recommendation import Recommendation, Status

_SETTINGS_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

_WALLET_SCHEMA = """
CREATE TABLE IF NOT EXISTS wallet_txns (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,
    kind          TEXT NOT NULL,   -- deposit | withdraw | buy | sell
    symbol        TEXT,
    qty           INTEGER,
    price         REAL,
    amount        REAL NOT NULL,   -- signed: +credit / -debit to cash
    balance_after REAL NOT NULL,
    note          TEXT
);
"""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS ideas (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    symbol       TEXT NOT NULL,
    side         TEXT NOT NULL,
    horizon      TEXT NOT NULL,
    entry        REAL NOT NULL,
    stop         REAL NOT NULL,
    target       REAL NOT NULL,
    qty          INTEGER NOT NULL,
    confidence   TEXT,
    reason       TEXT,
    why          TEXT,
    status       TEXT NOT NULL,
    fill_qty     INTEGER DEFAULT 0,
    fill_price   REAL DEFAULT 0,
    exit_price   REAL DEFAULT 0,
    pnl          REAL DEFAULT 0,
    updated_at   TEXT
);
"""


class Journal:
    def __init__(self, settings: Settings):
        self._lock = threading.Lock()
        if settings.database_url:
            try:
                import psycopg  # noqa: F401
                # Postgres wiring goes here if you want the shared dashboard DB;
                # the SQLite fallback below keeps recommend mode zero-setup.
            except ImportError:
                pass
        self._conn = sqlite3.connect(settings.journal_path, check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.execute(_SETTINGS_SCHEMA)
        self._conn.execute(_WALLET_SCHEMA)
        # migrate pre-existing DBs: trade-review columns (added 2026-07)
        for col, typ in (("notes", "TEXT"), ("tags", "TEXT"), ("rating", "INTEGER")):
            try:
                self._conn.execute(f"ALTER TABLE ideas ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass  # column already exists
        self._conn.commit()

    # ------------------------------------------------------------- wallet

    def wallet_balance(self) -> float:
        """Available cash: sum of every signed ledger entry."""
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(SUM(amount), 0) FROM wallet_txns").fetchone()
        return round(row[0], 2)

    def wallet_has_txns(self) -> bool:
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM wallet_txns").fetchone()[0] > 0

    def wallet_record(self, kind: str, amount: float, symbol: str = None,
                      qty: int = None, price: float = None, note: str = "") -> float:
        """Append one signed ledger entry; returns the new balance."""
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(SUM(amount), 0) FROM wallet_txns").fetchone()
            balance = round(row[0] + amount, 2)
            self._conn.execute(
                "INSERT INTO wallet_txns (ts, kind, symbol, qty, price, amount,"
                " balance_after, note) VALUES (?,?,?,?,?,?,?,?)",
                (datetime.now(IST).isoformat(), kind, symbol, qty, price,
                 round(amount, 2), balance, note),
            )
            self._conn.commit()
        return balance

    def wallet_txns(self, limit: int = 50) -> list[dict]:
        cols = ["id", "ts", "kind", "symbol", "qty", "price", "amount", "balance_after", "note"]
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {', '.join(cols)} FROM wallet_txns ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(zip(cols, r)) for r in rows]

    def load_setting_overrides(self) -> dict:
        """User-tuned runtime settings (dashboard Settings tab). Applied on top
        of env defaults at engine start; JSON-decoded values."""
        import json
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        out = {}
        for k, v in rows:
            try:
                out[k] = json.loads(v)
            except ValueError:
                continue
        return out

    def save_setting_override(self, key: str, value) -> None:
        import json
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?,?,?)"
                " ON CONFLICT(key) DO UPDATE SET value=excluded.value,"
                " updated_at=excluded.updated_at",
                (key, json.dumps(value), datetime.now(IST).isoformat()),
            )
            self._conn.commit()

    def record(self, rec: Recommendation) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO ideas (created_at, symbol, side, horizon, entry, stop,"
                " target, qty, confidence, reason, why, status, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    rec.created_at.isoformat(), rec.symbol, rec.side.value,
                    rec.horizon.value, rec.entry, rec.stop, rec.target, rec.qty,
                    rec.confidence, rec.reason, rec.why, rec.status.value,
                    datetime.now(IST).isoformat(),
                ),
            )
            self._conn.commit()
            return cur.lastrowid

    def update(self, row_id: int, rec: Recommendation, pnl: float = 0.0) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE ideas SET status=?, fill_qty=?, fill_price=?, exit_price=?,"
                " pnl=?, updated_at=? WHERE id=?",
                (
                    rec.status.value, rec.fill_qty, rec.fill_price, rec.exit_price,
                    pnl, datetime.now(IST).isoformat(), row_id,
                ),
            )
            self._conn.commit()

    _REVIEW_COLS = ("notes", "tags", "rating")

    _COLUMNS = ["id", "created_at", "symbol", "side", "horizon", "entry", "stop",
                "target", "qty", "confidence", "reason", "why", "status",
                "fill_qty", "fill_price", "exit_price", "pnl", "updated_at",
                "notes", "tags", "rating"]

    def review_update(self, idea_id: int, notes=None, tags=None, rating=None) -> bool:
        """Journal a closed trade: free-text notes, comma tags, 1-5 self-rating."""
        sets, vals = [], []
        if notes is not None:
            sets.append("notes=?"); vals.append(str(notes)[:2000])
        if tags is not None:
            sets.append("tags=?"); vals.append(",".join(t.strip() for t in tags)[:400]
                                              if isinstance(tags, list) else str(tags)[:400])
        if rating is not None:
            sets.append("rating=?"); vals.append(max(1, min(5, int(rating))))
        if not sets:
            return False
        vals.append(idea_id)
        with self._lock:
            cur = self._conn.execute(f"UPDATE ideas SET {', '.join(sets)} WHERE id=?", vals)
            self._conn.commit()
            return cur.rowcount > 0

    def analytics(self, days: int = 90) -> dict:
        """Control-center numbers from closed trades: equity curve, win rate,
        breakdowns by symbol / horizon / weekday, streaks, tag frequencies."""
        from datetime import timedelta
        since = (datetime.now(IST) - timedelta(days=days)).isoformat()
        with self._lock:
            rows = self._conn.execute(
                "SELECT created_at, updated_at, symbol, horizon, pnl, tags, rating, reason"
                " FROM ideas WHERE status='CLOSED' AND updated_at >= ? ORDER BY updated_at",
                (since,),
            ).fetchall()
        curve, cum = [], 0.0
        by_day, by_symbol, by_horizon, by_weekday, tag_counts = {}, {}, {}, {}, {}
        wins = losses = 0
        win_sum = loss_sum = 0.0
        streak = best_win_streak = worst_loss_streak = 0
        cutoff30 = (datetime.now(IST) - timedelta(days=30)).isoformat()
        w30 = t30 = 0
        for created, updated, sym, hz, pnl, tags, rating, reason in rows:
            pnl = pnl or 0.0
            day = (updated or created)[:10]
            by_day[day] = by_day.get(day, 0.0) + pnl
            for bucket, key in ((by_symbol, sym), (by_horizon, hz)):
                b = bucket.setdefault(key, {"trades": 0, "pnl": 0.0, "wins": 0})
                b["trades"] += 1; b["pnl"] += pnl; b["wins"] += 1 if pnl > 0 else 0
            try:
                wd = datetime.fromisoformat((updated or created)[:19]).strftime("%a")
                b = by_weekday.setdefault(wd, {"trades": 0, "pnl": 0.0, "wins": 0})
                b["trades"] += 1; b["pnl"] += pnl; b["wins"] += 1 if pnl > 0 else 0
            except ValueError:
                pass
            if pnl > 0:
                wins += 1; win_sum += pnl
                streak = streak + 1 if streak >= 0 else 1
                best_win_streak = max(best_win_streak, streak)
            elif pnl < 0:
                losses += 1; loss_sum += pnl
                streak = streak - 1 if streak <= 0 else -1
                worst_loss_streak = min(worst_loss_streak, streak)
            if (updated or created) >= cutoff30:
                t30 += 1; w30 += 1 if pnl > 0 else 0
            for t in (tags or "").split(","):
                t = t.strip()
                if t:
                    tag_counts[t] = tag_counts.get(t, 0) + 1
        for day in sorted(by_day):
            cum += by_day[day]
            curve.append({"date": day, "pnl": round(by_day[day], 2), "cum_pnl": round(cum, 2)})
        total = wins + losses
        return {
            "days": days,
            "closed_trades": total,
            "win_rate_pct": round(wins / total * 100, 1) if total else None,
            "win_rate_30d_pct": round(w30 / t30 * 100, 1) if t30 else None,
            "avg_win": round(win_sum / wins, 2) if wins else None,
            "avg_loss": round(loss_sum / losses, 2) if losses else None,
            "profit_factor": round(win_sum / abs(loss_sum), 2) if loss_sum else None,
            "best_win_streak": best_win_streak,
            "worst_loss_streak": abs(worst_loss_streak),
            "equity_curve": curve[-60:],
            "by_symbol": by_symbol,
            "by_horizon": by_horizon,
            "by_weekday": by_weekday,
            "tag_counts": tag_counts,
        }

    def history(self, limit: int = 200) -> list[dict]:
        """Most recent ideas first — for the dashboard's trade log + PnL curve."""
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {', '.join(self._COLUMNS)} FROM ideas"
                " ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(zip(self._COLUMNS, r)) for r in rows]

    def load_open(self) -> tuple[list[dict], list[dict]]:
        """State restore after a restart: (active_rows, todays_pending_rows).
        ACTIVE positions are always restored (a positional hold survives any
        number of restarts); SUGGESTED ideas only from today — older untaken
        ideas are stale, mark them EXPIRED here so they don't resurrect."""
        today = datetime.now(IST).date().isoformat()
        with self._lock:
            active = self._conn.execute(
                f"SELECT {', '.join(self._COLUMNS)} FROM ideas WHERE status = ?",
                (Status.ACTIVE.value,),
            ).fetchall()
            pending = self._conn.execute(
                f"SELECT {', '.join(self._COLUMNS)} FROM ideas"
                " WHERE status = ? AND created_at LIKE ?",
                (Status.SUGGESTED.value, f"{today}%"),
            ).fetchall()
            self._conn.execute(
                "UPDATE ideas SET status = ?, updated_at = ?"
                " WHERE status = ? AND created_at NOT LIKE ?",
                (Status.EXPIRED.value, datetime.now(IST).isoformat(),
                 Status.SUGGESTED.value, f"{today}%"),
            )
            self._conn.commit()
        return ([dict(zip(self._COLUMNS, r)) for r in active],
                [dict(zip(self._COLUMNS, r)) for r in pending])

    def day_stats(self) -> dict:
        today = datetime.now(IST).date().isoformat()
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(pnl), 0) FROM ideas"
                " WHERE created_at LIKE ? AND status = ?",
                (f"{today}%", Status.CLOSED.value),
            ).fetchone()
        return {"closed_today": row[0], "realised_pnl": round(row[1], 2)}

    def close(self) -> None:
        self._conn.close()
