"""
learning_engine.py
==================
Mechanical strategy-performance analyzer.

Runs on prod as a scheduled batch job. NO live AI calls — produces structured,
deterministic analysis from the snapshot + trade_log tables that the
StrategyStateLogger populates. Narrative interpretation happens on the Mac
on-demand via Claude Code or claude.ai paste.

What it computes per strategy
-----------------------------
1. Condition importance — winner-vs-loser hit-rate per condition; flags weak
   conditions (predictive_score < 0.1).
2. Condition co-occurrence — pairs whose joint hit-rate in winners far exceeds
   losers (synergistic) or whose joint score adds nothing over the individual
   (redundant).
3. Rolling win rate — last 10 / 20 / 50 trades; drift_alert if last-20 < 45%.
4. Flip suggestion — last-30 win_rate < 30% AND avg_pnl < 0.
5. Pattern signal summary — frequency of each pattern_signals key in winners
   vs losers (forward-compatible with patternPY's named patterns).
6. Templated recommendations — derived from the math above, no LLM.

Persists to `strategy_insights` table; exposes via FastAPI endpoints.

Usage
-----
    from learning_engine import LearningEngine
    engine = LearningEngine(db_path="output/strategy_state.db")
    engine.run_all_strategies()
    latest = engine.get_latest_insights("S1_Salmog3_Weekly")
"""

import json
import math
import sqlite3
import datetime
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple


STRATEGY_IDS = [
    "S1_Salmog3_Weekly",
    "S2_WickScaled",
    "S3_4H_Hybrid",
    "S1_BodyStrict",
    "S4_TQQQ_Regime",
    "S5_TQQQ_Regime_B",
]

WEAK_CONDITION_THRESHOLD = 0.10        # predictive_score < this → "WEAK"
SYNERGY_THRESHOLD = 0.40                # joint_predictive >= this → flag pair
REDUNDANCY_DELTA = 0.05                 # joint vs better-individual within this → redundant
DRIFT_WIN_RATE_THRESHOLD = 0.45         # last-20 below this → drift_alert
FLIP_WIN_RATE_THRESHOLD = 0.30          # last-30 below this AND avg_pnl<0 → flip
MIN_TRADES_FOR_DRIFT = 20
MIN_TRADES_FOR_FLIP = 30
MIN_TRADES_FOR_ANALYSIS = 5


