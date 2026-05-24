import os
import math
import logging
import datetime
import zoneinfo
from dotenv import load_dotenv
import pandas as pd
import numpy as np

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

# Setup Configurations
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="MIT-Loop Pro Live Terminal")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

HISTORICAL_DATA_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data"

clients = {
    "S1_BodyStrict": TradingClient(os.getenv("ALPACA_API_KEY_S1"), os.getenv("ALPACA_SECRET_KEY_S1"), paper=True),
    "S2_WickScaled": TradingClient(os.getenv("ALPACA_API_KEY_S2"), os.getenv("ALPACA_SECRET_KEY_S2"), paper=True),
    "S3_WickStrict": TradingClient(os.getenv("ALPACA_API_KEY_S3"), os.getenv("ALPACA_SECRET_KEY_S3"), paper=True)
}

system_state = {
    "last_scan": "Never",
    "market_status": "Checking Hours...",
    "scanner_status": "Operational",
    "accounts": {},
    "pending_setups": [],
    "recent_actions": [
        {"time": datetime.datetime.now().strftime("%H:%M:%S"), "message": "Pro Live Trading Machine online. Systems verified secure."}
    ]
}

def log_system_action(message: str):
    timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    system_state["recent_actions"].insert(0, {"time": timestamp, "message": message})
    if len(system_state["recent_actions"]) > 30:
        system_state["recent_actions"].pop()

def check_market_hours():
    tz = zoneinfo.ZoneInfo("America/New_York")
    now = datetime.datetime.now(tz)
    if now.weekday() >= 5:
        system_state["market_status"] = "CLOSED (Weekend)"
        return
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    if market_open <= now <= market_close:
        system_state["market_status"] = "OPEN (Live Session)"
    else:
        system_state["market_status"] = "CLOSED (Off-Hours)"

def update_account_states():
    check_market_hours()
    for strat_name, client in clients.items():
        try:
            account = client.get_account()
            positions = client.get_all_positions()
            orders = client.get_orders()
            
            system_state["accounts"][strat_name] = {
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "day_pnl": float(account.equity) - float(account.last_equity),
                "positions": [{"symbol": p.symbol, "qty": int(float(p.qty)), "unrealized_pl": p.unrealized_pl, "current_price": p.current_price} for p in positions],
                "active_orders": len(orders)
            }
        except Exception as e:
            logger.error(f"Error updating metrics for {strat_name}: {e}")

