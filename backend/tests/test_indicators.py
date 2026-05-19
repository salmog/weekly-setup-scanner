from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pandas as pd
import pytest
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.data_sources.postgres_provider import PostgresProvider
from app.indicators.engine import IndicatorEngine
from app.models.candle import Candle

# ====================================================================
# FIXTURES & UTILITIES
# ====================================================================


def make_historical_candle(
    symbol: str, timeframe: str, ts: datetime, close: float, high: float, low: float, vol: int
) -> Candle:
    return Candle(
        symbol=symbol.upper(),
        timeframe=timeframe.upper(),
        ts=ts,
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=vol,
        vwap=Decimal(str(close)),
    )


def create_known_dataset(count: int, pattern_type: str = "linear") -> list[Candle]:
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    series = []
    for i in range(count):
        if pattern_type == "linear":
            price = 100.0 + i
            high, low = price + 2.0, price - 1.0
        elif pattern_type == "gap_spike":
            price = 200.0 if i < 10 else 250.0
            high, low = price + 10.0, price - 5.0
        else:
            price = 150.0
            high, low = 151.0, 149.0

        series.append(
            make_historical_candle(
                symbol="TESTED",
                timeframe="1H",
                ts=base_time + timedelta(hours=i),
                close=price,
                high=high,
                low=low,
                vol=1000 + i * 10,
            )
        )
    return series


# ====================================================================
# CORE INDEPENDENT VALIDATION SUITE
# ====================================================================


def test_indicator_mathematical_determinism() -> None:
    """Requirement 5: Verification that identical vector inputs yield identical outputs."""
    dataset = create_known_dataset(160, "linear")

    df_first = IndicatorEngine.compute_breakout_indicators(dataset)
    df_second = IndicatorEngine.compute_breakout_indicators(dataset)

    pd.testing.assert_frame_equal(df_first, df_second)


def test_multi_period_sma_and_slope_ranges() -> None:
    """Requirement 1: Asserting multi-period boundaries (150 window metrics) and slope accuracy."""
    dataset = create_known_dataset(160, "linear")
    df = IndicatorEngine.compute_breakout_indicators(dataset)

    assert df["sma_150"].iloc[0:148].isna().all()
    assert not pd.isna(df["sma_150"].iloc[-1])

    assert float(df["sma_150_slope"].iloc[-1]) > 0.0
    assert bool(df["is_trend_bullish"].iloc[-1]) is True


def test_atr_rolling_and_anomaly_gaps() -> None:
    """Requirement 2: Validating True Range handling on large overnight session spikes."""
    dataset = create_known_dataset(30, "gap_spike")
    df = IndicatorEngine.compute_breakout_indicators(dataset)

    assert df["atr_14"].iloc[0:12].isna().all()
    assert not pd.isna(df["atr_14"].iloc[-1])

    # ATR expands at index 14 due to the gap at index 10, then cools off by index 25
    assert float(df["atr_14"].iloc[14]) > float(df["atr_14"].iloc[25])


def test_volume_moving_average_bounds() -> None:
    """Requirement 1: Testing 20-period rolling volume confirmation thresholds."""
    dataset = create_known_dataset(40, "linear")
    df = IndicatorEngine.compute_breakout_indicators(dataset)

    assert df["volume_avg_20"].iloc[0:18].isna().all()
    assert (
        float(df["volume_avg_20"].iloc[-1]) == sum(range(1000 + 20 * 10, 1000 + 40 * 10, 10)) / 20
    )


def test_multi_timeframe_isolation_bounds() -> None:
    """Requirement 3: Ensuring different interval schemas calculate without structural leakage."""
    base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

    candles_1h = [
        make_historical_candle("MTF", "1H", base_time + timedelta(hours=i), 100.0, 101.0, 99.0, 500)
        for i in range(20)
    ]
    candles_1d = [
        make_historical_candle("MTF", "1D", base_time + timedelta(days=i), 100.0, 101.0, 99.0, 500)
        for i in range(20)
    ]

    df_1h = IndicatorEngine.compute_breakout_indicators(candles_1h)
    df_1d = IndicatorEngine.compute_breakout_indicators(candles_1d)

    assert len(df_1h) == len(df_1d)
    assert df_1h.index[1] - df_1h.index[0] == timedelta(hours=1)
    assert df_1d.index[1] - df_1d.index[0] == timedelta(days=1)


# ====================================================================
# ASYNC DATABASE TO PIPELINE INTEGRATION TEST
# ====================================================================


@pytest.mark.asyncio
async def test_db_to_indicator_pipeline_execution() -> None:
    """Requirement 4: Tests the complete pipeline using live database queries."""
    symbol = "INTEGRATION"
    timeframe = "1D"
    base_time = datetime(2026, 2, 1, 0, 0, 0, tzinfo=UTC)

    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM candles WHERE symbol = :s;"), {"s": symbol})
        await db.commit()

        candles = []
        for i in range(160):
            price = 120.0 + (i * 0.5)
            candles.append(
                Candle(
                    symbol=symbol,
                    timeframe=timeframe,
                    ts=base_time + timedelta(days=i),
                    open=Decimal(str(price)),
                    high=Decimal(str(price + 1.5)),
                    low=Decimal(str(price - 1.0)),
                    close=Decimal(str(price)),
                    volume=50000 + i,
                    vwap=Decimal(str(price)),
                )
            )

        db.add_all(candles)
        await db.commit()

        provider = PostgresProvider(db)
        fetched_candles = await provider.fetch_historical_candles(
            symbol=symbol,
            timeframe=timeframe,
            start_ts=base_time,
            end_ts=base_time + timedelta(days=200),
        )

        assert len(fetched_candles) == 160

        df = IndicatorEngine.compute_breakout_indicators(fetched_candles)

        assert not df.empty
        assert len(df) == 160
        assert not pd.isna(df["sma_150"].iloc[-1])
        assert float(df["sma_150"].iloc[-1]) > 120.0

        await db.execute(text("DELETE FROM candles WHERE symbol = :s;"), {"s": symbol})
        await db.commit()
