from decimal import Decimal

import pandas as pd

from app.schemas.strategy import BreakoutEvaluation, StrategyRuleResult
from app.strategy.rule_engine import DeterministicRuleEngine


class MultiTimeframeEngine:
    """Coordinates and enforces strict hierarchical alignment constraints between timeframes."""

    @staticmethod
    def align_and_evaluate(
        symbol: str,
        weekly_df: pd.DataFrame,
        daily_df: pd.DataFrame,
        four_hour_df: pd.DataFrame,
        breadth_metrics: dict[str, float] = None,
    ) -> BreakoutEvaluation:
        """Evaluates multiple timeframes. Rejects setups if any timeframe violates structural constraints."""

        # 1. Macro Rule Layer: Evaluate Weekly Frame Trends
        if weekly_df.empty or len(weekly_df) < 2:
            return BreakoutEvaluation(
                symbol=symbol,
                timeframe="MTF_ALIGN",
                ts=pd.Timestamp.now(),
                is_valid_setup=False,
                confidence_score=0.0,
                reasoning=[],
                rejection_reasons=["Missing historical weekly structure"],
                rules_checked=[],
            )

        weekly_row = weekly_df.iloc[-1]
        weekly_macro_bullish = bool(weekly_row["close"] > weekly_row["sma_150"])

        if not weekly_macro_bullish:
            return BreakoutEvaluation(
                symbol=symbol,
                timeframe="WEEKLY",
                ts=weekly_df.index[-1].to_pydatetime(),
                is_valid_setup=False,
                confidence_score=0.0,
                reasoning=[],
                rejection_reasons=[
                    "Macro hierarchical veto: Weekly close sits below long-term trend lines."
                ],
                rules_checked=[],
            )

        # 2. Setup Layer: Evaluate Daily Breakout Indicators
        daily_results = DeterministicRuleEngine.evaluate_timeframe_rules(
            df=daily_df, symbol=symbol, timeframe="DAILY", breadth_metrics=breadth_metrics
        )

        # 3. Confirmation Trigger Layer: Evaluate 4H Timing Vectors
        four_hour_results = DeterministicRuleEngine.evaluate_timeframe_rules(
            df=four_hour_df, symbol=symbol, timeframe="4H", breadth_metrics=None
        )

        # Enforce unified alignment validation checks
        combined_rules: list[StrategyRuleResult] = []
        combined_rules.extend(daily_results.get("rules", []))
        combined_rules.extend(four_hour_results.get("rules", []))

        all_rejections = []
        all_rejections.extend(daily_results.get("rejections", []))
        all_rejections.extend(four_hour_results.get("rejections", []))

        all_reasoning = ["Weekly structural direction is confirmed bullish."]
        all_reasoning.extend(daily_results.get("reasoning", []))
        all_reasoning.extend(four_hour_results.get("reasoning", []))

        is_setup_valid = daily_results["passed"] and four_hour_results["passed"]

        # Compute position scaling metrics using ATR stop boundaries
        suggested_entry = None
        suggested_stop = None
        suggested_target = None

        if is_setup_valid:
            daily_row = daily_results["row"]
            suggested_entry = Decimal(str(round(daily_row["close"], 2)))

            # Apply ATR volatility stop formula
            atr_val = daily_row.get("atr_14", daily_row["close"] * 0.02)
            stop_calc = daily_row["close"] - (1.0 * atr_val)
            suggested_stop = Decimal(str(round(stop_calc, 2)))

            target_calc = daily_row["close"] + (3.0 * atr_val)
            suggested_target = Decimal(str(round(target_calc, 2)))

        total_rules = len(combined_rules)
        passed_rules = sum(1 for r in combined_rules if r.passed)
        final_confidence = (passed_rules / total_rules) * 100.0 if total_rules > 0 else 0.0

        return BreakoutEvaluation(
            symbol=symbol.upper(),
            timeframe="DAILY",  # Structural execution anchored to the Daily layer
            ts=daily_df.index[-1].to_pydatetime(),
            is_valid_setup=is_setup_valid,
            confidence_score=final_confidence,
            reasoning=all_reasoning,
            rejection_reasons=all_rejections,
            suggested_entry=suggested_entry,
            suggested_stop=suggested_stop,
            suggested_target=suggested_target,
            rules_checked=combined_rules,
        )
