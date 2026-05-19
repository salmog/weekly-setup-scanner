import pandas as pd


class StatisticalFilter:
    @staticmethod
    def generate_mask(df: pd.DataFrame) -> pd.Series:
        """
        Returns a boolean mask based on the Option A statistical edge report.
        Removes the lowest performing quartiles to boost win rate and cut drawdown.
        """
        trend_slope = (df["sma"] - df["sma"].shift(5)) / df["sma"].shift(5)
        distance_from_sma = (df["close"] - df["sma"]) / df["atr"].replace(0, 1e-9)
        volume_ratio = df["volume"] / df["vol_sma"].replace(0, 1e-9)
        candle_range = df["high"] - df["low"]
        breakout_strength = (df["close"] - df["low"]) / candle_range.replace(0, 1e-9)
        range_expansion = candle_range / df["atr"].replace(0, 1e-9)

        mask = (
            (trend_slope > 0.0006)  # Avoid flat/negative macro trends
            & (distance_from_sma < 5.66)  # Avoid overextended mean-reversion traps
            & (volume_ratio > 1.12)  # Demand above-average relative volume
            & (breakout_strength > 0.9268)  # Demand close near absolute highs
            & (range_expansion < 1.5193)  # Avoid climax/exhaustion candles
        )
        return mask
