"""Price bar repository for managing time-series price data."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc

from ..db.models import PriceBar
from ..db.session import get_db_session_readonly
from ..models.dto import PriceBarDTO
from .base import BaseRepository


class PriceBarRepository(BaseRepository[PriceBar]):
    """Repository for PriceBar entities with time-series functionality."""

    def __init__(self):
        super().__init__(PriceBar)

    def bulk_insert_bars(self, bars: List[PriceBarDTO]) -> None:
        """Bulk insert price bars."""
        if not bars:
            return

        with self._transaction_with_retry() as session:
            bar_objects = []
            for dto in bars:
                bar = PriceBar(
                    ticker=dto.ticker,
                    ts=dto.ts,
                    o=dto.o,
                    h=dto.h,
                    l=dto.l,
                    c=dto.c,
                    v=dto.v,
                    timeframe=dto.timeframe,
                )
                bar_objects.append(bar)

            session.add_all(bar_objects)
            session.flush()

    def get_bars_by_ticker(
        self,
        ticker: str,
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
        timeframe: Optional[str] = None,
        limit: int = 1000,
    ) -> List[PriceBar]:
        """Get price bars for a specific ticker within a time range."""
        with get_db_session_readonly() as session:
            query = session.query(PriceBar).filter(PriceBar.ticker == ticker)

            if start_ts:
                query = query.filter(PriceBar.ts >= start_ts)
            if end_ts:
                query = query.filter(PriceBar.ts <= end_ts)
            if timeframe:
                query = query.filter(PriceBar.timeframe == timeframe)

            return query.order_by(desc(PriceBar.ts)).limit(limit).all()

    def get_latest_bar(self, ticker: str, timeframe: str = "1d") -> Optional[PriceBar]:
        """Get the latest price bar for a ticker."""
        with get_db_session_readonly() as session:
            return (
                session.query(PriceBar)
                .filter(
                    and_(PriceBar.ticker == ticker, PriceBar.timeframe == timeframe)
                )
                .order_by(desc(PriceBar.ts))
                .first()
            )

    def get_bars_by_timeframe(
        self, ticker: str, timeframe: str, limit: int = 1000
    ) -> List[PriceBar]:
        """Get price bars for a specific ticker and timeframe."""
        with get_db_session_readonly() as session:
            return (
                session.query(PriceBar)
                .filter(
                    and_(PriceBar.ticker == ticker, PriceBar.timeframe == timeframe)
                )
                .order_by(desc(PriceBar.ts))
                .limit(limit)
                .all()
            )

    def get_bars_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        tickers: Optional[List[str]] = None,
        timeframe: Optional[str] = None,
        limit: int = 10000,
    ) -> List[PriceBar]:
        """Get price bars within a date range."""
        with get_db_session_readonly() as session:
            query = session.query(PriceBar).filter(
                and_(PriceBar.ts >= start_date, PriceBar.ts <= end_date)
            )

            if tickers:
                query = query.filter(PriceBar.ticker.in_(tickers))
            if timeframe:
                query = query.filter(PriceBar.timeframe == timeframe)

            return query.order_by(desc(PriceBar.ts)).limit(limit).all()

    def get_ohlcv_data(
        self, ticker: str, start_ts: datetime, end_ts: datetime, timeframe: str = "1d"
    ) -> List[Dict[str, Any]]:
        """Get OHLCV data for a ticker in a specific time range."""
        with get_db_session_readonly() as session:
            bars = (
                session.query(PriceBar)
                .filter(
                    and_(
                        PriceBar.ticker == ticker,
                        PriceBar.timeframe == timeframe,
                        PriceBar.ts >= start_ts,
                        PriceBar.ts <= end_ts,
                    )
                )
                .order_by(PriceBar.ts)
                .all()
            )

            return [
                {
                    "timestamp": bar.ts,
                    "open": bar.o,
                    "high": bar.h,
                    "low": bar.l,
                    "close": bar.c,
                    "volume": bar.v,
                }
                for bar in bars
            ]

    def get_price_stats(
        self, ticker: str, timeframe: str = "1d", days: int = 30
    ) -> Optional[Dict[str, Any]]:
        """Get price statistics for a ticker."""
        with get_db_session_readonly() as session:
            from datetime import timedelta

            end_date = datetime.utcnow()
            start_date = end_date - timedelta(days=days)

            bars = (
                session.query(PriceBar)
                .filter(
                    and_(
                        PriceBar.ticker == ticker,
                        PriceBar.timeframe == timeframe,
                        PriceBar.ts >= start_date,
                        PriceBar.ts <= end_date,
                        PriceBar.c.isnot(None),
                    )
                )
                .order_by(PriceBar.ts)
                .all()
            )

            if not bars:
                return None

            closes = [bar.c for bar in bars if bar.c is not None]
            volumes = [bar.v for bar in bars if bar.v is not None]

            if not closes:
                return None

            # Calculate statistics
            current_price = closes[-1]
            price_change = closes[-1] - closes[0] if len(closes) > 1 else 0
            price_change_pct = (price_change / closes[0]) * 100 if closes[0] != 0 else 0

            return {
                "ticker": ticker,
                "timeframe": timeframe,
                "current_price": current_price,
                "price_change": price_change,
                "price_change_pct": price_change_pct,
                "min_price": min(closes),
                "max_price": max(closes),
                "avg_volume": sum(volumes) / len(volumes) if volumes else 0,
                "total_volume": sum(volumes) if volumes else 0,
                "data_points": len(bars),
            }

    def delete_bars_by_ticker(self, ticker: str) -> int:
        """Delete all price bars for a specific ticker."""
        with self._transaction_with_retry() as session:
            result = session.query(PriceBar).filter(PriceBar.ticker == ticker).delete()
            return result

    def delete_bars_by_time_range(self, start_ts: datetime, end_ts: datetime) -> int:
        """Delete price bars within a time range."""
        with self._transaction_with_retry() as session:
            result = (
                session.query(PriceBar)
                .filter(and_(PriceBar.ts >= start_ts, PriceBar.ts <= end_ts))
                .delete()
            )
            return result

    def get_tickers_with_data(self, timeframe: Optional[str] = None) -> List[str]:
        """Get list of tickers that have price data."""
        with get_db_session_readonly() as session:
            query = session.query(PriceBar.ticker).distinct()
            if timeframe:
                query = query.filter(PriceBar.timeframe == timeframe)

            return [row[0] for row in query.all()]

    def get_data_coverage(self) -> Dict[str, Any]:
        """Get data coverage statistics."""
        with get_db_session_readonly() as session:
            total_bars = session.query(PriceBar).count()
            ticker_count = session.query(PriceBar.ticker).distinct().count()
            timeframe_counts = (
                session.query(
                    PriceBar.timeframe,
                    session.query(PriceBar)
                    .filter(PriceBar.timeframe == PriceBar.timeframe)
                    .count(),
                )
                .distinct()
                .all()
            )

            return {
                "total_bars": total_bars,
                "unique_tickers": ticker_count,
                "by_timeframe": dict(timeframe_counts),
            }
