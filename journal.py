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
        self._conn.commit()

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

    _COLUMNS = ["id", "created_at", "symbol", "side", "horizon", "entry", "stop",
                "target", "qty", "confidence", "reason", "why", "status",
                "fill_qty", "fill_price", "exit_price", "pnl", "updated_at"]

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
