"""Integration tests for repositories."""

from datetime import datetime, timedelta, timezone

import pytest

from market_pulse.db import create_tables, drop_tables, test_connection
from market_pulse.models.dto import (
    ArticleDTO,
    EmbeddingDTO,
    PriceBarDTO,
    SignalContribDTO,
    SignalDTO,
    TickerLinkDTO,
)
from market_pulse.repos import (
    ArticleRepository,
    EmbedRepository,
    PriceBarRepository,
    SignalRepository,
    TickerRepository,
)


@pytest.fixture(scope="module")
def setup_database():
    """Set up test database."""
    if not test_connection():
        pytest.skip("Database connection not available")

    # Create tables
    create_tables()
    yield
    # Clean up
    drop_tables()


@pytest.fixture
def article_repo():
    return ArticleRepository()


@pytest.fixture
def embed_repo():
    return EmbedRepository()


@pytest.fixture
def ticker_repo():
    return TickerRepository()


@pytest.fixture
def signal_repo():
    return SignalRepository()


@pytest.fixture
def price_bar_repo():
    return PriceBarRepository()


class TestArticleRepository:
    """Test ArticleRepository functionality."""

    def test_upsert_by_url_idempotency(self, setup_database, article_repo):
        """Test that upsert is idempotent."""
        # Create test article
        article_dto = ArticleDTO(
            source="test",
            url="https://example.com/test1",
            published_at=datetime.now(timezone.utc),
            title="Test Article",
            text="Test content",
            lang="en",
            credibility=80.0,
        )

        # First insert
        article_id1 = article_repo.upsert_by_url(article_dto)
        assert article_id1 > 0

        # Second insert with same URL should return same ID
        article_id2 = article_repo.upsert_by_url(article_dto)
        assert article_id2 == article_id1

        # Verify article exists
        article = article_repo.get_by_id(article_id1)
        assert article is not None
        assert article.url == article_dto.url
        assert article.title == article_dto.title

    def test_bulk_insert_links(self, setup_database, article_repo):
        """Test bulk insert of article-ticker links."""
        # Create test article
        article_dto = ArticleDTO(
            source="test",
            url="https://example.com/test2",
            published_at=datetime.now(timezone.utc),
            title="Test Article 2",
            text="Test content",
            lang="en",
        )
        article_id = article_repo.upsert_by_url(article_dto)

        # Create test links
        links = [
            TickerLinkDTO(
                ticker="AAPL",
                confidence=0.9,
                method="cashtag",
                matched_terms=["AAPL", "Apple"],
            ),
            TickerLinkDTO(
                ticker="GOOGL", confidence=0.7, method="dict", matched_terms=["Google"]
            ),
        ]

        # Insert links
        article_repo.bulk_insert_links(article_id, links)

        # Verify links were created
        article_with_tickers = article_repo.get_article_with_tickers(article_id)
        assert article_with_tickers is not None
        assert len(article_with_tickers["tickers"]) == 2

        ticker_symbols = [t.ticker for t in article_with_tickers["tickers"]]
        assert "AAPL" in ticker_symbols
        assert "GOOGL" in ticker_symbols


class TestEmbedRepository:
    """Test EmbedRepository functionality."""

    def test_upsert_embedding(self, setup_database, embed_repo, article_repo):
        """Test embedding upsert functionality."""
        # Create test article first
        article_dto = ArticleDTO(
            source="test",
            url="https://example.com/test3",
            published_at=datetime.now(timezone.utc),
            title="Test Article 3",
            text="Test content",
            lang="en",
        )
        article_id = article_repo.upsert_by_url(article_dto)

        # Create test embedding
        embedding_dto = EmbeddingDTO(
            article_id=article_id,
            embedding=[0.1] * 384,  # 384-dimensional vector
            model="MiniLM-L6-v2",
            dims=384,
        )

        # Insert embedding
        embed = embed_repo.upsert(article_id, embedding_dto)
        assert embed.article_id == article_id
        assert len(embed.embedding) == 384
        assert embed.model == "MiniLM-L6-v2"

        # Test idempotency
        embed2 = embed_repo.upsert(article_id, embedding_dto)
        assert embed2.article_id == article_id

    def test_vector_similarity_search(self, setup_database, embed_repo, article_repo):
        """Test vector similarity search functionality."""
        # Create test articles and embeddings
        embeddings = []
        for i in range(3):
            article_dto = ArticleDTO(
                source="test",
                url=f"https://example.com/test{i+4}",
                published_at=datetime.now(timezone.utc),
                title=f"Test Article {i+4}",
                text=f"Test content {i+4}",
                lang="en",
            )
            article_id = article_repo.upsert_by_url(article_dto)

            # Create similar embeddings
            embedding_dto = EmbeddingDTO(
                article_id=article_id,
                embedding=[0.1 + i * 0.1] * 384,
                model="MiniLM-L6-v2",
                dims=384,
            )
            embed_repo.upsert(article_id, embedding_dto)
            embeddings.append(embedding_dto.embedding)

        # Test similarity search
        query_embedding = [0.1] * 384
        similar = embed_repo.find_similar_articles(
            query_embedding, limit=5, threshold=0.5
        )

        # Should find at least one similar article
        assert len(similar) > 0


