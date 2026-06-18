"""
strategy_state_logger.py
========================
Thread-safe snapshot and trade logger for MIT-Loop Pro.

Captures a full condition-state snapshot on every candle evaluation and
persists trade lifecycle events (entry → exit) to SQLite.

All public methods catch exceptions internally — a logger failure never
propagates into execution logic.

Tables
------
strategy_snapshots
    One row per candle-close evaluation. conditions and pattern_signals
    columns are JSON-serialized lists / dicts.

trade_log
    One row per trade entry, updated in-place on exit.
    Links to entry_snapshot_id and exit_snapshot_id.
"""

import json
import os
import sqlite3
import threading
import datetime
import uuid
from typing import Any, Dict, List, Optional


class StrategyStateLogger:
    """
    Usage
    -----
    logger = StrategyStateLogger()

    # Every candle close:
    snap_id = logger.on_candle(
        strategy_id="S1_Salmog3_Weekly",
        symbol="SPY",
        timeframe="1W",
        ohlcv={"open": 525.10, "high": 528.40, "low": 522.80, "close": 527.20, "volume": 4500000},
        conditions=[
            {"name": "macro_bull_weekly", "threshold": 1.0, "actual": 1.03, "met": True},
        ],
        pattern_signals={"support_level": 520.0, "resistance_level": 530.0},
        trade_triggered=False,
    )

    # On entry:
    trade_id = logger.on_trade_entry(
        entry_snapshot_id=snap_id,
        strategy_id="S1_Salmog3_Weekly",
        symbol="SPY",
        direction="LONG",
        entry_time=datetime.datetime.utcnow(),
        entry_price=527.20,
    )

    # On exit:
    exit_snap_id = logger.on_candle(...)
    logger.on_trade_exit(
        trade_id=trade_id,
        exit_snapshot_id=exit_snap_id,
        exit_time=datetime.datetime.utcnow(),
        exit_price=534.10,
    )
    """

    def __init__(self, db_path: str = "output/strategy_state.db") -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    # -------------------------------------------------------------------------
    # DB bootstrap
    # -------------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS strategy_snapshots (
                        snapshot_id       TEXT    PRIMARY KEY,
                        timestamp         TEXT    NOT NULL,
                        strategy_id       TEXT    NOT NULL,
                        symbol            TEXT    NOT NULL,
                        timeframe         TEXT    NOT NULL,
                        ohlcv             TEXT    NOT NULL,
                        conditions        TEXT    NOT NULL,
                        conditions_met    INTEGER NOT NULL DEFAULT 0,
                        conditions_total  INTEGER NOT NULL DEFAULT 0,
                        readiness_score   REAL    NOT NULL DEFAULT 0.0,
                        pattern_signals   TEXT,
                        trade_triggered   INTEGER NOT NULL DEFAULT 0
                    );
                    CREATE INDEX IF NOT EXISTS idx_snap_strat_ts
                        ON strategy_snapshots (strategy_id, timestamp);
                    CREATE INDEX IF NOT EXISTS idx_snap_symbol_ts
                        ON strategy_snapshots (symbol, timestamp);

                    CREATE TABLE IF NOT EXISTS trade_log (
                        trade_id          TEXT    PRIMARY KEY,
                        strategy_id       TEXT    NOT NULL,
                        symbol            TEXT    NOT NULL,
                        direction         TEXT    NOT NULL DEFAULT 'LONG',
                        entry_time        TEXT,
                        exit_time         TEXT,
                        entry_price       REAL,
                        exit_price        REAL,
                        realized_pnl      REAL,
                        duration_bars     INTEGER,
                        entry_snapshot_id TEXT,
                        exit_snapshot_id  TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_trade_open
                        ON trade_log (strategy_id, symbol, exit_time);
                    CREATE INDEX IF NOT EXISTS idx_trade_strat_time
                        ON trade_log (strategy_id, entry_time);

                    CREATE TABLE IF NOT EXISTS proposed_changes (
                        id               INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at       TEXT    NOT NULL,
                        strategy_id      TEXT    NOT NULL,
                        change_type      TEXT    NOT NULL,
                        description      TEXT    NOT NULL,
                        current_value    TEXT    NOT NULL,
                        proposed_value   TEXT    NOT NULL,
                        evidence         TEXT,
                        expected_impact  TEXT,
                        status           TEXT    NOT NULL DEFAULT 'pending',
                        decided_at       TEXT,
                        decided_by       TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_changes_strat_status
                        ON proposed_changes (strategy_id, status);

                    CREATE TABLE IF NOT EXISTS strategy_settings (
                        strategy_id           TEXT PRIMARY KEY,
                        auto_accept           INTEGER NOT NULL DEFAULT 0,
                        ml_threshold          REAL    NOT NULL DEFAULT 1.0,
                        ml_enabled            INTEGER NOT NULL DEFAULT 0,
                        patternpy_gate        INTEGER NOT NULL DEFAULT 0,
                        patternpy_stop        INTEGER NOT NULL DEFAULT 0,
                        multitf_gate          INTEGER NOT NULL DEFAULT 0,
                        multitf_risk_block    TEXT    NOT NULL DEFAULT 'none',
                        multitf_align_require TEXT    NOT NULL DEFAULT 'none',
                        last_updated          TEXT
                    );

                    CREATE TABLE IF NOT EXISTS pattern_detections (
                        id               INTEGER PRIMARY KEY AUTOINCREMENT,
                        detected_at      TEXT    NOT NULL,
                        symbol           TEXT    NOT NULL,
                        timeframe        TEXT    NOT NULL,
                        pattern_bias     TEXT,
                        active_patterns  TEXT,
                        support_level    REAL,
                        resistance_level REAL,
                        head_shoulder    TEXT,
                        double_pattern   TEXT,
                        triangle         TEXT,
                        wedge            TEXT,
                        channel          TEXT,
                        trade_triggered  INTEGER NOT NULL DEFAULT 0,
                        trade_outcome    REAL,
                        approved         INTEGER,
                        notes            TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_pat_symbol_tf
                        ON pattern_detections (symbol, timeframe, detected_at);
                """)
                conn.commit()
            finally:
                conn.close()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def on_candle(
        self,
        strategy_id: str,
        symbol: str,
        timeframe: str,
        ohlcv: Dict[str, Any],
        conditions: List[Dict[str, Any]],
        pattern_signals: Optional[Dict[str, Any]] = None,
        trade_triggered: bool = False,
        ts: Optional[datetime.datetime] = None,
    ) -> str:
        """
        Persist a full state snapshot for one candle-close evaluation.

        Returns snapshot_id (str), or "" on failure.
        Guaranteed not to raise.
        """
        try:
            ts = ts or datetime.datetime.utcnow()
            ts_str = ts.strftime("%Y%m%d_%H%M%S_%f")
            snap_id = f"snap_{ts_str}_{strategy_id}_{symbol}"

            met   = sum(1 for c in conditions if c.get("met", False))
            total = len(conditions)
            score = round(met / total, 4) if total > 0 else 0.0

            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO strategy_snapshots
                        (snapshot_id, timestamp, strategy_id, symbol, timeframe,
                         ohlcv, conditions, conditions_met, conditions_total,
                         readiness_score, pattern_signals, trade_triggered)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            snap_id,
                            ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            strategy_id,
                            symbol,
                            timeframe,
                            json.dumps(ohlcv, default=str),
                            json.dumps(conditions, default=str),
                            met,
                            total,
                            score,
                            json.dumps(pattern_signals, default=str) if pattern_signals is not None else None,
                            int(trade_triggered),
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
            return snap_id
        except Exception:
            return ""

    def on_trade_entry(
        self,
        entry_snapshot_id: str,
        strategy_id: str,
        symbol: str,
        direction: str,
        entry_time: datetime.datetime,
        entry_price: float,
    ) -> str:
        """
        Insert a new open trade row.

        Returns trade_id (str), or "" on failure.
        Guaranteed not to raise.
        """
        try:
            trade_id = (
                f"trade_{entry_time.strftime('%Y%m%d_%H%M%S')}"
                f"_{strategy_id}_{symbol}_{uuid.uuid4().hex[:6]}"
            )
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        """
                        INSERT INTO trade_log
                        (trade_id, strategy_id, symbol, direction,
                         entry_time, entry_price, entry_snapshot_id)
                        VALUES (?,?,?,?,?,?,?)
                        """,
                        (
                            trade_id,
                            strategy_id,
                            symbol,
                            direction,
                            entry_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            float(entry_price),
                            entry_snapshot_id,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
            return trade_id
        except Exception:
            return ""

    def on_trade_exit(
        self,
        trade_id: str,
        exit_snapshot_id: str,
        exit_time: datetime.datetime,
        exit_price: float,
        duration_bars: int = 0,
    ) -> None:
        """
        Update trade_log with exit data, compute realized_pnl.

        If duration_bars == 0, it is computed from entry_time in the DB
        (assumes 1-min bars; pass duration_bars explicitly for other timeframes).
        Guaranteed not to raise.
        """
        if not trade_id:
            return
        try:
            with self._lock:
                conn = self._connect()
                try:
                    row = conn.execute(
                        "SELECT entry_price, entry_time FROM trade_log WHERE trade_id = ?",
                        (trade_id,),
                    ).fetchone()
                    if row is None:
                        return

                    entry_price  = float(row["entry_price"])
                    realized_pnl = round(exit_price - entry_price, 6)

                    if duration_bars == 0 and row["entry_time"]:
                        try:
                            et = datetime.datetime.fromisoformat(
                                row["entry_time"].rstrip("Z").replace("Z", "")
                            )
                            xt = exit_time.replace(tzinfo=None)
                            duration_bars = max(1, int((xt - et).total_seconds() / 60))
                        except Exception:
                            pass

                    conn.execute(
                        """
                        UPDATE trade_log
                        SET exit_time        = ?,
                            exit_price       = ?,
                            realized_pnl     = ?,
                            duration_bars    = ?,
                            exit_snapshot_id = ?
                        WHERE trade_id = ?
                        """,
                        (
                            exit_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            float(exit_price),
                            realized_pnl,
                            duration_bars,
                            exit_snapshot_id,
                            trade_id,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            pass

    def get_open_trade_id(self, strategy_id: str, symbol: str) -> Optional[str]:
        """
        Return the trade_id of the most recent open trade (no exit_time)
        for the given strategy + symbol. Returns None if none found.
        Guaranteed not to raise.
        """
        try:
            with self._lock:
                conn = self._connect()
                try:
                    row = conn.execute(
                        """
                        SELECT trade_id FROM trade_log
                        WHERE strategy_id = ? AND symbol = ? AND exit_time IS NULL
                        ORDER BY entry_time DESC LIMIT 1
                        """,
                        (strategy_id, symbol),
                    ).fetchone()
                    return row["trade_id"] if row else None
                finally:
                    conn.close()
        except Exception:
            return None

    def get_snapshots_for_strategy(
        self,
        strategy_id: str,
        since: datetime.datetime,
    ) -> List[dict]:
        """
        Return all snapshots for a strategy since `since` (UTC), ordered ascending.

        ohlcv, conditions, and pattern_signals are deserialized back to Python objects.
        The key conditions_met is renamed to conditions_met_count for clarity.
        Returns [] on failure.
        """
        try:
            since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute(
                        """
                        SELECT * FROM strategy_snapshots
                        WHERE strategy_id = ? AND timestamp >= ?
                        ORDER BY timestamp ASC
                        """,
                        (strategy_id, since_str),
                    ).fetchall()

                    result = []
                    for r in rows:
                        d = dict(r)
                        d["ohlcv"]               = json.loads(d["ohlcv"])
                        d["conditions"]          = json.loads(d["conditions"])
                        d["pattern_signals"]     = json.loads(d["pattern_signals"]) if d["pattern_signals"] else None
                        d["trade_triggered"]     = bool(d["trade_triggered"])
                        d["conditions_met_count"] = d.pop("conditions_met")
                        result.append(d)
                    return result
                finally:
                    conn.close()
        except Exception:
            return []

    # -------------------------------------------------------------------------
    # HITL — Human-in-the-Loop controls
    # -------------------------------------------------------------------------

    def bootstrap_settings(self, strategy_ids: list) -> None:
        """Insert default settings row for every strategy (safe, skips existing)."""
        try:
            with self._lock:
                conn = self._connect()
                try:
                    for sid in strategy_ids:
                        conn.execute(
                            """
                            INSERT OR IGNORE INTO strategy_settings
                            (strategy_id, auto_accept, ml_threshold, ml_enabled,
                             patternpy_gate, patternpy_stop, multitf_gate,
                             multitf_risk_block, multitf_align_require)
                            VALUES (?, 0, 1.0, 0, 0, 0, 0, 'none', 'none')
                            """,
                            (sid,),
                        )
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            pass

    def get_live_setting(self, strategy_id: str, key: str, default=None):
        """Read a single live parameter for a strategy. Never raises."""
        try:
            with self._lock:
                conn = self._connect()
                try:
                    row = conn.execute(
                        f"SELECT {key} FROM strategy_settings WHERE strategy_id = ?",
                        (strategy_id,),
                    ).fetchone()
                    return row[0] if row else default
                finally:
                    conn.close()
        except Exception:
            return default

    def get_all_settings(self) -> list:
        """Return all strategy_settings rows as dicts. Never raises."""
        try:
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute(
                        "SELECT * FROM strategy_settings ORDER BY strategy_id"
                    ).fetchall()
                    return [dict(r) for r in rows]
                finally:
                    conn.close()
        except Exception:
            return []

    def propose_change(
        self,
        strategy_id: str,
        change_type: str,
        description: str,
        current_value,
        proposed_value,
        evidence=None,
        expected_impact: str = "",
    ) -> int:
        """
        Write a pending change proposal.
        If auto_accept is ON for the strategy, applies immediately.
        Returns proposal id (0 on failure).
        """
        try:
            ts = datetime.datetime.utcnow().isoformat()
            with self._lock:
                conn = self._connect()
                try:
                    cur = conn.execute(
                        """
                        INSERT INTO proposed_changes
                        (created_at, strategy_id, change_type, description,
                         current_value, proposed_value, evidence, expected_impact)
                        VALUES (?,?,?,?,?,?,?,?)
                        """,
                        (
                            ts,
                            strategy_id,
                            change_type,
                            description,
                            json.dumps(current_value, default=str),
                            json.dumps(proposed_value, default=str),
                            json.dumps(evidence, default=str) if evidence else None,
                            expected_impact,
                        ),
                    )
                    conn.commit()
                    proposal_id = cur.lastrowid
                finally:
                    conn.close()

            # Auto-accept if enabled for this strategy
            auto = self.get_live_setting(strategy_id, "auto_accept", 0)
            if auto:
                self.apply_change(proposal_id, decided_by="auto")

            return proposal_id
        except Exception:
            return 0

    def apply_change(self, proposal_id: int, decided_by: str = "human") -> bool:
        """
        Accept a proposal: update strategy_settings and mark decided.
        Returns True on success, False if not found or already decided.
        """
        try:
            now = datetime.datetime.utcnow().isoformat()
            with self._lock:
                conn = self._connect()
                try:
                    row = conn.execute(
                        "SELECT * FROM proposed_changes WHERE id = ?",
                        (proposal_id,),
                    ).fetchone()
                    if not row or row["status"] != "pending":
                        return False

                    strategy_id  = row["strategy_id"]
                    change_type  = row["change_type"]
                    proposed_val = json.loads(row["proposed_value"])

                    column_map = {
                        "ml_threshold":          ("ml_threshold",          proposed_val.get("value")),
                        "ml_enabled":            ("ml_enabled",            int(proposed_val.get("value", 0))),
                        "patternpy_gate":        ("patternpy_gate",        int(proposed_val.get("value", 0))),
                        "patternpy_stop":        ("patternpy_stop",        int(proposed_val.get("value", 0))),
                        "multitf_gate":          ("multitf_gate",          int(proposed_val.get("value", 0))),
                        "multitf_risk_block":    ("multitf_risk_block",    proposed_val.get("value", "none")),
                        "multitf_align_require": ("multitf_align_require", proposed_val.get("value", "none")),
                        "auto_accept":           ("auto_accept",           int(proposed_val.get("value", 0))),
                    }

                    if change_type in column_map:
                        col, val = column_map[change_type]
                        conn.execute(
                            f"UPDATE strategy_settings SET {col} = ?, last_updated = ? WHERE strategy_id = ?",
                            (val, now, strategy_id),
                        )

                    status = "accepted" if decided_by == "human" else "auto_accepted"
                    conn.execute(
                        "UPDATE proposed_changes SET status=?, decided_at=?, decided_by=? WHERE id=?",
                        (status, now, decided_by, proposal_id),
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception:
            return False

    def reject_change(self, proposal_id: int) -> bool:
        """Mark a proposal as rejected. Returns True on success."""
        try:
            now = datetime.datetime.utcnow().isoformat()
            with self._lock:
                conn = self._connect()
                try:
                    row = conn.execute(
                        "SELECT status FROM proposed_changes WHERE id = ?",
                        (proposal_id,),
                    ).fetchone()
                    if not row or row["status"] != "pending":
                        return False
                    conn.execute(
                        "UPDATE proposed_changes SET status='rejected', decided_at=?, decided_by='human' WHERE id=?",
                        (now, proposal_id),
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception:
            return False

    def get_pending_changes(self, strategy_id: str = None) -> list:
        """Return pending proposals, optionally filtered by strategy. Never raises."""
        try:
            with self._lock:
                conn = self._connect()
                try:
                    if strategy_id:
                        rows = conn.execute(
                            "SELECT * FROM proposed_changes WHERE strategy_id=? AND status='pending' ORDER BY created_at DESC",
                            (strategy_id,),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            "SELECT * FROM proposed_changes WHERE status='pending' ORDER BY strategy_id, created_at DESC"
                        ).fetchall()
                    return [dict(r) for r in rows]
                finally:
                    conn.close()
        except Exception:
            return []

    def get_change_history(self, strategy_id: str = None, limit: int = 100) -> list:
        """Return decided proposals (accepted/rejected/auto_accepted). Never raises."""
        try:
            with self._lock:
                conn = self._connect()
                try:
                    if strategy_id:
                        rows = conn.execute(
                            """SELECT * FROM proposed_changes
                               WHERE strategy_id=? AND status != 'pending'
                               ORDER BY decided_at DESC LIMIT ?""",
                            (strategy_id, limit),
                        ).fetchall()
                    else:
                        rows = conn.execute(
                            """SELECT * FROM proposed_changes
                               WHERE status != 'pending'
                               ORDER BY decided_at DESC LIMIT ?""",
                            (limit,),
                        ).fetchall()
                    return [dict(r) for r in rows]
                finally:
                    conn.close()
        except Exception:
            return []

    def set_auto_accept(self, strategy_id: str, enabled: bool) -> bool:
        """Toggle auto-accept for a strategy. Returns True on success."""
        try:
            now = datetime.datetime.utcnow().isoformat()
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        "UPDATE strategy_settings SET auto_accept=?, last_updated=? WHERE strategy_id=?",
                        (1 if enabled else 0, now, strategy_id),
                    )
                    conn.commit()
                    return True
                finally:
                    conn.close()
        except Exception:
            return False

    def log_pattern_detection(self, symbol: str, timeframe: str, pat: dict, trade_triggered: bool = False) -> int:
        """Store a PatternPY detection event. Returns row id (0 on failure)."""
        try:
            with self._lock:
                conn = self._connect()
                try:
                    cur = conn.execute(
                        """INSERT INTO pattern_detections
                           (detected_at, symbol, timeframe, pattern_bias, active_patterns,
                            support_level, resistance_level, head_shoulder, double_pattern,
                            triangle, wedge, channel, trade_triggered)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (
                            datetime.datetime.utcnow().isoformat(),
                            symbol.upper(), timeframe.upper(),
                            pat.get("pattern_bias"),
                            json.dumps(pat.get("active_patterns", []), default=str),
                            pat.get("support_level"),
                            pat.get("resistance_level"),
                            pat.get("head_shoulder"),
                            pat.get("double"),
                            pat.get("triangle"),
                            pat.get("wedge"),
                            pat.get("channel"),
                            int(trade_triggered),
                        ),
                    )
                    conn.commit()
                    return cur.lastrowid
                finally:
                    conn.close()
        except Exception:
            return 0
