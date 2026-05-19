import asyncio
from datetime import UTC, datetime

import numpy as np
import pandas as pd
from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.data_sources.postgres_provider import PostgresProvider
from app.features.extractor import FeatureExtractor
from app.ml.model import MLFilter

SMA_PERIOD = 150
ATR_MULT = 4.0
CLOSE_THRESH = 0.10


async def execute_global_portfolio():
    print(" Initializing Portfolio (Tracking ML Scores & SPY Regime)...")

    async with AsyncSessionLocal() as db:
        provider = PostgresProvider(db)

        # 1. Generate Global SPY Market Regime Mask
        spy_candles = await provider.fetch_historical_candles(
            symbol="SPY",
            timeframe="1D",
            start_ts=datetime(2000, 1, 1, tzinfo=UTC),
            end_ts=datetime(2030, 1, 1, tzinfo=UTC),
        )
        has_spy = len(spy_candles) > 0
        if has_spy:
            spy_df = pd.DataFrame(
                [{"timestamp": c.ts, "spy_close": float(c.close)} for c in spy_candles]
            )
            spy_df.set_index("timestamp", inplace=True)
            spy_df.sort_index(inplace=True)
            spy_df["spy_sma200"] = spy_df["spy_close"].rolling(200).mean()
            spy_df["spy_bull"] = spy_df["spy_close"] > spy_df["spy_sma200"]
            spy_df["spy_dist"] = (spy_df["spy_close"] - spy_df["spy_sma200"]) / spy_df["spy_sma200"]

        q = await db.execute(text("SELECT DISTINCT symbol FROM candles ORDER BY symbol;"))
        symbols = [row[0] for row in q.fetchall()]

        print(f" Processing {len(symbols)} unique tickers...")
        ml_filter = MLFilter()
        all_trades = []

        for sym in symbols:
            try:
                candles = await provider.fetch_historical_candles(
                    symbol=sym,
                    timeframe="1D",
                    start_ts=datetime(2000, 1, 1, tzinfo=UTC),
                    end_ts=datetime(2030, 1, 1, tzinfo=UTC),
                )
                if len(candles) < 250:
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

                if has_spy:
                    df = df.join(spy_df[["spy_bull", "spy_dist"]], how="left")
                    df["spy_bull"] = df["spy_bull"].ffill().fillna(False).astype(bool)
                    df["spy_dist"] = df["spy_dist"].ffill().fillna(0.0).astype(float)
                else:
                    df["spy_bull"] = df["close"] > df["close"].rolling(200).mean()
                    df["spy_dist"] = 0.0

                df["sma"] = df["close"].rolling(SMA_PERIOD).mean()
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
                df.dropna(inplace=True)

                df = FeatureExtractor.compute_features(df)

                trend_up = df["close"] > df["sma"]
                df["volume_ratio"] = df["volume"] / df["vol_sma"].replace(0, 1e-9)
                vol_surge = df["volume_ratio"] >= 1.5

                candle_range = df["high"] - df["low"]
                strong_close = (
                    (df["high"] - df["close"]) / candle_range.replace(0, 1e-9)
                ) <= CLOSE_THRESH

                breakout_day = trend_up & vol_surge & strong_close
                confirmation = (df["close"] > df["high"].shift(1)) & breakout_day.shift(1)
                entries = confirmation & df["spy_bull"]

                in_position = False
                stop_loss = 0
                take_profit = 0
                entry_price = 0
                entry_time = None

                # Track entry features for logging
                current_ml_score = 0.0
                current_spy_dist = 0.0

                for idx, row in df.iterrows():
                    if in_position:
                        if row["low"] <= stop_loss:
                            pnl = -1036
                            all_trades.append(
                                {
                                    "Symbol": sym,
                                    "Direction": "LONG",
                                    "Entry_Time": entry_time,
                                    "Exit_Time": idx,
                                    "Entry_Price": round(entry_price, 2),
                                    "Exit_Price": round(stop_loss, 2),
                                    "PnL_Net": pnl,
                                    "R_Multiple": pnl / 1000.0,
                                    "Exit_Reason": "STOP_LOSS",
                                    "ML_Score": current_ml_score,
                                    "SPY_Dist": current_spy_dist,
                                }
                            )
                            in_position = False
                        elif row["high"] >= take_profit:
                            pnl = (1000 * ATR_MULT) - 36
                            all_trades.append(
                                {
                                    "Symbol": sym,
                                    "Direction": "LONG",
                                    "Entry_Time": entry_time,
                                    "Exit_Time": idx,
                                    "Entry_Price": round(entry_price, 2),
                                    "Exit_Price": round(take_profit, 2),
                                    "PnL_Net": pnl,
                                    "R_Multiple": pnl / 1000.0,
                                    "Exit_Reason": "TAKE_PROFIT",
                                    "ML_Score": current_ml_score,
                                    "SPY_Dist": current_spy_dist,
                                }
                            )
                            in_position = False
                    elif entries.loc[idx]:
                        features_dict = {
                            "trend_slope_150": row["trend_slope_150"],
                            "distance_from_sma": row["distance_from_sma"],
                            "atr_percent": row["atr_percent"],
                            "volume_ratio": row["volume_ratio"],
                            "breakout_strength": row["breakout_strength"],
                            "range_expansion": row["range_expansion"],
                            "higher_tf_alignment": row["higher_tf_alignment"],
                            "market_regime": row["market_regime"],
                        }

                        score = ml_filter.score_trade(features_dict)
                        if score >= 0.52:
                            in_position = True
                            entry_price = row["close"]
                            entry_time = idx
                            stop_loss = row["close"] - row["atr"]
                            take_profit = row["close"] + (row["atr"] * ATR_MULT)
                            current_ml_score = round(score, 4)
                            current_spy_dist = round(row["spy_dist"], 4)

                import sys

                sys.stdout.write(".")
                sys.stdout.flush()

            except Exception:
                pass

        print("\n\n Portfolio Execution Complete.")

        if all_trades:
            df_trades = pd.DataFrame(all_trades)
            df_trades.sort_values("Entry_Time", inplace=True)
            export_path = "/code/portfolio_trades_export.csv"
            df_trades.to_csv(export_path, index=False)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(execute_global_portfolio())
