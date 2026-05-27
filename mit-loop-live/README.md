# MIT-Loop Pro: V2.0 Institutional Trading Engine

A quantitative execution algorithm and unified active-trader web dashboard built for Alpaca Markets.

## 🚀 Architecture Overview
MIT-Loop Pro operates a fully autonomous execution engine managing three distinct structural trading portfolios. It utilizes offline static CSV market data (fetched by IBKR) to mathematically define structural floor geometry, and connects to Alpaca v2 REST APIs to route Limit and Bracket orders.

### The Portfolios
1. **Strategy 1 (S1_BodyStrict): S1 Macro Floor Sniper**
   - **Target:** Weekly Pivot Body Top.
   - **Protocol:** Single-entry Limit Order. 100% position.
   - **Exit:** Hard Stop-Loss set at `-1.0 Daily ATR`. No runner.

2. **Strategy 2 (S2_WickScaled): S2 Liquidity Rejection Sniper**
   - **Target:** Weekly Pivot Wick Top.
   - **Protocol:** Single-entry Limit Order. 100% position.
   - **Exit:** Hard Stop-Loss set at `-1.0 Daily ATR`. No runner.

3. **Strategy 3 (S3_4H_Hybrid): S3 Dual-Leg PRO Model**
   - **Target:** Weekly Pivot Body Top (confirmed via 4H structure).
   - **Protocol:** Validates trend (`4H EMA20 > EMA50`), volume (`>1.2x`), and age (`>4 bars`). Dual-Leg Execution splits position 50/50.
   - **Exit Leg 1:** Bracket order with locked `+2R` Take-Profit and `-1.0 ATR` Stop.
   - **Exit Leg 2 (Runner):** Actively monitored by backend async loop. Market sells strictly the runner shares if price closes below `4H EMA20`.

## ⚙️ Security and UI Mechanics
* **RTH Lock:** Engine only transmits orders between `09:30` and `16:00` EST to prevent liquidity gapping.
* **Master Killswitch:** Requires manual input of "LIQUIDATE" to execute a global API sweep canceling all orders and dumping all open inventory at Market.
* **Local Liquidation:** Per-strategy "Flatten" buttons safely cancel orphaned legs and close strategy-specific positions.
* **Margin Insulation:** Calculates fractional share constraints natively inside of an algorithmic 1.0% NAV risk limit.

## 🛠️ Recovery & Deployment
To redeploy this exact environment:
1. `git clone git@github.com:salmog/weekly-setup-scanner.git`
2. `python3 -m venv venv && source venv/bin/activate`
3. `pip install fastapi uvicorn alpaca-py pandas numpy python-dotenv apscheduler jinja2`
4. Touch `.env` and assign Alpaca S1, S2, and S3 Keys.
5. Ensure local IBKR fetcher routes to `/historical_data/`.
6. Run: `nohup uvicorn main:app --host 0.0.0.0 --port 8000 > uvicorn.log 2>&1 &`
