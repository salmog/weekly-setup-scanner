import os


def count_production_tickers():
    """
    Audits the current active directory structure to calculate the
    exact size of the equity database data streams.
    """
    target_dirs = [
        "historical_data",
        "historical_data_new/historical_data",
        "/code/historical_data",
    ]

    found_dir = None
    for d in target_dirs:
        if os.path.exists(d) and os.path.isdir(d):
            found_dir = d
            break

    if not found_dir:
        print("ERROR: Could not locate historical data repositories.")
        return

    all_files = os.listdir(found_dir)
    csv_tickers = [f.split("_")[0] for f in all_files if f.endswith(".csv") and "_" in f]
    unique_tickers = sorted(list(set(csv_tickers)))

    print("\n=========================================================")
    print("                PRODUCTION TICKER METRICS                ")
    print("=========================================================")
    print(f" Total Unique Equities Found : {len(unique_tickers)}")
    print(f" Target Source Repository    : {found_dir}")
    print(f" Sample Scanned Tickers      : {', '.join(unique_tickers[:10])}...")
    print("=========================================================\n")


if __name__ == "__main__":
    count_production_tickers()
