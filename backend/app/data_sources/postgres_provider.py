from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.data_sources.base import HistoricalDataProvider
from app.models.candle import Candle


class PostgresProvider(HistoricalDataProvider):
    """Production data access layer. Enforces database as the single source of truth."""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def fetch_historical_candles(
        self, symbol: str, timeframe: str, start_ts: datetime, end_ts: datetime
    ) -> list[Candle]:
        """Queries the persistent database. Returns candles strictly sorted ASC by timestamp."""
        stmt = (
            select(Candle)
            .where(
                Candle.symbol == symbol.upper().strip(),
                Candle.timeframe == timeframe.upper().strip(),
                Candle.ts >= start_ts,
                Candle.ts <= end_ts,
            )
            .order_by(Candle.ts.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
