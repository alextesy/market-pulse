"""Mapping utilities for transforming between DTOs."""

import hashlib
import html
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, urlparse, urlunparse

from .dto import (
    ArticleDTO,
    ArticleTickerDTO,
    IngestItem,
    SignalContribDTO,
    TickerLinkDTO,
)


def canonicalize_url(url: str) -> str:
    """Normalize URL by stripping UTM parameters and anchors."""
    parsed = urlparse(url)

    # Remove UTM parameters from query string
    if parsed.query:
        query_params = parse_qs(parsed.query)
        # Remove UTM parameters
        utm_params = [
            "utm_source",
            "utm_medium",
            "utm_campaign",
            "utm_term",
            "utm_content",
        ]
        for param in utm_params:
            query_params.pop(param, None)

        # Rebuild query string
        new_query = "&".join([f"{k}={v[0]}" for k, v in query_params.items() if v])
        parsed = parsed._replace(query=new_query)

    # Remove fragment/anchor
    parsed = parsed._replace(fragment="")

    return urlunparse(parsed)


def clean_text(text: str) -> Optional[str]:
    """Clean text by stripping HTML and normalizing whitespace."""
    if not text:
        return None

    # Unescape HTML entities
    text = html.unescape(text)

    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    return text if text else None


def generate_article_hash(title: str, url: str) -> str:
    """Generate SHA1 hash of canonical title + host."""
    if not title or not url:
        return ""

    # Get host from URL
    parsed = urlparse(url)
    host = parsed.netloc.lower()

    # Clean title
    clean_title = clean_text(title) or ""

    # Create hash string
    hash_string = f"{clean_title}:{host}"

    return hashlib.sha1(hash_string.encode("utf-8")).hexdigest()


def calculate_credibility(item: IngestItem) -> Optional[float]:
    """Calculate credibility score based on source and metadata."""
    # Base credibility by source
    source_credibility = {
        "sec": 90.0,  # SEC filings are highly credible
        "gdelt": 70.0,  # GDELT news articles
        "stocktwits": 40.0,  # Social media
        "twitter": 35.0,  # Social media
        "reddit": 30.0,  # Social media
    }

    base_score = source_credibility.get(item.source, 50.0)

    # Adjustments based on metadata
    adjustments = 0.0

    # Author presence
    if item.author:
        adjustments += 5.0

    # License information
    if item.license:
        adjustments += 3.0

    # URL quality (HTTPS, reputable domains)
    if str(item.url).startswith("https://"):
        adjustments += 2.0

    final_score = min(100.0, max(0.0, base_score + adjustments))
    return final_score


def ingest_item_to_article(item: IngestItem) -> ArticleDTO:
    """Transform IngestItem to ArticleDTO for DB insert."""
    return ArticleDTO(
        source=item.source,
        url=canonicalize_url(str(item.url)),
        published_at=item.published_at,  # Already timezone-aware and UTC
        title=clean_text(item.title),
        text=clean_text(item.text),
        lang=item.lang,
        hash=generate_article_hash(item.title, str(item.url)),
        credibility=calculate_credibility(item),
    )


def ticker_link_to_article_ticker(
    link: TickerLinkDTO, article_id: int
) -> ArticleTickerDTO:
    """Convert TickerLinkDTO to ArticleTickerDTO for DB insert."""
    return ArticleTickerDTO(
        article_id=article_id,
        ticker=link.ticker,
        confidence=link.confidence,
        method=link.method,
        matched_terms=link.matched_terms,
    )


def create_signal_contribution(
    signal_id: int, article_id: int, rank: Optional[int] = None
) -> SignalContribDTO:
    """Create SignalContribDTO for tracking individual article contributions to signals."""
    return SignalContribDTO(signal_id=signal_id, article_id=article_id, rank=rank)


def ensure_timezone_aware(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware, defaulting to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def validate_ticker_format(ticker: str) -> bool:
    """Validate ticker format using regex pattern."""
    import re

    pattern = r"^[A-Z.\-]{1,10}$"
    return bool(re.match(pattern, ticker))
