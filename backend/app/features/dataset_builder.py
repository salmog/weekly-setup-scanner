import asyncio
import sys
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.core.database import AsyncSessionLocal, engine
from app.data_sources.postgres_provider import PostgresProvider
from app.features.extractor import FeatureExtractor


async def build_dataset():
    print(" Building Trade Feature Dataset...")

    try:
        trades_df = pd.read_csv("/code/portfolio_trades_export.csv")
    except FileNotFoundError:
        print(" Error: Run global backtest first to generate trade export.")
        return

    trades_df["Entry_Time"] = pd.to_datetime(trades_df["Entry_Time"])
    symbols = trades_df["Symbol"].unique()
    all_features = []

    async with AsyncSessionLocal() as db:
        provider = PostgresProvider(db)

        for sym in symbols:
            sym_trades = trades_df[trades_df["Symbol"] == sym]
            candles = await provider.fetch_historical_candles(
                symbol=sym,
                timeframe="1D",
                start_ts=datetime(2000, 1, 1, tzinfo=UTC),
                end_ts=datetime(2030, 1, 1, tzinfo=UTC),
            )

            if len(candles) < 200:
                continue

            df = pd.DataFrame(
                [
                    {
                        "timestamp": c.ts,
                        "open": float(c.open),
                        "high": float(c.high),
                        "low": float(c.low),
                        "close": float(c.close),
                        "volume": float(c.volume),
                    }
                    for c in candles
                ]
            )
            df.set_index("timestamp", inplace=True)
            df.sort_index(inplace=True)

            # Rebuild base indicators required for features
            df["sma"] = df["close"].rolling(150).mean()
            ranges = pd.concat(
                [
                    df["high"] - df["low"],
                    np.abs(df["high"] - df["close"].shift()),
                    np.abs(df["low"] - df["close"].shift()),
                ],
                axis=1,
            )
            df["atr"] = np.max(ranges, axis=1).rolling(14).mean()
            df["vol_sma"] = df["volume"].rolling(20).mean()

            # Extract advanced features
            df = FeatureExtractor.compute_features(df)

            # Label outcomes (1 = Win, 0 = Loss)
            for _, trade in sym_trades.iterrows():
                entry_time = trade["Entry_Time"]
                if entry_time in df.index:
                    row = df.loc[entry_time]
                    all_features.append(
                        {
                            "Symbol": sym,
                            "Entry_Time": entry_time,
                            "Outcome": 1 if trade["PnL_Net"] > 0 else 0,
                            "PnL_Net": trade["PnL_Net"],
                            "trend_slope_150": float(row["trend_slope_150"]),
                            "distance_from_sma": float(row["distance_from_sma"]),
                            "atr_percent": float(row["atr_percent"]),
                            "volume_ratio": float(row["volume_ratio"]),
                            "breakout_strength": float(row["breakout_strength"]),
                            "range_expansion": float(row["range_expansion"]),
                            "higher_tf_alignment": int(row["higher_tf_alignment"]),
                            "market_regime": int(row["market_regime"]),
                        }
                    )
            sys.stdout.write(".")
            sys.stdout.flush()

    out_df = pd.DataFrame(all_features)
    out_df.dropna(inplace=True)
    out_df.to_csv("/code/trade_features.csv", index=False)
    print("\n Dataset generated successfully: /code/trade_features.csv")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(build_dataset())
