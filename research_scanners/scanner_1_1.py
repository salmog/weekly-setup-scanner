import yfinance as yf
import pandas as pd
import warnings
warnings.filterwarnings("ignore")

tickers = ["NVDA", "XLK", "OKLO", "ORCL", "BBAI", "TOPT", "TTD", "NAIL", "KRE", "TSLA", "HOOD", "ECG"]

def find_dynamic_resistance(weekly_df: pd.DataFrame, daily_df: pd.DataFrame, current_date: pd.Timestamp) -> float:
    lookbacks = [5, 12, 20, 26, 52]
    
    for weeks in lookbacks:
        start_date = current_date - pd.Timedelta(weeks=weeks)
        daily_slice = daily_df.loc[start_date:current_date]
        
        if daily_slice.empty: 
            continue
            
        # Sort daily highs from highest to lowest to find the true ceiling, ignoring single rogue wicks
        highs_sorted = daily_slice['High'].sort_values(ascending=False).unique()
        
        for candidate_peak in highs_sorted:
            lower_bound = candidate_peak * 0.999
            upper_bound = candidate_peak * 1.001
            
            touches = ((daily_slice['High'] >= lower_bound) & (daily_slice['High'] <= upper_bound)).sum()
            
            if touches >= 3:
                return candidate_peak
            
    fallback_start = current_date - pd.Timedelta(weeks=26)
    return daily_df.loc[fallback_start:current_date]['High'].max()

def scan_tickers():
    results = []
    end_date = pd.Timestamp.now()
    start_date = end_date - pd.Timedelta(weeks=104) 

    for ticker in tickers:
        try:
            df_daily = yf.Ticker(ticker).history(start=start_date, end=end_date)
            if df_daily.empty: 
                continue
            
            df_daily.index = df_daily.index.tz_localize(None)
            
            df_weekly = df_daily.resample('W-FRI').agg({
                'High': 'max', 'Close': 'last'
            }).dropna()

            if len(df_weekly) < 52: 
                continue

            latest_week_date = df_weekly.index[-1]
            res_line = find_dynamic_resistance(df_weekly, df_daily, latest_week_date)
            
            current_price = df_daily['Close'].iloc[-1]
            distance_pct = ((current_price - res_line) / res_line) * 100
            
            results.append({
                "Ticker": ticker,
                "Entry_Level": round(float(res_line), 2),
                "Current_Price": round(float(current_price), 2),
                "Distance": f"{round(float(distance_pct), 2)}%"
            })
        except Exception:
            pass

    df_results = pd.DataFrame(results)
    print("\n=== STRATEGY 1.1 ENTRY LEVELS (0.1% Tolerance, Multi-Peak Scan) ===")
    print(df_results.to_string(index=False))

if __name__ == "__main__":
    scan_tickers()
