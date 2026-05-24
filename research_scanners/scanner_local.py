import os
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

LOCAL_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"
TICKERS = ["NVDA", "XLK", "OKLO", "ORCL", "BBAI", "TOPT", "TTD", "TSLA", "HOOD", "ECG"]

def load_local_weekly_data(ticker):
    """Loads local daily CSV and cleanly resamples it to Friday weekly candles."""
    daily_path = os.path.join(LOCAL_DIR, f"{ticker}_daily.csv")
    if not os.path.exists(daily_path):
        return None
        
    try:
        df = pd.read_csv(daily_path)
        # Parse UTC date and strip timezone to get cleanly aligned dates
        df['date'] = pd.to_datetime(df['date'], utc=True).dt.tz_localize(None).dt.normalize()
        df.set_index('date', inplace=True)
        
        # Resample daily candles to true weekly candles ending on Friday
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
    """
    Finds the most recent major weekly swing high pivot.
    Returns the Body Top (max of Open/Close) and the Wick Top (High).
    """
    # Look back over historical data, excluding the actively forming current week
    lookback_df = df_weekly.iloc[-54:-1].copy()
    
    if len(lookback_df) < 10:
        return None, None
        
    # Structural pivot high logic: High is higher than 2 weeks prior and 2 weeks post
    lookback_df['Is_Pivot'] = (
        (lookback_df['high'] > lookback_df['high'].shift(1)) &
        (lookback_df['high'] > lookback_df['high'].shift(2)) &
        (lookback_df['high'] > lookback_df['high'].shift(-1)) &
        (lookback_df['high'] > lookback_df['high'].shift(-2))
    )
    
    pivots = lookback_df[lookback_df['Is_Pivot']]
    
    if pivots.empty:
        return None, None
        
    # Grab the most recent structural swing high level (closest to current price action)
    target_candle = pivots.iloc[-1]
        
    wick_top = target_candle['high']
    body_top = max(target_candle['open'], target_candle['close'])
    
    return body_top, wick_top

def scan_tickers():
    results = []

    for ticker in TICKERS:
        try:
            df_weekly = load_local_weekly_data(ticker)
            if df_weekly is None or len(df_weekly) < 25:
                continue
            
            # Calculate local 20-Week Volume Moving Average
            df_weekly['Vol_20_MA'] = df_weekly['volume'].rolling(window=20).mean()
            
            # Identify the resistance zone levels
            body_top, wick_top = find_recent_resistance_zone(df_weekly)
            
            if not body_top:
                continue
                
            current_price = df_weekly['close'].iloc[-1]
            
            # Volume Confirmation: Check if the breakout/momentum move had higher than average volume
            recent_max_vol = df_weekly['volume'].iloc[-2:].max()
            vol_ma = df_weekly['Vol_20_MA'].iloc[-1]
            vol_confirmed = "YES" if recent_max_vol > vol_ma else "NO"
            
            # Percentage distance from current price to the wick top ceiling
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
        print("\n=== STRATEGY 1.5: PURE LOCAL DATA BREAKOUT & RETEST ZONES ===")
        print(df_results.to_string(index=False))
    else:
        print("\nNo valid zones could be calculated from local data.")

if __name__ == "__main__":
    scan_tickers()
