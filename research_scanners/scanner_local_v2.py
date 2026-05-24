import os
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

LOCAL_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"
TICKERS = ["NVDA", "XLK", "OKLO", "ORCL", "BBAI", "TOPT", "TTD", "TSLA", "HOOD", "ECG"]

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

def find_recent_resistance_zone(df_weekly: pd.DataFrame):
    lookback_df = df_weekly.iloc[-54:-1].copy()
    
    if len(lookback_df) < 10:
        return None, None, None
        
    lookback_df['Is_Pivot'] = (
        (lookback_df['high'] > lookback_df['high'].shift(1)) &
        (lookback_df['high'] > lookback_df['high'].shift(2)) &
        (lookback_df['high'] > lookback_df['high'].shift(-1)) &
        (lookback_df['high'] > lookback_df['high'].shift(-2))
    )
    
    pivots = lookback_df[lookback_df['Is_Pivot']]
    
    if pivots.empty:
        return None, None, None
        
    target_candle = pivots.iloc[-1]
    wick_top = target_candle['high']
    body_top = max(target_candle['open'], target_candle['close'])
    
    return body_top, wick_top, target_candle.name

def scan_tickers():
    results = []

    for ticker in TICKERS:
        try:
            df_weekly = load_local_weekly_data(ticker)
            if df_weekly is None or len(df_weekly) < 25:
                continue
            
            df_weekly['Vol_20_MA'] = df_weekly['volume'].rolling(window=20).mean()
            
            # Get the zone levels and the exact date it formed
            body_top, wick_top, pivot_date = find_recent_resistance_zone(df_weekly)
            
            if not body_top or pivot_date is None:
                continue
                
            current_price = df_weekly['close'].iloc[-1]
            
            # CRITICAL FIX: Find the breakout candle sequence AFTER the pivot formed
            post_pivot_df = df_weekly.loc[pivot_date:]
            breakout_candles = post_pivot_df[post_pivot_df['close'] > wick_top]
            
            if not breakout_candles.empty:
                # Target the first candle that cleared the resistance zone
                breakout_candle = breakout_candles.iloc[0]
                
                # Verify if the breakout week itself had higher than average volume
                if breakout_candle['volume'] > breakout_candle['Vol_20_MA']:
                    vol_confirmed = "YES"
                else:
                    vol_confirmed = "NO"
            else:
                vol_confirmed = "NO BREAKOUT"
            
            distance_pct = ((current_price - wick_top) / wick_top) * 100
            
            results.append({
                "Ticker": ticker,
                "Res_Body_Top": round(float(body_top), 2),
                "Res_Wick_Top": round(float(wick_top), 2),
                "Current_Price": round(float(current_price), 2),
                "Dist_to_Res": f"{round(float(distance_pct), 2)}%",
                "Vol_Confirmed": vol_confirmed
            })
        except Exception:
            pass

    if results:
        df_results = pd.DataFrame(results)
        print("\n=== STRATEGY 1.6: LOCAL BREAKOUT ZONES WITH ACCURATE VOLUME ===")
        print(df_results.to_string(index=False))
    else:
        print("\nNo valid zones could be calculated from local data.")

if __name__ == "__main__":
    scan_tickers()
