import asyncio
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.core.database import AsyncSessionLocal, engine
from app.data_sources.postgres_provider import PostgresProvider


async def run_benchmark():
    print(" Benchmarking System vs Broad Market...")
    try:
        df = pd.read_csv("/code/portfolio_trades_export.csv")
        df["Entry_Time"] = pd.to_datetime(df["Entry_Time"], utc=True)
        start_date = df["Entry_Time"].min()
        end_date = df["Entry_Time"].max()
        print(f" Simulation Window: {start_date.date()} to {end_date.date()}")
    except Exception:
        start_date = datetime(2000, 1, 1, tzinfo=UTC)
        end_date = datetime(2030, 1, 1, tzinfo=UTC)

    async with AsyncSessionLocal() as db:
        provider = PostgresProvider(db)

        for sym in ["SPY", "QQQ"]:
            candles = await provider.fetch_historical_candles(
                symbol=sym, timeframe="1D", start_ts=start_date, end_ts=end_date
            )
            if not candles:
                print(f" {sym} not found in database. Skipping...")
                continue

            b_df = pd.DataFrame([{"timestamp": c.ts, "close": float(c.close)} for c in candles])
            b_df.set_index("timestamp", inplace=True)
            b_df.sort_index(inplace=True)

            initial = b_df["close"].iloc[0]
            final = b_df["close"].iloc[-1]
            roi = ((final - initial) / initial) * 100

            b_df["peak"] = b_df["close"].cummax()
            b_df["dd"] = (b_df["close"] - b_df["peak"]) / b_df["peak"]
            max_dd = b_df["dd"].min() * 100

            years = (b_df.index[-1] - b_df.index[0]).days / 365.25
            cagr = ((final / initial) ** (1 / years) - 1) * 100 if years > 0 else 0

            returns = b_df["close"].pct_change().dropna()
            sharpe = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0

            print("========================================================")
            print(f" BENCHMARK: {sym} (Buy & Hold)")
            print("========================================================")
            print(f"Total ROI   : {roi:.2f}%")
            print(f"CAGR        : {cagr:.2f}%")
            print(f"Max Drawdown: {max_dd:.2f}%")
            print(f"Sharpe Ratio: {sharpe:.2f}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_benchmark())
