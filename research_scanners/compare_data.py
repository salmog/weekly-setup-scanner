import os
import pandas as pd
import yfinance as yf
import warnings

warnings.filterwarnings("ignore")

LOCAL_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"
TICKERS = ["NVDA", "XLK", "OKLO", "ORCL", "BBAI", "TOPT", "TTD", "NAIL", "KRE", "TSLA", "HOOD", "ECG"]

def load_local_data(ticker, tf_type):
    """Loads local CSV, normalizes dates, and resamples to Weekly if needed."""
    daily_path = os.path.join(LOCAL_DIR, f"{ticker}_daily.csv")
    weekly_path = os.path.join(LOCAL_DIR, f"{ticker}_weekly.csv")
    
    # Decide which file to load based on timeframe
    if tf_type == 'Weekly' and os.path.exists(weekly_path):
        target_path = weekly_path
        needs_resampling = False
    elif tf_type == 'Weekly' and os.path.exists(daily_path):
        target_path = daily_path
        needs_resampling = True
    elif tf_type == 'Daily' and os.path.exists(daily_path):
        target_path = daily_path
        needs_resampling = False
    else:
        return None

    try:
        df = pd.read_csv(target_path)
        
        # Parse the UTC date string and strip timezone to match YF
        df['date'] = pd.to_datetime(df['date'], utc=True).dt.tz_localize(None).dt.normalize()
        df.set_index('date', inplace=True)
        
        if needs_resampling:
            df = df.resample('W-FRI').agg({
                'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'
            }).dropna()
            
        return df[['open', 'high', 'low', 'close', 'volume']].sort_index().tail(20)
    except Exception:
        return None

def fetch_yf_data(ticker, tf_type):
    """Fetches YF data and normalizes to match local structure."""
    try:
        period = "3mo" if tf_type == "Daily" else "1y"
        df = yf.Ticker(ticker).history(period=period)
        
        if df.empty: 
            return None
            
        df.index = df.index.tz_localize(None).floor('D')
        
        if tf_type == 'Weekly':
            df = df.resample('W-FRI').agg({
                'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
            }).dropna()
            
        # Rename columns to lowercase to match local IBKR data
        df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
        return df[['open', 'high', 'low', 'close', 'volume']].tail(20)
    except Exception:
        return None

def compare_datasets():
    results = []
    
    print("\nFetching data and comparing datasets... Please wait.\n")
    
    for ticker in TICKERS:
        for tf in ['Daily', 'Weekly']:
            local_df = load_local_data(ticker, tf)
            yf_df = fetch_yf_data(ticker, tf)
            
            if local_df is None:
                results.append({"Ticker": ticker, "TF": tf, "Status": "Missing Local Data", "Matched_Dates": 0, "Max_Price_Diff": "-", "Max_Vol_Diff_%": "-"})
                continue
            if yf_df is None:
                results.append({"Ticker": ticker, "TF": tf, "Status": "Missing YF Data", "Matched_Dates": 0, "Max_Price_Diff": "-", "Max_Vol_Diff_%": "-"})
                continue
                
            # Merge on dates
            merged = local_df.merge(yf_df, left_index=True, right_index=True, suffixes=('_ibkr', '_yf'))
            matched_count = len(merged)
            
            if matched_count == 0:
                results.append({"Ticker": ticker, "TF": tf, "Status": "Date Mismatch", "Matched_Dates": 0, "Max_Price_Diff": "-", "Max_Vol_Diff_%": "-"})
                continue
                
            # Calculate Max Price Difference
            merged['O_diff'] = abs(merged['open_ibkr'] - merged['open_yf'])
            merged['H_diff'] = abs(merged['high_ibkr'] - merged['high_yf'])
            merged['L_diff'] = abs(merged['low_ibkr'] - merged['low_yf'])
            merged['C_diff'] = abs(merged['close_ibkr'] - merged['close_yf'])
            max_price_diff = merged[['O_diff', 'H_diff', 'L_diff', 'C_diff']].max().max()
            
            # Calculate Max Volume % Difference
            merged['Vol_diff_%'] = (abs(merged['volume_ibkr'] - merged['volume_yf']) / (merged['volume_ibkr'] + 1)) * 100
            max_vol_diff = merged['Vol_diff_%'].max()
            
            # Allow 2 cents of float tolerance for identical status
            status = "IDENTICAL" if max_price_diff <= 0.02 and max_vol_diff < 1.0 else "DIFF FOUND"
            
            results.append({
                "Ticker": ticker,
                "TF": tf,
                "Status": status,
                "Matched_Dates": matched_count,
                "Max_Price_Diff": f"${round(max_price_diff, 3)}",
                "Max_Vol_Diff_%": f"{round(max_vol_diff, 2)}%"
            })
            
    df_results = pd.DataFrame(results)
    print("=== DATA COMPARISON: IBKR LOCAL VS YFINANCE (Last 20 Candles) ===")
    print(df_results.to_string(index=False))

if __name__ == "__main__":
    compare_datasets()
