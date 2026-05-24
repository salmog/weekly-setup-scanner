import yfinance as yf
import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings("ignore")

TICKERS = ["NVDA", "XLK", "OKLO", "ORCL", "BBAI", "TOPT", "TTD", "NAIL", "KRE", "TSLA", "HOOD", "ECG"]
PORTFOLIO_VALUE = 100000.0
RISK_PCT = 0.01

def get_atr(high, low, close, n=14):
    tr = np.maximum(high - low, np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1))))
    return tr.rolling(n).mean()

def is_weekly_uptrend(weekly_df):
    if len(weekly_df) < 52:
        return False
    # Define uptrend: 10-week SMA > 40-week SMA and current price above 10-week SMA (HH/HL proxy)
    sma10 = weekly_df['Close'].rolling(10).mean().iloc[-1]
    sma40 = weekly_df['Close'].rolling(40).mean().iloc[-1]
    close = weekly_df['Close'].iloc[-1]
    return (sma10 > sma40) and (close > sma10)

def find_demand_zone(daily_df, current_idx, lookback=130):
    if current_idx < lookback:
        return None
    
    window = daily_df.iloc[current_idx-lookback:current_idx]
    
    # Find local swing lows (troughs)
    window['local_min'] = window['Low'] == window['Low'].rolling(window=5, center=True).min()
    troughs = window[window['local_min']]['Low']
    
    if troughs.empty:
        return None
        
    # Find a price level defended at least twice (within 1% tolerance)
    trough_values = troughs.sort_values().unique()
    for tv in trough_values:
        touches = ((troughs >= tv * 0.99) & (troughs <= tv * 1.01)).sum()
        if touches >= 2:
            return tv
            
    return None

def analyze_ticker(ticker):
    try:
        df = yf.Ticker(ticker).history(period="2y")
        if df.empty or len(df) < 200:
            return {"Ticker": ticker, "Action": "REJECT", "Reason": "Insufficient data"}
            
        df.index = df.index.tz_localize(None)
        df['ATR'] = get_atr(df['High'], df['Low'], df['Close'])
        df['Vol_SMA'] = df['Volume'].rolling(20).mean()
        
        weekly_df = df.resample('W-FRI').agg({'High':'max', 'Low':'min', 'Close':'last', 'Volume':'sum'}).dropna()
        
        # 1. Market & Trend Filter
        if not is_weekly_uptrend(weekly_df):
            return {"Ticker": ticker, "Action": "REJECT", "Reason": "Not in dominant weekly uptrend (No HH/HL structure)"}
            
        # 2. Demand Zone Definition
        current_idx = len(df) - 1
        demand_zone = find_demand_zone(df, current_idx)
        
        if not demand_zone:
            return {"Ticker": ticker, "Action": "WATCH", "Reason": "No valid defended demand zone identified"}
            
        # 3. Entry Conditions
        current_price = df['Close'].iloc[-1]
        current_low = df['Low'].iloc[-1]
        current_vol = df['Volume'].iloc[-1]
        vol_sma = df['Vol_SMA'].iloc[-1]
        atr = df['ATR'].iloc[-1]
        
        # Price is at or near Demand Zone (within 2% above the zone)
        near_zone = (current_low <= demand_zone * 1.02) and (current_price >= demand_zone)
        
        # Volume contraction
        lower_volume = current_vol < vol_sma
        
        if near_zone and lower_volume:
            # 4 & 5. Stop Loss & Position Sizing
            stop_loss = demand_zone - (1.0 * atr)
            stop_distance_pct = (current_price - stop_loss) / current_price
            
            # Risk Management Check (6-10% typical, reject if too wide to protect capital)
            if stop_distance_pct > 0.15:
                 return {"Ticker": ticker, "Action": "WATCH", "Reason": f"Stop distance too wide ({stop_distance_pct*100:.1f}%)"}
                 
            risk_amount = PORTFOLIO_VALUE * RISK_PCT
            pos_size_usd = risk_amount / stop_distance_pct
            pos_size_pct = (pos_size_usd / PORTFOLIO_VALUE) * 100
            
            return {
                "Ticker": ticker,
                "Action": "BUY",
                "Confidence": 85,
                "Entry Price": f"${current_price:.2f}",
                "Stop-Loss Price": f"${stop_loss:.2f}",
                "Position Size %": f"{min(pos_size_pct, 10.0):.2f}%", # Cap at 10% portfolio allocation
                "Reason": "Pulled back to 2x defended Demand Zone with volume contraction."
            }
        elif current_price < demand_zone:
            return {"Ticker": ticker, "Action": "REJECT", "Reason": "Price broke below Demand Zone (Falling Knife)"}
        else:
            dist = ((current_price - demand_zone) / demand_zone) * 100
            return {"Ticker": ticker, "Action": "WATCH", "Reason": f"In uptrend, but {dist:.1f}% away from nearest Demand Zone"}
            
    except Exception as e:
        return {"Ticker": ticker, "Action": "ERROR", "Reason": str(e)}

def run_scanner():
    print("\n" + "="*50)
    print("DEMAND ZONE TREND FOLLOWING - DAILY SCAN")
    print("="*50)
    
    for ticker in TICKERS:
        res = analyze_ticker(ticker)
        print(f"\nTicker: {res['Ticker']}")
        print(f"Action: {res['Action']}")
        if res['Action'] == 'BUY':
            print(f"Confidence: {res['Confidence']}")
            print(f"Entry Price: {res['Entry Price']}")
            print(f"Stop-Loss Price: {res['Stop-Loss Price']}")
            print(f"Position Size % of portfolio: {res['Position Size %']}")
        print(f"Reason: {res['Reason']}")
        
    print("\n" + "="*50 + "\n")

if __name__ == "__main__":
    run_scanner()
