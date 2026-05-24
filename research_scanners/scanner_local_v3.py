import os
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

LOCAL_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"
# Added TAN to the ticker list
TICKERS = ["NVDA", "XLK", "OKLO", "ORCL", "BBAI", "TOPT", "TTD", "TSLA", "HOOD", "ECG", "TAN"]

def load_local_weekly_data(ticker):
    daily_path = os.path.join(LOCAL_DIR, f"{ticker}_daily.csv")
    if not os.path.exists(daily_path):
        return None
        
    try:
        df = pd.read_csv(daily_path)
        df['date'] = pd.to_datetime(df['date'], utc=True).dt.tz_localize(None).dt.normalize()
        df.set_index('date', inplace=True)
        
        df_weekly = df.resample('W-FRI').agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()
        
        return df_weekly
    except Exception:
        return None

def find_historical_breakouts(ticker, df_weekly: pd.DataFrame):
    df_weekly = df_weekly.copy()
    
    # Calculate 20-Week Volume Moving Average across the whole history
    df_weekly['Vol_20_MA'] = df_weekly['volume'].rolling(window=20).mean()
    
    # Structural pivot high logic across all historical candles
    df_weekly['Is_Pivot'] = (
        (df_weekly['high'] > df_weekly['high'].shift(1)) &
        (df_weekly['high'] > df_weekly['high'].shift(2)) &
        (df_weekly['high'] > df_weekly['high'].shift(-1)) &
        (df_weekly['high'] > df_weekly['high'].shift(-2))
    )
    
    pivots = df_weekly[df_weekly['Is_Pivot']]
    ticker_events = []
    
    for pivot_date, pivot_row in pivots.iterrows():
        wick_top = pivot_row['high']
        body_top = max(pivot_row['open'], pivot_row['close'])
        
        # Look forward strictly AFTER the pivot week to see when it was broken
        post_pivot_df = df_weekly.loc[pivot_date:].iloc[1:]
        
        # Find the first weekly candle that closed above this pivot's wick ceiling
        breakout_candles = post_pivot_df[post_pivot_df['close'] > wick_top]
        
        if not breakout_candles.empty:
            breakout_candle = breakout_candles.iloc[0]
            breakout_date = breakout_candles.index[0]
            
            # Check volume confirmation ON the breakout week itself
            if breakout_candle['volume'] > breakout_candle['Vol_20_MA']:
                vol_confirmed = "YES"
            else:
                vol_confirmed = "NO"
                
            ticker_events.append({
                "Ticker": ticker,
                "Pivot_Date": pivot_date.strftime('%Y-%m-%d'),
                "Breakout_Date": breakout_date.strftime('%Y-%m-%d'),
                "Res_Body_Top": round(float(body_top), 2),
                "Res_Wick_Top": round(float(wick_top), 2),
                "Vol_Confirmed": vol_confirmed,
                "_raw_bk_date": breakout_date # temporary field for chronological sorting
            })
            
    # Sort strictly by breakout date (most recent first) and select the last 3 occurrences
    ticker_events = sorted(ticker_events, key=lambda x: x['_raw_bk_date'], reverse=True)[:3]
    
    # Clean up the sorting key before rendering table
    for event in ticker_events:
        del event['_raw_bk_date']
        
    return ticker_events

def scan_tickers():
    all_results = []

    for ticker in TICKERS:
        df_weekly = load_local_weekly_data(ticker)
        if df_weekly is None or len(df_weekly) < 25:
            continue
            
        try:
            breakout_history = find_historical_breakouts(ticker, df_weekly)
            all_results.extend(breakout_history)
        except Exception:
            pass

    if all_results:
        df_results = pd.DataFrame(all_results)
        print("\n=== STRATEGY 1.7: LAST 3 HISTORICAL BREAKOUT EVENTS (LOCAL DATA) ===")
        print(df_results.to_string(index=False))
    else:
        print("\nNo historical breakout events found in the local database files.")

if __name__ == "__main__":
    scan_tickers()
