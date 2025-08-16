"""Pydantic DTOs for Market Pulse data models."""

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from pydantic import BaseModel, AnyUrl, Field, field_validator, model_validator
from pydantic.types import StringConstraints
from typing_extensions import Annotated

# Type aliases for reusability
TickerStr = Annotated[str, StringConstraints(pattern=r"^[A-Z.\-]{1,10}$")]


class IngestItem(BaseModel):
    """Raw item coming from collectors (source-agnostic)."""
    
    source: Literal['gdelt', 'sec', 'stocktwits', 'twitter', 'reddit']
    source_id: Optional[str] = None  # e.g., GDELT URLHash, SEC accession
    url: AnyUrl
    published_at: datetime  # Must be timezone-aware
    retrieved_at: datetime  # Must be timezone-aware
    title: Annotated[str, StringConstraints(max_length=512)]
    text: Annotated[str, StringConstraints(max_length=20000)]
    lang: Annotated[str, StringConstraints(to_lower=True, min_length=2, max_length=5)]  # ISO-639-1/BCP-47
    license: Optional[str] = None
    author: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    
    @field_validator('published_at', 'retrieved_at')
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware and normalize to UTC."""
        if v.tzinfo is None:
            raise ValueError('datetime must be timezone-aware')
        return v.astimezone(timezone.utc)


class ArticleDTO(BaseModel):
    """Normalized article ready for DB insert - matches article table."""
    
    source: str
    url: str  # TEXT in DB, not AnyUrl for flexibility
    published_at: datetime  # Must be timezone-aware, stored as UTC
    title: Optional[str] = None
    text: Optional[str] = None
    lang: Optional[str] = None
    hash: Optional[str] = None  # sha1 of canonical title+host
    credibility: Optional[float] = Field(None, ge=0, le=100)  # 0-100 scale
    
    @field_validator('published_at')
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware and normalize to UTC."""
        if v.tzinfo is None:
            raise ValueError('datetime must be timezone-aware')
        return v.astimezone(timezone.utc)
    
    @field_validator('credibility')
    @classmethod
    def validate_credibility(cls, v: Optional[float]) -> Optional[float]:
        """Validate credibility score is in valid range."""
        if v is not None and not (0 <= v <= 100):
            raise ValueError('credibility must be between 0 and 100')
        return v


class ArticleTickerDTO(BaseModel):
    """Article-ticker relationship - matches article_ticker table."""
    
    article_id: int
    ticker: TickerStr
    confidence: Optional[float] = Field(None, ge=0, le=1)
    method: Optional[Literal['cashtag', 'dict', 'synonym', 'ner']] = None
    matched_terms: Optional[list[str]] = None
    
    @field_validator('confidence')
    @classmethod
    def validate_confidence(cls, v: Optional[float]) -> Optional[float]:
        """Validate confidence score is in valid range."""
        if v is not None and not (0 <= v <= 1):
            raise ValueError('confidence must be between 0 and 1')
        return v


class TickerLinkDTO(BaseModel):
    """Output of ticker linker with confidence and metadata."""
    
    ticker: TickerStr
    confidence: float = Field(ge=0, le=1)
    method: Literal['cashtag', 'dict', 'synonym', 'ner']
    matched_terms: list[str]
    char_spans: Optional[list[tuple[int, int]]] = None
    article_id: Optional[int] = None  # For DB linking


class SentimentDTO(BaseModel):
    """Per-article sentiment analysis results."""
    
    prob_pos: float = Field(ge=0, le=1)
    prob_neg: float = Field(ge=0, le=1)
    prob_neu: float = Field(ge=0, le=1)
    score: float  # e.g., pos - neg
    model: str
    model_rev: str
    
    @model_validator(mode='after')
    def validate_probability_sum(self) -> 'SentimentDTO':
        """Validate that probabilities sum to approximately 1."""
        total = self.prob_pos + self.prob_neg + self.prob_neu
        epsilon = 0.01  # Allow small floating point errors
        if abs(total - 1.0) > epsilon:
            raise ValueError(f'probabilities must sum to 1.0, got {total}')
        return self
    
    @field_validator('prob_pos', 'prob_neg', 'prob_neu')
    @classmethod
    def validate_probabilities(cls, v: float) -> float:
        """Validate probability scores are in valid range."""
        if not (0 <= v <= 1):
            raise ValueError('probability must be between 0 and 1')
        return v


