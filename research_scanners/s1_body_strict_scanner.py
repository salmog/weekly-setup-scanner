import os
import glob
import pandas as pd
import numpy as np
import datetime
import warnings
warnings.simplefilter(action='ignore', category=FutureWarning)

DATA_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"
MAX_CONCURRENT_POSITIONS = 10
STARTING_CAPITAL = 100000.0
RISK_PCT = 0.01

def load_monthly_trend(symbol):
    m_path = os.path.join(DATA_DIR, f"{symbol}_monthly.csv")
    if not os.path.exists(m_path): return {}
    try:
        df = pd.read_csv(m_path)
        df.columns = df.columns.str.lower()
        if 'close' not in df.columns: return {}
        date_col = 'date' if 'date' in df.columns else 'timestamp'
        df[date_col] = pd.to_datetime(df[date_col])
        df['sma10'] = df['close'].rolling(10).mean()
        df['yyyy_mm'] = df[date_col].dt.strftime('%Y-%m')
        return dict(zip(df['yyyy_mm'], df['close'] > df['sma10']))
    except:
        return {}

def scan_ticker(filepath):
    symbol = os.path.basename(filepath).split('_')[0].split('.')[0]
    
    try:
        df = pd.read_csv(filepath)
        df.columns = df.columns.str.lower()
        if 'close' not in df.columns: return None
        
        date_col = 'date' if 'date' in df.columns else 'timestamp'
        df[date_col] = pd.to_datetime(df[date_col]).dt.date
        df['yyyy_mm'] = pd.to_datetime(df[date_col]).dt.strftime('%Y-%m')
        
        # S1 Logic Indicators
        df['atr'] = (df['high'] - df['low']).rolling(14).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['sma50'] = df['close'].rolling(50).mean()
        df['vol_avg'] = df['volume'].rolling(20).mean()
        
        # Find structural Resistance Points
        df['rolling_max_11'] = df['high'].rolling(11).max()
        df['is_pivot'] = df['high'].shift(5) == df['rolling_max_11']
        df['body_max'] = df[['open', 'close']].max(axis=1)
        df['swing_body_res'] = np.where(df['is_pivot'], df['body_max'].shift(5), np.nan)
        df['swing_body_res'] = pd.Series(df['swing_body_res']).ffill()
        
        m_map = load_monthly_trend(symbol)
        
        # We only care about the CURRENT setup (the last ~60 days of action)
        recent_df = df.iloc[-60:].copy()
        if recent_df.empty: return None
        
        setup_active = False
        body_level = 0.0
        breakout_vol = 0.0
        weeks_above = 0
        
        # Scan through the recent history to see if a valid setup formed and is still active today
        for i in range(1, len(recent_df)):
            row = recent_df.iloc[i]
            prev_row = recent_df.iloc[i-1]
            
            macro_bull = m_map.get(row['yyyy_mm'], False)
            current_body = row['swing_body_res']
            
            if pd.isna(current_body): continue

            if not setup_active:
                is_liquid = (row['close'] >= 5.0) and ((row['close'] * row['vol_avg']) >= 5000000)
                is_breakout = row['close'] > current_body and prev_row['close'] <= current_body
                is_zigzag = row['close'] <= (row['ema20'] * 1.25)
                is_high_vol = row['volume'] > (row['vol_avg'] * 1.5)
                is_aligned = row['ema20'] > row['sma50']
                
                # Sloping up check (protect against index bounds)
                is_sloping_up = False
                if i >= 4:
                    is_sloping_up = row['ema20'] > recent_df.iloc[i-4]['ema20']

                if is_liquid and is_breakout and macro_bull and is_zigzag and is_high_vol and is_aligned and is_sloping_up:
                    body_level = current_body
                    breakout_vol = row['volume']
                    weeks_above = 0
                    setup_active = True
                continue

            if setup_active:
                if row['close'] < row['sma50'] or weeks_above > 24:
                    setup_active = False
                    continue
                
                # Check for Pullback Retest Trigger on the LAST available day (Today)
                if i == len(recent_df) - 1:
                    if row['low'] <= body_level and weeks_above >= 4 and row['volume'] < breakout_vol:
                        
                        stop_loss = body_level - (1.1 * row['atr'])
                        risk_per_share = row['close'] - stop_loss
                        
                        if risk_per_share > 0:
                            shares = int((STARTING_CAPITAL * RISK_PCT) / risk_per_share)
                            cash_alloc = shares * row['close']
                            
                            return {
                                "Ticker": symbol,
                                "Action": "BUY",
                                "Entry Target": f"${body_level:.2f}",
                                "Current Price": f"${row['close']:.2f}",
                                "Stop Loss": f"${stop_loss:.2f}",
                                "Shares": shares,
                                "Cash Allocation": f"${cash_alloc:.2f}",
                                "Reason": "S1 Body Strict conditions met. Macro bullish, liquid, high-volume breakout held for 4+ weeks. Volume contracted on pullback."
                            }
                weeks_above += 1
                
        return None
    except Exception as e:
        return None

def run_scanner():
    weekly_files = glob.glob(os.path.join(DATA_DIR, "*_weekly.csv"))
    print(f"Executing S1: Body Strict Engine Scan...")
    print(f"Targeting {len(weekly_files)} Weekly Datasets...\n")
    
    found = False
    for file in weekly_files:
        res = scan_ticker(file)
        if res:
            found = True
            print(f"- Ticker: {res['Ticker']}")
            print(f"- Action: {res['Action']}")
            print(f"- Entry Target: {res['Entry Target']}")
            print(f"- Current Price: {res['Current Price']}")
            print(f"- Stop Loss: {res['Stop Loss']}")
            print(f"- Shares: {res['Shares']}")
            print(f"- Cash Allocation: {res['Cash Allocation']}")
            print(f"- Reason: {res['Reason']}\n" + "-"*50)
            
    if not found:
        print("No valid setups currently active for S1_BodyStrict.")

if __name__ == "__main__":
    run_scanner()
