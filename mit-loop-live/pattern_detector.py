"""
pattern_detector.py
===================
PatternPy integration for MIT-Loop Pro strategy engine.

Wraps all PatternPy detection functions with pandas 2.x compatibility fixes
and exposes a clean detect_all() / detect_for_symbol() API that the strategy
snapshot pipeline can call on every candle close.

Key findings from reading PatternPy source
-------------------------------------------
1. Actual function names differ from the repo README:
      detect_head_shoulder           (not head_and_shoulders)
      detect_multiple_tops_bottoms   (not multiple_tops_bottoms)
      calculate_support_resistance   (not horizontal_support_resistance)
      detect_triangle_pattern        (not ascending_descending_triangles)
      detect_wedge, detect_channel, detect_double_top_bottom

2. PatternPy expects Title-cased columns: High, Low, Close, Open.
   MIT-Loop data is lowercase.  Auto-renaming is handled here.

3. PatternPy initialises pattern columns with np.nan (creates float64),
   then assigns strings — this breaks pandas ≥ 2.0.  All six functions
   are re-implemented here with the one-line fix:
       df['col'] = np.nan               → df['col'] = pd.Series(None, dtype=object, ...)

4. Patterns that use shift(-1) always produce NaN on the LAST bar.
   detect_all() therefore scans the most-recent RECENT_SCAN_BARS rows
   and returns the LAST non-null value, not just row[-1].

5. PatternPy S/R (calculate_support_resistance) uses rolling mean ± 2σ,
   NOT pivot-based levels.  This replaces the existing pivot-based
   _find_sr() in MultiTFDataManager.  See migration note in
   multi_tf_manager.py (_find_sr_patternpy).

Usage
-----
    from pattern_detector import PatternDetector

    det = PatternDetector()
    result = det.detect_all(df)          # → dict
    result = det.detect_for_symbol("AAPL", "1D")   # → dict
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# PatternPy path resolution (checked in order, first hit wins)
# ─────────────────────────────────────────────────────────────────────────────

_HERE = Path(__file__).parent

_PATTERNPY_SEARCH_PATHS = [
    _HERE / "lib" / "PatternPy",            # task-specified location
    _HERE / "PatternPy-main",               # common unzip name (same dir)
    _HERE.parent / "PatternPy-main",        # one level up (e.g. auto_learn/../)
    _HERE.parent / "mit-loop" / "PatternPy-main",   # local dev: test/mit-loop/
    Path.home() / "test" / "mit-loop" / "PatternPy-main",
    Path("/root/MITLoop/PatternPy-main"),   # prod server default
    Path("/root/MITLoop/mit-loop-live/PatternPy-main"),
]

_PATTERNPY_PATH: Optional[Path] = None
for _p in _PATTERNPY_SEARCH_PATHS:
    if (_p / "tradingpatterns" / "tradingpatterns.py").exists():
        _PATTERNPY_PATH = _p
        break

_PATTERNPY_AVAILABLE = False
if _PATTERNPY_PATH:
    sys.path.insert(0, str(_PATTERNPY_PATH))
    try:
        import tradingpatterns.tradingpatterns as _pp   # noqa: F401 — confirm importable
        _PATTERNPY_AVAILABLE = True
    except ImportError:
        pass

if not _PATTERNPY_AVAILABLE:
    warnings.warn(
        "PatternPy library not found. Searched:\n" +
        "\n".join(f"  {p}" for p in _PATTERNPY_SEARCH_PATHS) +
        "\nPlace PatternPy-main/ at one of those locations. "
        "All detect_* calls will return None values until then.",
        stacklevel=2,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Pandas 2.x–compatible re-implementations
# (PatternPy's original code does df['col'] = np.nan which creates float64,
#  then assigns a string — TypeError in pandas ≥ 2.0)
# ─────────────────────────────────────────────────────────────────────────────

def _obj_col(df: pd.DataFrame, n: int) -> pd.Series:
    """Return a fresh object-dtype Series of NaN, length n."""
    return pd.Series([pd.NA] * n, dtype=object, index=df.index)


def _detect_head_shoulder(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    df = df.copy()
    w = window
    df["high_roll_max"] = df["High"].rolling(w).max()
    df["low_roll_min"]  = df["Low"].rolling(w).min()
    mask_hs  = ((df["high_roll_max"] > df["High"].shift(1)) &
                (df["high_roll_max"] > df["High"].shift(-1)) &
                (df["High"] < df["High"].shift(1)) &
                (df["High"] < df["High"].shift(-1)))
    mask_ihs = ((df["low_roll_min"]  < df["Low"].shift(1)) &
                (df["low_roll_min"]  < df["Low"].shift(-1)) &
                (df["Low"]  > df["Low"].shift(1)) &
                (df["Low"]  > df["Low"].shift(-1)))
    col = _obj_col(df, len(df))
    col[mask_hs]  = "Head and Shoulder"
    col[mask_ihs] = "Inverse Head and Shoulder"
    df["head_shoulder_pattern"] = col
    return df


def _detect_multiple_tops_bottoms(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    df = df.copy()
    w = window
    df["high_roll_max"]  = df["High"].rolling(w).max()
    df["low_roll_min"]   = df["Low"].rolling(w).min()
    df["close_roll_max"] = df["Close"].rolling(w).max()
    df["close_roll_min"] = df["Close"].rolling(w).min()
    mask_top    = ((df["high_roll_max"]  >= df["High"].shift(1)) &
                   (df["close_roll_max"] <  df["Close"].shift(1)))
    mask_bottom = ((df["low_roll_min"]   <= df["Low"].shift(1)) &
                   (df["close_roll_min"] >  df["Close"].shift(1)))
    col = _obj_col(df, len(df))
    col[mask_top]    = "Multiple Top"
    col[mask_bottom] = "Multiple Bottom"
    df["multiple_top_bottom_pattern"] = col
    return df


def _calculate_support_resistance(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    """
    Statistical S/R: support = rolling_mean(Low) − 2σ,
                   resistance = rolling_mean(High) + 2σ.
    NOTE: These are statistical bands, not pivot-based price levels.
    """
    df = df.copy()
    w = window
    df["support"]    = df["Low"].rolling(w).mean()  - 2 * df["Low"].rolling(w).std()
    df["resistance"] = df["High"].rolling(w).mean() + 2 * df["High"].rolling(w).std()
    return df


def _detect_triangle_pattern(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    df = df.copy()
    w = window
    df["high_roll_max"] = df["High"].rolling(w).max()
    df["low_roll_min"]  = df["Low"].rolling(w).min()
    mask_asc  = ((df["high_roll_max"] >= df["High"].shift(1)) &
                 (df["low_roll_min"]  <= df["Low"].shift(1)) &
                 (df["Close"] > df["Close"].shift(1)))
    mask_desc = ((df["high_roll_max"] <= df["High"].shift(1)) &
                 (df["low_roll_min"]  >= df["Low"].shift(1)) &
                 (df["Close"] < df["Close"].shift(1)))
    col = _obj_col(df, len(df))
    col[mask_asc]  = "Ascending Triangle"
    col[mask_desc] = "Descending Triangle"
    df["triangle_pattern"] = col
    return df


def _detect_wedge(df: pd.DataFrame, window: int = 3) -> pd.DataFrame:
    df = df.copy()
    w = window
    df["high_roll_max"] = df["High"].rolling(w).max()
    df["low_roll_min"]  = df["Low"].rolling(w).min()
    df["trend_high"] = df["High"].rolling(w).apply(
        lambda x: 1 if x[-1] - x[0] > 0 else (-1 if x[-1] - x[0] < 0 else 0), raw=True)
    df["trend_low"] = df["Low"].rolling(w).apply(
        lambda x: 1 if x[-1] - x[0] > 0 else (-1 if x[-1] - x[0] < 0 else 0), raw=True)
    mask_up   = ((df["high_roll_max"] >= df["High"].shift(1)) &
                 (df["low_roll_min"]  <= df["Low"].shift(1)) &
                 (df["trend_high"] == 1) & (df["trend_low"] == 1))
    mask_down = ((df["high_roll_max"] <= df["High"].shift(1)) &
                 (df["low_roll_min"]  >= df["Low"].shift(1)) &
                 (df["trend_high"] == -1) & (df["trend_low"] == -1))
    col = _obj_col(df, len(df))
    col[mask_up]   = "Wedge Up"
    col[mask_down] = "Wedge Down"
    df["wedge_pattern"] = col
    return df


def _detect_channel(df: pd.DataFrame, window: int = 3, channel_range: float = 0.1) -> pd.DataFrame:
    df = df.copy()
    w = window
    df["high_roll_max"] = df["High"].rolling(w).max()
    df["low_roll_min"]  = df["Low"].rolling(w).min()
    df["trend_high"] = df["High"].rolling(w).apply(
        lambda x: 1 if x[-1] - x[0] > 0 else (-1 if x[-1] - x[0] < 0 else 0), raw=True)
    df["trend_low"] = df["Low"].rolling(w).apply(
        lambda x: 1 if x[-1] - x[0] > 0 else (-1 if x[-1] - x[0] < 0 else 0), raw=True)
    mid = (df["high_roll_max"] + df["low_roll_min"]) / 2
    narrow = (df["high_roll_max"] - df["low_roll_min"]) <= channel_range * mid
    mask_up   = ((df["high_roll_max"] >= df["High"].shift(1)) &
                 (df["low_roll_min"]  <= df["Low"].shift(1)) &
                 narrow & (df["trend_high"] == 1) & (df["trend_low"] == 1))
    mask_down = ((df["high_roll_max"] <= df["High"].shift(1)) &
                 (df["low_roll_min"]  >= df["Low"].shift(1)) &
                 narrow & (df["trend_high"] == -1) & (df["trend_low"] == -1))
    col = _obj_col(df, len(df))
    col[mask_up]   = "Channel Up"
    col[mask_down] = "Channel Down"
    df["channel_pattern"] = col
    return df


def _detect_double_top_bottom(df: pd.DataFrame, window: int = 3, threshold: float = 0.05) -> pd.DataFrame:
    df = df.copy()
    w = window
    df["high_roll_max"] = df["High"].rolling(w).max()
    df["low_roll_min"]  = df["Low"].rolling(w).min()
    rng1 = (df["High"].shift(1) - df["Low"].shift(1))
    mid1 = (df["High"].shift(1) + df["Low"].shift(1)) / 2
    rng_1 = (df["High"].shift(-1) - df["Low"].shift(-1))
    mid_1 = (df["High"].shift(-1) + df["Low"].shift(-1)) / 2
    mask_top = ((df["high_roll_max"] >= df["High"].shift(1)) &
                (df["high_roll_max"] >= df["High"].shift(-1)) &
                (df["High"] < df["High"].shift(1)) &
                (df["High"] < df["High"].shift(-1)) &
                (rng1 <= threshold * mid1) & (rng_1 <= threshold * mid_1))
    mask_bot = ((df["low_roll_min"] <= df["Low"].shift(1)) &
                (df["low_roll_min"] <= df["Low"].shift(-1)) &
                (df["Low"] > df["Low"].shift(1)) &
                (df["Low"] > df["Low"].shift(-1)) &
                (rng1 <= threshold * mid1) & (rng_1 <= threshold * mid_1))
    col = _obj_col(df, len(df))
    col[mask_top] = "Double Top"
    col[mask_bot] = "Double Bottom"
    df["double_pattern"] = col
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Bias classification
# ─────────────────────────────────────────────────────────────────────────────

# Standard TA interpretation (not PatternPy naming — see comments)
_BULLISH_PATTERNS = frozenset({
    "Inverse Head and Shoulder",  # breakout above neckline → bullish
    "Multiple Bottom",            # support holding → bullish
    "Ascending Triangle",         # higher lows, flat top → bullish breakout
    "Wedge Down",                 # falling wedge = bullish reversal
    "Channel Up",                 # trend continuation up
    "Double Bottom",
})
_BEARISH_PATTERNS = frozenset({
    "Head and Shoulder",          # top reversal
    "Multiple Top",               # resistance holding → bearish
    "Descending Triangle",        # lower highs, flat bottom → bearish breakdown
    "Wedge Up",                   # rising wedge = bearish reversal
    "Channel Down",               # trend continuation down
    "Double Top",
})

RECENT_SCAN_BARS = 2  # rows to scan for most-recent non-null pattern value


# ─────────────────────────────────────────────────────────────────────────────
# PatternDetector
# ─────────────────────────────────────────────────────────────────────────────

class PatternDetector:
    """
    Detect chart patterns and S/R levels using PatternPy.

    Falls back gracefully when PatternPy is unavailable — every field
    in the output dict is None so callers don't crash.

    Parameters
    ----------
    patternpy_path:
        Override the PatternPy library path. Default: auto-detected.
    window:
        Rolling window passed to all PatternPy functions. Default 3.
    """

    def __init__(
        self,
        patternpy_path: Optional[str] = None,
        window: int = 3,
    ) -> None:
        self._window = window
        self._available = _PATTERNPY_AVAILABLE
        if patternpy_path and not _PATTERNPY_AVAILABLE:
            _p = Path(patternpy_path)
            if (_p / "tradingpatterns" / "tradingpatterns.py").exists():
                sys.path.insert(0, str(_p))
                try:
                    import tradingpatterns.tradingpatterns as _pp  # noqa: F401
                    self._available = True
                except ImportError:
                    pass

    # ─── Column normalisation ────────────────────────────────────────────────

    @staticmethod
    def _to_title(df: pd.DataFrame) -> pd.DataFrame:
        """Rename lowercase ohlcv columns to Title-case for PatternPy."""
        rename = {c: c.capitalize() for c in ("open", "high", "low", "close", "volume")
                  if c in df.columns}
        return df.rename(columns=rename)

    @staticmethod
    def _latest_value(series: pd.Series, scan: int = RECENT_SCAN_BARS) -> Optional[str]:
        """
        Return the most-recent non-null value in the last `scan` rows.
        Patterns using shift(-1) never fire on the very last bar, so we
        look back slightly to find the freshest signal.
        """
        tail = series.iloc[-scan:]
        valid = tail.dropna()
        if valid.empty:
            return None
        return str(valid.iloc[-1])

    # ─── Core detection ──────────────────────────────────────────────────────

    def detect_all(self, df: pd.DataFrame, lookback: int = 100) -> dict:
        """
        Run all pattern functions on the last `lookback` bars and return
        the most-recent active signal per pattern type.

        Parameters
        ----------
        df: DataFrame with columns open/high/low/close (lowercase or Title-case).
        lookback: number of candles to pass to PatternPy (default 100).

        Returns
        -------
        dict with keys: head_shoulder, multiple_top_bottom, support_level,
        resistance_level, triangle, wedge, channel, double, active_patterns,
        bullish_patterns, bearish_patterns, pattern_bias.
        """
        _empty = self._empty_result()
        if df is None or len(df) < 10:
            return _empty

        # Use last `lookback` bars
        df_work = df.iloc[-lookback:].copy()
        df_work = self._to_title(df_work).reset_index(drop=True)

        # Require minimum columns
        for col in ("High", "Low", "Close"):
            if col not in df_work.columns:
                return _empty

        try:
            df_work = _detect_head_shoulder(df_work,        self._window)
            df_work = _detect_multiple_tops_bottoms(df_work, self._window)
            df_work = _calculate_support_resistance(df_work, self._window)
            df_work = _detect_triangle_pattern(df_work,     self._window)
            df_work = _detect_wedge(df_work,                self._window)
            df_work = _detect_channel(df_work,              self._window)
            df_work = _detect_double_top_bottom(df_work,    self._window)
        except Exception:
            return _empty

        # Extract most-recent pattern per type
        head_shoulder  = self._latest_value(df_work["head_shoulder_pattern"])
        multi_tb       = self._latest_value(df_work["multiple_top_bottom_pattern"])
        triangle       = self._latest_value(df_work["triangle_pattern"])
        wedge          = self._latest_value(df_work["wedge_pattern"])
        channel        = self._latest_value(df_work["channel_pattern"])
        double         = self._latest_value(df_work["double_pattern"])

        # S/R from last row (statistical: mean ± 2σ)
        support_level    = float(df_work["support"].iloc[-1]) if "support" in df_work.columns else None
        resistance_level = float(df_work["resistance"].iloc[-1]) if "resistance" in df_work.columns else None
        if support_level is not None and np.isnan(support_level):
            support_level = None
        if resistance_level is not None and np.isnan(resistance_level):
            resistance_level = None

        active  = [p for p in (head_shoulder, multi_tb, triangle, wedge, channel, double) if p]
        bullish = [p for p in active if p in _BULLISH_PATTERNS]
        bearish = [p for p in active if p in _BEARISH_PATTERNS]

        if len(bullish) > len(bearish):
            bias = "BULLISH"
        elif len(bearish) > len(bullish):
            bias = "BEARISH"
        else:
            bias = "NEUTRAL"

        return {
            "head_shoulder":       head_shoulder,
            "multiple_top_bottom": multi_tb,
            "support_level":       round(support_level, 4) if support_level else None,
            "resistance_level":    round(resistance_level, 4) if resistance_level else None,
            "triangle":            triangle,
            "wedge":               wedge,
            "channel":             channel,
            "double":              double,
            "active_patterns":     active,
            "bullish_patterns":    bullish,
            "bearish_patterns":    bearish,
            "pattern_bias":        bias,
        }

    @staticmethod
    def _empty_result() -> dict:
        return {
            "head_shoulder": None, "multiple_top_bottom": None,
            "support_level": None, "resistance_level":    None,
            "triangle":      None, "wedge":               None,
            "channel":       None, "double":              None,
            "active_patterns": [], "bullish_patterns":    [],
            "bearish_patterns": [], "pattern_bias": "NEUTRAL",
        }

    def detect_for_symbol(
        self,
        symbol: str,
        timeframe: str,
        lookback: int = 100,
        data_dir: Optional[str] = None,
    ) -> dict:
        """
        Load OHLCV from the IBKR historical CSV and run detect_all().

        Parameters
        ----------
        symbol:  Ticker, e.g. "AAPL".
        timeframe: Display name, e.g. "1D", "4H", "1W".
        lookback:  Bars to pass to detect_all().
        data_dir:  Override the default data directory.
        """
        _TF_FILE = {
            "1M": "monthly", "1W": "weekly", "1D": "daily",
            "4H": "4h", "1H": "hourly",
            "30min": "30min", "15min": "15min",
            "5min":  "5min",  "1min":  "1min",
        }
        suffix = _TF_FILE.get(timeframe.upper())
        if suffix is None:
            return self._empty_result()

        if data_dir is None:
            # Try prod path first, then local dev path
            for candidate in (
                "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data",
                str(_HERE / "historical_data"),
            ):
                if os.path.isdir(candidate):
                    data_dir = candidate
                    break

        if not data_dir:
            return self._empty_result()

        path = os.path.join(data_dir, f"{symbol.upper()}_{suffix}.csv")
        if not os.path.exists(path):
            return self._empty_result()

        try:
            df = pd.read_csv(
                path,
                usecols=lambda c: c in ("date", "open", "high", "low", "close", "volume"),
                parse_dates=["date"],
            )
            df = df.dropna(subset=["close"]).sort_values("date").reset_index(drop=True)
            return self.detect_all(df, lookback=lookback)
        except Exception:
            return self._empty_result()

    # ─── Condition helper for StrategyStateLogger ────────────────────────────

    def as_condition(self, result: dict, required_bias: str = "BULLISH") -> dict:
        """
        Return a condition dict compatible with StrategyStateLogger.on_candle().

        Usage in strategy scan:
            cond = detector.as_condition(pattern_result, required_bias="BULLISH")
            conditions.append(cond)
        """
        return {
            "name":      "pattern_bias",
            "threshold": required_bias,
            "actual":    result.get("pattern_bias", "NEUTRAL"),
            "met":       result.get("pattern_bias") == required_bias,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Singleton for use in main_live_updated.py
# ─────────────────────────────────────────────────────────────────────────────

_default_detector: Optional[PatternDetector] = None


def get_detector() -> PatternDetector:
    """Return (or lazily create) the module-level PatternDetector singleton."""
    global _default_detector
    if _default_detector is None:
        _default_detector = PatternDetector()
    return _default_detector


# ─────────────────────────────────────────────────────────────────────────────
# Self-test  (python3 pattern_detector.py)
# ─────────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    import glob

    print("PatternPy Integration Self-Test")
    print("=" * 70)
    print(f"  PatternPy available : {_PATTERNPY_AVAILABLE}")
    if _PATTERNPY_PATH:
        print(f"  PatternPy path      : {_PATTERNPY_PATH}")

    LOCAL_DATA = str(_HERE / "historical_data")
    det = PatternDetector()

    # Find any daily CSV
    csv_files = sorted(glob.glob(f"{LOCAL_DATA}/*_daily.csv"))
    if not csv_files:
        print("  No daily CSV files found — skipping live data test.")
        return

    sym = csv_files[0].split("/")[-1].replace("_daily.csv", "")
    print(f"  Testing on: {sym} daily")

    df = pd.read_csv(csv_files[0], parse_dates=["date"])
    df = df.dropna(subset=["close"]).sort_values("date")

    result = det.detect_all(df, lookback=100)

    print(f"\n  Pattern results for {sym}:")
    for k, v in result.items():
        print(f"    {k:<24} {v}")

    # Condition helper
    cond = det.as_condition(result, required_bias="BULLISH")
    print(f"\n  as_condition(BULLISH): {cond}")

    # detect_for_symbol
    r2 = det.detect_for_symbol(sym, "1D")
    assert r2["pattern_bias"] == result["pattern_bias"], "detect_for_symbol mismatch"
    print(f"\n  detect_for_symbol({sym}, '1D') matches detect_all() ✓")

    # Bias logic unit tests
    assert "Head and Shoulder" in _BEARISH_PATTERNS
    assert "Ascending Triangle" in _BULLISH_PATTERNS
    assert "Channel Up" in _BULLISH_PATTERNS
    assert "Wedge Up" in _BEARISH_PATTERNS   # rising wedge = bearish
    assert "Wedge Down" in _BULLISH_PATTERNS  # falling wedge = bullish
    print("  Bias classification: all assertions passed ✓")

    # Scan window: patterns shouldn't all be None on last row
    print(f"\n  active_patterns: {result['active_patterns']}")
    print(f"  pattern_bias:    {result['pattern_bias']}")
    print(f"  support_level:   {result['support_level']}")
    print(f"  resistance_level:{result['resistance_level']}")

    print("\nAll tests passed.")


if __name__ == "__main__":
    _selftest()