class TestTickerRepository:
    """Test TickerRepository functionality."""

    def test_alias_mapping(self, setup_database, ticker_repo):
        """Test ticker alias mapping functionality."""
        # Create test tickers with aliases
        tickers_data = [
            {
                "symbol": "AAPL",
                "name": "Apple Inc.",
                "exchange": "NASDAQ",
                "aliases": {"aliases": ["Apple", "AAPL", "Apple Inc"]},
            },
            {
                "symbol": "GOOGL",
                "name": "Alphabet Inc.",
                "exchange": "NASDAQ",
                "aliases": {"aliases": ["Google", "GOOGL", "Alphabet"]},
            },
        ]

        ticker_repo.bulk_insert_tickers(tickers_data)

        # Test alias mapping
        alias_map = ticker_repo.get_alias_map()
        assert "AAPL" in alias_map
        assert "GOOGL" in alias_map
        assert "Apple" in alias_map["AAPL"]
        assert "Google" in alias_map["GOOGL"]

        # Test finding by alias
        ticker = ticker_repo.find_by_alias("Apple")
        assert ticker is not None
        assert ticker.symbol == "AAPL"

    def test_active_tickers(self, setup_database, ticker_repo):
        """Test active ticker filtering."""
        # Create test tickers with validity dates
        now = datetime.now()
        tickers_data = [
            {
                "symbol": "ACTIVE1",
                "name": "Active Ticker 1",
                "valid_from": now.date(),
                "valid_to": None,
            },
            {
                "symbol": "EXPIRED1",
                "name": "Expired Ticker 1",
                "valid_from": (now - timedelta(days=30)).date(),
                "valid_to": (now - timedelta(days=1)).date(),
            },
        ]

        ticker_repo.bulk_insert_tickers(tickers_data)

        # Test active tickers
        active_tickers = ticker_repo.get_active_tickers()
        active_symbols = [t.symbol for t in active_tickers]
        assert "ACTIVE1" in active_symbols
        assert "EXPIRED1" not in active_symbols


class TestSignalRepository:
    """Test SignalRepository functionality."""

    def test_bulk_insert_signals(self, setup_database, signal_repo):
        """Test bulk insert of signal points."""
        # Create test signals
        now = datetime.now(timezone.utc)
        signals = [
            SignalDTO(
                ticker="AAPL",
                ts=now,
                sentiment=0.8,
                novelty=0.6,
                velocity=0.7,
                event_tags=["earnings", "positive"],
                score=0.75,
            ),
            SignalDTO(
                ticker="GOOGL",
                ts=now + timedelta(hours=1),
                sentiment=0.6,
                novelty=0.8,
                velocity=0.5,
                event_tags=["product_launch"],
                score=0.65,
            ),
        ]

        # Insert signals
        signal_ids = signal_repo.insert(signals)
        assert len(signal_ids) == 2
        assert all(sid > 0 for sid in signal_ids)

        # Verify signals were created
        for signal_id in signal_ids:
            signal = signal_repo.get_by_id(signal_id)
            assert signal is not None
            assert signal.ticker in ["AAPL", "GOOGL"]

    def test_signal_contributions(self, setup_database, signal_repo, article_repo):
        """Test signal contribution functionality."""
        # Create test article
        article_dto = ArticleDTO(
            source="test",
            url="https://example.com/test5",
            published_at=datetime.now(timezone.utc),
            title="Test Article 5",
            text="Test content",
            lang="en",
        )
        article_id = article_repo.upsert_by_url(article_dto)

        # Create test signal
        signal_dto = SignalDTO(
            ticker="AAPL",
            ts=datetime.now(timezone.utc),
            sentiment=0.8,
            novelty=0.6,
            velocity=0.7,
            score=0.75,
        )
        signal_ids = signal_repo.insert([signal_dto])
        signal_id = signal_ids[0]

        # Add contribution
        contrib_dto = SignalContribDTO(
            signal_id=signal_id, article_id=article_id, rank=1
        )
        contrib = signal_repo.add_signal_contribution(contrib_dto)
        assert contrib.signal_id == signal_id
        assert contrib.article_id == article_id

        # Verify contribution
        contributions = signal_repo.get_signal_contributions(signal_id)
        assert len(contributions) == 1
        assert contributions[0].article_id == article_id


