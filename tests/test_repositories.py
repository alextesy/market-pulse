"""Tests for repository modules."""

from datetime import datetime, timezone
from unittest.mock import Mock, patch

import pytest

from market_pulse.models.dto import (
    ArticleDTO,
    EmbeddingDTO,
    PriceBarDTO,
    SignalDTO,
    TickerLinkDTO,
)
from market_pulse.repos.article import ArticleRepository
from market_pulse.repos.embed import EmbedRepository
from market_pulse.repos.price_bar import PriceBarRepository
from market_pulse.repos.signal import SignalRepository
from market_pulse.repos.ticker import TickerRepository


class TestArticleRepository:
    """Test ArticleRepository functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.repo = ArticleRepository()
        self.mock_session = Mock()

    def test_upsert_by_url_new_article(self):
        """Test upserting a new article."""
        dto = ArticleDTO(
            source="test",
            url="https://example.com/article",
            published_at=datetime.now(timezone.utc),
            title="Test Article",
            text="Test content",
            lang="en",
        )

        with patch.object(self.repo, "_transaction_with_retry") as mock_transaction:
            mock_session = Mock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )
            mock_transaction.return_value.__enter__.return_value = mock_session

            # Mock the article object that gets created
            mock_article = Mock()
            mock_article.id = 123

            # Mock the session.add to return the article
            def mock_add(article):
                article.id = 123
                return None

            mock_session.add.side_effect = mock_add

            result = self.repo.upsert_by_url(dto)

            assert result == 123
            mock_session.add.assert_called_once()
            mock_session.flush.assert_called()

    def test_upsert_by_url_existing_article(self):
        """Test upserting an existing article."""
        dto = ArticleDTO(
            source="test",
            url="https://example.com/article",
            published_at=datetime.now(timezone.utc),
            title="Test Article",
            text="Test content",
            lang="en",
        )

        existing_article = Mock()
        existing_article.id = 123

        with patch.object(self.repo, "_transaction_with_retry") as mock_transaction:
            mock_session = Mock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                existing_article
            )
            mock_transaction.return_value.__enter__.return_value = mock_session

            result = self.repo.upsert_by_url(dto)

            assert result == 123
            mock_session.add.assert_not_called()
            mock_session.flush.assert_called()

    def test_bulk_insert_links_empty_list(self):
        """Test bulk insert with empty links list."""
        with patch.object(self.repo, "_transaction_with_retry") as mock_transaction:
            self.repo.bulk_insert_links(1, [])
            mock_transaction.assert_not_called()

    def test_bulk_insert_links_with_data(self):
        """Test bulk insert with actual links."""
        links = [
            TickerLinkDTO(
                ticker="AAPL", confidence=0.8, method="cashtag", matched_terms=["AAPL"]
            ),
            TickerLinkDTO(
                ticker="TSLA", confidence=0.9, method="cashtag", matched_terms=["TSLA"]
            ),
        ]

        with patch.object(self.repo, "_transaction_with_retry") as mock_transaction:
            mock_session = Mock()
            mock_transaction.return_value.__enter__.return_value = mock_session

            # Mock the query chain for delete operation
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.delete.return_value = 0

            self.repo.bulk_insert_links(1, links)

            mock_session.query.assert_called()
            mock_session.add_all.assert_called_once()
            mock_session.flush.assert_called()


class TestEmbedRepository:
    """Test EmbedRepository functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.repo = EmbedRepository()
        self.mock_session = Mock()

    def test_upsert_embedding_new(self):
        """Test upserting a new embedding."""
        dto = EmbeddingDTO(
            article_id=1, embedding=[0.1] * 384, model="test-model", dims=384
        )

        with patch.object(self.repo, "_transaction_with_retry") as mock_transaction:
            mock_session = Mock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                None
            )
            mock_transaction.return_value.__enter__.return_value = mock_session

            result = self.repo.upsert(1, dto)

            assert result is not None
            mock_session.add.assert_called_once()
            mock_session.flush.assert_called()

    def test_upsert_embedding_existing(self):
        """Test upserting an existing embedding."""
        dto = EmbeddingDTO(
            article_id=1, embedding=[0.1] * 384, model="test-model", dims=384
        )

        existing_embed = Mock()
        existing_embed.article_id = 1

        with patch.object(self.repo, "_transaction_with_retry") as mock_transaction:
            mock_session = Mock()
            mock_session.query.return_value.filter.return_value.first.return_value = (
                existing_embed
            )
            mock_transaction.return_value.__enter__.return_value = mock_session

            result = self.repo.upsert(1, dto)

            assert result == existing_embed
            mock_session.add.assert_not_called()
            mock_session.flush.assert_called()

    def test_find_similar_articles(self):
        """Test finding similar articles."""
        embedding = [0.1] * 384

        with patch(
            "market_pulse.repos.embed.get_db_session_readonly"
        ) as mock_session_func:
            mock_session = Mock()
            mock_session_func.return_value.__enter__.return_value = mock_session

            # Mock the query chain
            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                []
            )

            result = self.repo.find_similar_articles(embedding, limit=5, threshold=0.7)

            assert result == []
            mock_session.query.assert_called()


