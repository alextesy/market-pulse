"""Ticker repository for managing ticker entities and aliases."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, text

from ..db.models import ArticleTicker, Ticker
from ..db.session import get_db_session_readonly
from .base import BaseRepository


class TickerRepository(BaseRepository[Ticker]):
    """Repository for Ticker entities with alias management."""

    def __init__(self):
        super().__init__(Ticker)

    def get_by_symbol(self, symbol: str) -> Optional[Ticker]:
        """Get ticker by symbol."""
        with get_db_session_readonly() as session:
            return session.query(Ticker).filter(Ticker.symbol == symbol).first()

    def get_active_tickers(self, as_of_date: Optional[datetime] = None) -> List[Ticker]:
        """Get active tickers (not expired)."""
        with get_db_session_readonly() as session:
            query = session.query(Ticker)

            if as_of_date:
                query = query.filter(
                    and_(
                        (
                            Ticker.valid_from.is_(None)
                            | (Ticker.valid_from <= as_of_date)
                        ),
                        (Ticker.valid_to.is_(None) | (Ticker.valid_to > as_of_date)),
                    )
                )
            else:
                query = query.filter(Ticker.valid_to.is_(None))

            return query.all()

    def get_alias_map(self) -> Dict[str, List[str]]:
        """Get mapping of ticker symbols to their aliases."""
        with get_db_session_readonly() as session:
            tickers = session.query(Ticker).filter(Ticker.aliases.isnot(None)).all()

            alias_map = {}
            for ticker in tickers:
                if ticker.aliases:
                    alias_map[ticker.symbol] = ticker.aliases.get("aliases", [])

            return alias_map

    def find_by_alias(self, alias: str) -> Optional[Ticker]:
        """Find ticker by alias."""
        with get_db_session_readonly() as session:
            # Search in aliases JSONB field
            tickers = (
                session.query(Ticker)
                .filter(Ticker.aliases.contains({"aliases": [alias]}))
                .all()
            )

            return tickers[0] if tickers else None

    def get_tickers_by_exchange(self, exchange: str) -> List[Ticker]:
        """Get tickers by exchange."""
        with get_db_session_readonly() as session:
            return session.query(Ticker).filter(Ticker.exchange == exchange).all()

    def get_tickers_by_cik(self, cik: str) -> List[Ticker]:
        """Get tickers by CIK."""
        with get_db_session_readonly() as session:
            return session.query(Ticker).filter(Ticker.cik == cik).all()

    def get_tickers_with_articles(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get tickers with article counts."""
        with get_db_session_readonly() as session:
            result = (
                session.query(
                    Ticker,
                    session.query(ArticleTicker)
                    .filter(ArticleTicker.ticker == Ticker.symbol)
                    .count()
                    .label("article_count"),
                )
                .filter(
                    session.query(ArticleTicker)
                    .filter(ArticleTicker.ticker == Ticker.symbol)
                    .exists()
                )
                .order_by(text("article_count DESC"))
                .limit(limit)
                .all()
            )

            return [
                {"ticker": ticker, "article_count": count} for ticker, count in result
            ]

    def bulk_insert_tickers(self, tickers: List[Dict[str, Any]]) -> None:
        """Bulk insert tickers."""
        if not tickers:
            return

        with self._transaction_with_retry() as session:
            ticker_objects = []
            for ticker_data in tickers:
                ticker = Ticker(
                    symbol=ticker_data["symbol"],
                    name=ticker_data.get("name"),
                    exchange=ticker_data.get("exchange"),
                    cik=ticker_data.get("cik"),
                    aliases=ticker_data.get("aliases"),
                    valid_from=ticker_data.get("valid_from"),
                    valid_to=ticker_data.get("valid_to"),
                )
                ticker_objects.append(ticker)

            session.add_all(ticker_objects)
            session.flush()

    def update_ticker(self, symbol: str, **updates) -> Optional[Ticker]:
        """Update ticker by symbol."""
        with self._transaction_with_retry() as session:
            ticker = session.query(Ticker).filter(Ticker.symbol == symbol).first()
            if not ticker:
                return None

            for field, value in updates.items():
                if hasattr(ticker, field):
                    setattr(ticker, field, value)

            session.flush()
            return ticker

    def add_alias(self, symbol: str, alias: str) -> bool:
        """Add an alias to a ticker."""
        with self._transaction_with_retry() as session:
            ticker = session.query(Ticker).filter(Ticker.symbol == symbol).first()
            if not ticker:
                return False

            if ticker.aliases is None:
                ticker.aliases = {"aliases": []}

            if alias not in ticker.aliases.get("aliases", []):
                ticker.aliases["aliases"].append(alias)

            session.flush()
            return True

    def remove_alias(self, symbol: str, alias: str) -> bool:
        """Remove an alias from a ticker."""
        with self._transaction_with_retry() as session:
            ticker = session.query(Ticker).filter(Ticker.symbol == symbol).first()
            if not ticker or not ticker.aliases:
                return False

            aliases = ticker.aliases.get("aliases", [])
            if alias in aliases:
                aliases.remove(alias)
                session.flush()
                return True

            return False

    def get_ticker_stats(self) -> Dict[str, Any]:
        """Get ticker statistics."""
        with get_db_session_readonly() as session:
            total_count = session.query(Ticker).count()
            exchange_counts = (
                session.query(
                    Ticker.exchange,
                    session.query(Ticker)
                    .filter(Ticker.exchange == Ticker.exchange)
                    .count(),
                )
                .filter(Ticker.exchange.isnot(None))
                .distinct()
                .all()
            )

            return {"total_tickers": total_count, "by_exchange": dict(exchange_counts)}
