import os

import numpy as np
import pandas as pd

from app.research.metrics import summarize_portfolio
from app.research.ranking_backtest import run_ranked_portfolio

# Expanded boundaries matching the new calibrated probability distribution scale
THRESHOLDS = np.arange(0.30, 0.85, 0.05)
TOP_N_VALUES = [1, 2, 3, 5]


def run_sweeps(trades: pd.DataFrame):
    results = []

    for threshold in THRESHOLDS:
        # Evaluate using the calibrated probability column
        filtered = trades[trades["calibrated_ml_score"] >= threshold]

        # Mode A: Standard Baseline Threshold-Only Filter
        threshold_metrics = summarize_portfolio(filtered)
        threshold_metrics["mode"] = "threshold"
        threshold_metrics["threshold"] = round(threshold, 2)
        threshold_metrics["top_n"] = "ALL"
        results.append(threshold_metrics)

        # Mode B: Capital-Constrained Top-N Ranking Engine
        for top_n in TOP_N_VALUES:
            ranked = run_ranked_portfolio(filtered, top_n=top_n, score_column="calibrated_ml_score")
            ranked_metrics = summarize_portfolio(ranked)
            ranked_metrics["mode"] = "ranked"
            ranked_metrics["threshold"] = round(threshold, 2)
            ranked_metrics["top_n"] = str(top_n)
            results.append(ranked_metrics)

    return pd.DataFrame(results)


if __name__ == "__main__":
    output_dir = "backend/data"
    csv_path = os.path.join(output_dir, "trades_calibrated.csv")

    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Missing calibrated matrix file at: {csv_path}")

    df = pd.read_csv(csv_path)

    # Run the optimization sweep
    results_df = run_sweeps(df)
    active_results = results_df[results_df["total_trades"] > 0].copy()

    # Sort by performance efficiency (Sharpe, then expectancy)
    active_results = active_results.sort_values(
        by=["sharpe", "expectancy"], ascending=[False, False]
    )
    results_path = os.path.join(output_dir, "optimization_results.csv")
    active_results.to_csv(results_path, index=False)

    print("\n--- CALIBRATED OPTIMIZATION METRICS MATRIX ---")
    if active_results.empty:
        print("No active configurations found.")
    else:
        print(
            active_results[
                [
                    "mode",
                    "threshold",
                    "top_n",
                    "expectancy",
                    "sharpe",
                    "max_drawdown",
                    "net_profit",
                    "total_trades",
                ]
            ]
            .head(15)
            .to_string(index=False)
        )
    print(f"\nSaved calculation parameters to: {results_path}")
