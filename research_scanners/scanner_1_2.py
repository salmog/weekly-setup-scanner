import yfinance as yf
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

tickers = ["NVDA", "XLK", "OKLO", "ORCL", "BBAI", "TOPT", "TTD", "NAIL", "KRE", "TSLA", "HOOD", "ECG"]

def find_weekly_resistance_zone(df_weekly: pd.DataFrame):
    # Look back over the last 52 weeks, excluding the most recent 2 weeks (to allow for breakout/retest)
    lookback_df = df_weekly.iloc[-54:-2].copy()
    
    if len(lookback_df) < 10:
        return None, None
        
    # Find a simple pivot high: a high greater than the 2 weeks before and 2 weeks after
    lookback_df['Is_Pivot'] = (
        (lookback_df['High'] > lookback_df['High'].shift(1)) &
        (lookback_df['High'] > lookback_df['High'].shift(2)) &
        (lookback_df['High'] > lookback_df['High'].shift(-1)) &
        (lookback_df['High'] > lookback_df['High'].shift(-2))
    )
    
    pivots = lookback_df[lookback_df['Is_Pivot']]
    
    if pivots.empty:
        # Fallback: Just take the absolute highest candle in the lookback period
        highest_candle = lookback_df.loc[lookback_df['High'].idxmax()]
    else:
        # Take the most prominent recent pivot
        highest_candle = pivots.loc[pivots['High'].idxmax()]
        
    wick_top = highest_candle['High']
    body_top = max(highest_candle['Open'], highest_candle['Close'])
    
    return body_top, wick_top

def scan_tickers():
    results = []
    end_date = pd.Timestamp.now()
    start_date = end_date - pd.Timedelta(weeks=104) 

    for ticker in tickers:
        try:
            # Fetch daily data
            df_daily = yf.Ticker(ticker).history(start=start_date, end=end_date)
            if df_daily.empty: 
                continue
            
            df_daily.index = df_daily.index.tz_localize(None)
            
            # Resample to Weekly including Open, Low, Close, Volume
            df_weekly = df_daily.resample('W-FRI').agg({
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }).dropna()

            if len(df_weekly) < 52: 
                continue

            # Calculate 20-Week Volume Moving Average
            df_weekly['Vol_20_MA'] = df_weekly['Volume'].rolling(window=20).mean()
            
            # Find Resistance Zone
            body_top, wick_top = find_weekly_resistance_zone(df_weekly)
            
            if not body_top:
                continue
                
            current_price = df_weekly['Close'].iloc[-1]
            current_vol = df_weekly['Volume'].iloc[-1]
            vol_ma = df_weekly['Vol_20_MA'].iloc[-1]
            
            # Check Volume Confirmation (Is current volume higher than average?)
            vol_confirmed = "YES" if current_vol > vol_ma else "NO"
            
            # Distance from the top of the resistance zone (wick top)
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
        print("\n=== STRATEGY 1.2 ENTRY ZONES (Weekly Structure & Volume) ===")
        print(df_results.to_string(index=False))
    else:
        print("\nNo valid zones found for the provided tickers.")

if __name__ == "__main__":
    scan_tickers()
