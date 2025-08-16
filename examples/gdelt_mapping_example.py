"""Example: Mapping GDELT JSON data to Market Pulse DTOs."""

import json
from datetime import datetime

from market_pulse.models.dto import IngestItem
from market_pulse.models.mappers import ingest_item_to_article


def create_sample_gdelt_data() -> dict:
    """Create sample GDELT JSON data."""
    return {
        "source": "gdelt",
        "source_id": "20231201120000-1234567890",
        "url": "https://www.reuters.com/business/finance/apple-stock-rises-earnings-beat-expectations?utm_source=google&utm_medium=cpc#section1",
        "published_at": "2023-12-01T12:00:00Z",
        "retrieved_at": "2023-12-01T12:05:00Z",
        "title": "<h1>Apple Stock Rises After Earnings Beat Expectations</h1>",
        "text": "<p>Apple Inc. (AAPL) reported quarterly earnings that exceeded analyst expectations, sending the stock higher in after-hours trading.</p><p>The company reported earnings per share of $1.29, beating the consensus estimate of $1.27.</p>",
        "lang": "EN",
        "license": "Reuters",
        "author": "Reuters Staff",
        "meta": {
            "gdelt_event_id": "1234567890",
            "goldstein_scale": 0.8,
            "num_mentions": 15,
            "num_sources": 8,
            "num_articles": 12,
        },
    }


def map_gdelt_to_ingest_item(gdelt_data: dict) -> IngestItem:
    """Map GDELT JSON data to IngestItem."""
    # Parse datetime strings
    published_at = datetime.fromisoformat(
        gdelt_data["published_at"].replace("Z", "+00:00")
    )
    retrieved_at = datetime.fromisoformat(
        gdelt_data["retrieved_at"].replace("Z", "+00:00")
    )

    return IngestItem(
        source=gdelt_data["source"],
        source_id=gdelt_data["source_id"],
        url=gdelt_data["url"],
        published_at=published_at,
        retrieved_at=retrieved_at,
        title=gdelt_data["title"],
        text=gdelt_data["text"],
        lang=gdelt_data["lang"].lower(),
        license=gdelt_data.get("license"),
        author=gdelt_data.get("author"),
        meta=gdelt_data.get("meta", {}),
    )


def main():
    """Demonstrate the complete mapping workflow."""
    print("=== GDELT to Market Pulse DTO Mapping Example ===\n")

    # Create sample GDELT data
    gdelt_data = create_sample_gdelt_data()
    print("1. Sample GDELT JSON data:")
    print(json.dumps(gdelt_data, indent=2))
    print()

    # Map to IngestItem
    ingest_item = map_gdelt_to_ingest_item(gdelt_data)
    print("2. Mapped to IngestItem:")
    print(f"   Source: {ingest_item.source}")
    print(f"   URL: {ingest_item.url}")
    print(f"   Title: {ingest_item.title}")
    print(f"   Text: {ingest_item.text[:100]}...")
    print(f"   Language: {ingest_item.lang}")
    print(f"   Author: {ingest_item.author}")
    print(f"   Meta keys: {list(ingest_item.meta.keys())}")
    print()

    # Transform to ArticleDTO
    article = ingest_item_to_article(ingest_item)
    print("3. Transformed to ArticleDTO (ready for DB):")
    print(f"   Source: {article.source}")
    print(f"   Canonical URL: {article.url}")  # UTM params and anchor removed
    print(f"   Clean Title: {article.title}")  # HTML removed
    print(f"   Clean Text: {article.text[:100]}...")  # HTML removed
    print(f"   Language: {article.lang}")
    print(f"   Hash: {article.hash}")
    print(f"   Credibility: {article.credibility}")
    print()

    # Show the transformation effects
    print("4. Transformation Effects:")
    print(f"   Original URL: {gdelt_data['url']}")
    print(f"   Canonical URL: {article.url}")
    print(f"   Original Title: {gdelt_data['title']}")
    print(f"   Clean Title: {article.title}")
    print(f"   Original Text: {gdelt_data['text'][:50]}...")
    print(f"   Clean Text: {article.text[:50]}...")
    print()

    # Serialize to JSON for storage
    article_dict = article.model_dump()
    print("5. ArticleDTO as dict (ready for DB insert):")
    print(json.dumps(article_dict, indent=2, default=str))


if __name__ == "__main__":
    main()
