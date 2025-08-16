"""Tests for improved validation and tightened DTOs."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from market_pulse.models.dto import (
    ArticleTickerDTO,
    EmbeddingDTO,
    IngestItem,
    PriceBarDTO,
    SentimentDTO,
    SignalContribDTO,
    SignalDTO,
    TickerLinkDTO,
)
from market_pulse.models.mappers import (
    create_signal_contribution,
    ensure_timezone_aware,
    ticker_link_to_article_ticker,
)


class TestTimezoneAwareness:
    """Test timezone awareness validation."""

    def test_timezone_aware_datetime_valid(self):
        """Test valid timezone-aware datetime."""
        dt = datetime.now(timezone.utc)
        item = IngestItem(
            source="gdelt",
            url="https://example.com/article",
            published_at=dt,
            retrieved_at=dt,
            title="Test Article",
            text="Test content",
            lang="en",
        )
        assert item.published_at.tzinfo is not None
        assert item.retrieved_at.tzinfo is not None

    def test_timezone_naive_datetime_invalid(self):
        """Test timezone-naive datetime raises error."""
        dt = datetime.now()  # No timezone info

        with pytest.raises(ValidationError, match="datetime must be timezone-aware"):
            IngestItem(
                source="gdelt",
                url="https://example.com/article",
                published_at=dt,
                retrieved_at=dt,
                title="Test Article",
                text="Test content",
                lang="en",
            )

    def test_timezone_normalization_to_utc(self):
        """Test datetime normalization to UTC."""
        # Create datetime in different timezone
        from datetime import timedelta

        est = timezone(timedelta(hours=-5))
        dt_est = datetime.now(est)

        item = IngestItem(
            source="gdelt",
            url="https://example.com/article",
            published_at=dt_est,
            retrieved_at=dt_est,
            title="Test Article",
            text="Test content",
            lang="en",
        )

        # Should be normalized to UTC
        assert item.published_at.tzinfo == timezone.utc
        assert item.retrieved_at.tzinfo == timezone.utc


class TestTickerStrTypeAlias:
    """Test TickerStr type alias validation."""

    def test_valid_ticker_formats(self):
        """Test valid ticker formats."""
        valid_tickers = ["AAPL", "TSLA", "BRK.A", "BRK-B", "A", "A" * 10]

        for ticker in valid_tickers:
            # Test in ArticleTickerDTO
            dto = ArticleTickerDTO(article_id=1, ticker=ticker, confidence=0.8)
            assert dto.ticker == ticker

    def test_invalid_ticker_formats(self):
        """Test invalid ticker formats."""
        invalid_tickers = [
            "aapl",  # lowercase
            "AAPL!",  # special char
            "A" * 11,  # too long
            "AAPL@",  # invalid char
            "AAPL#",  # invalid char
            "AAPL$",  # invalid char
        ]

        for ticker in invalid_tickers:
            try:
                ArticleTickerDTO(article_id=1, ticker=ticker, confidence=0.8)
                # If we get here, the ticker was accepted when it shouldn't be
                pytest.fail(
                    f"Ticker '{ticker}' should have been rejected but was accepted"
                )
            except ValidationError:
                # This is expected
                pass


class TestArticleTickerDTOImprovements:
    """Test ArticleTickerDTO improvements."""

    def test_article_ticker_with_method_and_terms(self):
        """Test ArticleTickerDTO with method and matched_terms."""
        dto = ArticleTickerDTO(
            article_id=1,
            ticker="AAPL",
            confidence=0.95,
            method="cashtag",
            matched_terms=["AAPL", "Apple"],
        )

        assert dto.article_id == 1
        assert dto.ticker == "AAPL"
        assert dto.confidence == 0.95
        assert dto.method == "cashtag"
        assert dto.matched_terms == ["AAPL", "Apple"]

    def test_ticker_link_to_article_ticker_with_new_fields(self):
        """Test ticker_link_to_article_ticker with new fields."""
        ticker_link = TickerLinkDTO(
            ticker="AAPL",
            confidence=0.95,
            method="cashtag",
            matched_terms=["AAPL", "Apple"],
            char_spans=[(0, 4), (10, 15)],
        )

        article_ticker = ticker_link_to_article_ticker(ticker_link, article_id=1)

        assert article_ticker.article_id == 1
        assert article_ticker.ticker == "AAPL"
        assert article_ticker.confidence == 0.95
        assert article_ticker.method == "cashtag"
        assert article_ticker.matched_terms == ["AAPL", "Apple"]


class TestSentimentDTOImprovements:
    """Test SentimentDTO probability sum validation."""

    def test_valid_probability_sum(self):
        """Test valid probability sum."""
        sentiment = SentimentDTO(
            prob_pos=0.7,
            prob_neg=0.2,
            prob_neu=0.1,
            score=0.5,
            model="bert-base",
            model_rev="v1.0",
        )

        assert sentiment.prob_pos == 0.7
        assert sentiment.prob_neg == 0.2
        assert sentiment.prob_neu == 0.1
        assert sentiment.score == 0.5

    def test_invalid_probability_sum(self):
        """Test invalid probability sum raises error."""
        with pytest.raises(ValidationError, match="probabilities must sum to 1.0"):
            SentimentDTO(
                prob_pos=0.8,
                prob_neg=0.3,  # Sum = 1.1
                prob_neu=0.1,
                score=0.5,
                model="bert-base",
                model_rev="v1.0",
            )

    def test_probability_sum_with_floating_point_error(self):
        """Test probability sum with small floating point errors."""
        # This should work due to epsilon tolerance
        sentiment = SentimentDTO(
            prob_pos=0.3333333333333333,
            prob_neg=0.3333333333333333,
            prob_neu=0.3333333333333334,  # Slightly different due to FP precision
            score=0.0,
            model="bert-base",
            model_rev="v1.0",
        )

        total = sentiment.prob_pos + sentiment.prob_neg + sentiment.prob_neu
        assert abs(total - 1.0) < 0.01  # Within epsilon


class TestEmbeddingDTOImprovements:
    """Test EmbeddingDTO dimension validation."""

    def test_valid_embedding_with_matching_dims(self):
        """Test valid embedding with matching dimensions."""
        embedding = [0.1] * 384
        dto = EmbeddingDTO(article_id=1, embedding=embedding, dims=384)

        assert dto.article_id == 1
        assert len(dto.embedding) == 384
        assert dto.dims == 384

    def test_embedding_dims_mismatch(self):
        """Test embedding dimension mismatch raises error."""
        embedding = [0.1] * 384

        with pytest.raises(ValidationError, match="dims.*must match embedding length"):
            EmbeddingDTO(article_id=1, embedding=embedding, dims=512)  # Mismatch

    def test_embedding_length_validation(self):
        """Test embedding length validation."""
        embedding = [0.1] * 100  # Wrong length

        with pytest.raises(ValidationError):
            EmbeddingDTO(article_id=1, embedding=embedding)


class TestSignalContribDTO:
    """Test new SignalContribDTO."""

    def test_valid_signal_contribution(self):
        """Test valid SignalContribDTO."""
        dto = SignalContribDTO(signal_id=1, article_id=123, rank=1)

        assert dto.signal_id == 1
        assert dto.article_id == 123
        assert dto.rank == 1

    def test_invalid_rank(self):
        """Test invalid rank raises error."""
        with pytest.raises(ValidationError):
            SignalContribDTO(
                signal_id=1, article_id=123, rank=0  # Invalid - must be positive
            )

    def test_create_signal_contribution_utility(self):
        """Test create_signal_contribution utility function."""
        dto = create_signal_contribution(signal_id=1, article_id=123, rank=1)

        assert isinstance(dto, SignalContribDTO)
        assert dto.signal_id == 1
        assert dto.article_id == 123
        assert dto.rank == 1


class TestSignalDTOImprovements:
    """Test SignalDTO improvements."""

    def test_signal_with_timezone_aware_ts(self):
        """Test SignalDTO with timezone-aware timestamp."""
        ts = datetime.now(timezone.utc)
        signal = SignalDTO(
            ticker="AAPL",
            ts=ts,
            sentiment=0.5,
            novelty=0.3,
            velocity=0.8,
            event_tags=["earnings"],
            score=0.7,
        )

        assert signal.ticker == "AAPL"
        assert signal.ts.tzinfo == timezone.utc
        assert signal.sentiment == 0.5

    def test_signal_with_timezone_naive_ts(self):
        """Test SignalDTO with timezone-naive timestamp raises error."""
        ts = datetime.now()  # No timezone

        with pytest.raises(ValidationError, match="datetime must be timezone-aware"):
            SignalDTO(ticker="AAPL", ts=ts, sentiment=0.5)


class TestPriceBarDTOImprovements:
    """Test PriceBarDTO improvements."""

    def test_price_bar_with_timezone_aware_ts(self):
        """Test PriceBarDTO with timezone-aware timestamp."""
        ts = datetime.now(timezone.utc)
        price_bar = PriceBarDTO(
            ticker="AAPL",
            ts=ts,
            o=150.0,
            h=155.0,
            l=148.0,
            c=152.0,
            v=1000000,
            timeframe="1d",
        )

        assert price_bar.ticker == "AAPL"
        assert price_bar.ts.tzinfo == timezone.utc
        assert price_bar.o == 150.0

    def test_price_bar_with_timezone_naive_ts(self):
        """Test PriceBarDTO with timezone-naive timestamp raises error."""
        ts = datetime.now()  # No timezone

        with pytest.raises(ValidationError, match="datetime must be timezone-aware"):
            PriceBarDTO(ticker="AAPL", ts=ts, timeframe="1d")


class TestUtilityFunctions:
    """Test utility functions."""

    def test_ensure_timezone_aware(self):
        """Test ensure_timezone_aware utility."""
        # Test with timezone-naive datetime
        naive_dt = datetime.now()
        aware_dt = ensure_timezone_aware(naive_dt)
        assert aware_dt.tzinfo == timezone.utc

        # Test with timezone-aware datetime
        from datetime import timedelta

        est = timezone(timedelta(hours=-5))
        est_dt = datetime.now(est)
        utc_dt = ensure_timezone_aware(est_dt)
        assert utc_dt.tzinfo == timezone.utc
