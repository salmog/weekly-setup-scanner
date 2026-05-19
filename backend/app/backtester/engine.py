from datetime import datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from app.schemas.backtest import BacktestResult, TradeLog
from app.strategy.rule_engine import DeterministicRuleEngine


class EventDrivenBacktester:
    """Simulates candle-by-candle trade execution enforcing realistic slippage and risk metrics."""

    def __init__(
        self,
        initial_balance: float = 100000.0,
        slippage_pct: float = 0.0005,
        commission_per_share: float = 0.005,
    ):
        self.initial_balance = Decimal(str(initial_balance))
        self.balance = self.initial_balance
        self.slippage_pct = Decimal(str(slippage_pct))
        self.commission_per_share = Decimal(str(commission_per_share))

        self.active_position: dict[str, Any] | None = None
        self.trade_history: list[TradeLog] = []

    def run_simulation(
        self, daily_df: pd.DataFrame, four_hour_df: pd.DataFrame, symbol: str
    ) -> BacktestResult:
        """Simulates historical execution sequentially across day intervals to prevent lookahead bias."""
        common_dates = daily_df.index.intersection(four_hour_df.index.normalize().unique())

        equity_curve = []
        high_water_mark = self.initial_balance
        max_drawdown = Decimal("0.0")

        for current_date in sorted(common_dates):
            day_slice_daily = daily_df.loc[:current_date]

            # Prevent future data leakage from 4H intraday cycles
            eod_four_hour = current_date + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            day_slice_4h = four_hour_df.loc[:eod_four_hour]

            if len(day_slice_daily) < 150:
                continue

            current_row_daily = day_slice_daily.iloc[-1]

            # 1. Manage Active Position Exits First
            if self.active_position:
                pos = self.active_position
                low_price = Decimal(str(current_row_daily["low"]))
                high_price = Decimal(str(current_row_daily["high"]))

                if low_price <= pos["stop_loss"]:
                    self._execute_exit(symbol, pos["stop_loss"], current_date, "STOP_LOSS")
                elif high_price >= pos["target_price"]:
                    self._execute_exit(symbol, pos["target_price"], current_date, "TAKE_PROFIT")

            # 2. Evaluate Setup Entries
            if not self.active_position:
                results = DeterministicRuleEngine.evaluate_timeframe_rules(
                    df=day_slice_daily, symbol=symbol, timeframe="DAILY"
                )

                if results["passed"]:
                    row = results["row"]
                    close_price = Decimal(str(row["close"]))
                    atr_val = Decimal(str(row.get("atr_14", row["close"] * 0.02)))

                    execution_entry = close_price * (Decimal("1.0") + self.slippage_pct)
                    stop_loss = execution_entry - atr_val
                    target_price = execution_entry + (atr_val * Decimal("3.0"))

                    risk_amount = self.balance * Decimal("0.01")
                    risk_per_share = execution_entry - stop_loss

                    if risk_per_share > 0:
                        shares = float(risk_amount / risk_per_share)
                        total_cost = Decimal(str(shares)) * execution_entry

                        if total_cost <= self.balance:
                            self.active_position = {
                                "entry_price": execution_entry,
                                "stop_loss": stop_loss,
                                "target_price": target_price,
                                "size": shares,
                                "entry_time": current_date,
                            }
                            self.balance -= total_cost

            # 3. Track Portfolio Equity and Peak Drawdown
            current_equity = self.balance
            if self.active_position:
                current_equity += Decimal(str(self.active_position["size"])) * Decimal(
                    str(current_row_daily["close"])
                )

            equity_curve.append(float(current_equity))
            if current_equity > high_water_mark:
                high_water_mark = current_equity

            if high_water_mark > 0:
                dd = (high_water_mark - current_equity) / high_water_mark * 100
                if dd > max_drawdown:
                    max_drawdown = dd

        total_trades = len(self.trade_history)
        wins = sum(1 for t in self.trade_history if t.pnl > 0)
        win_rate = (wins / total_trades) * 100.0 if total_trades > 0 else 0.0

        returns_series = np.diff(equity_curve) / equity_curve[:-1] if len(equity_curve) > 1 else [0]
        mean_ret = np.mean(returns_series) if len(returns_series) > 0 else 0
        std_ret = np.std(returns_series) if len(returns_series) > 0 else 1
        sharpe = (mean_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 0.0

        return BacktestResult(
            total_trades=total_trades,
            win_rate=round(win_rate, 2),
            initial_balance=self.initial_balance,
            final_balance=round(self.balance, 2),
            total_pnl=round(self.balance - self.initial_balance, 2),
            return_on_investment=round(
                float((self.balance - self.initial_balance) / self.initial_balance) * 100, 2
            ),
            max_drawdown_pct=round(float(max_drawdown), 2),
            sharpe_ratio=round(float(sharpe), 2),
            trades=self.trade_history,
        )

    def _execute_exit(
        self, symbol: str, price: Decimal, current_date: datetime, reason: str
    ) -> None:
        pos = self.active_position
        if not pos:
            return

        exit_price = (
            price * (Decimal("1.0") - self.slippage_pct) if reason == "STOP_LOSS" else price
        )
        gross_pnl = (exit_price - pos["entry_price"]) * Decimal(str(pos["size"]))
        commissions = Decimal(str(pos["size"])) * self.commission_per_share * Decimal("2.0")
        net_pnl = gross_pnl - commissions

        self.balance += (Decimal(str(pos["size"])) * exit_price) - commissions
        return_pct = float((exit_price - pos["entry_price"]) / pos["entry_price"]) * 100.0

        self.trade_history.append(
            TradeLog(
                symbol=symbol,
                direction="LONG",
                entry_time=pos["entry_time"],
                exit_time=current_date,
                entry_price=pos["entry_price"],
                exit_price=exit_price,
                size=pos["size"],
                pnl=net_pnl,
                return_pct=round(return_pct, 2),
                exit_reason=reason,
            )
        )
        self.active_position = None
