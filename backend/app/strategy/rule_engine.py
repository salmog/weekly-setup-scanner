from typing import Any

import pandas as pd

from app.schemas.strategy import StrategyRuleResult


class DeterministicRuleEngine:
    """Core rule processor executing strict conditional logic blocks on single timeframe inputs."""

    @staticmethod
    def evaluate_timeframe_rules(
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
        breadth_metrics: dict[str, float] = None,
        is_capitulation_active: bool = False,
    ) -> dict[str, Any]:
        """Runs rule compliance checks on the trailing index row of a single data frame."""
        rules_checked: list[StrategyRuleResult] = []
        rejection_reasons: list[str] = []
        reasoning: list[str] = []

        if df.empty or len(df) < 150:
            return {
                "passed": False,
                "confidence": 0.0,
                "rules": [],
                "rejections": ["Insufficient chronological lookback padding"],
                "reasoning": ["Dataset too short"],
            }

        row = df.iloc[-1]
        prev_row = df.iloc[-2]

        # 1. Macro Trend Filter (SMA150 + Slope) with capitulation override exception rule
        price_above_sma = bool(row["close"] > row["sma_150"])
        trend_sloping_up = bool(row.get("sma_150_slope", 0) > 0)

        trend_passed = (price_above_sma and trend_sloping_up) or is_capitulation_active

        if trend_passed:
            msg = (
                "Trend passed: Price above upward sloping SMA150."
                if not is_capitulation_active
                else "Trend passed via capitulation override exception."
            )
            reasoning.append(msg)
        else:
            rejection_reasons.append(
                "Trend failure: Price below SMA150 or negative structural slope gradient."
            )

        rules_checked.append(
            StrategyRuleResult(
                rule_name="Trend_Filter",
                passed=trend_passed,
                details=f"Price: {row['close']:.2f}, SMA150: {row['sma_150']:.2f}, Exception Active: {is_capitulation_active}",
            )
        )

        # 2. Choppy Market Filter (Overlapping range check defense)
        body_sizes = (df["close"] - df["open"]).abs().tail(5).mean()
        total_ranges = (df["high"] - df["low"]).tail(5).mean()
        is_choppy = bool(body_sizes / total_ranges < 0.25) if total_ranges > 0 else False

        choppy_passed = not is_choppy
        if choppy_passed:
            reasoning.append(
                "Volatility health verified: No structural choppy regime signature detected."
            )
        else:
            rejection_reasons.append(
                "Market state block: Consistently low candle body expansions flag a choppy zone."
            )

        rules_checked.append(
            StrategyRuleResult(
                rule_name="Choppy_Market_Defense",
                passed=choppy_passed,
                details=f"Body-to-Range structural compression metric: {body_sizes / total_ranges if total_ranges > 0 else 0:.4f}",
            )
        )

        # 3. Market Breadth Filter Dynamic Rules Execution
        breadth_passed = True
        if breadth_metrics:
            pct_above_150 = breadth_metrics.get("pct_above_sma150", 100.0)
            if pct_above_150 < 30.0:  # System rules flag weak breadth environments
                # Enforce strict volume expansion multipliers if breadth signals a mega-cap distortion
                if not bool(row["volume"] > row["volume_avg_20"] * 1.5):
                    breadth_passed = False
                    rejection_reasons.append(
                        "Breadth filter failure: Weak market breath requires 1.5x volume threshold expansion."
                    )

        rules_checked.append(
            StrategyRuleResult(
                rule_name="Market_Breadth_Filter",
                passed=breadth_passed,
                details=f"Breadth environment state dictionary metrics injected: {breadth_metrics}",
            )
        )

        # 4. Local Breakout Mechanics Verification (Close near high + high volume)
        candle_range = float(row["high"] - row["low"])
        close_location = (
            float(row["high"] - row["close"]) / candle_range if candle_range > 0 else 1.0
        )

        breakout_candle_valid = close_location <= 0.20  # Closes in top 20% of range
        volume_confirmed = bool(row["is_volume_expanding"])

        breakout_passed = breakout_candle_valid and volume_confirmed
        if breakout_passed:
            reasoning.append(
                "Breakout structural close and high volume expansion are mathematically verified."
            )
        else:
            if not breakout_candle_valid:
                rejection_reasons.append(
                    "Breakout mechanic failure: Candle failed to close inside the top 20% boundary vector."
                )
            if not volume_confirmed:
                rejection_reasons.append(
                    "Breakout mechanic failure: Volume expansion verification returned negative matching constraints."
                )

        rules_checked.append(
            StrategyRuleResult(
                rule_name="Breakout_Mechanics",
                passed=breakout_passed,
                details=f"Location: {close_location:.2f} (Target <= 0.20), Volume Expanding: {volume_confirmed}",
            )
        )

        # Consolidated output validation metrics
        passed_rules = sum(1 for r in rules_checked if r.passed)
        confidence = (passed_rules / len(rules_checked)) * 100.0

        return {
            "passed": passed_rules == len(rules_checked),
            "confidence": confidence,
            "rules": rules_checked,
            "rejections": rejection_reasons,
            "reasoning": reasoning,
            "row": row,
        }
