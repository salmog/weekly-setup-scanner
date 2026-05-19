import asyncio
import sys
from datetime import UTC, datetime
from itertools import product

import numpy as np
import pandas as pd

from app.core.database import AsyncSessionLocal, engine
from app.data_sources.postgres_provider import PostgresProvider

# The Grid: Scanning 27 different universes
SMA_PERIODS = [50, 100, 150]
ATR_MULTIPLIERS = [2.0, 3.0, 4.0]
BREAKOUT_THRESHOLDS = [0.10, 0.20, 0.30]


async def run_grid_search(symbol: str):
    symbol = symbol.upper().strip()
    print(f" Starting Vectorized Parameter Optimization for: {symbol}")

    async with AsyncSessionLocal() as db:
        provider = PostgresProvider(db)
        candles = await provider.fetch_historical_candles(
            symbol=symbol,
            timeframe="1D",
            start_ts=datetime(2000, 1, 1, tzinfo=UTC),
            end_ts=datetime(2030, 1, 1, tzinfo=UTC),
        )

    if len(candles) < 250:
        print(f" Aborting: Not enough historical data for {symbol}.")
        await engine.dispose()
        return

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

    results = []
    print(
        f" Scanning {len(SMA_PERIODS)*len(ATR_MULTIPLIERS)*len(BREAKOUT_THRESHOLDS)} parameter combinations...\n"
    )

    for sma, atr_mult, thresh in product(SMA_PERIODS, ATR_MULTIPLIERS, BREAKOUT_THRESHOLDS):
        df_opt = df.copy()

        # Calculate dynamic indicators
        df_opt["sma"] = df_opt["close"].rolling(sma).mean()
        high_low = df_opt["high"] - df_opt["low"]
        high_close = np.abs(df_opt["high"] - df_opt["close"].shift())
        low_close = np.abs(df_opt["low"] - df_opt["close"].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        df_opt["atr"] = np.max(ranges, axis=1).rolling(14).mean()
        df_opt["vol_sma"] = df_opt["volume"].rolling(20).mean()

        df_opt.dropna(inplace=True)

        # Logic matches our production RuleEngine
        trend_up = df_opt["close"] > df_opt["sma"]
        vol_surge = df_opt["volume"] > df_opt["vol_sma"]
        candle_range = df_opt["high"] - df_opt["low"]
        close_rel = (df_opt["high"] - df_opt["close"]) / candle_range.replace(0, 1e-9)
        strong_close = close_rel <= thresh
        entries = trend_up & vol_surge & strong_close

        trades = []
        in_position = False
        stop_loss = 0
        take_profit = 0

        # Fast simulation
        for idx, row in df_opt.iterrows():
            if in_position:
                if row["low"] <= stop_loss:
                    trades.append(-1036)  # Approx 1R Loss + friction
                    in_position = False
                elif row["high"] >= take_profit:
                    trades.append((1000 * atr_mult) - 36)  # Reward - friction
                    in_position = False
            elif entries.loc[idx]:
                in_position = True
                stop_loss = row["close"] - row["atr"]
                take_profit = row["close"] + (row["atr"] * atr_mult)

        total_trades = len(trades)
        if total_trades > 0:
            wins = len([t for t in trades if t > 0])
            win_rate = (wins / total_trades) * 100
            expectancy = np.mean(trades)

            results.append(
                {
                    "SMA": sma,
                    "Reward (ATR)": f"{atr_mult}x",
                    "Close Top %": f"{int(thresh*100)}%",
                    "Trades": total_trades,
                    "Win Rate": f"{win_rate:.1f}%",
                    "Expectancy": f"${expectancy:.2f}",
                }
            )

    # Display Top 10
    res_df = pd.DataFrame(results)
    if not res_df.empty:
        res_df["Raw_Exp"] = res_df["Expectancy"].str.replace("$", "").astype(float)
        res_df = (
            res_df.sort_values(by="Raw_Exp", ascending=False).head(10).drop(columns=["Raw_Exp"])
        )
        print(" TOP 10 PARAMETER COMBINATIONS (Ranked by Expectancy):")
        print("-" * 80)
        print(res_df.to_string(index=False))
    else:
        print(" No profitable combinations found.")

    await engine.dispose()


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "A"
    asyncio.run(run_grid_search(target))
