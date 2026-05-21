import os
import math
import logging
from datetime import datetime
from dotenv import load_dotenv
import pandas as pd
import yfinance as yf

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from apscheduler.schedulers.background import BackgroundScheduler

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import LimitOrderRequest, TakeProfitRequest, StopLossRequest
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass

# Setup
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(title="MIT-Loop Production Engine")
templates = Jinja2Templates(directory="templates")

# Initialize 3 Alpaca Clients
clients = {
    "S1_BodyStrict": TradingClient(os.getenv("ALPACA_API_KEY_S1"), os.getenv("ALPACA_SECRET_KEY_S1"), paper=True),
    "S2_WickScaled": TradingClient(os.getenv("ALPACA_API_KEY_S2"), os.getenv("ALPACA_SECRET_KEY_S2"), paper=True),
    "S3_WickStrict": TradingClient(os.getenv("ALPACA_API_KEY_S3"), os.getenv("ALPACA_SECRET_KEY_S3"), paper=True)
}

# Global State for the UI
system_state = {
    "last_scan": "Never",
    "market_status": "Closed",
    "accounts": {},
    "pending_setups": [] # "Waiting for..." logic
}

def update_account_states():
    """Fetches live balances and active positions from Alpaca for all strategies."""
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
                "positions": [{"symbol": p.symbol, "qty": p.qty, "unrealized_pl": p.unrealized_pl, "current_price": p.current_price} for p in positions],
                "active_orders": len(orders)
            }
        except Exception as e:
            logger.error(f"Error fetching data for {strat_name}: {e}")

def run_daily_scan():
    """
    The Core Engine: Runs daily after market close.
    1. Scans universe for structural setups.
    2. Submits Bracket Orders (Limit Entry + Stop Loss) to Alpaca.
    3. Checks active positions for trailing 20-EMA exits.
    """
    logger.info("Starting Daily Market Scan...")
    system_state["last_scan"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    update_account_states()
    
    # NOTE: In production, you will loop through your desired ticker universe here.
    # For this scaffold, we define the architecture of how a trade is sent.
    universe = ["AAPL", "MSFT", "TSLA"] # Expand this to your S&P500/R2K list
    system_state["pending_setups"].clear()

    for ticker in universe:
        try:
            # 1. Fetch live data (Simulated here with yfinance for robustness)
            df = yf.download(ticker, period="2y", interval="1wk", progress=False)
            if df.empty or len(df) < 50: continue
            
            # --- INSERT YOUR QUANT LOGIC HERE ---
            # (Calculate 11-Week Pivot, EMA20, SMA50, ATR, Breakout conditions)
            # Simulated output for demonstration:
            setup_found = False 
            target_body_px = 150.00
            target_wick_px = 155.00
            stop_loss_px = 140.00
            
            # Example: System spots a setup forming but waiting for pullback
            system_state["pending_setups"].append({
                "symbol": ticker,
                "status": "Waiting for Pullback",
                "trigger": f"Limit Buy @ ${target_body_px}",
                "strategy": "S1_BodyStrict"
            })

            # 2. Advanced Order Execution (If setup is perfectly triggered)
            # When the engine decides to buy, we let Alpaca handle the stop loss automatically!
            if setup_found:
                strat = "S1_BodyStrict"
                acct_equity = system_state["accounts"][strat]["equity"]
                risk_amt = acct_equity * 0.01
                risk_per_share = target_body_px - stop_loss_px
                shares = math.floor(risk_amt / risk_per_share)

                if shares > 0:
                    order_data = LimitOrderRequest(
                        symbol=ticker,
                        qty=shares,
                        side=OrderSide.BUY,
                        time_in_force=TimeInForce.GTC,
                        limit_price=target_body_px,
                        order_class=OrderClass.OTO, # One Triggers Other
                        stop_loss=StopLossRequest(stop_price=stop_loss_px)
                    )
                    clients[strat].submit_order(order_data)
                    logger.info(f"[{strat}] Submitted Limit Order for {shares} shares of {ticker} at ${target_body_px}")

            # 3. Trailing Stop Management (Check open positions)
            # If current close < EMA20, submit Market Sell
            # ... (Implementation of trailing exit loop here) ...

        except Exception as e:
            logger.error(f"Error scanning {ticker}: {e}")

    logger.info("Daily scan complete.")

# Background Scheduler
scheduler = BackgroundScheduler()
# Schedule to run every Monday-Friday at 16:15 PM EST (After market close)
scheduler.add_job(run_daily_scan, 'cron', day_of_week='mon-fri', hour=16, minute=15)
scheduler.start()

# API Endpoints
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    update_account_states()
    return templates.TemplateResponse("dashboard.html", {"request": request, "state": system_state})

@app.on_event("startup")
async def startup_event():
    logger.info("Starting MIT-Loop Auto-Trader...")
    update_account_states()
