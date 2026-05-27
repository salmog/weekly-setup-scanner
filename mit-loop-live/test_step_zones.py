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
print("🔍 STEP-DOWN ZONE VERIFICATION (IGNORING STRICT RULES)")
print("==================================================================")

all_files = [f for f in os.listdir(HISTORICAL_DATA_DIR) if f.endswith('_weekly.csv')]
count = 0

for file in all_files:
    if count >= 5: break
    try:
        symbol = file.split('_')[0].upper()
        csv_d_path = os.path.join(HISTORICAL_DATA_DIR, f"{symbol}_daily.csv")
        if not os.path.exists(csv_d_path): continue
        
        df_d = pd.read_csv(csv_d_path)
        df_d.columns = df_d.columns.str.lower()
        for col in ['high', 'low', 'close']: df_d[col] = pd.to_numeric(df_d[col], errors='coerce')
        daily_atr = calculate_wilders_atr(df_d, 14).iloc[-1]
        
        df_w = pd.read_csv(os.path.join(HISTORICAL_DATA_DIR, file))
        df_w.columns = df_w.columns.str.lower()
        for col in ['open', 'high', 'low', 'close']: df_w[col] = pd.to_numeric(df_w[col], errors='coerce').fillna(0)
        
        df_w['rolling_max_11'] = df_w['high'].rolling(11).max()
        df_w['is_pivot'] = df_w['high'].shift(5) == df_w['rolling_max_11']
        df_w['body_max'] = df_w[['open', 'close']].max(axis=1)
        
        # Calculate Wick (Upper) and Body (Lower)
        df_w['swing_body_res'] = np.where(df_w['is_pivot'], df_w['body_max'].shift(5), np.nan)
        df_w['swing_body_res'] = pd.Series(df_w['swing_body_res']).ffill()
        df_w['swing_wick_res'] = np.where(df_w['is_pivot'], df_w['high'].shift(5), np.nan)
        df_w['swing_wick_res'] = pd.Series(df_w['swing_wick_res']).ffill()

        current_row = df_w.iloc[-1]
        z1_upper = float(current_row['swing_wick_res'])
        z1_lower = float(current_row['swing_body_res'])
        
        if pd.isna(z1_upper) or pd.isna(z1_lower) or z1_upper <= 0: continue
        
        live_close = float(current_row['close'])
        atr = float(daily_atr)
        
        # --- YOUR EXACT ZONE MATH ---
        
        # ZONE 1 (STEP 1)
        z1_sl = z1_lower - atr
        
        # ZONE 2 (STEP 2) - Hardcoded 5% below Zone 1 for visual testing
        z2_upper = z1_upper * 0.95
        z2_lower = z1_lower * 0.95
        z2_sl = z2_lower - atr
        
        print(f"✅ TICKER: {symbol} (Spot: ${live_close:.2f} | 14D ATR: ${atr:.2f})")
        print(f"   ► ZONE 1 (First Attempt):")
        print(f"      Limit Buy 1 (50%): ${z1_upper:.2f} (Wick)")
        print(f"      Limit Buy 2 (50%): ${z1_lower:.2f} (Body)")
        print(f"      Zone 1 Stop-Loss:  ${z1_sl:.2f} (-1 ATR from Body)")
        print(f"   ► ZONE 2 (Recovery Step at -5%):")
        print(f"      Limit Buy 1 (50%): ${z2_upper:.2f}")
        print(f"      Limit Buy 2 (50%): ${z2_lower:.2f}")
        print(f"      Zone 2 Stop-Loss:  ${z2_sl:.2f} (-1 ATR from Lower)")
        print("-" * 65)
        count += 1

    except Exception as e:
        continue

print("==================================================================")