class TestPriceBarRepository:
    """Test PriceBarRepository functionality."""

    def test_bulk_insert_bars(self, setup_database, price_bar_repo):
        """Test bulk insert of price bars."""
        # Create test price bars
        now = datetime.now(timezone.utc)
        bars = [
            PriceBarDTO(
                ticker="AAPL",
                ts=now,
                o=150.0,
                h=155.0,
                l=149.0,
                c=153.0,
                v=1000000,
                timeframe="1d",
            ),
            PriceBarDTO(
                ticker="AAPL",
                ts=now + timedelta(days=1),
                o=153.0,
                h=157.0,
                l=152.0,
                c=156.0,
                v=1200000,
                timeframe="1d",
            ),
        ]

        # Insert bars
        price_bar_repo.bulk_insert_bars(bars)

        # Verify bars were created
        created_bars = price_bar_repo.get_bars_by_ticker("AAPL", timeframe="1d")
        assert len(created_bars) == 2

        # Verify latest bar
        latest_bar = price_bar_repo.get_latest_bar("AAPL", "1d")
        assert latest_bar is not None
        assert latest_bar.c == 156.0

    def test_ohlcv_data(self, setup_database, price_bar_repo):
        """Test OHLCV data retrieval."""
        # Create test price bars
        now = datetime.now(timezone.utc)
        bars = [
            PriceBarDTO(
                ticker="GOOGL",
                ts=now,
                o=2800.0,
                h=2850.0,
                l=2790.0,
                c=2830.0,
                v=500000,
                timeframe="1d",
            )
        ]

        price_bar_repo.bulk_insert_bars(bars)

        # Get OHLCV data
        ohlcv_data = price_bar_repo.get_ohlcv_data(
            "GOOGL", now - timedelta(days=1), now + timedelta(days=1), "1d"
        )

        assert len(ohlcv_data) == 1
        data_point = ohlcv_data[0]
        assert data_point["open"] == 2800.0
        assert data_point["high"] == 2850.0
        assert data_point["low"] == 2790.0
        assert data_point["close"] == 2830.0
        assert data_point["volume"] == 500000


class TestFKConstraints:
    """Test foreign key constraints and cascades."""

    def test_article_cascade_delete(self, setup_database, article_repo, embed_repo):
        """Test that deleting an article cascades to related data."""
        # Create test article
        article_dto = ArticleDTO(
            source="test",
            url="https://example.com/test6",
            published_at=datetime.now(timezone.utc),
            title="Test Article 6",
            text="Test content",
            lang="en",
        )
        article_id = article_repo.upsert_by_url(article_dto)

        # Create embedding for article
        embedding_dto = EmbeddingDTO(
            article_id=article_id, embedding=[0.1] * 384, model="MiniLM-L6-v2", dims=384
        )
        embed_repo.upsert(article_id, embedding_dto)

        # Verify embedding exists
        embed = embed_repo.get_by_article_id(article_id)
        assert embed is not None

        # Delete article
        article = article_repo.get_by_id(article_id)
        article_repo.delete(article)

        # Verify embedding was cascaded
        embed = embed_repo.get_by_article_id(article_id)
        assert embed is None

    def test_signal_cascade_delete(self, setup_database, signal_repo, article_repo):
        """Test that deleting a signal cascades to contributions."""
        # Create test article and signal
        article_dto = ArticleDTO(
            source="test",
            url="https://example.com/test7",
            published_at=datetime.now(timezone.utc),
            title="Test Article 7",
            text="Test content",
            lang="en",
        )
        article_id = article_repo.upsert_by_url(article_dto)

        signal_dto = SignalDTO(
            ticker="AAPL", ts=datetime.now(timezone.utc), sentiment=0.8, score=0.75
        )
        signal_ids = signal_repo.insert([signal_dto])
        signal_id = signal_ids[0]

        # Add contribution
        contrib_dto = SignalContribDTO(
            signal_id=signal_id, article_id=article_id, rank=1
        )
        signal_repo.add_signal_contribution(contrib_dto)

        # Verify contribution exists
        contributions = signal_repo.get_signal_contributions(signal_id)
        assert len(contributions) == 1

        # Delete signal
        signal = signal_repo.get_by_id(signal_id)
        signal_repo.delete(signal)

        # Verify contribution was cascaded
        contributions = signal_repo.get_signal_contributions(signal_id)
        assert len(contributions) == 0
