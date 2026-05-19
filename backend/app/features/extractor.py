import pandas as pd


class FeatureExtractor:
    @staticmethod
    def compute_features(df: pd.DataFrame) -> pd.DataFrame:
        """Computes statistical features on a vectorized historical dataframe."""
        df = df.copy()

        # Trend and Distance
        df["trend_slope_150"] = (df["sma"] - df["sma"].shift(5)) / df["sma"].shift(5)
        df["distance_from_sma"] = (df["close"] - df["sma"]) / df["atr"].replace(0, 1e-9)

        # Volatility and Volume
        df["atr_percent"] = df["atr"] / df["close"]
        df["volume_ratio"] = df["volume"] / df["vol_sma"].replace(0, 1e-9)

        # Price Action Mechanics
        candle_range = df["high"] - df["low"]
        df["breakout_strength"] = (df["close"] - df["low"]) / candle_range.replace(0, 1e-9)
        df["range_expansion"] = candle_range / df["atr"].replace(0, 1e-9)

        # Macro Alignments
        df["market_regime"] = (df["close"] > df["close"].rolling(200).mean()).astype(int)
        df["higher_tf_alignment"] = (df["sma"] > df["sma"].shift(20)).astype(int)

        return df
