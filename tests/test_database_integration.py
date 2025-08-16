"""Test database integration with our DTOs."""

import pytest
from datetime import datetime, timezone
from market_pulse.models.dto import (
    ArticleDTO,
    ArticleTickerDTO,
    EmbeddingDTO,
    SignalDTO,
    PriceBarDTO,
)
from market_pulse.models.mappers import ingest_item_to_article
from market_pulse.models.dto import IngestItem


class TestDatabaseSchemaAlignment:
    """Test that our DTOs align with the database schema."""
    
    def test_article_dto_to_dict(self):
        """Test ArticleDTO can be converted to dict for DB insert."""
        article = ArticleDTO(
            source='gdelt',
            url='https://example.com/article',
            published_at=datetime.now(timezone.utc),
            title='Test Article',
            text='Test content',
            lang='en',
            hash='abc123',
            credibility=75.5
        )
        
        # Convert to dict (simulating DB insert)
        article_dict = article.model_dump()
        
        # Verify all required fields are present
        required_fields = ['source', 'url', 'published_at', 'title', 'text', 'lang', 'hash', 'credibility']
        for field in required_fields:
            assert field in article_dict
        
        # Verify data types match schema
        assert isinstance(article_dict['source'], str)
        assert isinstance(article_dict['url'], str)
        assert isinstance(article_dict['published_at'], datetime)
        assert isinstance(article_dict['title'], str)
        assert isinstance(article_dict['text'], str)
        assert isinstance(article_dict['lang'], str)
        assert isinstance(article_dict['hash'], str)
        assert isinstance(article_dict['credibility'], float)
    
    def test_article_ticker_dto_to_dict(self):
        """Test ArticleTickerDTO can be converted to dict for DB insert."""
        article_ticker = ArticleTickerDTO(
            article_id=1,
            ticker='AAPL',
            confidence=0.85
        )
        
        article_ticker_dict = article_ticker.model_dump()
        
        # Verify all required fields are present
        required_fields = ['article_id', 'ticker', 'confidence']
        for field in required_fields:
            assert field in article_ticker_dict
        
        # Verify data types match schema
        assert isinstance(article_ticker_dict['article_id'], int)
        assert isinstance(article_ticker_dict['ticker'], str)
        assert isinstance(article_ticker_dict['confidence'], float)
    
    def test_embedding_dto_to_dict(self):
        """Test EmbeddingDTO can be converted to dict for DB insert."""
        embedding = [0.1] * 384  # 384 dimensions
        embedding_dto = EmbeddingDTO(
            article_id=1,
            embedding=embedding
        )
        
        embedding_dict = embedding_dto.model_dump()
        
        # Verify all required fields are present
        required_fields = ['article_id', 'embedding']
        for field in required_fields:
            assert field in embedding_dict
        
        # Verify data types match schema
        assert isinstance(embedding_dict['article_id'], int)
        assert isinstance(embedding_dict['embedding'], list)
        assert len(embedding_dict['embedding']) == 384
        assert all(isinstance(x, float) for x in embedding_dict['embedding'])
    
    def test_signal_dto_to_dict(self):
        """Test SignalDTO can be converted to dict for DB insert."""
        signal = SignalDTO(
            ticker='AAPL',
            ts=datetime.now(timezone.utc),
            sentiment=0.5,
            novelty=0.3,
            velocity=0.8,
            event_tags=['earnings', 'guidance'],
            score=0.7
        )
        
        signal_dict = signal.model_dump()
        
        # Verify all required fields are present
        required_fields = ['ticker', 'ts', 'sentiment', 'novelty', 'velocity', 'event_tags', 'score']
        for field in required_fields:
            assert field in signal_dict
        
        # Verify data types match schema
        assert isinstance(signal_dict['ticker'], str)
        assert isinstance(signal_dict['ts'], datetime)
        assert isinstance(signal_dict['sentiment'], float)
        assert isinstance(signal_dict['novelty'], float)
        assert isinstance(signal_dict['velocity'], float)
        assert isinstance(signal_dict['event_tags'], list)
        assert isinstance(signal_dict['score'], float)
    
    def test_price_bar_dto_to_dict(self):
        """Test PriceBarDTO can be converted to dict for DB insert."""
        price_bar = PriceBarDTO(
            ticker='AAPL',
            ts=datetime.now(timezone.utc),
            o=150.0,
            h=155.0,
            l=148.0,
            c=152.0,
            v=1000000,
            timeframe='1d'
        )
        
        price_bar_dict = price_bar.model_dump()
        
        # Verify all required fields are present
        required_fields = ['ticker', 'ts', 'o', 'h', 'l', 'c', 'v', 'timeframe']
        for field in required_fields:
            assert field in price_bar_dict
        
        # Verify data types match schema
        assert isinstance(price_bar_dict['ticker'], str)
        assert isinstance(price_bar_dict['ts'], datetime)
        assert isinstance(price_bar_dict['o'], float)
        assert isinstance(price_bar_dict['h'], float)
        assert isinstance(price_bar_dict['l'], float)
        assert isinstance(price_bar_dict['c'], float)
        assert isinstance(price_bar_dict['v'], int)
        assert isinstance(price_bar_dict['timeframe'], str)
    
    def test_complete_workflow(self):
        """Test complete workflow from IngestItem to database-ready dicts."""
        # Create IngestItem
        ingest_item = IngestItem(
            source='gdelt',
            url='https://example.com/article?utm_source=google',
            published_at=datetime.now(timezone.utc),
            retrieved_at=datetime.now(timezone.utc),
            title='<h1>Test Article</h1>',
            text='<p>Test content</p>',
            lang='en'
        )
        
        # Transform to ArticleDTO
        article = ingest_item_to_article(ingest_item)
        article_dict = article.model_dump()
        
        # Create related DTOs
        article_ticker = ArticleTickerDTO(
            article_id=1,  # Would be the actual article ID from DB
            ticker='AAPL',
            confidence=0.85
        )
        article_ticker_dict = article_ticker.model_dump()
        
        embedding = EmbeddingDTO(
            article_id=1,
            embedding=[0.1] * 384
        )
        embedding_dict = embedding.model_dump()
        
        # Verify all dicts are ready for database insertion
        assert 'source' in article_dict
        assert 'url' in article_dict
        assert 'article_id' in article_ticker_dict
        assert 'ticker' in article_ticker_dict
        assert 'article_id' in embedding_dict
        assert 'embedding' in embedding_dict
        
        # Verify data has been properly transformed
        assert article_dict['url'] == 'https://example.com/article'  # UTM removed
        assert article_dict['title'] == 'Test Article'  # HTML removed
        assert article_dict['text'] == 'Test content'  # HTML removed
        assert article_dict['hash'] is not None
        assert article_dict['credibility'] is not None