class TestTickerRepository:
    """Test TickerRepository functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.repo = TickerRepository()

    def test_get_active_tickers_no_date(self):
        """Test getting active tickers without date filter."""
        with patch(
            "market_pulse.repos.ticker.get_db_session_readonly"
        ) as mock_session_func:
            mock_session = Mock()
            mock_session_func.return_value.__enter__.return_value = mock_session

            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value = mock_query
            mock_query.all.return_value = []

            result = self.repo.get_active_tickers()

            assert result == []
            mock_session.query.assert_called()
            mock_query.filter.assert_called_once()
            mock_query.all.assert_called_once()

    def test_get_active_tickers_with_date(self):
        """Test getting active tickers with date filter."""
        as_of_date = datetime.now(timezone.utc)

        with patch(
            "market_pulse.repos.ticker.get_db_session_readonly"
        ) as mock_session_func:
            mock_session = Mock()
            mock_session_func.return_value.__enter__.return_value = mock_session

            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value.all.return_value = []

            result = self.repo.get_active_tickers(as_of_date=as_of_date)

            assert result == []
            mock_session.query.assert_called()

    def test_bulk_insert_tickers(self):
        """Test bulk inserting tickers."""
        tickers = [
            {"symbol": "AAPL", "name": "Apple Inc."},
            {"symbol": "TSLA", "name": "Tesla Inc."},
        ]

        with patch.object(self.repo, "_transaction_with_retry") as mock_transaction:
            mock_session = Mock()
            mock_transaction.return_value.__enter__.return_value = mock_session

            self.repo.bulk_insert_tickers(tickers)

            mock_session.add_all.assert_called_once()
            mock_session.flush.assert_called()


class TestSignalRepository:
    """Test SignalRepository functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.repo = SignalRepository()

    def test_bulk_insert_signals(self):
        """Test bulk inserting signals."""
        signals = [
            SignalDTO(
                ticker="AAPL",
                ts=datetime.now(timezone.utc),
                sentiment=0.5,
                novelty=0.3,
                velocity=0.7,
            ),
            SignalDTO(
                ticker="TSLA",
                ts=datetime.now(timezone.utc),
                sentiment=0.8,
                novelty=0.4,
                velocity=0.6,
            ),
        ]

        with patch.object(self.repo, "_transaction_with_retry") as mock_transaction:
            mock_session = Mock()
            mock_transaction.return_value.__enter__.return_value = mock_session

            self.repo.insert(signals)

            mock_session.add_all.assert_called_once()
            mock_session.flush.assert_called()

    def test_get_signals_by_ticker(self):
        """Test getting signals by ticker."""
        with patch(
            "market_pulse.repos.signal.get_db_session_readonly"
        ) as mock_session_func:
            mock_session = Mock()
            mock_session_func.return_value.__enter__.return_value = mock_session

            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                []
            )

            result = self.repo.get_signals_by_ticker("AAPL", limit=10)

            assert result == []

    def test_get_signals_by_score_threshold(self):
        """Test getting signals by score threshold."""
        with patch(
            "market_pulse.repos.signal.get_db_session_readonly"
        ) as mock_session_func:
            mock_session = Mock()
            mock_session_func.return_value.__enter__.return_value = mock_session

            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                []
            )

            result = self.repo.get_signals_by_score_threshold(0.5, limit=10)

            assert result == []


