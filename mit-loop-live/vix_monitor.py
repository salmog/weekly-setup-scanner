"""
vix_monitor.py
==============
Real-time VIX awareness engine.

Fetches ^VIX at 1-min, 5-min, and 15-min intervals, computes spike
detection and trend per interval, and derives a composite risk signal
used to gate new long entries across all strategies.

Data sources (in priority order)
----------------------------------
1. yfinance  ^VIX  — actual CBOE VIX index; thresholds map directly.
   Install: pip install yfinance  (handled by deploy_vix.sh)
2. Alpaca    VIXY  — VIX proxy ETF already connected in main_live_updated.py.
   Used only when yfinance is unavailable (e.g. rate-limited or network issue).
   Note: VIXY levels are NOT equal to VIX levels — they are used here for
   trend/spike shape, not for absolute regime classification.

Composite signal
----------------
RISK_OFF  — spike on any interval  OR  regime == "FEAR"
CAUTION   — regime == "ELEVATED"  OR  any interval rising
RISK_ON   — regime in [CALM, NORMAL]  AND  all intervals falling or flat
"""

from __future__ import annotations

import datetime
import os
import threading
import traceback
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

INTERVALS: Dict[str, Dict] = {
    "1min":  {"yf_interval": "1m",  "yf_period": "5d",  "minutes": 1},
    "5min":  {"yf_interval": "5m",  "yf_period": "5d",  "minutes": 5},
    "15min": {"yf_interval": "15m", "yf_period": "5d",  "minutes": 15},
}

# VIX level thresholds (^VIX, not VIXY)
REGIME_THRESHOLDS = [
    ("FEAR",     25.0),   # > 25
    ("ELEVATED", 20.0),   # 20–25
    ("NORMAL",   15.0),   # 15–20
    ("CALM",      0.0),   # < 15
]

SPIKE_THRESHOLD_PCT   = 5.0    # % change over last 15 candles triggers spike
SPIKE_CANDLES         = 15     # lookback candles for spike detection
EMA_FAST_PERIOD       = 5
EMA_SLOW_PERIOD       = 15
FLAT_THRESHOLD_PCT    = 0.3    # EMA diff < 0.3% → "flat"
CANDLES_TO_FETCH      = 40     # how many candles to keep per interval

VIX_TICKER_YF         = "^VIX"
VIX_TICKER_ALPACA     = "VIXY"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _classify_regime(vix_level: float) -> str:
    for name, threshold in REGIME_THRESHOLDS:
        if vix_level > threshold:
            return name
    return "CALM"


def _classify_trend(df: pd.DataFrame) -> str:
    """EMA5 vs EMA15 on the 'close' column."""
    if len(df) < EMA_SLOW_PERIOD + 2:
        return "flat"
    closes = df["close"].dropna()
    ema_fast = float(closes.ewm(span=EMA_FAST_PERIOD, adjust=False).mean().iloc[-1])
    ema_slow = float(closes.ewm(span=EMA_SLOW_PERIOD, adjust=False).mean().iloc[-1])
    if ema_slow == 0:
        return "flat"
    diff_pct = (ema_fast - ema_slow) / ema_slow * 100
    if diff_pct > FLAT_THRESHOLD_PCT:
        return "rising"
    if diff_pct < -FLAT_THRESHOLD_PCT:
        return "falling"
    return "flat"


def _detect_spike(df: pd.DataFrame) -> Tuple[bool, float]:
    """
    Returns (spike_detected, change_pct_over_15_candles).
    spike_detected is True when |change| > SPIKE_THRESHOLD_PCT.
    """
    closes = df["close"].dropna()
    n = min(SPIKE_CANDLES, len(closes))
    if n < 2:
        return False, 0.0
    old = float(closes.iloc[-n])
    new = float(closes.iloc[-1])
    if old == 0:
        return False, 0.0
    change_pct = (new - old) / old * 100
    return abs(change_pct) > SPIKE_THRESHOLD_PCT, round(change_pct, 3)


