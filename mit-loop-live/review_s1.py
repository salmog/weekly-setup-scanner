import os
import pandas as pd
import numpy as np

# --- CONFIGURATION (Mirroring your S1 Setup) ---
DATA_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"  # Adjust if your CSV path differs
STARTING_CAPITAL = 25000
RISK_PCT = 0.01

def calculate_s1_quality_score(df, body_level, breakout_vol):
    """
    Scores a setup from 50 to 100 based on strict structural price action.
    Fails (returns 0) if core 'Staircase' rules are violated.
    """
    score = 50  # Base score for passing minimum criteria
    
    # Get recent rows for analysis
    current_row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    # 1. Structural Trend check (Higher Highs & Higher Lows)
    # Ensure we aren't breaking down structurally on the weekly
    if current_row['low'] < df['low'].iloc[-5:-1].min():
        return 0  # CRITICAL FAILURE: Lower Low printed recently
        
    # 2. Contained Correction / Anti-Collapse Check
    # If the close slices way too deep below our support floor, it's a structural failure
    if current_row['close'] < body_level * 0.95:
        return 0  # CRITICAL FAILURE: Sliced more than 5% below support floor

    # 3. Volume Exhaustion (Up to 20 Points)
    # We want selling volume to dry up significantly compared to the breakout surge
    vol_ratio = current_row['volume'] / breakout_vol
    if vol_ratio < 0.50:
        score += 20  # Perfect institutional volume drying up
    elif vol_ratio < 0.75:
        score += 10
        
    # 4. Retest Cleanliness & Sweep Depth (Up to 20 Points)
    # Reward a deep, clean test of the level over a shallow front-run
    retest_gap = (body_level - current_row['low']) / body_level
    if 0.00 <= retest_gap <= 0.01:
        score += 20  # Perfect wick touch/sweep right at the support level
    elif retest_gap <= 0.03:
        score += 10  # Very close proximity
        
    # 5. Anti-Parabolic Checklist (Up to 10 Points)
    # Ensure it's a staircase, not a vertical bubble ripe for mean reversion
    if 'ema20' in current_row:
        extension = (current_row['close'] - current_row['ema20']) / current_row['ema20']
        if extension <= 0.12:
            score += 10  # Healthy staircase resting near its moving average
        elif extension > 0.25:
            score -= 15  # Penalize heavy parabolic extension

    return min(100, max(0, int(score)))

def check_flat_base(df):
    """
    Checks if there was a visible 2-4 week consolidation (flat base) 
    prior to the recent breakout move.
    """
    # Look at the chunk of data right before the breakout zone (approx weeks 4 to 8 back)
    if len(df) < 10:
        return False
    base_window = df.iloc[-8:-4]
    
    # Measure the variance/tightness of closing prices during that month
    max_close = base_window['close'].max()
    min_close = base_window['close'].min()
    percentage_width = (max_close - min_close) / min_close
    
    # If the weekly closes stayed within a tight 4.5% horizontal corridor, it's a valid flat base
    return percentage_width <= 0.045

def scan_ticker_review(symbol, filepath):
    try:
        df = pd.read_csv(filepath)
        if len(df) < 20:
            return None
        
        # Calculate basic technical baselines (adjust column names if yours differ)
        df['atr'] = df['high'] - df['low'] # Simple replacement if true ATR isn't in CSV
        
        current_row = df.iloc[-1]
        
        # Determine breakout anchor level (using a historical body cluster point)
        # For review simulation, we treat the highest body open/close of weeks 3-6 back as our floor
        historical_zone = df.iloc[-6:-2]
        body_level = max(historical_zone['open'].max(), historical_zone['close'].max())
        breakout_vol = historical_zone['volume'].max()
        
        # --- NEW DEEPER RETEST & WICK SWEEP CONDITION ---
        # 1. Price MUST have stabbed down close enough to touch or sweep the line
        # 2. Price must NOT have completely collapsed and closed deep underneath it
        wick_touched_support = current_row['low'] <= (body_level * 1.005) 
        held_above_cutoff = current_row['close'] >= (body_level * 0.95)
        
        if wick_touched_support and held_above_cutoff:
            
            # Run the Scoring Algorithm
            quality_score = calculate_s1_quality_score(df, body_level, breakout_vol)
            
            # Skip if it failed a core structural filter
            if quality_score < 75: 
                return None
                
            has_flat_base = check_flat_base(df)
            
            # Calculation of risk variables
            stop_loss = body_level - (1.2 * current_row['atr'])
            risk_per_share = current_row['close'] - stop_loss
            
            if risk_per_share > 0:
                shares = int((STARTING_CAPITAL * RISK_PCT) / risk_per_share)
                return {
                    "Ticker": symbol,
                    "Quality Score": quality_score,
                    "Flat Base?": "YES" if has_flat_base else "No",
                    "Entry Level": round(body_level, 2),
                    "Current Price": round(current_row['close'], 2),
                    "Stop Loss": round(stop_loss, 2),
                    "Est. Shares": shares
                }
    except Exception as e:
        # Silently skip errors for broken historical rows during dry run
        pass
    return None

def run_review_pipeline():
    print("=" * 70)
    print(" STRATEGY 1: DEEP RETEST & QUALITY LEADERBOARD SIMULATION ")
    print("=" * 70)
    
    results = []
    
    if not os.path.exists(DATA_DIR):
        print(f"Error: Data directory '{DATA_DIR}' not found.")
        return

    # Scan through files matching your historical sheets
    for file in os.listdir(DATA_DIR):
        if file.endswith("_weekly.csv") or file.endswith(".csv"):  # Adjust match rule to your system
            symbol = file.split('_')[0].upper().replace(".CSV", "")
            res = scan_ticker_review(symbol, os.path.join(DATA_DIR, file))
            if res:
                results.append(res)
                
    if not results:
        print("No tickers currently match the strict 75+ point Deep Retest parameters.")
        return
        
    # Convert to Dataframe and sort purely by Quality Score
    report_df = pd.DataFrame(results)
    report_df = report_df.sort_values(by="Quality Score", ascending=False)
    
    print(report_df.to_string(index=False))
    print("=" * 70)
    print(f"Total Quality Setups Found: {len(report_df)}")

if __name__ == "__main__":
    run_review_pipeline()
