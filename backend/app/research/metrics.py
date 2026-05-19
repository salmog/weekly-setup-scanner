import numpy as np
import pandas as pd

TRADING_DAYS = 252


def compute_equity_curve(trades: pd.DataFrame, initial_capital: float = 100000.0):
    if trades.empty:
        return pd.Series([initial_capital])

    # Sort chronologically to properly map equity progression
    sorted_trades = trades.sort_values(by="entry_time")
    equity = [initial_capital]
    for pnl in sorted_trades["pnl_net"]:
        equity.append(equity[-1] + pnl)
    return pd.Series(equity)


def compute_returns(equity_curve: pd.Series):
    return equity_curve.pct_change().dropna()


def sharpe_ratio(returns: pd.Series, risk_free_rate: float = 0.0):
    if returns.std() == 0:
        return 0.0
    excess = returns - (risk_free_rate / TRADING_DAYS)
    return np.sqrt(TRADING_DAYS) * excess.mean() / returns.std()


def sortino_ratio(returns: pd.Series):
    downside = returns[returns < 0]
    if downside.std() == 0:
        return 0.0
    return np.sqrt(TRADING_DAYS) * returns.mean() / downside.std()


def max_drawdown(equity_curve: pd.Series):
    if equity_curve.empty:
        return 0.0
    rolling_max = equity_curve.cummax()
    drawdown = (equity_curve - rolling_max) / rolling_max
    return float(drawdown.min())


def cagr(equity_curve: pd.Series):
    if len(equity_curve) <= 1:
        return 0.0
    start = equity_curve.iloc[0]
    end = equity_curve.iloc[-1]
    years = len(equity_curve) / TRADING_DAYS
    if years <= 0 or start <= 0:
        return 0.0
    return float((end / start) ** (1 / years) - 1)


def expectancy(trades: pd.DataFrame):
    if trades.empty:
        return 0.0
    return float(trades["pnl_net"].mean())


def profit_factor(trades: pd.DataFrame):
    if trades.empty:
        return 0.0
    gross_profit = trades[trades["pnl_net"] > 0]["pnl_net"].sum()
    gross_loss = abs(trades[trades["pnl_net"] < 0]["pnl_net"].sum())
    if gross_loss == 0:
        return float(gross_profit) if gross_profit > 0 else 1.0
    return float(gross_profit / gross_loss)


def summarize_portfolio(trades: pd.DataFrame, initial_capital: float = 100000.0):
    if trades.empty:
        return {
            "total_trades": 0,
            "net_profit": 0.0,
            "win_rate": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "cagr": 0.0,
        }

    equity_curve = compute_equity_curve(trades, initial_capital)
    returns = compute_returns(equity_curve)

    return {
        "total_trades": len(trades),
        "net_profit": float(trades["pnl_net"].sum()),
        "win_rate": float((trades["pnl_net"] > 0).mean() * 100),
        "expectancy": expectancy(trades),
        "profit_factor": profit_factor(trades),
        "sharpe": sharpe_ratio(returns),
        "sortino": sortino_ratio(returns),
        "max_drawdown": max_drawdown(equity_curve),
        "cagr": cagr(equity_curve),
    }
