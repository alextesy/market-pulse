"""Tests for Pydantic DTOs and mapping utilities."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from market_pulse.models.dto import (
    ArticleDTO,
    EmbeddingDTO,
    IngestItem,
    PriceBarDTO,
    SentimentDTO,
    SignalDTO,
    TickerLinkDTO,
)
from market_pulse.models.mappers import (
    calculate_credibility,
    canonicalize_url,
    clean_text,
    generate_article_hash,
    ingest_item_to_article,
    ticker_link_to_article_ticker,
    validate_ticker_format,
)


class TestIngestItem:
    """Test IngestItem DTO."""

    def test_valid_ingest_item(self):
        """Test valid IngestItem creation."""
        item = IngestItem(
            source="gdelt",
            source_id="test123",
            url="https://example.com/article",
            published_at=datetime.now(timezone.utc),
            retrieved_at=datetime.now(timezone.utc),
            title="Test Article",
            text="This is a test article content.",
            lang="en",
            license="CC-BY",
            author="Test Author",
            meta={"key": "value"},
        )

        assert item.source == "gdelt"
        assert item.source_id == "test123"
        assert str(item.url) == "https://example.com/article"
        assert item.title == "Test Article"
        assert item.text == "This is a test article content."
        assert item.lang == "en"
        assert item.license == "CC-BY"
        assert item.author == "Test Author"
        assert item.meta == {"key": "value"}

    def test_invalid_source(self):
        """Test invalid source raises error."""
        with pytest.raises(ValidationError):
            IngestItem(
                source="invalid_source",
                url="https://example.com/article",
                published_at=datetime.now(timezone.utc),
                retrieved_at=datetime.now(timezone.utc),
                title="Test Article",
                text="This is a test article content.",
                lang="en",
            )

    def test_title_length_validation(self):
        """Test title max length validation."""
        long_title = "A" * 513  # Exceeds 512 limit

        with pytest.raises(ValidationError):
            IngestItem(
                source="gdelt",
                url="https://example.com/article",
                published_at=datetime.now(timezone.utc),
                retrieved_at=datetime.now(timezone.utc),
                title=long_title,
                text="This is a test article content.",
                lang="en",
            )

    def test_text_length_validation(self):
        """Test text max length validation."""
        long_text = "A" * 20001  # Exceeds 20000 limit

        with pytest.raises(ValidationError):
            IngestItem(
                source="gdelt",
                url="https://example.com/article",
                published_at=datetime.now(timezone.utc),
                retrieved_at=datetime.now(timezone.utc),
                title="Test Article",
                text=long_text,
                lang="en",
            )


class TestArticleDTO:
    """Test ArticleDTO."""

    def test_valid_article_dto(self):
        """Test valid ArticleDTO creation."""
        article = ArticleDTO(
            source="gdelt",
            url="https://example.com/article",
            published_at=datetime.now(timezone.utc),
            title="Test Article",
            text="This is a test article content.",
            lang="en",
            hash="abc123",
            credibility=75.5,
        )

        assert article.source == "gdelt"
        assert article.url == "https://example.com/article"
        assert article.title == "Test Article"
        assert article.credibility == 75.5

    def test_credibility_validation(self):
        """Test credibility score validation."""
        # Test valid range
        article = ArticleDTO(
            source="gdelt",
            url="https://example.com/article",
            published_at=datetime.now(timezone.utc),
            credibility=50.0,
        )
        assert article.credibility == 50.0

        # Test out of range
        with pytest.raises(ValidationError):
            ArticleDTO(
                source="gdelt",
                url="https://example.com/article",
                published_at=datetime.now(timezone.utc),
                credibility=150.0,
            )


class TestTickerLinkDTO:
    """Test TickerLinkDTO."""

    def test_valid_ticker_link(self):
        """Test valid TickerLinkDTO creation."""
        link = TickerLinkDTO(
            ticker="AAPL",
            confidence=0.85,
            method="cashtag",
            matched_terms=["AAPL", "Apple"],
            char_spans=[(0, 4), (10, 15)],
        )

        assert link.ticker == "AAPL"
        assert link.confidence == 0.85
        assert link.method == "cashtag"
        assert link.matched_terms == ["AAPL", "Apple"]
        assert link.char_spans == [(0, 4), (10, 15)]

    def test_invalid_ticker_format(self):
        """Test invalid ticker format."""
        with pytest.raises(ValidationError):
            TickerLinkDTO(
                ticker="invalid-ticker!",
                confidence=0.85,
                method="cashtag",
                matched_terms=["AAPL"],
            )

    def test_confidence_validation(self):
        """Test confidence score validation."""
        with pytest.raises(ValidationError):
            TickerLinkDTO(
                ticker="AAPL",
                confidence=1.5,  # Exceeds 1.0
                method="cashtag",
                matched_terms=["AAPL"],
            )


class TestSentimentDTO:
    """Test SentimentDTO."""

    def test_valid_sentiment(self):
        """Test valid SentimentDTO creation."""
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

    def test_probability_validation(self):
        """Test probability validation."""
        with pytest.raises(ValidationError):
            SentimentDTO(
                prob_pos=1.5,  # Exceeds 1.0
                prob_neg=0.2,
                prob_neu=0.1,
                score=0.5,
                model="bert-base",
                model_rev="v1.0",
            )


class TestEmbeddingDTO:
    """Test EmbeddingDTO."""

    def test_valid_embedding(self):
        """Test valid EmbeddingDTO creation."""
        embedding = [0.1] * 384  # 384 dimensions
        dto = EmbeddingDTO(article_id=1, embedding=embedding)

        assert dto.article_id == 1
        assert len(dto.embedding) == 384
        assert dto.model == "MiniLM-L6-v2"
        assert dto.dims == 384

    def test_invalid_embedding_length(self):
        """Test invalid embedding length."""
        embedding = [0.1] * 100  # Wrong dimension

        with pytest.raises(ValidationError):
            EmbeddingDTO(article_id=1, embedding=embedding)


class TestSignalDTO:
    """Test SignalDTO."""

    def test_valid_signal(self):
        """Test valid SignalDTO creation."""
        signal = SignalDTO(
            ticker="AAPL",
            ts=datetime.now(timezone.utc),
            sentiment=0.5,
            novelty=0.3,
            velocity=0.8,
            event_tags=["earnings", "guidance"],
            score=0.7,
            contributors=[1, 2],
        )

        assert signal.ticker == "AAPL"
        assert signal.sentiment == 0.5
        assert signal.event_tags == ["earnings", "guidance"]
        assert signal.contributors == [1, 2]

    def test_contributors_limit(self):
        """Test contributors list limit."""
        with pytest.raises(ValidationError):
            SignalDTO(
                ticker="AAPL",
                ts=datetime.now(timezone.utc),
                contributors=[1, 2, 3],  # Exceeds limit of 2
            )


class TestPriceBarDTO:
    """Test PriceBarDTO."""

    def test_valid_price_bar(self):
        """Test valid PriceBarDTO creation."""
        price_bar = PriceBarDTO(
            ticker="AAPL",
            ts=datetime.now(timezone.utc),
            o=150.0,
            h=155.0,
            l=148.0,
            c=152.0,
            v=1000000,
            timeframe="1d",
        )

        assert price_bar.ticker == "AAPL"
        assert price_bar.o == 150.0
        assert price_bar.h == 155.0
        assert price_bar.l == 148.0
        assert price_bar.c == 152.0
        assert price_bar.v == 1000000
        assert price_bar.timeframe == "1d"

    def test_negative_price_validation(self):
        """Test negative price validation."""
        with pytest.raises(ValidationError):
            PriceBarDTO(
                ticker="AAPL",
                ts=datetime.now(timezone.utc),
                o=-150.0,  # Negative price
                timeframe="1d",
            )

    def test_negative_volume_validation(self):
        """Test negative volume validation."""
        with pytest.raises(ValidationError):
            PriceBarDTO(
                ticker="AAPL",
                ts=datetime.now(timezone.utc),
                v=-1000,  # Negative volume
                timeframe="1d",
            )


class TestMappingUtilities:
    """Test mapping utility functions."""

    def test_canonicalize_url(self):
        """Test URL canonicalization."""
        # Test UTM parameter removal
        url_with_utm = (
            "https://example.com/article?utm_source=google&utm_medium=cpc&param=value"
        )
        canonical = canonicalize_url(url_with_utm)
        assert canonical == "https://example.com/article?param=value"

        # Test anchor removal
        url_with_anchor = "https://example.com/article#section1"
        canonical = canonicalize_url(url_with_anchor)
        assert canonical == "https://example.com/article"

        # Test both
        url_complex = "https://example.com/article?utm_source=google#section1"
        canonical = canonicalize_url(url_complex)
        assert canonical == "https://example.com/article"

    def test_clean_text(self):
        """Test text cleaning."""
        # Test HTML removal
        html_text = "<p>This is <b>bold</b> text</p>"
        cleaned = clean_text(html_text)
        assert cleaned == "This is bold text"

        # Test HTML entity unescaping
        entity_text = "Apple &amp; Microsoft"
        cleaned = clean_text(entity_text)
        assert cleaned == "Apple & Microsoft"

        # Test whitespace normalization
        whitespace_text = "  Multiple    spaces  "
        cleaned = clean_text(whitespace_text)
        assert cleaned == "Multiple spaces"

    def test_generate_article_hash(self):
        """Test article hash generation."""
        title = "Test Article"
        url = "https://example.com/article"
        hash_value = generate_article_hash(title, url)

        assert len(hash_value) == 40  # SHA1 hex length
        assert isinstance(hash_value, str)

        # Same title and host should produce same hash
        hash_value2 = generate_article_hash(title, "https://example.com/different-path")
        assert hash_value == hash_value2

    def test_calculate_credibility(self):
        """Test credibility calculation."""
        item = IngestItem(
            source="sec",
            url="https://sec.gov/filing",
            published_at=datetime.now(timezone.utc),
            retrieved_at=datetime.now(timezone.utc),
            title="SEC Filing",
            text="Important filing content",
            lang="en",
            author="SEC",
            license="Public Domain",
        )

        credibility = calculate_credibility(item)
        assert credibility is not None
        assert 0 <= credibility <= 100
        assert credibility >= 90  # SEC should be high credibility

    def test_ingest_item_to_article(self):
        """Test IngestItem to ArticleDTO mapping."""
        item = IngestItem(
            source="gdelt",
            url="https://example.com/article?utm_source=google",
            published_at=datetime.now(timezone.utc),
            retrieved_at=datetime.now(timezone.utc),
            title="<p>Test Article</p>",
            text="<div>Test content</div>",
            lang="en",
        )

        article = ingest_item_to_article(item)

        assert article.source == "gdelt"
        assert article.url == "https://example.com/article"  # UTM removed
        assert article.title == "Test Article"  # HTML removed
        assert article.text == "Test content"  # HTML removed
        assert article.lang == "en"
        assert article.hash is not None
        assert article.credibility is not None

    def test_ticker_link_to_article_ticker(self):
        """Test TickerLinkDTO to ArticleTickerDTO mapping."""
        link = TickerLinkDTO(
            ticker="AAPL", confidence=0.85, method="cashtag", matched_terms=["AAPL"]
        )

        article_ticker = ticker_link_to_article_ticker(link, article_id=1)

        assert article_ticker.article_id == 1
        assert article_ticker.ticker == "AAPL"
        assert article_ticker.confidence == 0.85

    def test_validate_ticker_format(self):
        """Test ticker format validation."""
        assert validate_ticker_format("AAPL") is True
        assert validate_ticker_format("TSLA") is True
        assert validate_ticker_format("BRK.A") is True
        assert validate_ticker_format("BRK-B") is True

        assert validate_ticker_format("invalid") is False
        assert validate_ticker_format("AAPL!") is False
        assert validate_ticker_format("aapl") is False
        assert validate_ticker_format("A") is True  # Single char valid
        assert validate_ticker_format("A" * 11) is False  # Too long


class TestModelSerialization:
    """Test model serialization and deserialization."""

    def test_ingest_item_round_trip(self):
        """Test IngestItem JSON round-trip."""
        item = IngestItem(
            source="gdelt",
            url="https://example.com/article",
            published_at=datetime.now(timezone.utc),
            retrieved_at=datetime.now(timezone.utc),
            title="Test Article",
            text="Test content",
            lang="en",
        )

        # Serialize to dict
        data = item.model_dump()

        # Deserialize back to model
        item2 = IngestItem(**data)

        assert item.source == item2.source
        assert str(item.url) == str(item2.url)
        assert item.title == item2.title
        assert item.text == item2.text
        assert item.lang == item2.lang

    def test_article_dto_round_trip(self):
        """Test ArticleDTO JSON round-trip."""
        article = ArticleDTO(
            source="gdelt",
            url="https://example.com/article",
            published_at=datetime.now(timezone.utc),
            title="Test Article",
            text="Test content",
            lang="en",
            hash="abc123",
            credibility=75.5,
        )

        # Serialize to dict
        data = article.model_dump()

        # Deserialize back to model
        article2 = ArticleDTO(**data)

        assert article.source == article2.source
        assert article.url == article2.url
        assert article.title == article2.title
        assert article.credibility == article2.credibility