class EmbeddingDTO(BaseModel):
    """Article vector embedding - matches article_embed table."""
    
    article_id: int
    embedding: list[float] = Field(min_length=384, max_length=384)  # MiniLM-L6-v2 dimension
    model: str = "MiniLM-L6-v2"
    dims: int = 384
    
    @field_validator('embedding')
    @classmethod
    def validate_embedding_length(cls, v: list[float]) -> list[float]:
        """Validate embedding has correct dimension."""
        if len(v) != 384:
            raise ValueError('embedding must have exactly 384 dimensions')
        return v
    
    @model_validator(mode='after')
    def validate_dims_match_embedding(self) -> 'EmbeddingDTO':
        """Validate that dims matches embedding length."""
        if self.dims != len(self.embedding):
            raise ValueError(f'dims ({self.dims}) must match embedding length ({len(self.embedding)})')
        return self


class SignalContribDTO(BaseModel):
    """Signal contribution from individual article - for signal_contrib table."""
    
    signal_id: int
    article_id: int
    rank: Optional[int] = Field(None, ge=1)  # Contribution rank
    
    @field_validator('rank')
    @classmethod
    def validate_rank(cls, v: Optional[int]) -> Optional[int]:
        """Validate rank is positive if provided."""
        if v is not None and v < 1:
            raise ValueError('rank must be positive')
        return v


class SignalDTO(BaseModel):
    """Per-ticker timepoint signal - matches signal table."""
    
    ticker: TickerStr
    ts: datetime  # Must be timezone-aware, stored as UTC
    sentiment: Optional[float] = None
    novelty: Optional[float] = None
    velocity: Optional[float] = None
    event_tags: list[str] = Field(default_factory=list)  # TEXT[] in DB
    score: Optional[float] = None
    contributors: Optional[list[int]] = Field(None, max_length=2)  # article IDs, limited to N=2
    
    @field_validator('ts')
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware and normalize to UTC."""
        if v.tzinfo is None:
            raise ValueError('datetime must be timezone-aware')
        return v.astimezone(timezone.utc)
    
    @field_validator('contributors')
    @classmethod
    def validate_contributors(cls, v: Optional[list[int]]) -> Optional[list[int]]:
        """Validate contributors list is limited to 2 items."""
        if v is not None and len(v) > 2:
            raise ValueError('contributors list cannot exceed 2 items')
        return v


class PriceBarDTO(BaseModel):
    """Price bar data - matches price_bar table."""
    
    ticker: TickerStr
    ts: datetime  # Must be timezone-aware, stored as UTC
    o: Optional[float] = None  # DECIMAL(10,4) in DB
    h: Optional[float] = None
    l: Optional[float] = None
    c: Optional[float] = None
    v: Optional[int] = None  # BIGINT in DB
    timeframe: Literal['1d', '1h', '1m']
    
    @field_validator('ts')
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware and normalize to UTC."""
        if v.tzinfo is None:
            raise ValueError('datetime must be timezone-aware')
        return v.astimezone(timezone.utc)
    
    @field_validator('o', 'h', 'l', 'c')
    @classmethod
    def validate_price_fields(cls, v: Optional[float]) -> Optional[float]:
        """Validate price fields are non-negative."""
        if v is not None and v < 0:
            raise ValueError('price fields must be non-negative')
        return v
    
    @field_validator('v')
    @classmethod
    def validate_volume(cls, v: Optional[int]) -> Optional[int]:
        """Validate volume is non-negative."""
        if v is not None and v < 0:
            raise ValueError('volume must be non-negative')
        return v
