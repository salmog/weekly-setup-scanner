import os

import numpy as np
import pandas as pd

from app.research.metrics import summarize_portfolio
from app.research.ranking_backtest import run_ranked_portfolio

THRESHOLDS = np.arange(0.50, 0.66, 0.02)
TOP_N_VALUES = [3, 5, 10, 20]


def execute_production_sweep():
    # Prioritize the active 76KB trade export log found inside your workspace
    possible_paths = [
        "portfolio_trades_export.csv",
        "/code/portfolio_trades_export.csv",
        "data/trades.csv",
        "trades.csv",
    ]

    container_csv = None
    for p in possible_paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            container_csv = p
            break

    if not container_csv:
        print("ERROR: Could not find an active non-empty trade log file.")
        return

    df = pd.read_csv(container_csv)
    df.columns = df.columns.str.lower()

    if "pnl_net" not in df.columns and "pnl" in df.columns:
        df["pnl_net"] = df["pnl"]

    print(
        f"Successfully optimized using container dataset: {container_csv} ({len(df)} records found)."
    )

    results = []
    for threshold in THRESHOLDS:
        filtered = df[df["ml_score"] >= threshold]

        m = summarize_portfolio(filtered)
        m["mode"] = "unconstrained"
        m["threshold"] = round(threshold, 2)
        m["top_n"] = "ALL"
        results.append(m)

        for top_n in TOP_N_VALUES:
            ranked = run_ranked_portfolio(filtered, top_n=top_n, score_column="ml_score")
            rm = summarize_portfolio(ranked)
            rm["mode"] = "ranked"
            rm["threshold"] = round(threshold, 2)
            rm["top_n"] = str(top_n)
            results.append(rm)

    results_df = pd.DataFrame(results)
    active_results = results_df[results_df["total_trades"] > 0].copy()
    active_results = active_results.sort_values(by="sharpe", ascending=False)

    print("\n=====================================================================")
    print("                PRODUCTION PORTFOLIO OPTIMIZATION MATRIX             ")
    print("=====================================================================")
    print(
        active_results[
            ["mode", "threshold", "top_n", "sharpe", "max_drawdown", "cagr", "total_trades"]
        ]
        .head(15)
        .to_string(index=False)
    )
    print("=====================================================================")


if __name__ == "__main__":
    execute_production_sweep()
