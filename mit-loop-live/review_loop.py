import os
import pandas as pd
import numpy as np

DATA_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"

def calculate_indicators(df):
    """
    Applies indicator context required for core calculations.
    """
    if df.empty:
        return df
    df = df.copy()
    df['body_max'] = df[['open', 'close']].max(axis=1)
    df['body_min'] = df[['open', 'close']].min(axis=1)
    
    # ATR calculation for risk positioning (Standard 14 Period)
    high_low = df['high'] - df['low']
    high_cp = (df['high'] - df['close'].shift(1)).abs()
    low_cp = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()
    return df

# ==============================================================================
# STRATEGY 1: 1H DEEP MEAN REVERSION (V-SHAPE HUNTING)
# ==============================================================================
def evaluate_strategy_1(df_1h, df_weekly):
    """
    Strategy 1 Core: Catching rapid capitulations back to institutional value zones 
    using 1-Hour intraday timing.
    """
    if df_1h.empty or df_weekly.empty or len(df_weekly) < 30:
        return 5, "Missing required historical data streams"
        
    current_row_1h = df_1h.iloc[-1]
    
    # 1. Macro Quality Filter (Cannot be a broken structural asset)
    # Using 30-Week SMA from weekly data to enforce long-term health (Daily 150 MA equivalent)
    df_weekly_calc = df_weekly.copy()
    df_weekly_calc['sma30'] = df_weekly_calc['close'].rolling(30).mean()
    wk_sma30 = df_weekly_calc['sma30'].iloc[-1]
    
    if pd.isna(wk_sma30) or current_row_1h['close'] < wk_sma30 * 0.85:
        return 5, f"Macro breakdown (< 85% of 30W SMA: ${wk_sma30*0.85:.2f})"
        
    # 2. Extension Metric (Look back 6 months on weekly to check for the 15-25% drop)
    cycle_high = df_weekly['high'].iloc[-26:].max()
    drawdown = (cycle_high - current_row_1h['close']) / cycle_high
    
    if drawdown < 0.15:
        return 4, f"Drawdown insufficient (-{drawdown*100:.1f}%)"
        
    # 3. 1H Exhaustion Signature
    # Tail must represent more than 3% of the asset's total close price
    tail_size = (current_row_1h['body_min'] - current_row_1h['low']) / current_row_1h['close']
    if tail_size > 0.03:
        sl_price = current_row_1h['low'] - (0.5 * (current_row_1h['atr'] if 'atr' in current_row_1h and pd.notna(current_row_1h['atr']) else current_row_1h['close'] * 0.01))
        return 1, f"MATCH! 1H Capitulation tail ({tail_size*100:.1f}%). Trigger entry. SL: ${sl_price:.2f}"
        
    return 2, f"Overextended (-{drawdown*100:.1f}%), waiting for 1H tail signature"

# ==============================================================================
# STRATEGY 2: BASE COMPRESSION & EXPANSION
# ==============================================================================
def evaluate_strategy_2(df_weekly):
    """
    Strategy 2 Core: Trading breakouts from highly compressed weekly ranges.
    """
    if len(df_weekly) < 20: 
        return 5, "Insufficient weekly historical base"
        
    recent_range = df_weekly.iloc[-8:]
    max_close = recent_range['close'].max()
    min_close = recent_range['close'].min()
    current_row = df_weekly.iloc[-1]
    
    compression = (max_close - min_close) / min_close
    if compression > 0.06:
        return 5, f"Chop zone too wide ({compression*100:.1f}%)"
        
    avg_vol = df_weekly['volume'].iloc[-20:-1].mean()
    if current_row['close'] > max_close * 0.99 and current_row['volume'] > avg_vol * 1.5:
        sl_price = min_close * 0.995
        return 1, f"MATCH! Compression break active on vol expansion. SL: ${sl_price:.2f}"
        
    return 4, f"Coiling tightly ({compression*100:.1f}%), waiting for breakout volume"

