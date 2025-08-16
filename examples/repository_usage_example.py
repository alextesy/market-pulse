"""Example usage of Market Pulse repositories."""

import os
from datetime import datetime, timezone, timedelta
from typing import List

from market_pulse.db import create_tables, test_connection
from market_pulse.repos import (
    ArticleRepository, EmbedRepository, TickerRepository,
    SignalRepository, PriceBarRepository
)
from market_pulse.models.dto import (
    ArticleDTO, EmbeddingDTO, TickerLinkDTO, SignalDTO,
    PriceBarDTO
)


def main():
    """Demonstrate repository usage."""
    
    # Check database connection
    if not test_connection():
        print("Database connection not available. Please set POSTGRES_URL environment variable.")
        return
    
    # Create tables
    create_tables()
    print("Database tables created successfully.")
    
    # Initialize repositories
    article_repo = ArticleRepository()
    embed_repo = EmbedRepository()
    ticker_repo = TickerRepository()
    signal_repo = SignalRepository()
    price_bar_repo = PriceBarRepository()
    
    # Example 1: Insert tickers with aliases
    print("\n1. Creating tickers with aliases...")
    tickers_data = [
        {
            "symbol": "AAPL",
            "name": "Apple Inc.",
            "exchange": "NASDAQ",
            "aliases": {"aliases": ["Apple", "AAPL", "Apple Inc"]}
        },
        {
            "symbol": "GOOGL",
            "name": "Alphabet Inc.",
            "exchange": "NASDAQ",
            "aliases": {"aliases": ["Google", "GOOGL", "Alphabet"]}
        }
    ]
    ticker_repo.bulk_insert_tickers(tickers_data)
    print("Tickers created successfully.")
    
    # Example 2: Upsert article by URL
    print("\n2. Upserting article by URL...")
    article_dto = ArticleDTO(
        source="gdelt",
        url="https://example.com/apple-earnings",
        published_at=datetime.now(timezone.utc),
        title="Apple Reports Strong Q4 Earnings",
        text="Apple Inc. reported better-than-expected earnings for Q4...",
        lang="en",
        credibility=85.0
    )
    article_id = article_repo.upsert_by_url(article_dto)
    print(f"Article created with ID: {article_id}")
    
    # Example 3: Add article-ticker links
    print("\n3. Adding article-ticker links...")
    links = [
        TickerLinkDTO(
            ticker="AAPL",
            confidence=0.95,
            method="cashtag",
            matched_terms=["AAPL", "Apple"]
        )
    ]
    article_repo.bulk_insert_links(article_id, links)
    print("Article-ticker links created successfully.")
    
    # Example 4: Store article embedding
    print("\n4. Storing article embedding...")
    embedding_dto = EmbeddingDTO(
        article_id=article_id,
        embedding=[0.1] * 384,  # 384-dimensional vector
        model="MiniLM-L6-v2",
        dims=384
    )
    embed_repo.upsert(article_id, embedding_dto)
    print("Article embedding stored successfully.")
    
    # Example 5: Create signal
    print("\n5. Creating market signal...")
    signal_dto = SignalDTO(
        ticker="AAPL",
        ts=datetime.now(timezone.utc),
        sentiment=0.8,
        novelty=0.6,
        velocity=0.7,
        event_tags=["earnings", "positive"],
        score=0.75
    )
    signal_ids = signal_repo.insert([signal_dto])
    print(f"Signal created with ID: {signal_ids[0]}")
    
    # Example 6: Add price bars
    print("\n6. Adding price bars...")
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
            timeframe="1d"
        ),
        PriceBarDTO(
            ticker="AAPL",
            ts=now + timedelta(days=1),
            o=153.0,
            h=157.0,
            l=152.0,
            c=156.0,
            v=1200000,
            timeframe="1d"
        )
    ]
    price_bar_repo.bulk_insert_bars(bars)
    print("Price bars added successfully.")
    
    # Example 7: Query recent embeddings for ticker
    print("\n7. Querying recent embeddings for AAPL...")
    since_ts = datetime.now(timezone.utc) - timedelta(days=1)
    recent_embeddings = embed_repo.get_recent_embeddings_for_ticker("AAPL", since_ts, limit=10)
    print(f"Found {len(recent_embeddings)} recent embeddings for AAPL")
    
    # Example 8: Get ticker alias map
    print("\n8. Getting ticker alias map...")
    alias_map = ticker_repo.get_alias_map()
    print("Ticker aliases:")
    for symbol, aliases in alias_map.items():
        print(f"  {symbol}: {aliases}")
    
    # Example 9: Get latest signal for ticker
    print("\n9. Getting latest signal for AAPL...")
    latest_signal = signal_repo.get_latest_signal("AAPL")
    if latest_signal:
        print(f"Latest signal score: {latest_signal.score}")
        print(f"Latest signal sentiment: {latest_signal.sentiment}")
    
    # Example 10: Get OHLCV data
    print("\n10. Getting OHLCV data for AAPL...")
    ohlcv_data = price_bar_repo.get_ohlcv_data(
        "AAPL",
        now - timedelta(days=2),
        now + timedelta(days=1),
        "1d"
    )
    print(f"Found {len(ohlcv_data)} price bars")
    for bar in ohlcv_data:
        print(f"  {bar['timestamp']}: O={bar['open']}, H={bar['high']}, L={bar['low']}, C={bar['close']}, V={bar['volume']}")
    
    print("\nRepository usage example completed successfully!")


if __name__ == "__main__":
    main()
