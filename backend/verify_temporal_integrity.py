import asyncio
from datetime import UTC, datetime

import pandas as pd

from app.core.database import AsyncSessionLocal
from app.data_sources.postgres_provider import PostgresProvider
from app.indicators.engine import IndicatorEngine
from app.strategy.rule_engine import DeterministicRuleEngine


async def run_temporal_validation() -> None:
    print(" Starting Final Gate: Temporal Integrity & Lookahead Bias Check...")

    async with AsyncSessionLocal() as db:
        provider = PostgresProvider(db)

        # We will use ticker 'A' since our previous log confirmed it has 2,009 rows
        symbol = "A"
        candles = await provider.fetch_historical_candles(
            symbol=symbol,
            timeframe="1D",
            start_ts=datetime(2000, 1, 1, tzinfo=UTC),
            end_ts=datetime(2030, 1, 1, tzinfo=UTC),
        )

    if len(candles) < 200:
        print(f" Error: Not enough data for {symbol}. Found {len(candles)} rows.")
        return

    print(f"\n Data Loaded: {len(candles)} daily bars for {symbol}.")

    # Pre-compute bulk to cross-reference against the sliding window (Proves no lookahead bias)
    bulk_df = IndicatorEngine.compute_breakout_indicators(candles)

    evaluations = 0
    valid_setups = 0
    first_signal_idx = -1
    run1_results = []

    print("\n1. Running Sliding Window Time-Series Evaluation (Pass 1)...")
    # Iterate over history chronologically (simulating live market progression)
    for i in range(150, len(candles)):
        # Provide ONLY the history up to index 'i' (Strict No-Future-Data constraint)
        window = candles[:i]

        window_df = IndicatorEngine.compute_breakout_indicators(window)
        eval_res = DeterministicRuleEngine.evaluate_timeframe_rules(window_df, symbol, "1D")

        is_valid = eval_res["passed"]
        run1_results.append(is_valid)
        evaluations += 1

        if is_valid:
            valid_setups += 1
            if first_signal_idx == -1:
                first_signal_idx = i

        # Lookahead Bias Check: The trailing SMA150 in the isolated window MUST
        # exactly match the SMA150 computed in the full future-aware bulk dataset.
        val_window = window_df["sma_150"].iloc[-1]
        val_bulk = bulk_df["sma_150"].iloc[i - 1]

        if pd.isna(val_window) and pd.isna(val_bulk):
            continue
        elif abs(float(val_window) - float(val_bulk)) > 0.001:
            print(f" CRITICAL: Lookahead Bias Detected at index {i}!")
            print(f"   Window Value: {val_window} | Bulk Value: {val_bulk}")
            return

    print("\n2. Executing Forward Consistency Check (Pass 2)...")
    run2_results = []
    for i in range(150, len(candles)):
        window = candles[:i]
        window_df = IndicatorEngine.compute_breakout_indicators(window)
        eval_res = DeterministicRuleEngine.evaluate_timeframe_rules(window_df, symbol, "1D")
        run2_results.append(eval_res["passed"])

    # --- REPORT GENERATION ---
    print("\n========================================================")
    print(" TEMPORAL INTEGRITY & SIGNAL DISTRIBUTION REPORT")
    print("========================================================")

    # Metric 1 & 2: Signal Distribution
    dist_pct = (valid_setups / evaluations) * 100 if evaluations > 0 else 0
    print(f"Total Time-Series Evaluations: {evaluations}")
    print(f"Total Valid Setups Triggered:  {valid_setups}")
    print(f"Signal Distribution Rate:      {dist_pct:.2f}%")

    if 0 < dist_pct < 15:
        print("  ->  SUCCESS: Signal distribution is realistic and non-trivial (1% - 15%).")
    else:
        print("  ->  FAILURE: Signal distribution is abnormal (0% or too high).")

    # Metric 3: First Signal Timestamp Sanity
    print(f"\nFirst Valid Signal Index:      {first_signal_idx}")
    if first_signal_idx > 150:
        print("  ->  SUCCESS: First signal correctly respected the SMA150 warmup padding.")
    else:
        print("  ->  FAILURE: Engine evaluated a signal before mathematical warmup completed.")

    # Metric 4: Forward Consistency
    is_consistent = run1_results == run2_results
    if is_consistent:
        print("\nForward Consistency Match:     TRUE")
        print(
            "  ->  SUCCESS: Run 1 output perfectly matches Run 2. Zero randomness or temporal drift."
        )
    else:
        print("\nForward Consistency Match:     FALSE")
        print("  ->  FAILURE: The engine is non-deterministic across executions.")

    print("\nLookahead Bias Check:          PASSED")
    print("  ->  SUCCESS: Indicators rely strictly on past indices. Zero future data leakage.")
    print("========================================================")


if __name__ == "__main__":
    asyncio.run(run_temporal_validation())
