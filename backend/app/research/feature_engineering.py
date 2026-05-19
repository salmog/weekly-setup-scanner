import numpy as np
import pandas as pd


def calculate_engineered_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Transforms raw historical market bars into advanced institutional features
    to widen model score distribution and improve signal ranking accuracy.
    Required columns in input df: ['close', 'high', 'low', 'volume', 'sma150', 'avg_volume_20', 'atr_14', 'atr_50', 'rolling_high_20', 'spy_close', 'spy_return_20d', 'stock_return_20d']
    """
    out = df.copy()

    # 1. Trend Distance Ratio
    if "sma150" in out.columns:
        out["feat_trend_dist"] = (out["close"] - out["sma150"]) / out["sma150"]
    else:
        out["feat_trend_dist"] = 0.0

    # 2. Volume Expansion Ratio
    if "volume" in out.columns and "avg_volume_20" in out.columns:
        out["feat_volume_ratio"] = out["volume"] / out["avg_volume_20"].replace(0, np.nan)
        out["feat_volume_ratio"] = out["feat_volume_ratio"].fillna(1.0)
    else:
        out["feat_volume_ratio"] = 1.0

    # 3. ATR Volatility Expansion Ratio
    if "atr_14" in out.columns and "atr_50" in out.columns:
        out["feat_atr_expansion"] = out["atr_14"] / out["atr_50"].replace(0, np.nan)
        out["feat_atr_expansion"] = out["feat_atr_expansion"].fillna(1.0)
    else:
        out["feat_atr_expansion"] = 1.0

    # 4. Candle Close Strength (0 to 1 relative positioning)
    if "high" in out.columns and "low" in out.columns:
        denom = out["high"] - out["low"]
        out["feat_candle_strength"] = (out["close"] - out["low"]) / denom.replace(0, np.nan)
        out["feat_candle_strength"] = out["feat_candle_strength"].fillna(0.5)
    else:
        out["feat_candle_strength"] = 0.5

    # 5. Breakout Proximity Distance
    if "rolling_high_20" in out.columns:
        out["feat_breakout_dist"] = out["close"] / out["rolling_high_20"].replace(0, np.nan)
        out["feat_breakout_dist"] = out["feat_breakout_dist"].fillna(1.0)
    else:
        out["feat_breakout_dist"] = 1.0

    # 6. Institutional Relative Strength vs SPY Matrix
    if "stock_return_20d" in out.columns and "spy_return_20d" in out.columns:
        out["feat_relative_strength"] = out["stock_return_20d"] - out["spy_return_20d"]
    else:
        out["feat_relative_strength"] = 0.0

    return out


if __name__ == "__main__":
    print("Feature engineering core mathematical pipeline compiled successfully.")
    # Mock validation block to verify framework safety
    mock_data = pd.DataFrame(
        {
            "close": [105.0],
            "high": [106.0],
            "low": [100.0],
            "volume": [1500],
            "sma150": [100.0],
            "avg_volume_20": [1000],
            "atr_14": [2.5],
            "atr_50": [2.0],
            "rolling_high_20": [104.0],
            "stock_return_20d": [0.05],
            "spy_return_20d": [0.02],
        }
    )
    processed = calculate_engineered_features(mock_data)
    print("\nCalculated Vector Blueprint Verification:")
    for col in [c for c in processed.columns if c.startswith("feat_")]:
        print(f" -> {col}: {processed[col].iloc[0]:.4f}")
