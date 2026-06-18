"""
multi_tf_manager.py
===================
Multi-timeframe S/R and trend analyzer.

On every primary-TF candle close, fetches/caches the 3 lower timeframes
for a symbol, computes EMA-based trend direction, pivot-based S/R levels,
and aggregates alignment + risk signals.

Design principles
-----------------
- Zero live API calls — reads IBKR historical CSVs from disk.
- PatternPY integration point is clearly stubbed and forward-compatible.
- Missing TF files are skipped gracefully; a strategy never crashes on
  absent data.
- Snapshot persisted to `multi_tf_snapshots` in the shared SQLite DB.

Available TF file suffixes on prod (IBKR pipeline output)
----------------------------------------------------------
    monthly → {SYM}_monthly.csv
    weekly  → {SYM}_weekly.csv
    daily   → {SYM}_daily.csv
    4h      → {SYM}_4h.csv          (derived from hourly)
    hourly  → {SYM}_hourly.csv
    30min   → {SYM}_30min.csv       (from 1-min IBKR resample)
    15min   → {SYM}_15min.csv
    5min    → {SYM}_5min.csv
    1min    → {SYM}_1min.csv

Usage
-----
    from multi_tf_manager import MultiTFDataManager

    mgr = MultiTFDataManager(
        data_dir="/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data",
        db_path="/root/MITLoop/mit-loop-live/output/strategy_state.db",
    )

    status = mgr.get_multi_tf_status("AAPL", primary_tf="1W")
    print(status["lower_tf_alignment"])   # "BULLISH"
    print(status["risk_level"])           # "NORMAL"
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# PatternPy integration — import lazily so multi_tf_manager works without it
try:
    from pattern_detector import PatternDetector as _PatternDetector, _PATTERNPY_AVAILABLE
    _pattern_detector: _PatternDetector | None = _PatternDetector()
except ImportError:
    _pattern_detector = None
    _PATTERNPY_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Timeframe constants
# ─────────────────────────────────────────────────────────────────────────────

# Display name → file-system suffix used in CSV file names
_TF_TO_FILE: Dict[str, str] = {
    "1M":    "monthly",
    "1W":    "weekly",
    "1D":    "daily",
    "4H":    "4h",
    "1H":    "hourly",
    "30min": "30min",
    "15min": "15min",
    "5min":  "5min",
    "1min":  "1min",
}

# Default 3-level lower-TF hierarchy per primary timeframe.
# Only TFs whose CSV files actually exist on disk are used at runtime.
DEFAULT_HIERARCHY: Dict[str, List[str]] = {
    "1M":    ["1W",    "1D",    "4H"],
    "1W":    ["1D",    "4H",    "1H"],
    "1D":    ["4H",    "1H",    "30min"],
    "4H":    ["1H",    "30min", "15min"],
    "1H":    ["30min", "15min", "5min"],
    "30min": ["15min", "5min",  "1min"],
    "15min": ["5min",  "1min"],
}

# ─────────────────────────────────────────────────────────────────────────────
# Algorithm parameters
# ─────────────────────────────────────────────────────────────────────────────
EMA_FAST           = 20
EMA_SLOW           = 50
EMA_SLOPE_BARS     = 5       # bars to measure EMA-20 slope for trend confirm
SR_LOOKBACK        = 200     # candles used for pivot detection
PIVOT_WINDOW       = 5       # pivot high/low half-window (bars on each side)
CLUSTER_PCT        = 0.003   # levels within 0.3% → same cluster
APPROACH_THRESHOLD = 1.5     # % → is_approaching_support / resistance
MIN_SR_BARS        = 60      # minimum bars needed before S/R is reliable

# Alignment / risk thresholds
BULLISH_MIN_TFS    = 2       # ≥ N TFs trending up → BULLISH
BEARISH_MIN_TFS    = 2       # ≥ N TFs trending down → BEARISH
RISK_CAUTION_TFS   = 2       # ≥ N TFs approaching resistance → CAUTION
RISK_WATCH_TFS     = 1       # ≥ N TFs approaching resistance → WATCH


# ─────────────────────────────────────────────────────────────────────────────
# Data structures
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TFAnalysis:
    """Result of analyzing one lower timeframe."""
    tf: str
    trend: str                            # "up" | "down" | "sideways"
    support: Optional[float]
    resistance: Optional[float]
    distance_to_support_pct: Optional[float]
    distance_to_resistance_pct: Optional[float]
    is_approaching_support: bool
    is_approaching_resistance: bool
    pattern: Optional[str]                # patternPY stub → None until integrated
    current_price: float
    ema_fast: float
    ema_slow: float
    bars_loaded: int
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "trend": self.trend,
            "support": round(self.support, 4) if self.support else None,
            "resistance": round(self.resistance, 4) if self.resistance else None,
            "distance_to_support_pct":
                round(self.distance_to_support_pct, 3) if self.distance_to_support_pct is not None else None,
            "distance_to_resistance_pct":
                round(self.distance_to_resistance_pct, 3) if self.distance_to_resistance_pct is not None else None,
            "is_approaching_support": self.is_approaching_support,
            "is_approaching_resistance": self.is_approaching_resistance,
            "pattern": self.pattern,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main class
# ─────────────────────────────────────────────────────────────────────────────

class MultiTFDataManager:
    """
    Analyze up to 3 lower timeframes for any symbol and primary TF.

    Parameters
    ----------
    data_dir:
        Directory containing IBKR CSV files (`{SYM}_{tf}.csv`).
    db_path:
        Shared SQLite DB path (same file as StrategyStateLogger).
    custom_hierarchy:
        Override DEFAULT_HIERARCHY for specific primary TFs.
        e.g. {"1W": ["1D", "4H", "1H"]}
    cache_ttl_seconds:
        How long to keep a loaded DataFrame in memory before re-reading disk.
        Default 300 s (5 min) — covers one full scan cycle.
    """

    def __init__(
        self,
        data_dir: str,
        db_path: str = "output/strategy_state.db",
        custom_hierarchy: Optional[Dict[str, List[str]]] = None,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self._data_dir      = data_dir
        self._db_path       = db_path
        self._cache_ttl     = cache_ttl_seconds
        self._lock          = threading.Lock()
        self._df_cache: Dict[str, Tuple[pd.DataFrame, float]] = {}  # key → (df, expiry_ts)
        self._hierarchy     = {**DEFAULT_HIERARCHY, **(custom_hierarchy or {})}
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
                    CREATE TABLE IF NOT EXISTS multi_tf_snapshots (
                        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                        snapshot_time       TEXT    NOT NULL,
                        symbol              TEXT    NOT NULL,
                        primary_tf          TEXT    NOT NULL,
                        entry_snapshot_id   TEXT,
                        lower_tf_alignment  TEXT,
                        risk_level          TEXT,
                        timeframes_json     TEXT    NOT NULL,
                        full_status_json    TEXT    NOT NULL
                    );
                    CREATE INDEX IF NOT EXISTS idx_multitf_sym_ts
                        ON multi_tf_snapshots (symbol, snapshot_time DESC);
                    CREATE INDEX IF NOT EXISTS idx_multitf_snap_id
                        ON multi_tf_snapshots (entry_snapshot_id)
                        WHERE entry_snapshot_id IS NOT NULL;
                """)
                conn.commit()
            finally:
                conn.close()

    # ─── Data loading (with TTL cache) ───────────────────────────────────────

    def _csv_path(self, symbol: str, tf_display: str) -> Optional[str]:
        """Return the CSV path if the file exists, else None."""
        suffix = _TF_TO_FILE.get(tf_display)
        if not suffix:
            return None
        path = os.path.join(self._data_dir, f"{symbol}_{suffix}.csv")
        return path if os.path.exists(path) else None

    def _load_df(self, symbol: str, tf_display: str, n: int = SR_LOOKBACK) -> Optional[pd.DataFrame]:
        """
        Load last `n` bars from the CSV for (symbol, tf).
        Uses an in-memory TTL cache so repeated calls within one scan cycle
        don't hit disk.
        """
        cache_key = f"{symbol}|{tf_display}"
        now = time.monotonic()

        # Cache hit
        cached = self._df_cache.get(cache_key)
        if cached is not None:
            df, expiry = cached
            if now < expiry:
                return df.iloc[-n:].copy() if len(df) >= n else df.copy()

        path = self._csv_path(symbol, tf_display)
        if path is None:
            return None

        try:
            df = pd.read_csv(
                path,
                usecols=lambda c: c in ("date", "open", "high", "low", "close", "volume"),
                parse_dates=["date"],
            )
            df = df.dropna(subset=["open", "high", "low", "close"])
            df = df.sort_values("date").reset_index(drop=True)
            for col in ("open", "high", "low", "close", "volume"):
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            df = df.dropna(subset=["close"])

            # Store full history in cache; return only last n
            self._df_cache[cache_key] = (df, now + self._cache_ttl)
            return df.iloc[-n:].copy() if len(df) >= n else df.copy()
        except Exception:
            return None

    # ─── Indicator computation ────────────────────────────────────────────────

    @staticmethod
    def _add_emas(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
        return df

    @staticmethod
    def _calc_trend(df: pd.DataFrame) -> Tuple[str, float, float]:
        """
        Determine trend using EMA20 vs EMA50 + 5-bar EMA20 slope.

        Returns (trend, ema_fast_last, ema_slow_last).
        """
        if len(df) < EMA_SLOW + 5:
            return "sideways", float("nan"), float("nan")

        df = MultiTFDataManager._add_emas(df)
        last       = df.iloc[-1]
        ema_fast   = float(last["ema_fast"])
        ema_slow   = float(last["ema_slow"])
        slope_bars = min(EMA_SLOPE_BARS, len(df) - 1)
        slope      = ema_fast - float(df["ema_fast"].iloc[-(slope_bars + 1)])

        if ema_fast > ema_slow and slope > 0:
            trend = "up"
        elif ema_fast < ema_slow and slope < 0:
            trend = "down"
        else:
            trend = "sideways"

        return trend, ema_fast, ema_slow

    # ─── Support / Resistance detection ─────────────────────────────────────

    @staticmethod
    def _pivot_highs(df: pd.DataFrame, n: int = PIVOT_WINDOW) -> List[float]:
        """Local maxima: bars whose high > n bars on each side."""
        highs = df["high"].values
        out = []
        for i in range(n, len(highs) - n):
            window = highs[max(0, i - n) : i + n + 1]
            if highs[i] == window.max() and list(window).count(highs[i]) == 1:
                out.append(float(highs[i]))
        return out

    @staticmethod
    def _pivot_lows(df: pd.DataFrame, n: int = PIVOT_WINDOW) -> List[float]:
        """Local minima: bars whose low < n bars on each side."""
        lows = df["low"].values
        out = []
        for i in range(n, len(lows) - n):
            window = lows[max(0, i - n) : i + n + 1]
            if lows[i] == window.min() and list(window).count(lows[i]) == 1:
                out.append(float(lows[i]))
        return out

    @staticmethod
    def _cluster_levels(levels: List[float], cluster_pct: float = CLUSTER_PCT) -> List[float]:
        """
        Merge pivot levels that are within cluster_pct of each other into a
        single representative level (mean of the cluster). Removes duplicates.
        """
        if not levels:
            return []
        sorted_lvls = sorted(set(levels))
        clusters: List[List[float]] = [[sorted_lvls[0]]]
        for lvl in sorted_lvls[1:]:
            ref = clusters[-1][-1]
            if ref > 0 and (lvl - ref) / ref <= cluster_pct:
                clusters[-1].append(lvl)
            else:
                clusters.append([lvl])
        return [float(np.mean(c)) for c in clusters]

    def _find_sr(
        self, df: pd.DataFrame, current_price: float
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Find nearest support (below) and resistance (above) using pivot levels.
        Returns (support, resistance) — either may be None.
        """
        if len(df) < MIN_SR_BARS:
            return None, None

        resistance_candidates = self._cluster_levels(self._pivot_highs(df))
        support_candidates    = self._cluster_levels(self._pivot_lows(df))

        supports    = [l for l in support_candidates    if l < current_price * (1 - 0.0005)]
        resistances = [l for l in resistance_candidates if l > current_price * (1 + 0.0005)]

        support    = max(supports)    if supports    else None
        resistance = min(resistances) if resistances else None

        return support, resistance

    # ─── patternPY integration stub ─────────────────────────────────────────

    def _get_pattern_signal(
        self,
        df: pd.DataFrame,
        symbol: str,
        tf: str,
    ) -> Optional[str]:
        """
        Returns the most-recently active pattern for this TF, or None.
        Uses PatternDetector.detect_all() — STUB replaced with real PatternPy.
        """
        if _pattern_detector is None or not _PATTERNPY_AVAILABLE:
            return None
        try:
            result = _pattern_detector.detect_all(df, lookback=100)
            active = result.get("active_patterns", [])
            return active[0] if active else None
        except Exception:
            return None

    # ─── Single-TF analysis ─────────────────────────────────────────────────

    def _find_sr_patternpy(
        self, df: pd.DataFrame, current_price: float
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Support/Resistance via PatternPy calculate_support_resistance.
        ⚠ REPLACED: was pivot-based horizontal levels (_find_sr).
        PatternPy uses rolling mean ± 2σ — dynamic statistical bands, not
        fixed price levels. More responsive but less precise than pivot S/R.
        Falls back to the original pivot method when PatternPy unavailable.
        """
        if _pattern_detector is not None and _PATTERNPY_AVAILABLE:
            try:
                result = _pattern_detector.detect_all(df, lookback=100)
                sup = result.get("support_level")
                res = result.get("resistance_level")
                # Validate: levels must be on correct side of current price
                if sup is not None and sup >= current_price:
                    sup = None
                if res is not None and res <= current_price:
                    res = None
                return sup, res
            except Exception:
                pass
        # Fallback: original pivot-based method
        return self._find_sr(df, current_price)

    def _analyze_tf(self, symbol: str, tf: str) -> Optional[TFAnalysis]:
        """
        Full analysis for one (symbol, tf) combination.
        Returns None if no data file exists for this TF.
        """
        df = self._load_df(symbol, tf)
        if df is None or len(df) < 5:
            return None

        current_price = float(df["close"].iloc[-1])

        # Trend
        try:
            trend, ema_fast, ema_slow = self._calc_trend(df)
        except Exception as exc:
            return TFAnalysis(
                tf=tf, trend="sideways", support=None, resistance=None,
                distance_to_support_pct=None, distance_to_resistance_pct=None,
                is_approaching_support=False, is_approaching_resistance=False,
                pattern=None, current_price=current_price,
                ema_fast=float("nan"), ema_slow=float("nan"),
                bars_loaded=len(df), error=str(exc),
            )

        # S/R via PatternPy (replaces pivot-based _find_sr)
        support, resistance = self._find_sr_patternpy(df, current_price)

        d_sup = (
            (current_price - support) / current_price * 100
            if support is not None and current_price > 0 else None
        )
        d_res = (
            (resistance - current_price) / current_price * 100
            if resistance is not None and current_price > 0 else None
        )

        return TFAnalysis(
            tf=tf,
            trend=trend,
            support=support,
            resistance=resistance,
            distance_to_support_pct=d_sup,
            distance_to_resistance_pct=d_res,
            is_approaching_support=d_sup is not None and d_sup < APPROACH_THRESHOLD,
            is_approaching_resistance=d_res is not None and d_res < APPROACH_THRESHOLD,
            pattern=self._get_pattern_signal(df, symbol, tf),
            current_price=current_price,
            ema_fast=ema_fast,
            ema_slow=ema_slow,
            bars_loaded=len(df),
        )

    # ─── Aggregation ─────────────────────────────────────────────────────────

    @staticmethod
    def _lower_tf_alignment(analyses: List[TFAnalysis]) -> str:
        """
        BULLISH  — 2+ TFs trending up
        BEARISH  — 2+ TFs trending down
        MIXED    — split or all sideways
        """
        valid = [a for a in analyses if a.error is None]
        ups   = sum(1 for a in valid if a.trend == "up")
        downs = sum(1 for a in valid if a.trend == "down")
        if ups >= BULLISH_MIN_TFS:
            return "BULLISH"
        if downs >= BEARISH_MIN_TFS:
            return "BEARISH"
        return "MIXED"

    @staticmethod
    def _risk_level(analyses: List[TFAnalysis]) -> str:
        """
        HIGH_RISK — 3/3 TFs approaching resistance
        CAUTION   — 2+ TFs approaching resistance
        WATCH     — 1 TF approaching resistance
        NORMAL    — no resistance warnings
        """
        valid = [a for a in analyses if a.error is None]
        n = sum(1 for a in valid if a.is_approaching_resistance)
        if n >= len(valid) and n > 0:
            return "HIGH_RISK"
        if n >= RISK_CAUTION_TFS:
            return "CAUTION"
        if n >= RISK_WATCH_TFS:
            return "WATCH"
        return "NORMAL"

    # ─── Public API ──────────────────────────────────────────────────────────

    def get_multi_tf_status(
        self,
        symbol: str,
        primary_tf: str,
        entry_snapshot_id: Optional[str] = None,
        persist: bool = True,
    ) -> dict:
        """
        Build and return the full multi-TF status dict for a symbol.

        Parameters
        ----------
        symbol:
            Ticker symbol, e.g. "SPY".
        primary_tf:
            Primary strategy timeframe, e.g. "1W".
        entry_snapshot_id:
            If provided, stored in the DB row to link this snapshot to the
            corresponding entry in strategy_snapshots.
        persist:
            Write the result to multi_tf_snapshots table (default True).

        Returns
        -------
        dict matching the multi_tf_status schema documented in the module
        docstring.
        """
        lower_tfs = self._hierarchy.get(primary_tf, [])[:3]  # max 3 lower TFs
        snapshot_time = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        analyses: Dict[str, Optional[TFAnalysis]] = {}
        for tf in lower_tfs:
            analyses[tf] = self._analyze_tf(symbol, tf)

        valid_analyses = [a for a in analyses.values() if a is not None]

        alignment  = self._lower_tf_alignment(valid_analyses)
        risk       = self._risk_level(valid_analyses)

        timeframes_dict = {}
        for tf, a in analyses.items():
            if a is None:
                timeframes_dict[tf] = {"error": "no_data_file"}
            else:
                timeframes_dict[tf] = a.to_dict()

        status = {
            "symbol":             symbol,
            "primary_tf":         primary_tf,
            "lower_tfs_requested": lower_tfs,
            "lower_tfs_loaded":   [tf for tf, a in analyses.items() if a is not None],
            "snapshot_time":      snapshot_time,
            "timeframes":         timeframes_dict,
            "lower_tf_alignment": alignment,
            "risk_level":         risk,
        }

        if persist:
            self._persist(status, entry_snapshot_id)

        return status

    def get_lower_tfs(self, primary_tf: str) -> List[str]:
        """Return the configured lower TF list for a primary TF."""
        return self._hierarchy.get(primary_tf, [])[:3]

    def available_tfs_for_symbol(self, symbol: str) -> List[str]:
        """Return all display-name TFs that have a data file on disk."""
        return [tf for tf in _TF_TO_FILE if self._csv_path(symbol, tf) is not None]

    def invalidate_cache(self, symbol: Optional[str] = None) -> None:
        """Clear the in-memory DF cache (all symbols, or one symbol)."""
        if symbol is None:
            self._df_cache.clear()
        else:
            keys = [k for k in self._df_cache if k.startswith(f"{symbol}|")]
            for k in keys:
                del self._df_cache[k]

    # ─── Persistence ─────────────────────────────────────────────────────────

    def _persist(self, status: dict, entry_snapshot_id: Optional[str]) -> None:
        try:
            with self._lock:
                conn = self._connect()
                try:
                    conn.execute(
                        """
                        INSERT INTO multi_tf_snapshots
                        (snapshot_time, symbol, primary_tf, entry_snapshot_id,
                         lower_tf_alignment, risk_level,
                         timeframes_json, full_status_json)
                        VALUES (?,?,?,?,?,?,?,?)
                        """,
                        (
                            status["snapshot_time"],
                            status["symbol"],
                            status["primary_tf"],
                            entry_snapshot_id,
                            status["lower_tf_alignment"],
                            status["risk_level"],
                            json.dumps(status["timeframes"], default=str),
                            json.dumps(status, default=str),
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
        except Exception:
            pass

    # ─── Query helpers ───────────────────────────────────────────────────────

    def get_latest_snapshot(self, symbol: str, primary_tf: str) -> Optional[dict]:
        """Return the most-recent persisted multi_tf_status for a symbol."""
        try:
            with self._lock:
                conn = self._connect()
                try:
                    row = conn.execute(
                        """
                        SELECT full_status_json FROM multi_tf_snapshots
                        WHERE symbol = ? AND primary_tf = ?
                        ORDER BY id DESC LIMIT 1
                        """,
                        (symbol, primary_tf),
                    ).fetchone()
                    if not row:
                        return None
                    return json.loads(row["full_status_json"])
                finally:
                    conn.close()
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI endpoint helper
# ─────────────────────────────────────────────────────────────────────────────

def make_mgr_from_env() -> MultiTFDataManager:
    """
    Construct a MultiTFDataManager from environment / well-known prod paths.
    Useful in main_live_updated.py:

        from multi_tf_manager import make_mgr_from_env
        tf_mgr = make_mgr_from_env()
    """
    data_dir = os.environ.get(
        "HISTORICAL_DATA_DIR",
        "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data",
    )
    db_path = os.environ.get(
        "STRATEGY_STATE_DB",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "output", "strategy_state.db"),
    )
    return MultiTFDataManager(data_dir=data_dir, db_path=db_path)


# ─────────────────────────────────────────────────────────────────────────────
# Self-test  (python3 multi_tf_manager.py)
# ─────────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    import tempfile, os as _os

    LOCAL_DATA = "/Users/salmog/test/auto_learn/historical_data"
    DB = _os.path.join(tempfile.mkdtemp(), "test_multitf.db")

    mgr = MultiTFDataManager(data_dir=LOCAL_DATA, db_path=DB)

    # ── What TFs are available locally?
    syms = sorted({f.split("_")[0] for f in _os.listdir(LOCAL_DATA) if f.endswith("_weekly.csv")})
    sym = syms[0] if syms else None

    print("Multi-TF Manager Self-Test")
    print("=" * 70)

    if not sym:
        print("  No weekly CSV files found in", LOCAL_DATA)
        return

    available = mgr.available_tfs_for_symbol(sym)
    print(f"  Symbol: {sym}")
    print(f"  Available TFs on disk: {available}")

    for primary_tf in ("1W", "1D", "4H"):
        lower = mgr.get_lower_tfs(primary_tf)
        present = [tf for tf in lower if tf in available]
        print(f"  {primary_tf} hierarchy: {lower}  →  on-disk: {present}")

    # ── Main call
    print()
    status = mgr.get_multi_tf_status(sym, "1W", persist=True)

    print(f"  symbol:             {status['symbol']}")
    print(f"  primary_tf:         {status['primary_tf']}")
    print(f"  lower_tf_alignment: {status['lower_tf_alignment']}")
    print(f"  risk_level:         {status['risk_level']}")
    print(f"  TFs loaded:         {status['lower_tfs_loaded']}")
    print()

    for tf, data in status["timeframes"].items():
        if "error" in data:
            print(f"  [{tf}] no data file")
            continue
        sup  = f"${data['support']:.2f}"  if data['support']    else "—"
        res  = f"${data['resistance']:.2f}" if data['resistance'] else "—"
        d_s  = f"{data['distance_to_support_pct']:.2f}%"    if data['distance_to_support_pct']    is not None else "—"
        d_r  = f"{data['distance_to_resistance_pct']:.2f}%" if data['distance_to_resistance_pct'] is not None else "—"
        asr  = "⚠ near S" if data['is_approaching_support']    else ""
        ares = "⚠ near R" if data['is_approaching_resistance'] else ""
        pat  = data['pattern'] or "—"
        print(
            f"  [{tf}]  trend={data['trend']:<9}  "
            f"sup={sup:<10}  res={res:<10}  "
            f"d_s={d_s:<7}  d_r={d_r:<7}  "
            f"pat={pat}  {asr}{ares}"
        )

    # ── Cache round-trip
    status2 = mgr.get_multi_tf_status(sym, "1W", persist=False)
    assert status["symbol"] == status2["symbol"]
    print("\n  Cache hit: same result on second call (no extra file reads).")

    # ── DB persistence
    latest = mgr.get_latest_snapshot(sym, "1W")
    assert latest is not None
    print("  DB read-back: OK.")

    # ── Alignment / risk logic unit tests
    from multi_tf_manager import TFAnalysis, MultiTFDataManager as M

    def _mock(trend, approaching_resistance=False):
        return TFAnalysis(
            tf="1D", trend=trend, support=500.0, resistance=510.0,
            distance_to_support_pct=2.0,
            distance_to_resistance_pct=0.5 if approaching_resistance else 3.0,
            is_approaching_support=False,
            is_approaching_resistance=approaching_resistance,
            pattern=None, current_price=508.0,
            ema_fast=507.0, ema_slow=504.0, bars_loaded=200,
        )

    assert M._lower_tf_alignment([_mock("up"), _mock("up"), _mock("down")]) == "BULLISH"
    assert M._lower_tf_alignment([_mock("down"), _mock("down"), _mock("up")]) == "BEARISH"
    assert M._lower_tf_alignment([_mock("up"), _mock("down"), _mock("sideways")]) == "MIXED"
    assert M._risk_level([_mock("up", True), _mock("up", True), _mock("up")]) == "CAUTION"
    assert M._risk_level([_mock("up", True), _mock("up", True), _mock("up", True)]) == "HIGH_RISK"
    assert M._risk_level([_mock("up"), _mock("up"), _mock("up")]) == "NORMAL"
    print("  Alignment / risk unit tests: all passed.")

    _os.unlink(DB)
    print("\nAll tests passed.")


if __name__ == "__main__":
    _selftest()
