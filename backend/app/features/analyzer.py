import pandas as pd


def analyze_features():
    print(" Analyzing Feature Edges & Generating Report...\n")
    df = pd.read_csv("/code/trade_features.csv")

    features_to_analyze = [
        "trend_slope_150",
        "distance_from_sma",
        "atr_percent",
        "volume_ratio",
        "breakout_strength",
        "range_expansion",
    ]

    report = []

    for feature in features_to_analyze:
        # Segment data into 4 quartiles to find the mathematical edge
        try:
            df[f"{feature}_bucket"] = pd.qcut(
                df[feature],
                q=4,
                duplicates="drop",
                labels=["Low", "Medium-Low", "Medium-High", "High"],
            )
        except ValueError:
            continue  # Skip if data doesn't variance well

        grouped = (
            df.groupby(f"{feature}_bucket", observed=False)
            .agg(
                sample_size=("Outcome", "count"),
                win_rate=("Outcome", "mean"),
                avg_pnl=("PnL_Net", "mean"),
                min_val=(feature, "min"),
                max_val=(feature, "max"),
            )
            .reset_index()
        )

        for _, row in grouped.iterrows():
            report.append(
                {
                    "Feature": feature,
                    "Bucket": row[f"{feature}_bucket"],
                    "Range": f"{row['min_val']:.4f} to {row['max_val']:.4f}",
                    "Sample_Size": row["sample_size"],
                    "Win_Rate": f"{row['win_rate']*100:.1f}%",
                    "Avg_PnL": f"${row['avg_pnl']:.2f}",
                }
            )

    report_df = pd.DataFrame(report)
    report_df.to_csv("/code/feature_edge_report.csv", index=False)

    print(report_df.to_string(index=False))
    print("\n Edge Report saved to: /code/feature_edge_report.csv")


if __name__ == "__main__":
    analyze_features()
