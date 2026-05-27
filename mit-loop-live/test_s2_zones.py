import os
import pandas as pd
import numpy as np

HISTORICAL_DATA_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"

def calculate_wilders_atr(df, period=14):
    df['prev_close'] = df['close'].shift(1)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['prev_close']).abs()
    tr3 = (df['low'] - df['prev_close']).abs()
    df['true_range'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return df['true_range'].ewm(alpha=1/period, adjust=False).mean()

def load_monthly_trend(symbol):
    m_path = os.path.join(HISTORICAL_DATA_DIR, f"{symbol}_monthly.csv")
    if not os.path.exists(m_path): return {}
    try:
        df = pd.read_csv(m_path)
        df.columns = df.columns.str.lower()
        if 'close' not in df.columns: return {}
        date_col = 'date' if 'date' in df.columns else 'timestamp'
        df[date_col] = pd.to_datetime(df[date_col])
        df['yyyy_mm'] = df[date_col].dt.strftime('%Y-%m')
        df['sma10'] = pd.to_numeric(df['close'], errors='coerce').rolling(10).mean()
        return dict(zip(df['yyyy_mm'], df['close'] > df['sma10']))
    except: return {}

print("==================================================================")
print("🔍 STRATEGY 2: MULTI-ZONE 'NET' DRY-RUN SCANNER")
print("==================================================================")

if not os.path.exists(HISTORICAL_DATA_DIR):
    print("❌ Data directory not found.")
    exit()

all_files = [f for f in os.listdir(HISTORICAL_DATA_DIR) if f.endswith('_weekly.csv')]
setups_found = 0

for file in all_files:
    try:
        symbol = file.split('_')[0].upper()
        csv_d_path = os.path.join(HISTORICAL_DATA_DIR, f"{symbol}_daily.csv")
        if not os.path.exists(csv_d_path): continue
        
        # 1. Calculate Daily 14-ATR
        df_d = pd.read_csv(csv_d_path)
        df_d.columns = df_d.columns.str.lower()
        for col in ['high', 'low', 'close']: df_d[col] = pd.to_numeric(df_d[col], errors='coerce')
        daily_atr = calculate_wilders_atr(df_d, 14).iloc[-1]
        if pd.isna(daily_atr) or daily_atr <= 0: continue
        
        # 2. Process Weekly Structure
        df_w = pd.read_csv(os.path.join(HISTORICAL_DATA_DIR, file))
        df_w.columns = df_w.columns.str.lower()
        if len(df_w) < 60: continue
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df_w.columns: df_w[col] = pd.to_numeric(df_w[col], errors='coerce').fillna(0)
        
        date_col = 'date' if 'date' in df_w.columns else 'timestamp'
        df_w[date_col] = pd.to_datetime(df_w[date_col]).dt.date
        df_w['yyyy_mm'] = pd.to_datetime(df_w[date_col]).dt.strftime('%Y-%m')

        df_w['ema20'] = df_w['close'].ewm(span=20, adjust=False).mean()
        df_w['sma50'] = df_w['close'].rolling(50).mean()
        df_w['vol_avg'] = df_w['volume'].rolling(20).mean()

        df_w['rolling_max_11'] = df_w['high'].rolling(11).max()
        df_w['is_pivot'] = df_w['high'].shift(5) == df_w['rolling_max_11']
        df_w['body_max'] = df_w[['open', 'close']].max(axis=1)
        
        df_w['swing_body_res'] = np.where(df_w['is_pivot'], df_w['body_max'].shift(5), np.nan)
        df_w['swing_body_res'] = pd.Series(df_w['swing_body_res']).ffill()
        df_w['swing_wick_res'] = np.where(df_w['is_pivot'], df_w['high'].shift(5), np.nan)
        df_w['swing_wick_res'] = pd.Series(df_w['swing_wick_res']).ffill()

        m_map = load_monthly_trend(symbol)
        recent_df = df_w.iloc[-60:].copy()
        current_row = recent_df.iloc[-1]
        
        setup_active = False
        weeks_above = 0
        z1_upper, z1_lower = 0.0, 0.0
        
        # We only scan for the "WICK" setup parameters for Strategy 2
        for i in range(1, len(recent_df)):
            row = recent_df.iloc[i]
            prev_row = recent_df.iloc[i-1]
            
            macro_bull = m_map.get(str(row['yyyy_mm']), False)
            wick_res = row['swing_wick_res']
            body_res = row['swing_body_res']
            
            if pd.isna(wick_res) or pd.isna(body_res): continue

            if not setup_active:
                is_liquid = (row['close'] >= 5.0) and ((row['close'] * row['vol_avg']) >= 5000000)
                is_breakout = row['close'] > wick_res and prev_row['close'] <= wick_res
                is_zigzag = row['close'] <= (row['ema20'] * 1.25)
                is_high_vol = row['volume'] > (row['vol_avg'] * 1.5)
                is_aligned = row['ema20'] > row['sma50']
                is_sloping_up = i >= 4 and row['ema20'] > recent_df.iloc[i-4]['ema20']
                
                if is_liquid and is_breakout and is_zigzag and is_high_vol and is_aligned and is_sloping_up:
                    setup_active = True
                    z1_upper = wick_res
                    z1_lower = body_res
                    weeks_above = 0
                continue

            if setup_active:
                if row['close'] < row['sma50'] or weeks_above > 30:
                    setup_active = False
                    continue
                weeks_above += 1

                # If it's the last candle and the setup is still valid
                if i == len(recent_df) - 1 and weeks_above >= 4:  
                    setups_found += 1
                    live_close = float(current_row['close'])
                    atr = float(daily_atr)
                    
                    # Zone 1 Math
                    z1_sl = z1_lower - atr
                    
                    # Zone 2 Math (-5% from Zone 1)
                    z2_upper = z1_upper * 0.95
                    z2_lower = z1_lower * 0.95
                    z2_sl = z2_lower - atr
                    
                    print(f"✅ TICKER: {symbol} (Spot: ${live_close:.2f} | 14D ATR: ${atr:.2f})")
                    print(f"   ► ZONE 1 (Retest):")
                    print(f"      Upper: ${z1_upper:.2f} (Swing Wick)")
                    print(f"      Lower: ${z1_lower:.2f} (Swing Body)")
                    print(f"      Z1 SL: ${z1_sl:.2f}    (-1 ATR from Lower)")
                    print(f"   ► ZONE 2 (Deep Dip / -5%):")
                    print(f"      Upper: ${z2_upper:.2f}")
                    print(f"      Lower: ${z2_lower:.2f}")
                    print(f"      Z2 SL: ${z2_sl:.2f}    (-1 ATR from Lower)")
                    print("-" * 65)

    except Exception as e:
        continue

if setups_found == 0:
    print("No active Strategy 2 setups found in current data.")
print("==================================================================")
