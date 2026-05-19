import math
import os

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def compute_compounded_metrics(equity_curve: pd.Series):
    """Calculates institutional metrics directly from a compounded time-series curve."""
    if len(equity_curve) < 2:
        return 0.0, 0.0, 0.0

    returns = equity_curve.pct_change().dropna()

    if returns.std() == 0:
        sharpe = 0.0
    else:
        sharpe = np.sqrt(TRADING_DAYS) * returns.mean() / returns.std()

    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    max_dd = drawdown.min()

    start = equity_curve.iloc[0]
    end = equity_curve.iloc[-1]
    years = len(equity_curve) / TRADING_DAYS

    if years <= 0 or start <= 0:
        cagr_val = 0.0
    else:
        cagr_val = (end / start) ** (1 / years) - 1

    return cagr_val, max_dd, sharpe


def simulate_compounding_portfolio(
    trades_df: pd.DataFrame, initial_capital: float = 100000.0, risk_percent: float = 0.01
):
    """
    Simulates a finite portfolio chronologically using the exact TradingView
    Fixed Fractional formula, tested against the entire unfiltered trade universe.
    """
    if trades_df.empty:
        return {"cagr": 0.0, "max_dd": 0.0, "sharpe": 0.0, "total_trades": 0}

    events = []
    for _, row in trades_df.iterrows():
        events.append({"time": pd.to_datetime(row["entry_time"]), "type": "entry", "data": row})
        events.append({"time": pd.to_datetime(row["exit_time"]), "type": "exit", "data": row})

    events.sort(key=lambda x: x["time"])

    current_equity = initial_capital
    available_cash = initial_capital
    active_positions = []
    executed_trades = 0

    equity_history = [{"date": events[0]["time"].date(), "equity": initial_capital}]
    last_date = events[0]["time"].date()

    for event in events:
        current_date = event["time"].date()
        trade = event["data"]

        if event["type"] == "exit":
            for i, pos in enumerate(active_positions):
                if pos["symbol"] == trade["symbol"] and pos["entry_time"] == trade["entry_time"]:
                    proceeds = pos["shares"] * trade["exit_price"]
                    pnl = proceeds - pos["position_value"]

                    available_cash += proceeds
                    current_equity += pnl
                    active_positions.pop(i)
                    break

        elif event["type"] == "entry":
            entry_price = trade["entry_price"]

            if "stop_loss" in trade and pd.notna(trade["stop_loss"]):
                stop_loss = trade["stop_loss"]
            else:
                stop_loss = entry_price * 0.90

            # -------------------------------------------------------------
            # EXACT TRADINGVIEW RISK FORMULA
            # -------------------------------------------------------------
            risk_dollar = current_equity * risk_percent
            risk_per_share = entry_price - stop_loss

            if risk_per_share <= 0:
                continue

            shares = math.floor(risk_dollar / risk_per_share)
            position_value = shares * entry_price
            # -------------------------------------------------------------

            if position_value > available_cash:
                shares = math.floor(available_cash / entry_price)
                position_value = shares * entry_price

            if shares > 0:
                available_cash -= position_value
                active_positions.append(
                    {
                        "symbol": trade["symbol"],
                        "entry_time": trade["entry_time"],
                        "shares": shares,
                        "position_value": position_value,
                    }
                )
                executed_trades += 1

        if current_date != last_date:
            equity_history.append({"date": current_date, "equity": current_equity})
            last_date = current_date

    equity_series = pd.DataFrame(equity_history).set_index("date")["equity"]
    cagr_val, max_dd, sharpe = compute_compounded_metrics(equity_series)

    return {
        "cagr": cagr_val * 100,
        "max_dd": max_dd * 100,
        "sharpe": sharpe,
        "total_trades": executed_trades,
    }


def execute_risk_sweep():
    print("Running Baseline Risk Sweep (No ML Over-Filtering) & Dynamic Compounding...")

    possible_paths = [
        "portfolio_trades_export.csv",
        "/code/portfolio_trades_export.csv",
        "data/trades.csv",
    ]

    container_csv = None
    for p in possible_paths:
        if os.path.exists(p) and os.path.getsize(p) > 0:
            container_csv = p
            break

    if not container_csv:
        print("ERROR: Trade log file not found for simulation.")
        return

    df = pd.read_csv(container_csv)
    df.columns = df.columns.str.lower()

    # Intentionally removed the ML filter here so you test against the ENTIRE trade history.

    print("\n=====================================================================")
    print(" RISK SWEEP COMPARISON MATRIX (Full Trade Universe)                  ")
    print("=====================================================================")
    print(f"{'Base Risk':<10} {'CAGR':<10} {'Max DD':<10} {'Sharpe':<10} {'Trades':<10}")

    risk_levels = [0.0040, 0.0075, 0.0100, 0.0125, 0.0150]

    for risk in risk_levels:
        res = simulate_compounding_portfolio(df, initial_capital=100000.0, risk_percent=risk)
        print(
            f"{risk*100:>4.2f}%      {res['cagr']:>5.2f}%    {res['max_dd']:>5.2f}%     {res['sharpe']:>5.2f}       {res['total_trades']}"
        )

    print("=====================================================================")


if __name__ == "__main__":
    execute_risk_sweep()