# ==============================================================================
# STRATEGY 3: 4H DEEP MEAN REVERSION (V-SHAPE HUNTING)
# ==============================================================================
def evaluate_strategy_3(df_4h, df_weekly):
    """
    Strategy 3 Core: Catching rapid capitulations back to institutional value zones
    using intermediate 4-Hour intraday timing.
    """
    if df_4h.empty or df_weekly.empty or len(df_weekly) < 30: 
        return 5, "Missing required historical data streams"
        
    current_row_4h = df_4h.iloc[-1]
    
    df_weekly_calc = df_weekly.copy()
    df_weekly_calc['sma30'] = df_weekly_calc['close'].rolling(30).mean()
    wk_sma30 = df_weekly_calc['sma30'].iloc[-1]
    
    if pd.isna(wk_sma30) or current_row_4h['close'] < wk_sma30 * 0.85:
        return 5, f"Macro breakdown (< 85% of 30W SMA: ${wk_sma30*0.85:.2f})"
        
    cycle_high = df_weekly['high'].iloc[-26:].max()
    drawdown = (cycle_high - current_row_4h['close']) / cycle_high
    
    if drawdown < 0.15:
        return 4, f"Drawdown insufficient (-{drawdown*100:.1f}%)"
        
    tail_size = (current_row_4h['body_min'] - current_row_4h['low']) / current_row_4h['close']
    if tail_size > 0.03:
        sl_price = current_row_4h['low'] - (0.5 * (current_row_4h['atr'] if 'atr' in current_row_4h and pd.notna(current_row_4h['atr']) else current_row_4h['close'] * 0.01))
        return 1, f"MATCH! 4H Capitulation tail ({tail_size*100:.1f}%). Trigger entry. SL: ${sl_price:.2f}"
        
    return 2, f"Overextended (-{drawdown*100:.1f}%), waiting for 4H tail signature"

def run_training_scan():
    print("\n" + "="*90)
    print(" 🧠 MIT LOOP LIVE UI SCANNERS: S1 (1H REVERSION) | S2 (COMPRESSION) | S3 (4H REVERSION)")
    print("="*90)
    
    if not os.path.exists(DATA_DIR):
        print(f"❌ Target historical directory not detected: {DATA_DIR}")
        return

    # Extract all uniquely available symbols based on existing weekly baseline files
    symbols = set([f.split('_')[0] for f in os.listdir(DATA_DIR) if f.endswith('_weekly.csv')])
    
    if not symbols:
        print("⚠ No historical CSV data bundles detected inside directory.")
        return

    for symbol in sorted(symbols):
        symbol = symbol.upper()
        try:
            wk_file = os.path.join(DATA_DIR, f"{symbol}_weekly.csv")
            h1_file = os.path.join(DATA_DIR, f"{symbol}_1h.csv")
            h4_file = os.path.join(DATA_DIR, f"{symbol}_4h.csv")
            
            # Load and normalize weekly base arrays
            df_wk = pd.read_csv(wk_file)
            df_wk.columns = df_wk.columns.str.lower()
            df_wk = calculate_indicators(df_wk)
            
            if df_wk.empty: continue
            current_price = df_wk['close'].iloc[-1]
            
            # Load hourly data streams safely if files are provisioned
            df_1h = pd.read_csv(h1_file) if os.path.exists(h1_file) else pd.DataFrame()
            df_4h = pd.read_csv(h4_file) if os.path.exists(h4_file) else pd.DataFrame()
            
            if not df_1h.empty:
                df_1h.columns = df_1h.columns.str.lower()
                df_1h = calculate_indicators(df_1h)
            if not df_4h.empty:
                df_4h.columns = df_4h.columns.str.lower()
                df_4h = calculate_indicators(df_4h)
                
            # Process real structural logic runs
            r1, n1 = evaluate_strategy_1(df_1h, df_wk) if not df_1h.empty else (5, "No 1H historical source file found")
            r2, n2 = evaluate_strategy_2(df_wk)
            r3, n3 = evaluate_strategy_3(df_4h, df_wk) if not df_4h.empty else (5, "No 4H historical source file found")
            
            # Beautiful interactive human-grade review console
            print(f"[{symbol}] Last Traded Price: ${current_price:.2f}")
            print(f"  ⚡ STRATEGY 1 (1H Deep Reversion) -> Rank: {r1} | {n1}")
            print(f"  🗜️ STRATEGY 2 (Base Compression)  -> Rank: {r2} | {n2}")
            print(f"  ⚡ STRATEGY 3 (4H Deep Reversion) -> Rank: {r3} | {n3}")
            print(f"  => HUMAN VERIFICATION RATING (1-5): [   ]")
            print("-" * 90)
            
        except Exception as e:
            # Silently pass errors for unformed/empty data files to keep the console layout pristine
            continue

if __name__ == "__main__":
    run_training_scan()
