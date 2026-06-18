"""
model_router.py
===============
Selects the correct Anthropic model for each task type and logs every
routing decision to SQLite. No live API calls — pure routing logic.

Usage
-----
    from model_router import ModelRouter

    router = ModelRouter(db_path="output/strategy_state.db")
    model  = router.select_model("daily_insights", trade_count=50)
    tokens = router.estimate_tokens("RSI crossed 30 and volume surged 2x average…")

Routing rules
-------------
    daily_insights + trade_count < 200      → claude-sonnet-4-6
    weekly_deep_review OR trade_count >= 500 → claude-opus-4-7
    new_strategy_generation                 → claude-opus-4-8
    large_history_analysis + tokens > 100k  → claude-sonnet-4-6  (extended context)
    ui_chat                                 → claude-sonnet-4-6

Pricing note
------------
The user-specified prices below differ from the current claude-api skill
reference (which lists Opus 4.7/4.8 at $5/$25 per 1M — not $15/$75).
$15/$75 matches Claude 3 Opus pricing. The values here are kept exactly
as specified; verify against https://anthropic.com/pricing before
reporting costs externally.
"""

from __future__ import annotations

import datetime
import os
import re
import sqlite3
import threading
from dataclasses import dataclass
from typing import Optional

# ── tiktoken (optional) ──────────────────────────────────────────────────────
# tiktoken gives the most accurate token count (same encoding as Claude).
# If not installed, a character-based fallback is used (~1 token per 4 chars).
try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
    _TIKTOKEN_AVAILABLE = True
except ImportError:
    _ENC = None
    _TIKTOKEN_AVAILABLE = False


# ── Model IDs ────────────────────────────────────────────────────────────────
SONNET_4_6 = "claude-sonnet-4-6"
OPUS_4_7   = "claude-opus-4-7"
OPUS_4_8   = "claude-opus-4-8"

# ── Pricing (per 1M tokens, as specified by the user) ────────────────────────
# ⚠ NOTE: claude-api skill reference prices Opus 4.7/4.8 at $5.00/$25.00 per 1M.
#   The $15/$75 below matches Claude 3 Opus pricing. Verify before reporting costs.
PRICING: dict[str, dict[str, float]] = {
    SONNET_4_6: {"input": 3.0,  "output": 15.0},
    OPUS_4_7:   {"input": 15.0, "output": 75.0},
    OPUS_4_8:   {"input": 15.0, "output": 75.0},
}

# Typical output-token estimates per task (used for cost projection only)
TYPICAL_OUTPUT_TOKENS: dict[str, int] = {
    "daily_insights":         600,
    "weekly_deep_review":    2500,
    "new_strategy_generation": 3500,
    "large_history_analysis": 1200,
    "ui_chat":                400,
}

# Context-window thresholds
LARGE_CONTEXT_THRESHOLD = 100_000   # tokens — triggers extended-context path


@dataclass(frozen=True)
class RoutingDecision:
    """Immutable result from ModelRouter.select_model()."""
    model: str
    task_type: str
    estimated_input_tokens: int
    trade_count: int
    extended_context: bool          # True when the 100k+ path was triggered
    cost_estimate_usd: float
    reason: str                     # human-readable routing rationale

    def __str__(self) -> str:
        ctx = " [extended context]" if self.extended_context else ""
        return (
            f"{self.model}{ctx}  |  {self.task_type}  |  "
            f"~{self.estimated_input_tokens:,} tok  |  "
            f"${self.cost_estimate_usd:.4f} est  |  {self.reason}"
        )


