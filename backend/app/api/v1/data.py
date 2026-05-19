from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.data_sources.ibkr_csv import IBKRCsvProvider
from app.data_sources.postgres_provider import PostgresProvider
from app.schemas.candle import CandleResponse
from app.services.market_data_service import MarketDataService

router = APIRouter(prefix="/data", tags=["Market Data"])


@router.post("/upload-csv", summary="Idempotent CSV File Import")
async def upload_ticker_csv(
    symbol: str = Form(...),
    timeframe: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Processing constraints require valid file inputs matching .csv format extension.",
        )

    try:
        contents = await file.read()
        csv_string = contents.decode("utf-8")

        provider = IBKRCsvProvider()
        parsed_records = provider.parse_csv_stream(csv_string, symbol, timeframe)

        if not parsed_records:
            return {
                "status": "success",
                "inserted": 0,
                "skipped": 0,
                "detail": "Zero valid data sequences identified.",
            }

        metrics = await MarketDataService.ingest_candles(db, parsed_records)
        return {"status": "success", **metrics}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error aborted operation processing: {str(e)}",
        )


@router.get("/candles/{symbol}/{timeframe}", response_model=list[CandleResponse])
async def get_candles(
    symbol: str,
    timeframe: str,
    start_date: str = "1970-01-01T00:00:00Z",
    end_date: str = "2030-01-01T00:00:00Z",
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retrieve historical candle arrays via the PostgresProvider access layer."""
    try:
        start_ts = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        end_ts = datetime.fromisoformat(end_date.replace("Z", "+00:00"))

        provider = PostgresProvider(db)
        return await provider.fetch_historical_candles(symbol, timeframe, start_ts, end_ts)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format string constraint: {str(e)}",
        )
