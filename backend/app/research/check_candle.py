import os
import argparse
import pandas as pd

def check_candle(ticker, tf, target_date):
    repo = "historical_data" if os.path.exists("historical_data") else "/code/historical_data"
    
    # Handle filename formats
    if tf.lower() in ['d', 'daily']:
        file_path = os.path.join(repo, f"{ticker.upper()}.csv")
        if not os.path.exists(file_path):
            file_path = os.path.join(repo, f"{ticker.upper()}_daily.csv")
    else:
        file_path = os.path.join(repo, f"{ticker.upper()}_{tf.lower()}.csv")

    if not os.path.exists(file_path):
        print(f"ERROR: Could not find data file for {ticker.upper()} ({tf}) at {file_path}")
        return

    df = pd.read_csv(file_path)
    df.columns = df.columns.str.lower()
    
    date_col = 'date' if 'date' in df.columns else ('timestamp' if 'timestamp' in df.columns else None)
    if not date_col:
        print("ERROR: No date column found in CSV.")
        return

    df[date_col] = pd.to_datetime(df[date_col]).dt.date

    print(f"\n[{ticker.upper()} | {tf.upper()} DATA]")
    print("="*75)
    
    if target_date:
        try:
            dt = pd.to_datetime(target_date).date()
            match = df[df[date_col] == dt]
            if match.empty:
                print(f"No exact match for {dt}. Showing closest surrounding candles:")
                df['diff'] = abs(df[date_col] - dt)
                closest = df.sort_values('diff').head(5).sort_values(date_col)
                print(closest[[date_col, 'open', 'high', 'low', 'close', 'volume']].to_string(index=False))
            else:
                print(match[[date_col, 'open', 'high', 'low', 'close', 'volume']].to_string(index=False))
        except Exception as e:
            print(f"Date parsing error: {e}")
    else:
        print("No date provided. Showing last 10 candles:")
        print(df.tail(10)[[date_col, 'open', 'high', 'low', 'close', 'volume']].to_string(index=False))
    print("="*75 + "\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Check specific candles in local database.')
    parser.add_argument('--ticker', type=str, required=True, help='Ticker symbol (e.g. UHAL)')
    parser.add_argument('--tf', type=str, default='weekly', help='Timeframe (daily, weekly, monthly)')
    parser.add_argument('--date', type=str, default=None, help='Target date YYYY-MM-DD (optional)')
    
    args = parser.parse_args()
    check_candle(args.ticker, args.tf, args.date)
