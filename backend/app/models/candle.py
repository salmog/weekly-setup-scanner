from sqlalchemy import BigInteger, Column, DateTime, Index, Numeric, String, UniqueConstraint

from app.core.database import Base


class Candle(Base):
    __tablename__ = "candles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    ts = Column(DateTime(timezone=True), nullable=False, index=True)
    open = Column(Numeric, nullable=False)
    high = Column(Numeric, nullable=False)
    low = Column(Numeric, nullable=False)
    close = Column(Numeric, nullable=False)
    volume = Column(BigInteger, nullable=False)
    vwap = Column(Numeric, nullable=True)

    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "ts", name="uix_symbol_tf_ts"),
        Index("idx_symbol_tf_ts", "symbol", "timeframe", "ts"),
    )
