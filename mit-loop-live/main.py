import os
import glob
import math
import logging
import datetime
import zoneinfo
import asyncio
from dotenv import load_dotenv
import pandas as pd
import numpy as np

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, StopLossRequest, TakeProfitRequest, StopOrderRequest, MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockLatestTradeRequest

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="MIT-Loop Pro Live Terminal")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")
HISTORICAL_DATA_DIR = "/home/shay/autotrade_dev/fetch_candles_ibkr/historical_data/"
IGNORED_TICKERS_FILE = "/root/MITLoop/mit-loop-live/ignored_tickers.txt"

clients = {
    "S1_BodyStrict": TradingClient(os.getenv("ALPACA_API_KEY_S1"), os.getenv("ALPACA_SECRET_KEY_S1"), paper=True),
    "S2_WickScaled": TradingClient(os.getenv("ALPACA_API_KEY_S2"), os.getenv("ALPACA_SECRET_KEY_S2"), paper=True),
    "S3_4H_Hybrid": TradingClient(os.getenv("ALPACA_API_KEY_S3"), os.getenv("ALPACA_SECRET_KEY_S3"), paper=True)
}

data_client = StockHistoricalDataClient(os.getenv("ALPACA_API_KEY_S1"), os.getenv("ALPACA_SECRET_KEY_S1"))

system_state = {
    "last_scan": "Never",
    "market_status": "Checking Hours...",
    "scanner_status": "Operational",
    "margin_limits": {"S1_BodyStrict": 0.0, "S2_WickScaled": 0.0, "S3_4H_Hybrid": 0.0},
    "accounts": {},
    "pending_setups": [],
    "recent_actions": [{"time": datetime.datetime.now().strftime("%H:%M:%S"), "message": "Live Engine Online. S3 Runner Isolation Logic Active."}]
}

def log_system_action(message: str):
    system_state["recent_actions"].insert(0, {"time": datetime.datetime.now().strftime("%H:%M:%S"), "message": message})
    if len(system_state["recent_actions"]) > 30: system_state["recent_actions"].pop()

def get_ignored_tickers():
    if os.path.exists(IGNORED_TICKERS_FILE):
        with open(IGNORED_TICKERS_FILE, "r") as f: return set(f.read().splitlines())
    return set()

def toggle_ignored_ticker(symbol):
    ignored = get_ignored_tickers()
    if symbol in ignored:
        ignored.remove(symbol)
        log_system_action(f"🔓 Manual Override Removed: {symbol} cleared for execution.")
    else:
        ignored.add(symbol)
        log_system_action(f"🛑 Killswitch Activated: {symbol} execution blocked.")
    with open(IGNORED_TICKERS_FILE, "w") as f: f.write("\n".join(ignored))

def check_market_hours():
    tz = zoneinfo.ZoneInfo("America/New_York")
    now = datetime.datetime.now(tz)
    if now.weekday() >= 5:
        system_state["market_status"] = "CLOSED (Weekend)"
        return
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    system_state["market_status"] = "OPEN (Live Session)" if market_open <= now <= market_close else "CLOSED (Off-Hours)"