class LearningEngine:
    """Batch analyzer over snapshot + trade_log tables. No live AI dependency."""

    def __init__(self, db_path: str = "output/strategy_state.db") -> None:
        self._db_path = db_path
        self._init_db()

    # -------------------------------------------------------------------------
    # DB bootstrap
    # -------------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        conn = self._connect()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS strategy_insights (
                    id                              INTEGER PRIMARY KEY AUTOINCREMENT,
                    strategy_id                     TEXT    NOT NULL,
                    analysis_date                   TEXT    NOT NULL,
                    trades_analyzed                 INTEGER NOT NULL DEFAULT 0,
                    win_rate_10                     REAL,
                    win_rate_20                     REAL,
                    win_rate_50                     REAL,
                    avg_pnl                         REAL,
                    drift_alert                     INTEGER NOT NULL DEFAULT 0,
                    flip_suggestion                 INTEGER NOT NULL DEFAULT 0,
                    condition_importance_json       TEXT,
                    condition_co_occurrence_json    TEXT,
                    pattern_signals_summary_json    TEXT,
                    recommendations_json            TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_insights_strat_date
                    ON strategy_insights (strategy_id, analysis_date DESC);
            """)
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Data loading
    # -------------------------------------------------------------------------

    def _load_closed_trades(self, strategy_id: str) -> List[Dict[str, Any]]:
        """
        Load every closed trade for the strategy, joined with its entry snapshot
        so we have the conditions + pattern_signals available.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT t.trade_id, t.symbol, t.direction, t.entry_time, t.exit_time,
                       t.entry_price, t.exit_price, t.realized_pnl, t.duration_bars,
                       s.conditions, s.pattern_signals, s.readiness_score,
                       s.conditions_met, s.conditions_total
                FROM trade_log t
                LEFT JOIN strategy_snapshots s ON t.entry_snapshot_id = s.snapshot_id
                WHERE t.strategy_id = ? AND t.exit_time IS NOT NULL
                ORDER BY t.entry_time ASC
                """,
                (strategy_id,),
            ).fetchall()
        finally:
            conn.close()

        out = []
        for r in rows:
            d = dict(r)
            d["conditions"] = json.loads(d["conditions"]) if d["conditions"] else []
            d["pattern_signals"] = json.loads(d["pattern_signals"]) if d["pattern_signals"] else None
            d["is_winner"] = (d["realized_pnl"] or 0) > 0
            out.append(d)
        return out

    # -------------------------------------------------------------------------
    # Condition importance
    # -------------------------------------------------------------------------

    def _condition_importance(self, trades: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        winners = [t for t in trades if t["is_winner"]]
        losers  = [t for t in trades if not t["is_winner"]]
        nw, nl = len(winners), len(losers)
        if nw == 0 and nl == 0:
            return []

        names = set()
        for t in trades:
            for c in t["conditions"]:
                if isinstance(c, dict) and "name" in c:
                    names.add(c["name"])

        rows = []
        for name in sorted(names):
            wins_met = sum(1 for t in winners if self._condition_met(t, name))
            loss_met = sum(1 for t in losers  if self._condition_met(t, name))
            hr_w = wins_met / nw if nw else 0.0
            hr_l = loss_met / nl if nl else 0.0
            score = hr_w - hr_l
            rows.append({
                "name": name,
                "hit_rate_in_winners": round(hr_w, 4),
                "hit_rate_in_losers":  round(hr_l, 4),
                "predictive_score":    round(score, 4),
                "status": "keep" if score >= WEAK_CONDITION_THRESHOLD else "WEAK - consider removing",
            })

        rows.sort(key=lambda r: r["predictive_score"], reverse=True)
        return rows

    @staticmethod
    def _condition_met(trade: Dict[str, Any], name: str) -> bool:
        for c in trade["conditions"]:
            if isinstance(c, dict) and c.get("name") == name:
                return bool(c.get("met", False))
        return False

    # -------------------------------------------------------------------------
    # Condition co-occurrence
    # -------------------------------------------------------------------------

    def _condition_co_occurrence(
        self,
        trades: List[Dict[str, Any]],
        condition_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Look at pairs of conditions and find:
          - SYNERGY: pair's joint_predictive_score >> max of individuals
          - REDUNDANT: pair's joint_predictive_score ≈ max of individuals
        Limits to top-12 individually-strong conditions to keep O(n^2) tractable.
        """
        winners = [t for t in trades if t["is_winner"]]
        losers  = [t for t in trades if not t["is_winner"]]
        nw, nl = len(winners), len(losers)
        if nw < 3 or nl < 3:
            return []

        scored = sorted(condition_rows, key=lambda r: r["predictive_score"], reverse=True)
        top = [r["name"] for r in scored[:12]]
        if len(top) < 2:
            return []

        ind = {r["name"]: r["predictive_score"] for r in condition_rows}

        pairs = []
        for a, b in combinations(top, 2):
            both_w = sum(1 for t in winners if self._condition_met(t, a) and self._condition_met(t, b))
            both_l = sum(1 for t in losers  if self._condition_met(t, a) and self._condition_met(t, b))
            hr_w = both_w / nw
            hr_l = both_l / nl
            joint = hr_w - hr_l
            best_individual = max(ind.get(a, 0), ind.get(b, 0))
            delta = joint - best_individual

            tag = None
            if joint >= SYNERGY_THRESHOLD and delta > REDUNDANCY_DELTA:
                tag = "SYNERGY"
            elif abs(delta) <= REDUNDANCY_DELTA and joint >= WEAK_CONDITION_THRESHOLD:
                tag = "REDUNDANT"

            if tag:
                pairs.append({
                    "pair": [a, b],
                    "joint_hit_rate_winners": round(hr_w, 4),
                    "joint_hit_rate_losers":  round(hr_l, 4),
                    "joint_predictive_score": round(joint, 4),
                    "best_individual_score":  round(best_individual, 4),
                    "delta_vs_best_individual": round(delta, 4),
                    "tag": tag,
                })

        pairs.sort(key=lambda p: p["joint_predictive_score"], reverse=True)
        return pairs

    # -------------------------------------------------------------------------
    # Pattern-signal summary (forward-compatible with patternPY)
    # -------------------------------------------------------------------------

    def _pattern_signal_summary(self, trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate pattern_signals frequency in winners vs losers.

        Numeric levels (support_level, resistance_level) → presence frequency.
        Categorical pattern names (head_shoulders, double_top, ...) → frequency
        of value when present. Designed to absorb whatever patternPY emits.
        """
        winners = [t for t in trades if t["is_winner"] and t["pattern_signals"]]
        losers  = [t for t in trades if not t["is_winner"] and t["pattern_signals"]]
        nw_total = sum(1 for t in trades if t["is_winner"])
        nl_total = sum(1 for t in trades if not t["is_winner"])
        if nw_total == 0 and nl_total == 0:
            return {}

        keys = set()
        for t in trades:
            ps = t["pattern_signals"]
            if isinstance(ps, dict):
                keys.update(ps.keys())

        summary = {}
        for k in sorted(keys):
            win_present = sum(1 for t in winners if k in t["pattern_signals"] and t["pattern_signals"][k] is not None)
            loss_present = sum(1 for t in losers  if k in t["pattern_signals"] and t["pattern_signals"][k] is not None)
            entry = {
                "frequency_in_winners": round(win_present / nw_total, 4) if nw_total else 0.0,
                "frequency_in_losers":  round(loss_present / nl_total, 4) if nl_total else 0.0,
            }

            # If categorical (string values), break down by value
            sample_value = next(
                (t["pattern_signals"][k] for t in trades
                 if isinstance(t["pattern_signals"], dict) and t["pattern_signals"].get(k) is not None),
                None,
            )
            if isinstance(sample_value, str):
                by_value: Dict[str, Dict[str, int]] = {}
                for t in winners:
                    v = t["pattern_signals"].get(k)
                    if isinstance(v, str):
                        by_value.setdefault(v, {"winners": 0, "losers": 0})["winners"] += 1
                for t in losers:
                    v = t["pattern_signals"].get(k)
                    if isinstance(v, str):
                        by_value.setdefault(v, {"winners": 0, "losers": 0})["losers"] += 1
                entry["by_value"] = by_value

            summary[k] = entry

        return summary

    # -------------------------------------------------------------------------
    # Rolling win rate + drift + flip
    # -------------------------------------------------------------------------

    @staticmethod
    def _rolling_metrics(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
        def win_rate(slice_: List[Dict[str, Any]]) -> Optional[float]:
            if not slice_:
                return None
            return round(sum(1 for t in slice_ if t["is_winner"]) / len(slice_), 4)

        last_10 = trades[-10:]
        last_20 = trades[-20:]
        last_50 = trades[-50:]

        wr_10 = win_rate(last_10) if len(trades) >= 10 else None
        wr_20 = win_rate(last_20) if len(trades) >= MIN_TRADES_FOR_DRIFT else None
        wr_50 = win_rate(last_50) if len(trades) >= 50 else None

        drift = wr_20 is not None and wr_20 < DRIFT_WIN_RATE_THRESHOLD
        return {
            "win_rate_last_10": wr_10,
            "win_rate_last_20": wr_20,
            "win_rate_last_50": wr_50,
            "drift_alert": drift,
        }

    @staticmethod
    def _flip_suggestion(trades: List[Dict[str, Any]]) -> bool:
        if len(trades) < MIN_TRADES_FOR_FLIP:
            return False
        recent = trades[-MIN_TRADES_FOR_FLIP:]
        wr = sum(1 for t in recent if t["is_winner"]) / len(recent)
        avg_pnl = sum((t["realized_pnl"] or 0) for t in recent) / len(recent)
        return wr < FLIP_WIN_RATE_THRESHOLD and avg_pnl < 0

    @staticmethod
    def _avg_pnl(trades: List[Dict[str, Any]]) -> float:
        if not trades:
            return 0.0
        return round(sum((t["realized_pnl"] or 0) for t in trades) / len(trades), 4)

    # -------------------------------------------------------------------------
    # Recommendations (templated — no LLM)
    # -------------------------------------------------------------------------

    @staticmethod
    def _generate_recommendations(
        cond_rows: List[Dict[str, Any]],
        cooc: List[Dict[str, Any]],
        rolling: Dict[str, Any],
        flip: bool,
        trades_n: int,
    ) -> List[str]:
        recs = []

        weak = [c for c in cond_rows if c["status"].startswith("WEAK")]
        for c in weak[:3]:
            recs.append(
                f"`{c['name']}` has predictive_score={c['predictive_score']:+.2f} — "
                f"contributes little to winner/loser separation; consider removing or relaxing."
            )

        synergies = [p for p in cooc if p["tag"] == "SYNERGY"]
        for p in synergies[:2]:
            recs.append(
                f"`{p['pair'][0]}` + `{p['pair'][1]}` co-occur in "
                f"{p['joint_hit_rate_winners']*100:.0f}% of winners vs "
                f"{p['joint_hit_rate_losers']*100:.0f}% of losers "
                f"(+{p['delta_vs_best_individual']:.2f} over best individual) — "
                f"consider making both required."
            )

        redundants = [p for p in cooc if p["tag"] == "REDUNDANT"]
        for p in redundants[:2]:
            recs.append(
                f"`{p['pair'][0]}` and `{p['pair'][1]}` add no separation when used together "
                f"(joint={p['joint_predictive_score']:.2f} vs best={p['best_individual_score']:.2f}) — "
                f"likely redundant; one can be dropped."
            )

        if rolling.get("drift_alert"):
            recs.append(
                f"DRIFT ALERT: win rate last-20 = {rolling['win_rate_last_20']*100:.0f}% "
                f"(< {DRIFT_WIN_RATE_THRESHOLD*100:.0f}% threshold). Review recent regime change."
            )

        if flip:
            recs.append(
                f"FLIP SUGGESTION: last-30 trades win rate < {FLIP_WIN_RATE_THRESHOLD*100:.0f}% with "
                f"negative avg PnL. Strategy may be inverted in current regime — consider testing opposite direction."
            )

        if trades_n < MIN_TRADES_FOR_ANALYSIS:
            recs.append(
                f"INSUFFICIENT DATA: only {trades_n} closed trades. Analysis will sharpen "
                f"once you cross {MIN_TRADES_FOR_ANALYSIS} closed trades."
            )

        if not recs:
            recs.append(
                f"Strategy is behaving as intended over {trades_n} trades. No actionable changes."
            )

        return recs

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def analyze_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """
        Run full mechanical analysis for one strategy. Never raises — always
        returns a dict (with `status: "no_data"` if no closed trades).
        """
        try:
            trades = self._load_closed_trades(strategy_id)
        except Exception as e:
            return {"strategy_id": strategy_id, "status": "error", "error": str(e)}

        today = datetime.datetime.utcnow().strftime("%Y-%m-%d")

        if not trades:
            result = {
                "strategy_id": strategy_id,
                "analysis_date": today,
                "trades_analyzed": 0,
                "status": "no_data",
                "win_rate_last_10": None,
                "win_rate_last_20": None,
                "win_rate_last_50": None,
                "avg_pnl": 0.0,
                "drift_alert": False,
                "flip_suggestion": False,
                "condition_importance": [],
                "condition_co_occurrence": [],
                "pattern_signals_summary": {},
                "recommendations": [
                    "No closed trades yet. Analysis will populate after the first trade exits."
                ],
            }
            self._persist(result)
            return result

        cond_rows = self._condition_importance(trades)
        cooc      = self._condition_co_occurrence(trades, cond_rows)
        pat       = self._pattern_signal_summary(trades)
        rolling   = self._rolling_metrics(trades)
        flip      = self._flip_suggestion(trades)
        avg_pnl   = self._avg_pnl(trades)
        recs      = self._generate_recommendations(cond_rows, cooc, rolling, flip, len(trades))

        result = {
            "strategy_id": strategy_id,
            "analysis_date": today,
            "trades_analyzed": len(trades),
            "status": "ok",
            "win_rate_last_10": rolling["win_rate_last_10"],
            "win_rate_last_20": rolling["win_rate_last_20"],
            "win_rate_last_50": rolling["win_rate_last_50"],
            "avg_pnl": avg_pnl,
            "drift_alert": rolling["drift_alert"],
            "flip_suggestion": flip,
            "condition_importance": cond_rows,
            "condition_co_occurrence": cooc,
            "pattern_signals_summary": pat,
            "recommendations": recs,
        }
        self._persist(result)
        self._write_proposals(strategy_id, cond_rows, rolling, flip, avg_pnl, len(trades))
        return result

    def run_all_strategies(self) -> Dict[str, Dict[str, Any]]:
        return {sid: self.analyze_strategy(sid) for sid in STRATEGY_IDS}

    def get_latest_insights(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Read back the most-recent persisted analysis for a strategy."""
        try:
            conn = self._connect()
            try:
                row = conn.execute(
                    """
                    SELECT * FROM strategy_insights
                    WHERE strategy_id = ?
                    ORDER BY analysis_date DESC, id DESC LIMIT 1
                    """,
                    (strategy_id,),
                ).fetchone()
                if not row:
                    return None
                d = dict(row)
                for k in ("condition_importance_json", "condition_co_occurrence_json",
                          "pattern_signals_summary_json", "recommendations_json"):
                    if d.get(k):
                        d[k.replace("_json", "")] = json.loads(d[k])
                    d.pop(k, None)
                d["drift_alert"]     = bool(d["drift_alert"])
                d["flip_suggestion"] = bool(d["flip_suggestion"])
                return d
            finally:
                conn.close()
        except Exception:
            return None

    # -------------------------------------------------------------------------
    # Persistence
    # -------------------------------------------------------------------------

    def _persist(self, result: Dict[str, Any]) -> None:
        try:
            conn = self._connect()
            try:
                conn.execute(
                    """
                    INSERT INTO strategy_insights
                    (strategy_id, analysis_date, trades_analyzed,
                     win_rate_10, win_rate_20, win_rate_50, avg_pnl,
                     drift_alert, flip_suggestion,
                     condition_importance_json, condition_co_occurrence_json,
                     pattern_signals_summary_json, recommendations_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        result["strategy_id"],
                        result["analysis_date"],
                        result["trades_analyzed"],
                        result.get("win_rate_last_10"),
                        result.get("win_rate_last_20"),
                        result.get("win_rate_last_50"),
                        result.get("avg_pnl"),
                        int(bool(result.get("drift_alert"))),
                        int(bool(result.get("flip_suggestion"))),
                        json.dumps(result.get("condition_importance", []), default=str),
                        json.dumps(result.get("condition_co_occurrence", []), default=str),
                        json.dumps(result.get("pattern_signals_summary", {}), default=str),
                        json.dumps(result.get("recommendations", []), default=str),
                    ),
                )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass

    def _write_proposals(
        self,
        strategy_id: str,
        cond_rows: list,
        rolling: dict,
        flip: bool,
        avg_pnl: float,
        trade_count: int,
    ) -> None:
        """
        Write HITL proposals to proposed_changes table based on analysis results.
        Each actionable finding becomes a pending change for human review.
        Never raises — proposal failures must not disrupt the analysis run.
        """
        if trade_count < MIN_TRADES_FOR_ANALYSIS:
            return
        try:
            conn = self._connect()
            try:
                def _already_pending(change_type: str, desc_prefix: str) -> bool:
                    row = conn.execute(
                        """SELECT id FROM proposed_changes
                           WHERE strategy_id=? AND change_type=? AND status='pending'
                           AND description LIKE ?""",
                        (strategy_id, change_type, desc_prefix + "%"),
                    ).fetchone()
                    return row is not None

                def _current_setting(key: str, default):
                    row = conn.execute(
                        f"SELECT {key} FROM strategy_settings WHERE strategy_id=?",
                        (strategy_id,),
                    ).fetchone()
                    return row[0] if row else default

                now = datetime.datetime.utcnow().isoformat()

                # Weak conditions — at most 3 proposals per run
                weak = [c for c in cond_rows if c["status"].startswith("WEAK")]
                for c in weak[:3]:
                    desc = f"Weak condition `{c['name']}`"
                    if _already_pending("condition_weight", desc):
                        continue
                    conn.execute(
                        """INSERT INTO proposed_changes
                           (created_at, strategy_id, change_type, description,
                            current_value, proposed_value, evidence, expected_impact)
                           VALUES (?,?,?,?,?,?,?,?)""",
                        (
                            now, strategy_id, "condition_weight",
                            f"{desc}: predictive_score={c['predictive_score']:+.3f} — consider removing or relaxing",
                            json.dumps({"condition": c["name"], "status": "active"}),
                            json.dumps({"condition": c["name"], "status": "remove_or_relax"}),
                            json.dumps({
                                "predictive_score": c["predictive_score"],
                                "hit_rate_winners": c["hit_rate_in_winners"],
                                "hit_rate_losers":  c["hit_rate_in_losers"],
                                "trades_analyzed":  trade_count,
                            }),
                            "May increase entry volume; review manually before removing",
                        ),
                    )

                # Drift alert → propose raising ML threshold
                if rolling.get("drift_alert"):
                    wr = rolling.get("win_rate_last_20", 0) or 0
                    current_thresh = _current_setting("ml_threshold", 1.0)
                    new_thresh = min(round(current_thresh + 0.06, 2), 0.75)
                    desc = f"Drift alert: win rate last-20 = {wr*100:.0f}%"
                    if not _already_pending("ml_threshold", desc[:20]):
                        conn.execute(
                            """INSERT INTO proposed_changes
                               (created_at, strategy_id, change_type, description,
                                current_value, proposed_value, evidence, expected_impact)
                               VALUES (?,?,?,?,?,?,?,?)""",
                            (
                                now, strategy_id, "ml_threshold",
                                f"{desc} — raise ML threshold to {new_thresh} to filter weaker setups",
                                json.dumps({"value": current_thresh}),
                                json.dumps({"value": new_thresh}),
                                json.dumps({
                                    "win_rate_last_20": wr,
                                    "threshold": DRIFT_WIN_RATE_THRESHOLD,
                                    "trades_analyzed": trade_count,
                                }),
                                f"Reduces entries ~15–25%. Target: win rate back above {DRIFT_WIN_RATE_THRESHOLD*100:.0f}%",
                            ),
                        )

                # Flip suggestion → propose enabling PatternPY gate as first defensive step
                if flip:
                    patternpy_gate = _current_setting("patternpy_gate", 0)
                    if not patternpy_gate:
                        desc = "Flip suggestion: enable PatternPY BEARISH block"
                        if not _already_pending("patternpy_gate", desc[:20]):
                            conn.execute(
                                """INSERT INTO proposed_changes
                                   (created_at, strategy_id, change_type, description,
                                    current_value, proposed_value, evidence, expected_impact)
                                   VALUES (?,?,?,?,?,?,?,?)""",
                                (
                                    now, strategy_id, "patternpy_gate",
                                    f"{desc} — strategy may be inverted in current regime",
                                    json.dumps({"value": 0, "label": "log-only"}),
                                    json.dumps({"value": 1, "label": "hard block on BEARISH bias"}),
                                    json.dumps({
                                        "avg_pnl": avg_pnl,
                                        "trades_analyzed": trade_count,
                                        "flip_threshold": FLIP_WIN_RATE_THRESHOLD,
                                    }),
                                    "Blocks entries when PatternPY detects BEARISH bias. Review carefully.",
                                ),
                            )

                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point (for cron / systemd)
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    import os
    db_path = os.environ.get(
        "STRATEGY_STATE_DB",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "strategy_state.db"),
    )
    engine = LearningEngine(db_path=db_path)
    results = engine.run_all_strategies()
    summary = {
        sid: {
            "trades_analyzed": r.get("trades_analyzed", 0),
            "status": r.get("status"),
            "drift_alert": r.get("drift_alert"),
            "flip_suggestion": r.get("flip_suggestion"),
            "n_recommendations": len(r.get("recommendations", [])),
        }
        for sid, r in results.items()
    }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
