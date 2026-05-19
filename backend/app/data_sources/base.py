from datetime import datetime
from typing import Protocol

from app.models.candle import Candle


class HistoricalDataProvider(Protocol):
    """Abstract structural boundary for all system data access requirements."""

    async def fetch_historical_candles(
        self, symbol: str, timeframe: str, start_ts: datetime, end_ts: datetime
    ) -> list[Candle]:
        """Retrieves historical records strictly ordered chronologically from the data tier."""
        ...