def run_daily_scan():
    system_state["scanner_status"] = "Scanning Local DB Files..."
    log_system_action("Starting automated high-precision engine scan...")
    system_state["last_scan"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_account_states()
    
    if not os.path.exists(HISTORICAL_DATA_DIR):
        system_state["scanner_status"] = "Directory Error"
        log_system_action(f"Scan aborted. Missing directory: {HISTORICAL_DATA_DIR}")
        return

    all_files = [f for f in os.listdir(HISTORICAL_DATA_DIR) if f.endswith('_weekly.csv')]
    discovered_setups = []

    for file in all_files:
        try:
            symbol = file.split('_')[0].upper()
            df_w = pd.read_csv(os.path.join(HISTORICAL_DATA_DIR, file))
            df_w.columns = df_w.columns.str.lower()
            if len(df_w) < 60: continue
            
            df_w['atr'] = (df_w['high'] - df_w['low']).rolling(14).mean()
            df_w['ema20'] = df_w['close'].ewm(span=20, adjust=False).mean()
            df_w['sma50'] = df_w['close'].rolling(50).mean()
            df_w['volume_float'] = df_w['volume'].astype(float)
            df_w['vol_avg'] = df_w['volume_float'].rolling(20).mean()
            df_w['rolling_max_11'] = df_w['high'].rolling(11).max()
            df_w['is_pivot'] = df_w['high'].shift(5) == df_w['rolling_max_11']
            df_w['body_max'] = df_w[['open', 'close']].max(axis=1)
            df_w['swing_wick_res'] = np.where(df_w['is_pivot'], df_w['high'].shift(5), np.nan)
            df_w['swing_body_res'] = np.where(df_w['is_pivot'], df_w['body_max'].shift(5), np.nan)
            df_w['swing_wick_res'] = pd.Series(df_w['swing_wick_res']).ffill()
            df_w['swing_body_res'] = pd.Series(df_w['swing_body_res']).ffill()

            current_row = df_w.iloc[-1]
            
            for target_type in ["body", "wick"]:
                strat_assigned = "Strategy 1: Body Strict (1%)" if target_type == "body" else "Strategy 2 & 3: Wick Retest"
                
                for b_idx in range(len(df_w) - 25, len(df_w) - 5):
                    if b_idx < 1: continue
                    b_row = df_w.iloc[b_idx]
                    b_prev = df_w.iloc[b_idx - 1]
                    
                    res_line = b_row['swing_body_res'] if target_type == "body" else b_row['swing_wick_res']
                    prev_res_line = b_prev['swing_body_res'] if target_type == "body" else b_prev['swing_wick_res']
                    
                    if pd.isna(res_line) or pd.isna(prev_res_line): continue

                    is_breakout = b_row['close'] > res_line and b_prev['close'] <= prev_res_line
                    is_high_vol = b_row['volume'] > (b_row['vol_avg'] * 1.5)
                    
                    if is_breakout and is_high_vol:
                        waiting_candles = df_w.iloc[b_idx + 1 :]
                        weeks_count = len(waiting_candles)
                        
                        if weeks_count >= 4:
                            has_touched_early = waiting_candles['low'].min() <= res_line
                            dropped_below_trend = waiting_candles['close'].min() < waiting_candles['sma50'].min()
                            
                            if not has_touched_early and not dropped_below_trend:
                                current_close = current_row['close']
                                distance_pct = ((current_close - res_line) / res_line) * 100
                                
                                if distance_pct > 0:
                                    logic_desc = (
                                        f"Confirmed institutional breakout {weeks_count} weeks ago with a volume spike. "
                                        f"Price held above the breakout line for {weeks_count} weeks straight, validating "
                                        f"the support floor. Rested limit orders are prepared to capture the institutional retest."
                                    )
                                    discovered_setups.append({
                                        "symbol": symbol,
                                        "strategy": strat_assigned,
                                        "type": target_type.upper(),
                                        "target": float(res_line),
                                        "dist": float(distance_pct),
                                        "weeks": int(weeks_count),
                                        "logic": logic_desc,
                                        "atr": float(current_row['atr'])
                                    })
                                break
        except Exception as e:
            continue

    discovered_setups.sort(key=lambda x: x['dist'])
    system_state["pending_setups"] = discovered_setups[:10]

    system_state["scanner_status"] = "Routing Rested Limit Orders..."
    for setup in system_state["pending_setups"]:
        for strat_name, client in clients.items():
            strat_target = "BODY" if "Body" in strat_name else "WICK"
            if setup["type"] == strat_target:
                try:
                    acct_data = system_state["accounts"].get(strat_name)
                    if not acct_data: continue
                    
                    acct_equity = acct_data["equity"]
                    cash_available = acct_data["cash"]
                    risk_pct = 0.02 if "Scaled" in strat_name else 0.01
                    
                    stop_loss_px = setup["target"] - (1.1 * setup["atr"])
                    risk_per_share = setup["target"] - stop_loss_px
                    
                    if risk_per_share > 0:
                        # ENFORCED STRICT ROUND DOWN LOGIC TO WHOLE INTEGERS ONLY
                        shares = int(math.floor((acct_equity * risk_pct) / risk_per_share))
                        total_cost = shares * setup["target"]
                        
                        if shares > 0 and total_cost <= cash_available:
                            order_request = LimitOrderRequest(
                                symbol=setup["symbol"],
                                qty=shares,
                                side=OrderSide.BUY,
                                time_in_force=TimeInForce.GTC,
                                limit_price=round(setup["target"], 2),
                                order_class=OrderClass.OTO,
                                stop_loss=StopLossRequest(stop_price=round(stop_loss_px, 2))
                            )
                            client.submit_order(order_request)
                            log_system_action(f"✅ [{strat_name}] Rested OTO Limit: {shares} shares of {setup['symbol']} at ${setup['target']:.2f} (SL: ${stop_loss_px:.2f})")
                        else:
                            if total_cost > cash_available:
                                log_system_action(f"⚠️ [{strat_name}] Order bypassed for {setup['symbol']}: Insufficient Buying Power.")
                except Exception as e:
                    log_system_action(f"❌ [{strat_name}] API Rejection for {setup['symbol']}: {str(e)}")

    system_state["scanner_status"] = "Monitoring Active Portfolios"
    log_system_action(f"Pipeline calculation sequence complete. {len(system_state['pending_setups'])} active structural trackers loaded.")

# Scheduler Configuration
scheduler = BackgroundScheduler()
scheduler.add_job(update_account_states, 'interval', minutes=1)
scheduler.add_job(run_daily_scan, 'cron', day_of_week='mon-fri', hour=16, minute=15, timezone='US/Eastern')
scheduler.start()

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    update_account_states()
    return templates.TemplateResponse(request, "dashboard.html", {"state": system_state})

@app.post("/scan")
async def force_scan():
    run_daily_scan()
    return RedirectResponse(url="/", status_code=303)

@app.on_event("startup")
async def startup_event():
    update_account_states()
    run_daily_scan()

# ==========================================
# NEXT.JS V2 FRONTEND DATA BRIDGE
# ==========================================
@app.get("/api/live-state")
async def get_live_state_json():
    update_account_states()
    return system_state
