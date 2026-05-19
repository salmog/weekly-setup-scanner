from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class CandleBase(BaseModel):
    symbol: str
    timeframe: str
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    vwap: Decimal | None = None


class CandleCreate(CandleBase):
    pass


class CandleResponse(CandleBase):
    id: int
    model_config = ConfigDict(from_attributes=True)