def calculate_wilders_atr(df, period=14):
    df['prev_close'] = df['close'].shift(1)
    tr1 = df['high'] - df['low']
    tr2 = (df['high'] - df['prev_close']).abs()
    tr3 = (df['low'] - df['prev_close']).abs()
    df['true_range'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return df['true_range'].ewm(alpha=1/period, adjust=False).mean()

def update_account_states():
    check_market_hours()
    for strat_name, client in clients.items():
        try:
            account = client.get_account()
            positions = client.get_all_positions()
            orders = client.get_orders()
            
            pos_data = []
            for p in positions:
                pos_orders = [o for o in orders if o.symbol == p.symbol and o.side == OrderSide.SELL]
                tp_price = next((float(o.limit_price) for o in pos_orders if o.limit_price), None)
                sl_price = next((float(o.stop_price) for o in pos_orders if o.stop_price), None)
                
                pos_data.append({
                    "symbol": p.symbol,
                    "qty": int(float(p.qty)),
                    "market_value": float(p.market_value),
                    "avg_entry": float(p.avg_entry_price),
                    "current_price": float(p.current_price),
                    "lastday_price": float(p.lastday_price) if p.lastday_price else float(p.current_price),
                    "unrealized_pl": float(p.unrealized_pl),
                    "unrealized_plpc": float(p.unrealized_plpc) * 100,
                    "intraday_pl": float(p.unrealized_intraday_pl),
                    "intraday_plpc": float(p.unrealized_intraday_plpc) * 100,
                    "tp_price": tp_price,
                    "sl_price": sl_price,
                    "current_atr": 0.0,
                    "current_atr_pct": 0.0
                })
            
            raw_cash = float(account.cash)
            margin_limit = system_state["margin_limits"].get(strat_name, 0.0)
            custom_bp = max(0.0, raw_cash + margin_limit)
            effective_bp = min(custom_bp, float(account.buying_power))
                
            system_state["accounts"][strat_name] = {
                "equity": float(account.equity),
                "cash": raw_cash,
                "buying_power": effective_bp, 
                "broker_bp": float(account.buying_power),
                "tied_up_cash": max(0.0, float(account.cash) - float(account.buying_power)),
                "day_pnl": float(account.equity) - float(account.last_equity),
                "margin_limit": margin_limit,
                "positions": pos_data,
                "active_orders": len(orders)
            }
            
            # --- DYNAMIC EXITS (S3 Runner Isolation ONLY) ---
            for p in pos_data:
                sym = p["symbol"]
                csv_d_path = os.path.join(HISTORICAL_DATA_DIR, f"{sym}_daily.csv")
                
                # Attach live ATR data to the UI for all strategies
                if os.path.exists(csv_d_path):
                    df_d = pd.read_csv(csv_d_path)
                    df_d.columns = df_d.columns.str.lower()
                    for col in ['high', 'low', 'close']: df_d[col] = pd.to_numeric(df_d[col], errors='coerce')
                    current_atr = calculate_wilders_atr(df_d, 14).iloc[-1]
                    if pd.notna(current_atr) and current_atr > 0:
                        p["current_atr"] = float(current_atr)
                        if p["current_price"] > 0: p["current_atr_pct"] = (float(current_atr) / float(p["current_price"])) * 100

                # Strategy 3: Target and Liquidate the 50% Runner ONLY
                csv_4h_path = os.path.join(HISTORICAL_DATA_DIR, f"{sym}_4h.csv")
                if strat_name == "S3_4H_Hybrid" and os.path.exists(csv_4h_path):
                    df_4h = pd.read_csv(csv_4h_path)
                    df_4h.columns = df_4h.columns.str.lower()
                    df_4h['close'] = pd.to_numeric(df_4h['close'], errors='coerce')
                    df_4h['ema20'] = df_4h['close'].ewm(span=20, adjust=False).mean()
                    
                    if not df_4h.empty and df_4h['close'].iloc[-1] < df_4h['ema20'].iloc[-1]:
                        if system_state["market_status"] == "OPEN (Live Session)":
                            try:
                                pos_orders = [o for o in orders if o.symbol == sym and o.side == OrderSide.SELL]
                                tp_qty = sum([float(o.qty) for o in pos_orders if o.limit_price is not None])
                                runner_qty = int(float(p["qty"]) - tp_qty)
                                
                                if runner_qty > 0:
                                    req = MarketOrderRequest(symbol=sym, qty=runner_qty, side=OrderSide.SELL, time_in_force=TimeInForce.DAY)
                                    client.submit_order(req)
                                    # Attempt to clear orphaned runner stop-loss
                                    for o in pos_orders:
                                        if o.stop_price is not None and float(o.qty) == runner_qty and o.limit_price is None:
                                            client.cancel_order_by_id(o.id)
                                    log_system_action(f"📉 [S3] Trend Broke (<4H EMA20). Runner Leg ({runner_qty}x {sym}) safely liquidated.")
                            except Exception as e:
                                pass
                                
                # Note: S1 and S2 have NO dynamic trailing stop. They are single-entry snipers managed by the initial -1 ATR OTO Stop-Loss.

        except Exception as e:
            pass

def run_daily_scan():
    system_state["scanner_status"] = "Scanning Hybrid DB Files..."
    update_account_states()
    ignored_tickers = get_ignored_tickers()
    
    if not os.path.exists(HISTORICAL_DATA_DIR): return

    all_files = [f for f in os.listdir(HISTORICAL_DATA_DIR) if f.endswith('_weekly.csv')]
    system_state["last_scan"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    prelim_setups = []

    for file in all_files:
        try:
            symbol = file.split('_')[0].upper()
            csv_d_path = os.path.join(HISTORICAL_DATA_DIR, f"{symbol}_daily.csv")
            if not os.path.exists(csv_d_path): continue
            
            df_d = pd.read_csv(csv_d_path)
            df_d.columns = df_d.columns.str.lower()
            for col in ['high', 'low', 'close']: df_d[col] = pd.to_numeric(df_d[col], errors='coerce')
            daily_atr = calculate_wilders_atr(df_d, 14).iloc[-1]
            if pd.isna(daily_atr) or daily_atr <= 0: continue
            
            df_w = pd.read_csv(os.path.join(HISTORICAL_DATA_DIR, file))
            df_w.columns = df_w.columns.str.lower()
            if len(df_w) < 60: continue
            
            for col in ['open', 'high', 'low', 'close', 'volume']:
                if col in df_w.columns: df_w[col] = pd.to_numeric(df_w[col], errors='coerce').fillna(0)

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

            recent_df = df_w.iloc[-60:].copy()
            if len(recent_df) < 20: continue
            current_row = recent_df.iloc[-1]
            
            # STRATEGY 1 & 2 DETECTION
            for target_type in ["body", "wick"]:
                strat_assigned = "Strategy 1: Body Strict" if target_type == "body" else "Strategy 2: Wick Retest"
                setup_active = False
                trigger_level, breakout_vol, weeks_above = 0.0, 0.0, 0
                
                for i in range(1, len(recent_df)):
                    row = recent_df.iloc[i]
                    prev_row = recent_df.iloc[i-1]
                    current_res = row['swing_body_res'] if target_type == "body" else row['swing_wick_res']
                    if pd.isna(current_res): continue

                    if not setup_active:
                        is_liquid = (row['close'] >= 5.0) and ((row['close'] * row['vol_avg']) >= 5000000)
                        is_breakout = row['close'] > current_res and prev_row['close'] <= current_res
                        is_zigzag = row['close'] <= (row['ema20'] * 1.25)
                        is_high_vol = row['volume'] > (row['vol_avg'] * 1.5)
                        is_aligned = row['ema20'] > row['sma50']
                        is_sloping_up = i >= 4 and row['ema20'] > recent_df.iloc[i-4]['ema20']
                        
                        if is_liquid and is_breakout and is_zigzag and is_high_vol and is_aligned and is_sloping_up:
                            setup_active = True
                            trigger_level = current_res
                            breakout_vol = row['volume']
                            weeks_above = 0
                        continue

                    if setup_active:
                        if row['close'] < row['sma50'] or weeks_above > 30:
                            setup_active = False
                            continue
                        weeks_above += 1
                        if i == len(recent_df) - 1 and weeks_above >= 4:  
                            prelim_setups.append({
                                "symbol": symbol, "strategy": strat_assigned, "type": target_type.upper(),
                                "target": float(trigger_level), "age_label": f"{int(weeks_above)}W", 
                                "csv_close": float(current_row['close']), "csv_vol": float(current_row['volume']),
                                "breakout_vol": float(breakout_vol), "atr": float(daily_atr)
                            })
                            
            # STRATEGY 3 HYBRID 4H DETECTION 
            csv_4h_path = os.path.join(HISTORICAL_DATA_DIR, f"{symbol}_4h.csv")
            s3_target = float(current_row['swing_body_res'])
            
            if pd.notna(s3_target) and s3_target > 0 and os.path.exists(csv_4h_path):
                df_4h = pd.read_csv(csv_4h_path)
                df_4h.columns = df_4h.columns.str.lower()
                
                if len(df_4h) > 60:
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df_4h[col] = pd.to_numeric(df_4h[col], errors='coerce').fillna(0)
                        
                    df_4h['ema20'] = df_4h['close'].ewm(span=20, adjust=False).mean()
                    df_4h['ema50'] = df_4h['close'].ewm(span=50, adjust=False).mean()
                    df_4h['vol_avg'] = df_4h['volume'].rolling(20).mean()
                    
                    recent_4h = df_4h.iloc[-60:].copy()
                    current_4h = recent_4h.iloc[-1]
                    
                    if current_4h['ema20'] > current_4h['ema50']:
                        held_bars = 0
                        for val in reversed(recent_4h['close'].values):
                            if val > s3_target: held_bars += 1
                            else: break
                                
                        if held_bars >= 4:
                            breakout_idx = len(recent_4h) - held_bars - 1
                            if breakout_idx >= 0:
                                breakout_bar = recent_4h.iloc[breakout_idx]
                                if breakout_bar['volume'] > (breakout_bar['vol_avg'] * 1.2):
                                    dist = (current_4h['close'] - s3_target) / s3_target
                                    if 0 <= dist <= 0.05:
                                        prelim_setups.append({
                                            "symbol": symbol, "strategy": "Strategy 3: 4H PRO Model", "type": "BODY_4H",
                                            "target": float(s3_target), "age_label": f"{held_bars} bars", 
                                            "csv_close": float(current_4h['close']), "csv_vol": float(current_4h['volume']),
                                            "breakout_vol": float(breakout_bar['volume']), "atr": float(daily_atr)
                                        })
        except Exception as e:
            continue

    symbols_to_fetch = list(set([s["symbol"] for s in prelim_setups]))
    live_prices = {}
    if symbols_to_fetch:
        try:
            chunk_size = 50
            for i in range(0, len(symbols_to_fetch), chunk_size):
                chunk = symbols_to_fetch[i:i + chunk_size]
                req = StockLatestTradeRequest(symbol_or_symbols=chunk)
                trades = data_client.get_stock_latest_trade(req)
                for sym, trade in trades.items(): live_prices[sym] = float(trade.price)
        except Exception as e: pass

    discovered_setups = []
    for setup in prelim_setups:
        sym = setup["symbol"]
        live_px = live_prices.get(sym, setup["csv_close"])
        trigger_level = setup["target"]
        
        distance_to_level = ((live_px - trigger_level) / trigger_level) * 100
        trigger_envelope = trigger_level * 1.015 
        
        is_ignored = sym in ignored_tickers
        atr_pct = (setup["atr"] / trigger_level) * 100 if trigger_level > 0 and setup["atr"] > 0 else 0.0

        if live_px <= trigger_envelope:
            logic_desc = f"LIVE TRIGGER: Dropped into 1.5% envelope ({setup['age_label']})."
            if is_ignored: logic_desc = "MANUAL OVERRIDE: Execution blocked."
            discovered_setups.append({**setup, "live_price": live_px, "dist": distance_to_level, "logic": logic_desc, "atr_pct": atr_pct, "actionable": not is_ignored, "ignored": is_ignored})
        elif 1.5 < distance_to_level <= 15:
            logic_desc = f"WATCHLIST: Spot is +{distance_to_level:.2f}% above floor."
            if is_ignored: logic_desc = "MANUAL OVERRIDE: Trading Disabled by User."
            discovered_setups.append({**setup, "live_price": live_px, "dist": distance_to_level, "logic": logic_desc, "atr_pct": atr_pct, "actionable": False, "ignored": is_ignored})

    discovered_setups.sort(key=lambda x: abs(x['dist']))
    system_state["pending_setups"] = discovered_setups

    local_buying_power = {s: float(system_state["accounts"][s]["buying_power"]) if s in system_state["accounts"] else 0.0 for s in clients}
    system_state["scanner_status"] = "Routing Live Triggers..."
    
    target_map = {"S1_BodyStrict": "BODY", "S2_WickScaled": "WICK", "S3_4H_Hybrid": "BODY_4H"}
    
    for setup in system_state["pending_setups"]:
        if not setup.get("actionable") or setup.get("ignored"): continue

        for strat_name, client in clients.items():
            if setup["type"] == target_map.get(strat_name):
                try:
                    acct_data = system_state["accounts"].get(strat_name)
                    if not acct_data: continue
                    
                    risk_pct = 0.01 
                    usable_capital = min(acct_data["equity"] * 0.10, local_buying_power[strat_name])
                    
                    stop_loss_px = setup["target"] - (1.0 * setup["atr"])
                    risk_per_share = setup["target"] - stop_loss_px
                    
                    if risk_per_share > 0:
                        raw_shares = int(math.floor((acct_data["equity"] * risk_pct) / risk_per_share))
                        shares = int(math.floor(usable_capital / setup["target"])) if (raw_shares * setup["target"]) > usable_capital else raw_shares
                        total_cost = shares * setup["target"]
                        
                        if shares >= 1 and total_cost <= local_buying_power[strat_name]:
                            
                            # STRATEGY 3: DUAL-LEG ENTRY
                            if strat_name == "S3_4H_Hybrid" and shares >= 2:
                                half_shares = shares // 2
                                runner_shares = shares - half_shares
                                tp1_px = setup["target"] + (2.0 * risk_per_share)
                                
                                req1 = LimitOrderRequest(
                                    symbol=setup["symbol"], qty=half_shares, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
                                    limit_price=round(setup["target"], 2), order_class=OrderClass.BRACKET,
                                    take_profit=TakeProfitRequest(limit_price=round(tp1_px, 2)),
                                    stop_loss=StopLossRequest(stop_price=round(stop_loss_px, 2))
                                )
                                client.submit_order(req1)
                                
                                req2 = LimitOrderRequest(
                                    symbol=setup["symbol"], qty=runner_shares, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
                                    limit_price=round(setup["target"], 2), order_class=OrderClass.OTO,
                                    stop_loss=StopLossRequest(stop_price=round(stop_loss_px, 2))
                                )
                                client.submit_order(req2)
                                log_system_action(f"🚀 [S3] DUAL-LEG FIRED: {shares}x {setup['symbol']} @ ${setup['target']:.2f}. 2R TP Locked.")
                                
                            # STRATEGY 1 & 2: PURE SNIPERS (100% position, hard stop, no TP)
                            else:
                                req = LimitOrderRequest(
                                    symbol=setup["symbol"], qty=shares, side=OrderSide.BUY, time_in_force=TimeInForce.GTC,
                                    limit_price=round(setup["target"], 2), order_class=OrderClass.OTO,
                                    stop_loss=StopLossRequest(stop_price=round(stop_loss_px, 2))
                                )
                                client.submit_order(req)
                                log_system_action(f"🚀 [{strat_name}] ENTRY FIRED: {shares}x {setup['symbol']} @ ${setup['target']:.2f}")
                                
                            local_buying_power[strat_name] -= total_cost
                            setup["actionable"] = False 
                except Exception as e: 
                    log_system_action(f"❌ API REJECTION [{setup['symbol']}]: {str(e)}")
                    setup["actionable"] = False 

    system_state["scanner_status"] = "Monitoring Active Portfolios"

scheduler = BackgroundScheduler()
scheduler.add_job(update_account_states, 'interval', minutes=1)
scheduler.add_job(run_daily_scan, 'cron', day_of_week='mon-fri', hour=16, minute=15, timezone='US/Eastern')
scheduler.start()

@app.post("/set-margin/{strat_name}")
async def set_margin(strat_name: str, margin_amount: float = Form(...)):
    if strat_name in system_state["margin_limits"]:
        system_state["margin_limits"][strat_name] = max(0.0, margin_amount)
        log_system_action(f"⚙️ [{strat_name}] Margin allowance updated to ${margin_amount:,.2f}")
    return RedirectResponse(url="/", status_code=303)

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    update_account_states()
    return templates.TemplateResponse(request, "dashboard.html", {"state": system_state})

@app.post("/scan")
async def force_scan():
    run_daily_scan()
    return RedirectResponse(url="/", status_code=303)

@app.post("/toggle-ignore/{symbol}")
async def override_ticker(symbol: str):
    toggle_ignored_ticker(symbol)
    return RedirectResponse(url="/", status_code=303)

@app.post("/market-sell-all/{strat_name}/{symbol}")
async def market_sell_all(strat_name: str, symbol: str):
    try:
        client = clients[strat_name]
        for o in client.get_orders():
            if o.symbol == symbol: client.cancel_order_by_id(o.id)
        await asyncio.sleep(2)
        client.close_position(symbol)
        log_system_action(f"⚡ EMERGENCY SELL: Liquidated {symbol} at Market Price in {strat_name}.")
    except Exception as e: pass
    return RedirectResponse(url="/", status_code=303)

@app.post("/cancel-all-orders")
async def cancel_all_orders():
    for strat_name, client in clients.items():
        try:
            client.cancel_orders()
            log_system_action(f"🗑️ [{strat_name}] Wiped all pending limit orders. Cash freed.")
        except Exception as e: pass
    return RedirectResponse(url="/", status_code=303)

@app.post("/liquidate-strategy/{strat_name}")
async def liquidate_strategy(strat_name: str):
    try:
        client = clients[strat_name]
        client.close_all_positions(cancel_orders=True)
        log_system_action(f"🚨 [{strat_name}] STRATEGY NUKED: All positions closed, all orders cancelled.")
    except Exception as e:
        log_system_action(f"❌ Failed to liquidate {strat_name}: {str(e)}")
    return RedirectResponse(url="/", status_code=303)

@app.post("/liquidate-all")
async def liquidate_all():
    for strat_name, client in clients.items():
        try:
            client.close_all_positions(cancel_orders=True)
            log_system_action(f"🚨 [{strat_name}] GLOBAL LIQUIDATION: All positions and orders wiped.")
        except Exception as e: pass
    return RedirectResponse(url="/", status_code=303)

@app.on_event("startup")
async def startup_event():
    update_account_states()
