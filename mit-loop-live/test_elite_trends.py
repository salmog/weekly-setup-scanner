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

print("==================================================================")
print("👑 SCANNING FOR ELITE TECHNICAL UPTRENDS WITH CLEAN GEOMETRY")
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
        
        # 1. Daily ATR
        df_d = pd.read_csv(csv_d_path)
        df_d.columns = df_d.columns.str.lower()
        for col in ['high', 'low', 'close']: df_d[col] = pd.to_numeric(df_d[col], errors='coerce')
        daily_atr = calculate_wilders_atr(df_d, 14).iloc[-1]
        
        # 2. Weekly Data
        df_w = pd.read_csv(os.path.join(HISTORICAL_DATA_DIR, file))
        df_w.columns = df_w.columns.str.lower()
        if len(df_w) < 200: continue  # Must have deep history to calculate SMA200
        
        for col in ['open', 'high', 'low', 'close', 'volume']:
            if col in df_w.columns: df_w[col] = pd.to_numeric(df_w[col], errors='coerce').fillna(0)
        
        # Moving Averages
        df_w['ema20'] = df_w['close'].ewm(span=20, adjust=False).mean()
        df_w['sma50'] = df_w['close'].rolling(50).mean()
        df_w['sma200'] = df_w['close'].rolling(200).mean()
        df_w['vol_avg'] = df_w['volume'].rolling(20).mean()

        # Structural Pivots
        df_w['rolling_max_11'] = df_w['high'].rolling(11).max()
        df_w['is_pivot'] = df_w['high'].shift(5) == df_w['rolling_max_11']
        df_w['body_max'] = df_w[['open', 'close']].max(axis=1)
        
        df_w['swing_body_res'] = np.where(df_w['is_pivot'], df_w['body_max'].shift(5), np.nan)
        df_w['swing_body_res'] = pd.Series(df_w['swing_body_res']).ffill()
        df_w['swing_wick_res'] = np.where(df_w['is_pivot'], df_w['high'].shift(5), np.nan)
        df_w['swing_wick_res'] = pd.Series(df_w['swing_wick_res']).ffill()

        # --- ELITE INSTITUTIONAL TREND FILTERS ---
        lookback = df_w.iloc[-20:] # Analyze the last 20 weeks of the run
        
        # Filter 1: The Stack (EMA20 > SMA50 > SMA200)
        current_row = df_w.iloc[-1]
        is_stacked = current_row['ema20'] > current_row['sma50'] > current_row['sma200']
        
        # Filter 2: Slope Continuity (EMA20 rising for at least 8 consecutive weeks)
        ema20_diff = df_w['ema20'].diff()
        is_sloping_up = (ema20_diff.iloc[-8:] > 0).all()
        
        # Filter 3: Institutional Defense (Price stays above EMA20 for at least 85% of the last 20 weeks)
        above_ema_count = (lookback['close'] > lookback['ema20']).sum()
        is_clean_defense = (above_ema_count / 20) >= 0.85
        
        # Check Liquidity
        is_liquid = (current_row['close'] >= 5.0) and ((current_row['close'] * current_row['vol_avg']) >= 5000000)

        if is_stacked and is_sloping_up and is_clean_defense and is_liquid:
            z1_upper = float(current_row['swing_wick_res'])
            z1_lower = float(current_row['swing_body_res'])
            
            if pd.isna(z1_upper) or pd.isna(z1_lower) or z1_upper <= 0: continue
            
            # Check if current price is within a reasonable distance to the structure to be actionable
            live_close = float(current_row['close'])
            dist_to_floor = ((live_close - z1_upper) / z1_upper) * 100
            
            if 0 <= dist_to_floor <= 15:  # Only print if it's currently setting up or pulling back close by
                setups_found += 1
                atr = float(daily_atr)
                
                # Step 1 Math
                z1_sl = z1_lower - atr
                
                # Step 2 Math (Forced -6% for step-down testing)
                z2_upper = z1_upper * 0.94
                z2_lower = z1_lower * 0.94
                z2_sl = z2_lower - atr
                
                print(f"👑 ELITE TREND DETECTED: {symbol} (Spot: ${live_close:.2f} | Distance to Floor: +{dist_to_floor:.2f}%)")
                print(f"   📊 Trend Cleanliness: Price spent {above_ema_count*5}% of the last 5 months strictly above the Weekly EMA20.")
                print(f"   ► STEP 1 (Zone 1 Retest Zone):")
                print(f"      Upper Entry (Wick): ${z1_upper:.2f}")
                print(f"      Lower Entry (Body): ${z1_lower:.2f}")
                print(f"      Step 1 Stop-Loss:   ${z1_sl:.2f}  [-1 ATR from Body]")
                print(f"   ► STEP 2 (Zone 2 Sequential Recovery Zone):")
                print(f"      Upper Entry:        ${z2_upper:.2f}")
                print(f"      Lower Entry:        ${z2_lower:.2f}")
                print(f"      Step 2 Stop-Loss:   ${z2_sl:.2f}")
                print("-" * 75)

    except Exception as e:
        continue

if setups_found == 0:
    print("No stocks in the local database currently meet the pristine Elite Trend criteria.")
print("==================================================================")
