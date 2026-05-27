import os
import time
import pandas as pd
from dotenv import load_dotenv
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import StopOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce

# Setup
load_dotenv("/root/MITLoop/mit-loop-live/.env")
HISTORICAL_DATA_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"

clients = {
    "S1_BodyStrict": TradingClient(os.getenv("ALPACA_API_KEY_S1"), os.getenv("ALPACA_SECRET_KEY_S1"), paper=True),
    "S2_WickScaled": TradingClient(os.getenv("ALPACA_API_KEY_S2"), os.getenv("ALPACA_SECRET_KEY_S2"), paper=True),
    "S3_WickStrict": TradingClient(os.getenv("ALPACA_API_KEY_S3"), os.getenv("ALPACA_SECRET_KEY_S3"), paper=True)
}

def calculate_wilders_atr(df, period=14):
    df['prev_close'] = df['close'].shift(1)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['prev_close']).abs()
    tr3 = (df['low'] - df['prev_close']).abs()
    df['true_range'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return df['true_range'].ewm(alpha=1/period, adjust=False).mean()

print("🚀 Starting Stop-Loss Migration to Daily ATR...")

for strat_name, client in clients.items():
    try:
        positions = client.get_all_positions()
        orders = client.get_orders()
        
        for p in positions:
            sym = p.symbol
            qty = int(float(p.qty))
            avg_entry = float(p.avg_entry_price)
            
            csv_d_path = os.path.join(HISTORICAL_DATA_DIR, f"{sym}_daily.csv")
            if not os.path.exists(csv_d_path):
                print(f"⚠️ No daily CSV found for {sym}, skipping.")
                continue
                
            # Calculate 14-Day ATR
            df_d = pd.read_csv(csv_d_path)
            df_d.columns = df_d.columns.str.lower()
            for col in ['high', 'low', 'close']:
                df_d[col] = pd.to_numeric(df_d[col], errors='coerce')
                
            current_atr = calculate_wilders_atr(df_d, 14).iloc[-1]
            new_stop = round(avg_entry - current_atr, 2)
            
            if new_stop > 0:
                # 1. Cancel all existing sell orders for this symbol
                canceled_any = False
                for o in orders:
                    if o.symbol == sym and o.side == OrderSide.SELL:
                        client.cancel_order_by_id(o.id)
                        canceled_any = True
                
                # 2. Wait for Alpaca to clear the cache and free the shares
                if canceled_any:
                    time.sleep(2) 
                
                # 3. Submit new precision stop loss
                try:
                    req = StopOrderRequest(
                        symbol=sym,
                        qty=qty,
                        side=OrderSide.SELL,
                        time_in_force=TimeInForce.GTC,
                        stop_price=new_stop
                    )
                    client.submit_order(req)
                    print(f"✅ [{strat_name}] {sym}: Old stops cleared. New SL set to ${new_stop:.2f} (Entry: ${avg_entry:.2f} - ATR: ${current_atr:.2f})")
                except Exception as order_err:
                    print(f"⚠️ Skipping {sym} - Likely already updated or still pending: {order_err}")
                
    except Exception as e:
        print(f"❌ Error processing {strat_name}: {e}")

print("🏁 Migration Complete. Check your dashboard!")
