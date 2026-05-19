import asyncio
import glob
from pathlib import Path

from app.core.database import AsyncSessionLocal, engine
from app.data_sources.ibkr_csv import IBKRCsvProvider
from app.services.market_data_service import MarketDataService

# Exact translation matrix mapping file string names to unified platform tokens
TIMEFRAME_MAP = {"hourly": "1H", "4h": "4H", "daily": "1D", "weekly": "1W", "monthly": "1M"}


async def bulk_ingest() -> None:
    # Target path mapped inside the docker workspace container environment
    data_dir = Path("/code/historical_data")
    if not data_dir.exists():
        print(
            f" Error: Target directory {data_dir} not found. Ensure volume mapping is configured."
        )
        return

    csv_files = glob.glob(str(data_dir / "*.csv"))
    if not csv_files:
        print(
            " No data targets found matching *.csv extension rules inside target path /code/historical_data."
        )
        return

    csv_provider = IBKRCsvProvider()
    print(f" Found {len(csv_files)} historical data targets. Processing batch pipeline...")

    for file_path in csv_files:
        filename = Path(file_path).stem  # e.g., 'JPM_daily'
        if "_" not in filename:
            print(f" Skipping file with non-standard naming convention: {filename}")
            continue

        raw_symbol, raw_tf = filename.split("_", 1)
        symbol = raw_symbol.upper().strip()
        timeframe = TIMEFRAME_MAP.get(raw_tf.lower().strip(), raw_tf.upper().strip())

        print(f" Processing: {symbol} | Timeframe: {timeframe} ({Path(file_path).name})")

        try:
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            parsed_records = csv_provider.parse_csv_stream(content, symbol, timeframe)
            if not parsed_records:
                print("   Skipped: 0 valid records parsed.")
                continue

            async with AsyncSessionLocal() as db:
                metrics = await MarketDataService.ingest_candles(db, parsed_records)
                print(
                    f"   Complete: Ingested={metrics['inserted']}, Skipped/Duplicate={metrics['skipped']}"
                )

        except Exception as e:
            print(f"   Error processing file {filename}: {str(e)}")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(bulk_ingest())
