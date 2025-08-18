"""SQLAlchemy 2.0 ORM models for Market Pulse."""

from datetime import datetime
from typing import List, Optional

from pgvector.sqlalchemy import Vector as VECTOR
from sqlalchemy import (
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all models."""

    pass


class Ticker(Base):
    """Ticker table with symbol as primary key."""

    __tablename__ = "ticker"

    symbol: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(Text)
    exchange: Mapped[Optional[str]] = mapped_column(Text)
    cik: Mapped[Optional[str]] = mapped_column(Text)
    aliases: Mapped[Optional[dict]] = mapped_column(JSONB)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # Relationships
    articles: Mapped[List["ArticleTicker"]] = relationship(back_populates="ticker_rel")
    price_bars: Mapped[List["PriceBar"]] = relationship(back_populates="ticker_rel")
    signals: Mapped[List["Signal"]] = relationship(back_populates="ticker_rel")


class Article(Base):
    """Article table with BIGSERIAL primary key."""

    __tablename__ = "article"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[Optional[str]] = mapped_column(Text, unique=True)
    published_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(Text)
    text: Mapped[Optional[str]] = mapped_column(Text)
    lang: Mapped[Optional[str]] = mapped_column(Text)
    hash: Mapped[Optional[str]] = mapped_column(Text)
    credibility: Mapped[Optional[float]] = mapped_column(Float)

    # Relationships
    tickers: Mapped[List["ArticleTicker"]] = relationship(
        back_populates="article_rel", cascade="all, delete-orphan"
    )
    embedding: Mapped[Optional["ArticleEmbed"]] = relationship(
        back_populates="article_rel", cascade="all, delete-orphan"
    )
    signal_contributions: Mapped[List["SignalContrib"]] = relationship(
        back_populates="article_rel"
    )


class ArticleEmbed(Base):
    """Article embedding table with vector support."""

    __tablename__ = "article_embed"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("article.id", ondelete="CASCADE")
    )
    embedding: Mapped[List[float]] = mapped_column(VECTOR(384), nullable=False)

    # Relationships
    article_rel: Mapped["Article"] = relationship(back_populates="embedding")

    # Index for vector similarity search
    __table_args__ = (
        Index(
            "article_embed_embedding_idx",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class ArticleTicker(Base):
    """Article-ticker relationship table."""

    __tablename__ = "article_ticker"

    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("article.id", ondelete="CASCADE"), primary_key=True
    )
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("ticker.symbol"), primary_key=True
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    method: Mapped[Optional[str]] = mapped_column(Text)
    matched_terms: Mapped[Optional[dict]] = mapped_column(JSONB)

    # Relationships
    article_rel: Mapped["Article"] = relationship(back_populates="tickers")
    ticker_rel: Mapped["Ticker"] = relationship(back_populates="articles")

    # Index for ticker lookups
    __table_args__ = (Index("idx_article_ticker_ticker", "ticker"),)


class PriceBar(Base):
    """Price bar table with TimescaleDB hypertable support."""

    __tablename__ = "price_bar"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("ticker.symbol"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    o: Mapped[Optional[float]] = mapped_column(Float)
    h: Mapped[Optional[float]] = mapped_column(Float)
    l: Mapped[Optional[float]] = mapped_column(Float)
    c: Mapped[Optional[float]] = mapped_column(Float)
    v: Mapped[Optional[int]] = mapped_column(BigInteger)
    timeframe: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    ticker_rel: Mapped["Ticker"] = relationship(back_populates="price_bars")

    # Index for time-series queries
    __table_args__ = (
        Index("idx_price_bar_ticker_ts", "ticker", "ts", postgresql_ops={"ts": "DESC"}),
    )


class Signal(Base):
    """Signal table with TimescaleDB hypertable support."""

    __tablename__ = "signal"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(
        String(10), ForeignKey("ticker.symbol"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    sentiment: Mapped[Optional[float]] = mapped_column(Float)
    novelty: Mapped[Optional[float]] = mapped_column(Float)
    velocity: Mapped[Optional[float]] = mapped_column(Float)
    event_tags: Mapped[Optional[List[str]]] = mapped_column(ARRAY(Text))
    score: Mapped[Optional[float]] = mapped_column(Float)

    # Relationships
    ticker_rel: Mapped["Ticker"] = relationship(back_populates="signals")

    # Index for time-series queries
    __table_args__ = (
        Index("idx_signal_ticker_ts", "ticker", "ts", postgresql_ops={"ts": "DESC"}),
    )


class SignalContrib(Base):
    """Signal contribution table linking signals to articles."""

    __tablename__ = "signal_contrib"

    signal_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    signal_ts: Mapped[datetime] = mapped_column(DateTime, primary_key=True)
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("article.id", ondelete="CASCADE"), primary_key=True
    )
    rank: Mapped[Optional[int]] = mapped_column(SmallInteger)

    # Relationships - simplified to avoid complex composite foreign key issues
    article_rel: Mapped["Article"] = relationship(back_populates="signal_contributions")