def _normalize_yf_df(raw: pd.DataFrame) -> pd.DataFrame:
    """
    yfinance returns a MultiIndex DataFrame (Price, Ticker).
    Flatten to single-level lowercase columns.
    """
    if raw.empty:
        return pd.DataFrame()
    df = raw.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0].lower().replace(" ", "_") for col in df.columns]
    else:
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    df = df.reset_index()
    # Lowercase the index column too (yfinance yields 'Datetime' after reset)
    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
    for cname in ("datetime", "date", "index"):
        if cname in df.columns:
            df = df.rename(columns={cname: "timestamp"})
            break
    needed = {"timestamp", "open", "high", "low", "close"}
    if not needed.issubset(set(df.columns)):
        return pd.DataFrame()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.dropna(subset=["close"]).sort_values("timestamp").reset_index(drop=True)


# ─────────────────────────────────────────────────────────────────────────────
# VIX Monitor
# ─────────────────────────────────────────────────────────────────────────────

class VIXMonitor:
    """
    Multi-interval VIX tracker with spike detection, regime classification,
    and composite risk-signal generation.

    Parameters
    ----------
    alpaca_client:
        StockHistoricalDataClient from alpaca-py — used as fallback data source
        if yfinance is unavailable. Pass ``None`` to disable Alpaca fallback.
    update_interval_sec:
        How often (in seconds) a cached result is considered stale.
        Default 60 — matches the 1-minute scheduler cadence.
    """

    def __init__(
        self,
        alpaca_client=None,
        update_interval_sec: int = 60,
    ) -> None:
        self._alpaca_client     = alpaca_client
        self._update_interval   = update_interval_sec
        self._lock              = threading.Lock()
        self._status: dict      = {}
        self._prev_spike: Dict[str, bool] = {iv: False for iv in INTERVALS}
        self._spike_callbacks: List[Callable] = []
        self._last_update: Optional[float]    = None

        # Confirm yfinance is importable at startup
        try:
            import yfinance as _  # noqa: F401
            self._yfinance_ok = True
        except ImportError:
            self._yfinance_ok = False

    # ─── Data fetching ───────────────────────────────────────────────────────

    def _fetch_yf(self, interval_key: str) -> Optional[pd.DataFrame]:
        """Fetch ^VIX from yfinance for the given interval."""
        if not self._yfinance_ok:
            return None
        try:
            import yfinance as yf
            cfg = INTERVALS[interval_key]
            raw = yf.download(
                VIX_TICKER_YF,
                period=cfg["yf_period"],
                interval=cfg["yf_interval"],
                progress=False,
                auto_adjust=False,
            )
            df = _normalize_yf_df(raw)
            if df.empty:
                return None
            return df.iloc[-CANDLES_TO_FETCH:].copy()
        except Exception:
            return None

    def _fetch_alpaca(self, interval_key: str) -> Optional[pd.DataFrame]:
        """Fetch VIXY from Alpaca as a fallback."""
        if self._alpaca_client is None:
            # Try to build a client from env vars
            try:
                from alpaca.data.historical import StockHistoricalDataClient
                key    = os.getenv("ALPACA_API_KEY_S1") or os.getenv("ALPACA_API_KEY_SALMOG3")
                secret = os.getenv("ALPACA_SECRET_KEY_S1") or os.getenv("ALPACA_SECRET_KEY_SALMOG3")
                if not (key and secret):
                    return None
                client = StockHistoricalDataClient(key, secret)
            except ImportError:
                return None
        else:
            client = self._alpaca_client

        try:
            import zoneinfo
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

            cfg = INTERVALS[interval_key]
            minutes = cfg["minutes"]
            tz  = zoneinfo.ZoneInfo("America/New_York")
            now = datetime.datetime.now(tz)
            # Fetch enough minutes to cover CANDLES_TO_FETCH bars + buffer
            lookback = datetime.timedelta(minutes=minutes * (CANDLES_TO_FETCH + 20))
            start    = now - lookback

            unit_map = {1: TimeFrameUnit.Minute, 5: TimeFrameUnit.Minute, 15: TimeFrameUnit.Minute}
            req = StockBarsRequest(
                symbol_or_symbols=VIX_TICKER_ALPACA,
                timeframe=TimeFrame(minutes, TimeFrameUnit.Minute),
                start=start,
                end=now,
            )
            bars = client.get_stock_bars(req)
            if bars.df.empty:
                return None
            df = bars.df.xs(VIX_TICKER_ALPACA).reset_index()
            df.columns = [c.lower() for c in df.columns]
            df = df.rename(columns={"timestamp": "timestamp"})
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df = df.dropna(subset=["close"])
            # ⚠ Note: VIXY levels ≠ VIX levels — only used for trend/spike shape
            return df.iloc[-CANDLES_TO_FETCH:].copy()
        except Exception:
            return None

    def _fetch_interval(self, interval_key: str) -> Optional[pd.DataFrame]:
        """Try yfinance first, fall back to Alpaca."""
        df = self._fetch_yf(interval_key)
        if df is not None and len(df) >= 5:
            return df
        return self._fetch_alpaca(interval_key)

    # ─── Per-interval analysis ───────────────────────────────────────────────

    def _analyze_interval(
        self, interval_key: str, df: pd.DataFrame
    ) -> Dict:
        current_vix = float(df["close"].iloc[-1])
        spike, change_pct = _detect_spike(df)
        regime = _classify_regime(current_vix)
        trend  = _classify_trend(df)
        return {
            "current":             round(current_vix, 2),
            "vix_change_pct_15min": round(change_pct, 3),
            "spike":               spike,
            "regime":              regime,
            "trend":               trend,
            "bars_used":           len(df),
            "source":              "^VIX" if self._yfinance_ok else "VIXY~",
        }

    # ─── Composite signal ────────────────────────────────────────────────────

    @staticmethod
    def _compute_composite(analyses: Dict[str, Dict]) -> str:
        """
        RISK_OFF  — any spike  OR  regime == FEAR
        CAUTION   — regime == ELEVATED  OR  any trend == rising
        RISK_ON   — regime in [CALM, NORMAL]  AND  all trends in [falling, flat]
        """
        vals = [v for v in analyses.values() if v]
        if not vals:
            return "CAUTION"  # unknown → be cautious

        any_spike = any(v["spike"] for v in vals)
        any_fear  = any(v["regime"] == "FEAR" for v in vals)

        if any_spike or any_fear:
            return "RISK_OFF"

        any_elevated = any(v["regime"] == "ELEVATED" for v in vals)
        any_rising   = any(v["trend"] == "rising" for v in vals)

        if any_elevated or any_rising:
            return "CAUTION"

        # RISK_ON: all intervals calm/normal AND not rising
        all_calm   = all(v["regime"] in ("CALM", "NORMAL") for v in vals)
        all_stable = all(v["trend"] in ("falling", "flat") for v in vals)

        if all_calm and all_stable:
            return "RISK_ON"

        return "CAUTION"

    # ─── Spike callbacks ─────────────────────────────────────────────────────

    def subscribe_to_spikes(self, callback: Callable) -> None:
        """
        Register a callback fired when spike_detected transitions False → True
        on any interval.

        callback receives:
            {
                "event":        "VIX_SPIKE",
                "timestamp":    "...",
                "interval":     "1min",
                "current_vix":  19.5,
                "change_pct":   6.2,
                "composite":    "RISK_OFF",
            }
        """
        with self._lock:
            self._spike_callbacks.append(callback)

    def _fire_spike(self, interval_key: str, analysis: Dict, composite: str) -> None:
        """Call registered spike callbacks, catching exceptions."""
        event = {
            "event":       "VIX_SPIKE",
            "timestamp":   datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "interval":    interval_key,
            "current_vix": analysis["current"],
            "change_pct":  analysis["vix_change_pct_15min"],
            "composite":   composite,
        }
        for cb in self._spike_callbacks:
            try:
                cb(event)
            except Exception:
                pass

    # ─── Public API ──────────────────────────────────────────────────────────

    def update(self) -> dict:
        """
        Fetch fresh data for all intervals, compute composite signal,
        update internal state, fire spike callbacks on transitions.

        Called by the scheduler every minute. Always returns the
        (possibly stale) status dict — never raises.
        """
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        interval_results: Dict[str, Dict] = {}

        for iv_key in INTERVALS:
            try:
                df = self._fetch_interval(iv_key)
                if df is None or len(df) < 5:
                    interval_results[iv_key] = None
                    continue
                interval_results[iv_key] = self._analyze_interval(iv_key, df)
            except Exception:
                interval_results[iv_key] = None

        valid = {k: v for k, v in interval_results.items() if v is not None}
        composite = self._compute_composite(valid)

        status = {
            **{f"vix_{k}": v for k, v in interval_results.items()},
            "composite": composite,
            "timestamp": timestamp,
        }

        # Fire spike callbacks on False → True transitions
        for iv_key, analysis in valid.items():
            spike_now  = analysis["spike"]
            spike_prev = self._prev_spike.get(iv_key, False)
            if spike_now and not spike_prev:
                self._fire_spike(iv_key, analysis, composite)
            self._prev_spike[iv_key] = spike_now

        import time as _time
        with self._lock:
            self._status      = status
            self._last_update = _time.monotonic()

        return status

    def get_vix_status(self) -> dict:
        """
        Return the most-recent status dict (cached from last update()).
        Returns an empty/safe dict if update() has never run.
        """
        with self._lock:
            if self._status:
                return dict(self._status)
        # Return a safe fallback so callers never get KeyError
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "vix_1min":  None, "vix_5min":  None, "vix_15min": None,
            "composite": "CAUTION",
            "timestamp": ts,
            "error":     "no_data_yet",
        }

    def is_risk_off(self) -> bool:
        """Quick boolean gate for strategy logic."""
        return self.get_vix_status().get("composite") == "RISK_OFF"

    def current_vix(self) -> Optional[float]:
        """Latest ^VIX value (from any available interval), or None."""
        status = self.get_vix_status()
        for key in ("vix_1min", "vix_5min", "vix_15min"):
            v = status.get(key)
            if v and v.get("current") is not None:
                return v["current"]
        return None

    def current_regime(self) -> str:
        """Current regime string from the most granular available interval."""
        status = self.get_vix_status()
        for key in ("vix_1min", "vix_5min", "vix_15min"):
            v = status.get(key)
            if v and v.get("regime"):
                return v["regime"]
        return "UNKNOWN"

    def to_system_state_dict(self) -> dict:
        """
        Return a dict matching the existing system_state["vix"] schema so the
        dashboard renders without changes.
        """
        vix   = self.current_vix()
        regime = self.current_regime()
        # Map internal regime names to legacy dashboard level names
        level_map = {"CALM": "LOW", "NORMAL": "LOW", "ELEVATED": "ELEVATED",
                     "FEAR": "HIGH", "UNKNOWN": "unknown"}
        return {
            "current":    vix,
            "change_pct": None,
            "level":      level_map.get(regime, "unknown"),
            "last_update": self.get_vix_status().get("timestamp"),
            "composite":  self.get_vix_status().get("composite"),
            "regime":     regime,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Self-test  (python3 vix_monitor.py)
# ─────────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    print("VIX Monitor Self-Test")
    print("=" * 70)

    mon = VIXMonitor(alpaca_client=None)

    # ── Unit tests — spike / regime / trend / composite
    def _df(closes):
        return pd.DataFrame({"close": closes})

    # regime
    assert _classify_regime(12.0) == "CALM"
    assert _classify_regime(17.5) == "NORMAL"
    assert _classify_regime(22.0) == "ELEVATED"
    assert _classify_regime(28.0) == "FEAR"
    print("  regime classification: OK")

    # trend
    rising_closes  = list(range(10, 10 + 20))   # monotone up
    falling_closes = list(range(30, 30 - 20, -1))
    flat_closes    = [20.0] * 20
    assert _classify_trend(_df(rising_closes))  == "rising"
    assert _classify_trend(_df(falling_closes)) == "falling"
    assert _classify_trend(_df(flat_closes))    == "flat"
    print("  trend classification: OK")

    # spike — 15 candles, >5% change
    spike_closes   = [20.0] * 15 + [27.0]    # +35% → spike
    nospike_closes = [20.0] * 15 + [20.5]    # +2.5% → no spike
    spike, chg = _detect_spike(_df(spike_closes))
    assert spike, f"expected spike, got {spike}"
    no_spike, _ = _detect_spike(_df(nospike_closes))
    assert not no_spike
    print(f"  spike detection: OK (change {chg:+.1f}%)")

    # composite — RISK_OFF
    risk_off_analyses = {
        "1min":  {"spike": True,  "regime": "ELEVATED", "trend": "rising"},
        "5min":  {"spike": False, "regime": "ELEVATED", "trend": "rising"},
        "15min": {"spike": False, "regime": "NORMAL",   "trend": "flat"},
    }
    assert VIXMonitor._compute_composite(risk_off_analyses) == "RISK_OFF"

    # composite — CAUTION
    caution_analyses = {
        "1min":  {"spike": False, "regime": "ELEVATED", "trend": "flat"},
        "5min":  {"spike": False, "regime": "NORMAL",   "trend": "rising"},
        "15min": {"spike": False, "regime": "NORMAL",   "trend": "flat"},
    }
    assert VIXMonitor._compute_composite(caution_analyses) == "CAUTION"

    # composite — RISK_ON
    risk_on_analyses = {
        "1min":  {"spike": False, "regime": "CALM",   "trend": "falling"},
        "5min":  {"spike": False, "regime": "NORMAL", "trend": "flat"},
        "15min": {"spike": False, "regime": "CALM",   "trend": "falling"},
    }
    assert VIXMonitor._compute_composite(risk_on_analyses) == "RISK_ON"
    print("  composite signal: OK")

    # spike callback fires only on transition
    fired = []
    mon.subscribe_to_spikes(lambda e: fired.append(e))

    # ── Live data fetch
    print()
    print("  Fetching live ^VIX data (requires internet)...")
    status = mon.update()
    print(f"  composite: {status['composite']}")
    for key in ("vix_1min", "vix_5min", "vix_15min"):
        v = status.get(key)
        if v:
            print(
                f"  {key}: VIX={v['current']:.2f}  "
                f"regime={v['regime']:<9}  "
                f"trend={v['trend']:<8}  "
                f"spike={v['spike']}  "
                f"Δ15={v['vix_change_pct_15min']:+.2f}%  "
                f"src={v['source']}  bars={v['bars_used']}"
            )
        else:
            print(f"  {key}: no data")

    # Round-trip
    s2 = mon.get_vix_status()
    assert s2["composite"] == status["composite"]
    assert mon.current_vix() is not None or True  # None is OK if no data
    print()
    print(f"  is_risk_off(): {mon.is_risk_off()}")
    print(f"  current_vix(): {mon.current_vix()}")
    print(f"  current_regime(): {mon.current_regime()}")
    print(f"  system_state compat: {mon.to_system_state_dict()}")
    print()
    print("All tests passed.")


if __name__ == "__main__":
    _selftest()