class ModelRouter:
    """
    Stateless model selector with SQLite audit log.

    Parameters
    ----------
    db_path:
        Path to the SQLite database (same file as StrategyStateLogger /
        LearningEngine by default so all analytics land in one place).
    default_output_ratio:
        Fraction of input tokens used to estimate output tokens when no
        better information is available. Default 0.25.
    """

    def __init__(
        self,
        db_path: str = "output/strategy_state.db",
        default_output_ratio: float = 0.25,
    ) -> None:
        self._db_path = db_path
        self._default_output_ratio = default_output_ratio
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    # ─── DB ──────────────────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS model_usage_log (
                        id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp            TEXT    NOT NULL,
                        task_type            TEXT    NOT NULL,
                        model_selected       TEXT    NOT NULL,
                        trade_count          INTEGER NOT NULL DEFAULT 0,
                        estimated_tokens     INTEGER NOT NULL DEFAULT 0,
                        output_tokens_est    INTEGER NOT NULL DEFAULT 0,
                        extended_context     INTEGER NOT NULL DEFAULT 0,
                        actual_cost_usd_estimate REAL NOT NULL DEFAULT 0.0,
                        reason               TEXT
                    );
                    CREATE INDEX IF NOT EXISTS idx_usage_ts
                        ON model_usage_log (timestamp DESC);
                    CREATE INDEX IF NOT EXISTS idx_usage_task
                        ON model_usage_log (task_type, timestamp DESC);
                """)
                conn.commit()
            finally:
                conn.close()

    def _log(self, decision: RoutingDecision, output_tokens: int) -> None:
        try:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        """
                        INSERT INTO model_usage_log
                        (timestamp, task_type, model_selected, trade_count,
                         estimated_tokens, output_tokens_est, extended_context,
                         actual_cost_usd_estimate, reason)
                        VALUES (?,?,?,?,?,?,?,?,?)
                        """,
                        (
                            datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            decision.task_type,
                            decision.model,
                            decision.trade_count,
                            decision.estimated_input_tokens,
                            output_tokens,
                            int(decision.extended_context),
                            decision.cost_estimate_usd,
                            decision.reason,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            pass  # logging must never surface to callers

    # ─── Token estimation ────────────────────────────────────────────────────

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """
        Estimate token count for `text`.

        Uses tiktoken cl100k_base when available (pip install tiktoken).
        Falls back to a character-based heuristic:
          - ~4 chars per token for prose/code (English text)
          - Adds a small word-boundary correction for short, whitespace-sparse strings

        The fallback error vs tiktoken is typically < 10% for English text.
        """
        if _TIKTOKEN_AVAILABLE and _ENC is not None:
            return len(_ENC.encode(text))

        # Fallback: chars / 4 + word count / 2 as boundary correction
        chars = len(text)
        words = len(re.findall(r'\S+', text))
        return max(1, chars // 4 + words // 2)

    # ─── Cost projection ─────────────────────────────────────────────────────

    @staticmethod
    def estimate_cost(
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """
        Estimate API cost in USD for one call.

        Returns 0.0 if the model is unknown.
        """
        prices = PRICING.get(model)
        if not prices:
            return 0.0
        return (
            input_tokens  * prices["input"]  / 1_000_000 +
            output_tokens * prices["output"] / 1_000_000
        )

    # ─── Routing ─────────────────────────────────────────────────────────────

    def select_model(
        self,
        task_type: str,
        payload_size_tokens: int = 0,
        trade_count: int = 0,
    ) -> str:
        """
        Select the best model for a task and return the model ID string.

        Parameters
        ----------
        task_type:
            One of: daily_insights, weekly_deep_review, new_strategy_generation,
            large_history_analysis, ui_chat. Unknown types fall back to
            claude-sonnet-4-6.
        payload_size_tokens:
            Estimated input token count. Pass 0 if unknown.
        trade_count:
            Number of trades included in the analysis payload. Used as a
            secondary routing signal for insights tasks.

        Returns
        -------
        str — the Anthropic model ID to use.
        """
        decision = self._route(task_type, payload_size_tokens, trade_count)
        out_est = TYPICAL_OUTPUT_TOKENS.get(task_type, int(payload_size_tokens * self._default_output_ratio))
        self._log(decision, out_est)
        return decision.model

    def select_model_full(
        self,
        task_type: str,
        payload_size_tokens: int = 0,
        trade_count: int = 0,
    ) -> RoutingDecision:
        """
        Like select_model() but returns the full RoutingDecision dataclass
        with cost estimates and rationale. Also logs the decision.
        """
        decision = self._route(task_type, payload_size_tokens, trade_count)
        out_est = TYPICAL_OUTPUT_TOKENS.get(task_type, int(payload_size_tokens * self._default_output_ratio))
        self._log(decision, out_est)
        return decision

    def _route(
        self,
        task_type: str,
        payload_size_tokens: int,
        trade_count: int,
    ) -> RoutingDecision:
        """Pure routing logic — no side effects."""

        def _decision(model: str, extended: bool, reason: str) -> RoutingDecision:
            out_est = TYPICAL_OUTPUT_TOKENS.get(
                task_type, int(payload_size_tokens * self._default_output_ratio)
            )
            cost = self.estimate_cost(model, payload_size_tokens, out_est)
            return RoutingDecision(
                model=model,
                task_type=task_type,
                estimated_input_tokens=payload_size_tokens,
                trade_count=trade_count,
                extended_context=extended,
                cost_estimate_usd=round(cost, 6),
                reason=reason,
            )

        # ── Rule 1: new_strategy_generation ─────────────────────────────────
        # Most creative, highest-stakes task — always use best model.
        if task_type == "new_strategy_generation":
            return _decision(
                OPUS_4_8, False,
                "new_strategy_generation always uses most capable model",
            )

        # ── Rule 2: weekly_deep_review OR large trade corpus ─────────────────
        if task_type == "weekly_deep_review" or trade_count >= 500:
            reason = (
                "weekly_deep_review task" if task_type == "weekly_deep_review"
                else f"large trade corpus ({trade_count} trades ≥ 500)"
            )
            return _decision(OPUS_4_7, False, reason)

        # ── Rule 3: large_history_analysis with big context ──────────────────
        if task_type == "large_history_analysis" and payload_size_tokens > LARGE_CONTEXT_THRESHOLD:
            return _decision(
                SONNET_4_6, True,
                f"large_history_analysis with {payload_size_tokens:,} tokens "
                f"(> {LARGE_CONTEXT_THRESHOLD:,}) — Sonnet 4.6 1M-context window",
            )

        # ── Rule 4: daily_insights with small trade count ────────────────────
        if task_type == "daily_insights" and trade_count < 200:
            return _decision(
                SONNET_4_6, False,
                f"daily_insights with small trade count ({trade_count} < 200)",
            )

        # ── Rule 5: ui_chat ──────────────────────────────────────────────────
        if task_type == "ui_chat":
            return _decision(
                SONNET_4_6, False,
                "ui_chat — low-latency conversational task",
            )

        # ── Fallback ─────────────────────────────────────────────────────────
        # Covers: daily_insights with trade_count >= 200, large_history_analysis
        # under threshold, or unknown task types.
        if trade_count >= 200:
            return _decision(
                OPUS_4_7, False,
                f"trade_count ({trade_count}) ≥ 200 triggers Opus escalation",
            )

        return _decision(
            SONNET_4_6, False,
            f"unknown or unconstrained task_type '{task_type}' — default to Sonnet",
        )

    # ─── Usage query helpers ─────────────────────────────────────────────────

    def get_usage_log(self, limit: int = 100) -> list[dict]:
        """Return the most-recent `limit` routing decisions from the log."""
        try:
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute(
                        """
                        SELECT * FROM model_usage_log
                        ORDER BY id DESC LIMIT ?
                        """,
                        (limit,),
                    ).fetchall()
                    return [dict(r) for r in rows]
                finally:
                    conn.close()
        except Exception:
            return []

    def usage_summary(self) -> dict:
        """Aggregate cost + call counts from the log, grouped by model."""
        try:
            with self._lock:
                conn = self._connect()
                try:
                    rows = conn.execute(
                        """
                        SELECT model_selected,
                               COUNT(*)                              AS calls,
                               SUM(estimated_tokens)                AS total_input_tokens,
                               SUM(output_tokens_est)               AS total_output_tokens,
                               ROUND(SUM(actual_cost_usd_estimate), 6) AS total_cost_usd
                        FROM model_usage_log
                        GROUP BY model_selected
                        ORDER BY total_cost_usd DESC
                        """
                    ).fetchall()
                    return {r["model_selected"]: dict(r) for r in rows}
                finally:
                    conn.close()
        except Exception:
            return {}


# ─────────────────────────────────────────────────────────────────────────────
# CLI smoke-test  (python3 model_router.py)
# ─────────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    import os, tempfile, json

    db = os.path.join(tempfile.mkdtemp(), "test.db")
    r  = ModelRouter(db_path=db)

    cases = [
        # (task_type,                  tokens,  trade_count, expected_model)
        ("daily_insights",             5_000,   50,          SONNET_4_6),
        ("daily_insights",             5_000,   250,         OPUS_4_7),    # trade_count >= 200
        ("weekly_deep_review",         10_000,  100,         OPUS_4_7),
        ("new_strategy_generation",    2_000,   0,           OPUS_4_8),
        ("large_history_analysis",     120_000, 300,         SONNET_4_6),  # > 100k tokens
        ("large_history_analysis",     80_000,  300,         OPUS_4_7),    # ≤ 100k + trade>=200
        ("ui_chat",                    200,     0,           SONNET_4_6),
        ("any_unknown_type",           1_000,   0,           SONNET_4_6),
        ("any_unknown_type",           1_000,   600,         OPUS_4_7),    # trade_count >= 500
    ]

    print("Model Router Self-Test")
    print("=" * 72)
    all_ok = True
    for task, tokens, trades, expected in cases:
        d = r.select_model_full(task, tokens, trades)
        ok = d.model == expected
        if not ok:
            all_ok = False
        status = "✓" if ok else "✗ FAIL"
        print(f"  {status}  {task:<30} tok={tokens:<7,} trades={trades:<4}  → {d.model}")
        if not ok:
            print(f"       expected {expected}")
        print(f"         {d.reason}")

    print()
    # Token estimation
    txt = "The strategy detected a bullish reversal on TQQQ with RSI=28 and volume 2x average."
    est = r.estimate_tokens(txt)
    mode = "tiktoken" if _TIKTOKEN_AVAILABLE else "char-heuristic"
    print(f"  estimate_tokens ({mode}): '{txt[:40]}…' → {est} tokens")

    # Cost check
    cost = ModelRouter.estimate_cost(OPUS_4_8, 10_000, 2_000)
    print(f"  estimate_cost (opus-4-8, 10k in, 2k out): ${cost:.4f}")

    # Usage summary
    summary = r.usage_summary()
    print(f"\n  Usage summary ({len(cases)} calls logged):")
    for model, stats in summary.items():
        print(f"    {model:<22} calls={stats['calls']}  cost=${stats['total_cost_usd']:.4f}")

    print()
    print("All tests passed." if all_ok else "SOME TESTS FAILED.")
    import os as _os; _os.unlink(db)


if __name__ == "__main__":
    _selftest()
