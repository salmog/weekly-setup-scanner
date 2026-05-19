import asyncio
from datetime import UTC, datetime

from sqlalchemy import text

from app.core.database import AsyncSessionLocal, engine
from app.data_sources.postgres_provider import PostgresProvider
from app.indicators.engine import IndicatorEngine
from app.strategy.rule_engine import DeterministicRuleEngine


async def run_scale_verification() -> None:
    print(" Starting Production Data Scale & Rule Engine Evaluation...")

    async with AsyncSessionLocal() as db:
        # 1. Query Cross-Ticker Row Counts
        print("\n1. DATABASE STORAGE MATRIX STATUS:")
        q1 = await db.execute(
            text(
                """
            SELECT symbol, timeframe, COUNT(*)
            FROM candles
            GROUP BY symbol, timeframe
            ORDER BY symbol, timeframe;
        """
            )
        )
        rows = q1.fetchall()
        if not rows:
            print("    Database is currently empty. Run the ingestion script first.")
            await engine.dispose()
            return

        for row in rows:
            print(f"   Symbol: {row[0]:<6} | Timeframe: {row[1]:<3} | Total Stored Rows: {row[2]}")

        # 2. Global Duplicate Contiguity Check
        print("\n2. GLOBAL DUPLICATE CONSTRAINT CHECK:")
        q2 = await db.execute(
            text(
                """
            SELECT symbol, timeframe, ts, COUNT(*)
            FROM candles
            GROUP BY symbol, timeframe, ts
            HAVING COUNT(*) > 1;
        """
            )
        )
        dups = q2.fetchall()
        if not dups:
            print(
                "   [SUCCESS] 0 global duplicate combinations exist inside the database instance."
            )
        else:
            print(
                f"   [CRITICAL FAILURE] Duplicates identified: {len(dups)} rows fail constraints."
            )

        # 3. End-to-End Pipeline Evaluation on Live Extracted Rows
        print("\n3. LIVE PIPELINE PASS THROUGH (REAL VOLUMES):")
        postgres_provider = PostgresProvider(db)

        # Extract unique symbol tokens present in your active database cluster
        symbols_present = list(set([r[0] for r in rows]))

        for sym in symbols_present[:3]:  # Evaluate the first 3 tickers found
            for tf in ["1D", "1H", "4H"]:
                # Check if this combination exists in our row matrix summary
                if not any(r[0] == sym and r[1] == tf for r in rows):
                    continue

                candles = await postgres_provider.fetch_historical_candles(
                    symbol=sym,
                    timeframe=tf,
                    start_ts=datetime(2000, 1, 1, tzinfo=UTC),
                    end_ts=datetime(2030, 1, 1, tzinfo=UTC),
                )

                if len(candles) < 150:
                    print(
                        f"   Ticker: {sym:<5} ({tf:<3}) ->  Skipped: {len(candles)} bars is below the SMA150 window limit."
                    )
                    continue

                # Compute deep analytical indicator matrices over raw historical records
                df = IndicatorEngine.compute_breakout_indicators(candles)

                # Evaluate full strategy rule metrics on the real historical data edge
                eval_results = DeterministicRuleEngine.evaluate_timeframe_rules(df, sym, tf)

                print(
                    f"   Ticker: {sym:<5} ({tf:<3}) -> Valid Setup: {str(eval_results['passed']):<5} | Confidence: {eval_results['confidence']:.1f}%"
                )
                if eval_results["rejections"] and not eval_results["passed"]:
                    print(f"      Top Rejection Reason: {eval_results['rejections'][0]}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run_scale_verification())
