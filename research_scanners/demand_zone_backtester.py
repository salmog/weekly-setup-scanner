import os
import glob
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

DATA_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"
PORTFOLIO_VALUE = 100000.0
RISK_PCT = 0.01
MAX_DOLLAR_RISK = PORTFOLIO_VALUE * RISK_PCT

stats = {
    'total_scanned': 0,
    'failed_data_length': 0,
    'failed_trend_hh_hl': 0,
    'failed_breakout_hold': 0,
    'failed_retest_touch_or_vol': 0,
    'valid_setups': 0
}

def get_atr(high, low, close, n=14):
    tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
    return tr.rolling(n).mean()

def analyze_ticker(filepath):
    ticker = os.path.basename(filepath).replace('_daily.csv', '')
    stats['total_scanned'] += 1
    
    try:
        df = pd.read_csv(filepath)
        df.columns = df.columns.str.lower()
        
        date_col = next((c for c in df.columns if 'date' in c or 'time' in c), None)
        if not date_col: return None
            
        df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
        df.dropna(subset=[date_col], inplace=True)
        df.set_index(date_col, inplace=True)
        df.sort_index(inplace=True)
        
        rename_map = {'open':'Open', 'high':'High', 'low':'Low', 'close':'Close', 'volume':'Volume'}
        df.rename(columns=rename_map, inplace=True)
        
        if 'Close' not in df.columns or len(df) < 150:
            stats['failed_data_length'] += 1
            return None
            
        # Resample entire structure to Weekly
        weekly = df.resample('W-FRI').agg({
            'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
        }).dropna()
        
        if len(weekly) < 52:
            stats['failed_data_length'] += 1
            return None
            
        weekly['ATR'] = get_atr(weekly['High'], weekly['Low'], weekly['Close'], 14)
        
        w_highs = weekly['High'][weekly['High'] == weekly['High'].rolling(5, center=True).max()].dropna()
        w_lows = weekly['Low'][weekly['Low'] == weekly['Low'].rolling(5, center=True).min()].dropna()
        
        if len(w_highs) < 2 or len(w_lows) < 2:
            stats['failed_trend_hh_hl'] += 1
            return None
            
        is_hh = w_highs.iloc[-1] > w_highs.iloc[-2]
        is_hl = w_lows.iloc[-1] > w_lows.iloc[-2]
        
        if not (is_hh and is_hl):
            stats['failed_trend_hh_hl'] += 1
            return None
            
        demand_zone = None
        breakout_vol = None
        
        for peak_price in reversed(w_highs.values[-3:]):
            breakouts = weekly[weekly['Close'] > peak_price]
            if breakouts.empty: continue
                
            bo_date = breakouts.index[0]
            bo_idx = weekly.index.get_loc(bo_date)
            
            if bo_idx + 4 < len(weekly):
                next_4_weeks = weekly.iloc[bo_idx+1 : bo_idx+5]
                if all(next_4_weeks['Close'] > (peak_price * 0.98)):
                    demand_zone = peak_price
                    breakout_vol = weekly.loc[bo_date, 'Volume']
                    break 
                    
        if demand_zone is None:
            stats['failed_breakout_hold'] += 1
            return None
            
        # Analyze pullback strictly on WEEKLY timeframe
        current_week = weekly.iloc[-1]
        
        is_retest = (current_week['Low'] <= demand_zone * 1.02) and (current_week['Close'] >= demand_zone * 0.98)
        weaker_volume = current_week['Volume'] < breakout_vol
        
        if is_retest and weaker_volume:
            # StopLoss = Entry - ATR
            stop_loss = current_week['Close'] - (1.0 * current_week['ATR'])
            stop_distance = current_week['Close'] - stop_loss
            
            if stop_distance <= 0: return None
                
            shares = int(MAX_DOLLAR_RISK / stop_distance)
            
            if shares > 0:
                cash_allocation = shares * current_week['Close']
                actual_risk_pct = ((shares * stop_distance) / PORTFOLIO_VALUE) * 100
                
                stats['valid_setups'] += 1
                return {
                    "Ticker": ticker, 
                    "Action": "BUY", 
                    "Confidence": 95,
                    "Entry Price": f"${current_week['Close']:.2f}",
                    "Stop-Loss": f"${stop_loss:.2f}",
                    "Shares / Allocation": f"{shares} shares / ${cash_allocation:.2f}",
                    "Risk %": f"{actual_risk_pct:.2f}%",
                    "Reason": "Weekly structure intact. Retest on weekly chart with weekly volume contraction."
                }
        
        stats['failed_retest_touch_or_vol'] += 1
        return None
    except Exception:
        return None

def run_backtest():
    csv_files = glob.glob(os.path.join(DATA_DIR, "*_daily.csv"))
    
    for file in csv_files:
        result = analyze_ticker(file)
        if result and result['Action'] == 'BUY':
            print(f"- Ticker: {result['Ticker']}")
            print(f"- Action: {result['Action']}")
            print(f"- Confidence: {result['Confidence']}")
            print(f"- Entry Price: {result['Entry Price']}")
            print(f"- Stop-Loss: {result['Stop-Loss']}")
            print(f"- Shares / Allocation: {result['Shares / Allocation']}")
            print(f"- Risk %: {result['Risk %']}")
            print(f"- Reason: {result['Reason']}\n" + "-"*40)
            
    print("\n=== SCANNER DROP-OFF FUNNEL ===")
    print(f"Total Scanned         : {stats['total_scanned']}")
    print(f"Failed Data Length    : {stats['failed_data_length']}")
    print(f"Failed Weekly HH/HL   : {stats['failed_trend_hh_hl']}")
    print(f"Failed 4W Hold        : {stats['failed_breakout_hold']}")
    print(f"Failed Retest/Volume  : {stats['failed_retest_touch_or_vol']}")
    print(f"VALID SETUPS FOUND    : {stats['valid_setups']}")

if __name__ == "__main__":
    run_backtest()
