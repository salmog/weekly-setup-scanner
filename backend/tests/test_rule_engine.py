from datetime import UTC

import pandas as pd

from app.strategy.multi_timeframe import MultiTimeframeEngine
from app.strategy.rule_engine import DeterministicRuleEngine


def make_test_mock_dataframe(count: int, pass_all_rules: bool = True) -> pd.DataFrame:
    idx = pd.date_range(start="2026-01-01", periods=count, freq="D", tz=UTC)

    close_vals = [150.0 + i for i in range(count)]
    vol_vals = [2000 for _ in range(count)]
    if not pass_all_rules:
        # Cause a volume confirmation failure on the trailing index row
        vol_vals[-1] = 10

    return pd.DataFrame(
        {
            "close": close_vals,
            "open": [c - 0.5 for c in close_vals],
            "high": [c + 0.1 for c in close_vals],  # Forces close location near high
            "low": [c - 1.0 for c in close_vals],
            "volume": vol_vals,
            "sma_150": [100.0 for _ in range(count)],
            "sma_150_slope": [0.5 for _ in range(count)],
            "is_trend_bullish": [True for _ in range(count)],
            "volume_avg_20": [1000 for _ in range(count)],
            "is_volume_expanding": [True if v > 1000 else False for v in vol_vals],
            "atr_14": [2.5 for _ in range(count)],
        },
        index=idx,
    )


def test_rule_engine_rejection_mechanics() -> None:
    """Test 1: Validates that individual rules fail cleanly when parameters are corrupted."""
    df_failing = make_test_mock_dataframe(160, pass_all_rules=False)
    results = DeterministicRuleEngine.evaluate_timeframe_rules(df_failing, "SPY", "1H")

    assert results["passed"] is False
    assert any("volume" in rej.lower() for rej in results["rejections"])


def test_weekly_hierarchy_macro_veto() -> None:
    """Test 2: Verifies the multi-timeframe layout rejects trades when weekly structures are bearish."""
    weekly_bearish_df = make_test_mock_dataframe(160)
    # Force weekly price below its long-term line
    weekly_bearish_df["sma_150"] = 5000.0

    daily_df = make_test_mock_dataframe(160)
    four_hour_df = make_test_mock_dataframe(160)

    evaluation = MultiTimeframeEngine.align_and_evaluate(
        symbol="SPY", weekly_df=weekly_bearish_df, daily_df=daily_df, four_hour_df=four_hour_df
    )

    assert evaluation.is_valid_setup is False
    assert any("veto" in rej.lower() for rej in evaluation.rejection_reasons)


def test_perfect_alignment_execution_parameters() -> None:
    """Test 3: Verifies that full structural alignment yields valid entries, stops, and targets."""
    weekly_df = make_test_mock_dataframe(160)
    daily_df = make_test_mock_dataframe(160)
    four_hour_df = make_test_mock_dataframe(160)

    evaluation = MultiTimeframeEngine.align_and_evaluate(
        symbol="SPY", weekly_df=weekly_df, daily_df=daily_df, four_hour_df=four_hour_df
    )

    assert evaluation.is_valid_setup is True
    assert evaluation.confidence_score == 100.0
    assert evaluation.suggested_entry is not None
    assert evaluation.suggested_stop < evaluation.suggested_entry
    assert evaluation.suggested_target > evaluation.suggested_entry
