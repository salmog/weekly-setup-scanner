import pandas as pd
import os

data_dir = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"

for tf in ['weekly', 'daily']:
    file_path = os.path.join(data_dir, f"MNST_{tf}.csv")
    print(f"\n" + "="*60)
    print(f" 📊 MNST LAST 20 {tf.upper()} CANDLES")
    print("="*60)
    try:
        df = pd.read_csv(file_path)
        df.columns = df.columns.str.lower()
        date_col = 'date' if 'date' in df.columns else 'time' if 'time' in df.columns else df.columns[0]
        
        # Select OHLCV columns if they exist
        cols = [date_col, 'open', 'high', 'low', 'close', 'volume']
        cols = [c for c in cols if c in df.columns]
        
        print(df[cols].tail(20).to_string(index=False))
    except Exception as e:
        print(f"❌ Error loading {tf} data: {e}")
