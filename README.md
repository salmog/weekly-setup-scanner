# MIT-Loop: Institutional Quantitative Breakout Engine

MIT-Loop is an automated quantitative equity trading system. It utilizes a top-down structural market approach combined with bottom-up probabilistic Machine Learning (Random Forest + Isotonic Calibration) to identify high-expectancy breakout setups.

## Core Performance Objective
* **Benchmark:** Outperform S&P 500 (SPY) Buy & Hold by 2x annually (CAGR).
* **Risk Constraint:** Maintain a maximum drawdown structurally lower than the broad market benchmark (e.g., capping portfolio drawdowns to < 15%).

## Strategy & Logic (The Power Law)

The system relies on asymmetrical risk/reward. It expects a low win rate (~25-30%) but relies on fat-tailed winners (3.5R to 4R) to generate net positive expectancy.

### 1. Entry Triggers (Multi-Layer Alignment)
* **Macro Regime:** Broad market (SPY) must be in a confirmed structural uptrend (e.g., above the 150/200-day moving average).
* **Price Breakout:** The equity must cross a defined structural ceiling (e.g., 20-day or 50-day rolling high).
* **Institutional Volume:** The breakout must be accompanied by extreme volume expansion (>1.5x of the 20-day average volume).
* **ML Probability Gatekeeper:** Continuous features (candle strength, relative strength to SPY, ATR expansion) are evaluated by a calibrated Random Forest model. Trades scoring below the optimized threshold are discarded as "fakeouts".
* **Timeframe Hierarchy:** Signal generation on Daily/Weekly charts to avoid intraday noise. Only Regular Trading Hours (RTH) are evaluated. Monthly (macro) and 4h (micro) are used strictly for confirmation.

### 2. Risk Management (Fixed Fractional Sizing)
* **Stop Loss Placement:** Hard stop placed technically beneath the breakout level or recent structural support.
* **Position Sizing:** The portfolio utilizes strict 1% Fixed Fractional compounding.
  * `Risk_$ = Current_Equity * 0.01`
  * `Risk_per_share = Entry_Price - Stop_Loss`
  * `Shares = Risk_$ / Risk_per_share`
* **Margin Constraint:** The engine will not allocate beyond available cash, safely skipping signals if capital is fully deployed.

### 3. Take Profit / Exit Strategy
* **R-Multiple Targeting:** The strategy mathematically targets minimums of 3.5R to 4R. Small profits are ignored to allow the math of the fat-tail distribution to play out.
* **Trailing Stops:** Once deep in profit, exits rely on trailing mechanisms to ride momentum anomalies to their absolute peak.

## System Architecture
* `backend/run_portfolio.py`: The data ingestion and signal generation pipeline. Processes thousands of equities to build the raw trade log.
* `backend/simulate_finite_portfolio.py`: The portfolio compounding engine. Processes the raw trade log chronologically, managing concurrent cash, applying fixed fractional sizing, and calculating institutional metrics (CAGR, Max DD, Sharpe).
* `backend/app/research/sweep_production.py`: The quantitative optimization matrix. Sweeps through threshold and ranking constraints to find peak mathematical efficiency.