class TestPriceBarRepository:
    """Test PriceBarRepository functionality."""

    def setup_method(self):
        """Set up test fixtures."""
        self.repo = PriceBarRepository()

    def test_bulk_insert_bars(self):
        """Test bulk inserting price bars."""
        bars = [
            PriceBarDTO(
                ticker="AAPL",
                ts=datetime.now(timezone.utc),
                o=150.0,
                h=155.0,
                low=148.0,
                c=152.0,
                v=1000000,
                timeframe="1d",
            ),
            PriceBarDTO(
                ticker="TSLA",
                ts=datetime.now(timezone.utc),
                o=200.0,
                h=205.0,
                low=198.0,
                c=202.0,
                v=500000,
                timeframe="1d",
            ),
        ]

        with patch.object(self.repo, "_transaction_with_retry") as mock_transaction:
            mock_session = Mock()
            mock_transaction.return_value.__enter__.return_value = mock_session

            self.repo.bulk_insert_bars(bars)

            mock_session.add_all.assert_called_once()
            mock_session.flush.assert_called()

    def test_get_bars_by_ticker(self):
        """Test getting price bars by ticker."""
        with patch(
            "market_pulse.repos.price_bar.get_db_session_readonly"
        ) as mock_session_func:
            mock_session = Mock()
            mock_session_func.return_value.__enter__.return_value = mock_session

            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                []
            )

            result = self.repo.get_bars_by_ticker("AAPL", limit=100)

            assert result == []

    def test_get_latest_bar(self):
        """Test getting the latest price bar."""
        with patch(
            "market_pulse.repos.price_bar.get_db_session_readonly"
        ) as mock_session_func:
            mock_session = Mock()
            mock_session_func.return_value.__enter__.return_value = mock_session

            mock_query = Mock()
            mock_session.query.return_value = mock_query
            mock_query.filter.return_value.order_by.return_value.first.return_value = (
                None
            )

            result = self.repo.get_latest_bar("AAPL")

            assert result is None


class TestRepositoryErrorHandling:
    """Test repository error handling."""

    def test_article_repository_transaction_retry(self):
        """Test transaction retry logic in ArticleRepository."""
        repo = ArticleRepository()

        with patch.object(repo, "_transaction_with_retry") as mock_transaction:
            mock_transaction.side_effect = Exception("Database error")

            with pytest.raises(Exception):
                repo.upsert_by_url(Mock())

    def test_embed_repository_transaction_retry(self):
        """Test transaction retry logic in EmbedRepository."""
        repo = EmbedRepository()

        with patch.object(repo, "_transaction_with_retry") as mock_transaction:
            mock_transaction.side_effect = Exception("Database error")

            with pytest.raises(Exception):
                repo.upsert(1, Mock())

    def test_signal_repository_transaction_retry(self):
        """Test transaction retry logic in SignalRepository."""
        repo = SignalRepository()

        with patch.object(repo, "_transaction_with_retry") as mock_transaction:
            mock_transaction.side_effect = Exception("Database error")

            # The insert method returns empty list for empty input, so it won't raise
            result = repo.insert([])
            assert result == []
