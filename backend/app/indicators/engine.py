import pandas as pd

from app.models.candle import Candle


class IndicatorEngine:
    """Vectorized mathematical engine for financial indicator generation."""

    @staticmethod
    def candles_to_df(candles: list[Candle]) -> pd.DataFrame:
        """Transforms SQLAlchemy model sequences into an indexed DataFrame matrix."""
        if not candles:
            return pd.DataFrame()

        data = [
            {
                "ts": c.ts,
                "open": float(c.open),
                "high": float(c.high),
                "low": float(c.low),
                "close": float(c.close),
                "volume": int(c.volume),
            }
            for c in candles
        ]

        df = pd.DataFrame(data)
        df.sort_values("ts", inplace=True)
        df.set_index("ts", inplace=True)
        return df

    @classmethod
    def compute_breakout_indicators(
        cls, target_candles: list[Candle], benchmark_candles: list[Candle] | None = None
    ) -> pd.DataFrame:
        """Computes all deterministic rules indicators via pandas vectorized operations."""
        df = cls.candles_to_df(target_candles)
        if df.empty:
            return df

        # 1. Trend Filters (SMA & EMA series)
        df["sma_150"] = df["close"].rolling(window=150).mean()

        # 2. Trend Slope Detection (Linear gradient over 5 periods to check direction)
        df["sma_150_slope"] = df["sma_150"].diff(periods=5) / 5
        df["is_trend_bullish"] = df["sma_150_slope"] > 0

        # 3. Volatility Engine: True Range (TR) and Average True Range (ATR 14)
        high_low = df["high"] - df["low"]
        high_prev_close = (df["high"] - df["close"].shift(1)).abs()
        low_prev_close = (df["low"] - df["close"].shift(1)).abs()

        tr = pd.concat([high_low, high_prev_close, low_prev_close], axis=1).max(axis=1)
        df["atr_14"] = tr.rolling(window=14).mean()

        # 4. Volume Verification Layer
        df["volume_avg_20"] = df["volume"].rolling(window=20).mean()
        df["is_volume_expanding"] = df["volume"] > df["volume_avg_20"]

        # 5. Relative Strength (RS) Component vs Benchmark Ticker (e.g. SPY)
        if benchmark_candles:
            df_bench = cls.candles_to_df(benchmark_candles)
            if not df_bench.empty:
                # Synchronize timestamps cleanly across both vectors to prevent lookahead shifts
                df_merged = df.join(df_bench[["close"]], rsuffix="_bench", how="left")
                df_merged["close_bench"] = df_merged["close_bench"].ffill()

                # Compute RS Ratio: higher slope means outperforming benchmark
                df["relative_strength"] = df_merged["close"] / df_merged["close_bench"]
                df["rs_sma_20"] = df["relative_strength"].rolling(window=20).mean()
                df["is_relative_strength_positive"] = df["relative_strength"] > df["rs_sma_20"]
            else:
                cls._fallback_rs(df)
        else:
            cls._fallback_rs(df)

        return df

    @staticmethod
    def _fallback_rs(df: pd.DataFrame) -> None:
        """Injects clean defaults if benchmark datasets are empty."""
        df["relative_strength"] = 1.0
        df["rs_sma_20"] = 1.0
        df["is_relative_strength_positive"] = True
