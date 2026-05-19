from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.models.candle import Candle
from app.schemas.candle import CandleCreate


class MarketDataService:
    @staticmethod
    async def ingest_candles(db: AsyncSession, candles: list[CandleCreate]) -> dict[str, int]:
        """Bulk inserts transactional records into PostgreSQL safely ignoring duplicates."""
        if not candles:
            return {"inserted": 0, "skipped": 0}

        # Transform inputs into clean raw data payloads
        values = [candle.model_dump() for candle in candles]

        # Use 1000-row execution chunks to prevent memory limits
        batch_size = 1000
        total_inserted = 0

        for i in range(0, len(values), batch_size):
            batch = values[i : i + batch_size]
            stmt = insert(Candle).values(batch)

            # Pure mathematical idempotency via unique constraints execution
            stmt = stmt.on_conflict_do_nothing(index_elements=["symbol", "timeframe", "ts"])

            result = await db.execute(stmt)
            if result.rowcount is not None and result.rowcount > -1:
                total_inserted += result.rowcount

        await db.commit()
        return {"inserted": total_inserted, "skipped": len(candles) - total_inserted}

    @staticmethod
    async def get_candles(
        db: AsyncSession, symbol: str, timeframe: str, limit: int = 100
    ) -> list[Candle]:
        """Retrieves historical candle arrays verified for ordering metrics."""
        stmt = (
            select(Candle)
            .where(Candle.symbol == symbol.upper(), Candle.timeframe == timeframe.upper())
            .order_by(Candle.ts.asc())
            .limit(limit)
        )  # Ascending order matching backtest rules

        result = await db.execute(stmt)
        return list(result.scalars().all())
