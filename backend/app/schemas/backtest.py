from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class TradeLog(BaseModel):
    symbol: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal
    size: float
    pnl: Decimal
    return_pct: float
    exit_reason: str


class BacktestResult(BaseModel):
    total_trades: int
    win_rate: float
    initial_balance: Decimal
    final_balance: Decimal
    total_pnl: Decimal
    return_on_investment: float
    max_drawdown_pct: float
    sharpe_ratio: float
    trades: list[TradeLog]
