"""Signal repository for managing signal entities and time-series data."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc

from ..db.models import Signal, SignalContrib
from ..db.session import get_db_session_readonly
from ..models.dto import SignalContribDTO, SignalDTO
from .base import BaseRepository


class SignalRepository(BaseRepository[Signal]):
    """Repository for Signal entities with time-series functionality."""

    def __init__(self):
        super().__init__(Signal)

    def insert(self, points: List[SignalDTO]) -> List[int]:
        """Bulk insert signal points."""
        if not points:
            return []

        with self._transaction_with_retry() as session:
            signal_objects = []
            for dto in points:
                signal = Signal(
                    ticker=dto.ticker,
                    ts=dto.ts,
                    sentiment=dto.sentiment,
                    novelty=dto.novelty,
                    velocity=dto.velocity,
                    event_tags=dto.event_tags,
                    score=dto.score,
                )
                signal_objects.append(signal)

            session.add_all(signal_objects)
            session.flush()

            # Return the IDs of created signals
            return [signal.id for signal in signal_objects]

    def get_signals_by_ticker(
        self,
        ticker: str,
        start_ts: Optional[datetime] = None,
        end_ts: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[Signal]:
        """Get signals for a specific ticker within a time range."""
        with get_db_session_readonly() as session:
            query = session.query(Signal).filter(Signal.ticker == ticker)

            if start_ts:
                query = query.filter(Signal.ts >= start_ts)
            if end_ts:
                query = query.filter(Signal.ts <= end_ts)

            return query.order_by(desc(Signal.ts)).limit(limit).all()

    def get_latest_signal(self, ticker: str) -> Optional[Signal]:
        """Get the latest signal for a ticker."""
        with get_db_session_readonly() as session:
            return (
                session.query(Signal)
                .filter(Signal.ticker == ticker)
                .order_by(desc(Signal.ts))
                .first()
            )

    def get_signals_by_score_threshold(
        self, threshold: float, limit: int = 100
    ) -> List[Signal]:
        """Get signals above a certain score threshold."""
        with get_db_session_readonly() as session:
            return (
                session.query(Signal)
                .filter(Signal.score >= threshold)
                .order_by(desc(Signal.score))
                .limit(limit)
                .all()
            )

    def get_signals_by_event_tags(
        self, event_tags: List[str], limit: int = 100
    ) -> List[Signal]:
        """Get signals containing specific event tags."""
        with get_db_session_readonly() as session:
            query = session.query(Signal)
            for tag in event_tags:
                query = query.filter(Signal.event_tags.contains([tag]))

            return query.order_by(desc(Signal.ts)).limit(limit).all()

    def get_signal_with_contributions(self, signal_id: int) -> Optional[Dict[str, Any]]:
        """Get signal with its contributing articles."""
        with get_db_session_readonly() as session:
            signal = session.query(Signal).filter(Signal.id == signal_id).first()
            if not signal:
                return None

            contributions = (
                session.query(SignalContrib)
                .filter(SignalContrib.signal_id == signal_id)
                .order_by(SignalContrib.rank)
                .all()
            )

            return {"signal": signal, "contributions": contributions}

    def add_signal_contribution(self, dto: SignalContribDTO) -> SignalContrib:
        """Add a contribution to a signal."""
        with self._transaction_with_retry() as session:
            contrib = SignalContrib(
                signal_id=dto.signal_id, article_id=dto.article_id, rank=dto.rank
            )
            session.add(contrib)
            session.flush()
            return contrib

    def get_signal_contributions(self, signal_id: int) -> List[SignalContrib]:
        """Get all contributions for a signal."""
        with get_db_session_readonly() as session:
            return (
                session.query(SignalContrib)
                .filter(SignalContrib.signal_id == signal_id)
                .order_by(SignalContrib.rank)
                .all()
            )

    def get_signals_by_time_range(
        self,
        start_ts: datetime,
        end_ts: datetime,
        tickers: Optional[List[str]] = None,
        limit: int = 1000,
    ) -> List[Signal]:
        """Get signals within a time range, optionally filtered by tickers."""
        with get_db_session_readonly() as session:
            query = session.query(Signal).filter(
                and_(Signal.ts >= start_ts, Signal.ts <= end_ts)
            )

            if tickers:
                query = query.filter(Signal.ticker.in_(tickers))

            return query.order_by(desc(Signal.ts)).limit(limit).all()

    def get_signal_stats(self, ticker: Optional[str] = None) -> Dict[str, Any]:
        """Get signal statistics."""
        with get_db_session_readonly() as session:
            query = session.query(Signal)

            if ticker:
                query = query.filter(Signal.ticker == ticker)

            total_count = query.count()

            # Get average scores
            avg_sentiment = session.query(
                session.query(Signal.sentiment)
                .filter(Signal.sentiment.isnot(None))
                .subquery()
                .columns[0]
                .avg()
            ).scalar()

            avg_novelty = session.query(
                session.query(Signal.novelty)
                .filter(Signal.novelty.isnot(None))
                .subquery()
                .columns[0]
                .avg()
            ).scalar()

            avg_velocity = session.query(
                session.query(Signal.velocity)
                .filter(Signal.velocity.isnot(None))
                .subquery()
                .columns[0]
                .avg()
            ).scalar()

            return {
                "total_signals": total_count,
                "avg_sentiment": avg_sentiment,
                "avg_novelty": avg_novelty,
                "avg_velocity": avg_velocity,
            }

    def delete_signals_by_ticker(self, ticker: str) -> int:
        """Delete all signals for a specific ticker."""
        with self._transaction_with_retry() as session:
            result = session.query(Signal).filter(Signal.ticker == ticker).delete()
            return result

    def delete_signals_by_time_range(self, start_ts: datetime, end_ts: datetime) -> int:
        """Delete signals within a time range."""
        with self._transaction_with_retry() as session:
            result = (
                session.query(Signal)
                .filter(and_(Signal.ts >= start_ts, Signal.ts <= end_ts))
                .delete()
            )
            return result
