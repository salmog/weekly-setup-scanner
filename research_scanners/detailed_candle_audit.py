import os
import pandas as pd
import yfinance as yf
import warnings
warnings.filterwarnings("ignore")

LOCAL_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"
TICKERS = ["NVDA", "XLK", "OKLO", "ORCL", "BBAI", "TOPT", "TTD", "TSLA", "HOOD", "ECG"]

def get_local_candles(ticker, tf_type):
    daily_path = os.path.join(LOCAL_DIR, f"{ticker}_daily.csv")
    if not os.path.exists(daily_path):
        return None
    try:
        df = pd.read_csv(daily_path)
        df['date'] = pd.to_datetime(df['date'], utc=True).dt.tz_localize(None).dt.normalize()
        df.set_index('date', inplace=True)
        if tf_type == 'Weekly':
            df = df.resample('W-FRI').agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
            }).dropna()
        return df[['open', 'high', 'low', 'close', 'volume']].sort_index()
    except Exception:
        return None

def get_yf_candles(ticker, tf_type):
    try:
        period = "3mo" if tf_type == "Daily" else "1y"
        df = yf.Ticker(ticker).history(period=period)
        if df.empty: return None
        df.index = df.index.tz_localize(None).floor('D')
        if tf_type == 'Weekly':
            df = df.resample('W-FRI').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
        df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
        return df[['open', 'high', 'low', 'close', 'volume']]
    except Exception:
        return None

def perform_detailed_audit():
    for tf in ['Daily', 'Weekly']:
        print(f"\n=========================================================")
        print(f"      RAW CANDLE AUDIT: {tf.upper()} TIMEFRAME (LATEST CANDLE)")
        print(f"=========================================================")
        
        table_data = []
        for ticker in TICKERS:
            local_df = get_local_candles(ticker, tf)
            yf_df = get_yf_candles(ticker, tf)
            
            if local_df is None or yf_df is None:
                continue
                
            # Align by date to make sure we look at the identical day/week
            merged = local_df.merge(yf_df, left_index=True, right_index=True, suffixes=('_IBKR', '_YF'))
            if merged.empty:
                continue
                
            # Pull the absolute latest fully matched candle
            latest_row = merged.iloc[-1]
            date_str = merged.index[-1].strftime('%Y-%m-%d')
            
            table_data.append({
                "Ticker": ticker,
                "Date": date_str,
                "High_IBKR": round(latest_row['high_IBKR'], 2),
                "High_YF": round(latest_row['high_YF'], 2),
                "Close_IBKR": round(latest_row['close_IBKR'], 2),
                "Close_YF": round(latest_row['close_YF'], 2),
                "Vol_IBKR (M)": f"{round(latest_row['volume_IBKR'] / 1_000_000, 2)}M",
                "Vol_YF (M)": f"{round(latest_row['volume_YF'] / 1_000_000, 2)}M"
            })
            
        df_table = pd.DataFrame(table_data)
        if not df_table.empty:
            print(df_table.to_string(index=False))
        else:
            print("No matching data rows found to compare.")

if __name__ == "__main__":
    perform_detailed_audit()
