# Processing DTOs: TickerLinkDTO and SentimentDTO

## Overview

`TickerLinkDTO` and `SentimentDTO` are **processing DTOs** - they represent intermediate data structures used during data processing but are not stored directly in the database. Instead, they get transformed into database-ready DTOs.

## DTO Categories

### 🗄️ **Database DTOs** (Stored in Tables)
- `ArticleDTO` → `article` table
- `ArticleTickerDTO` → `article_ticker` table
- `EmbeddingDTO` → `article_embed` table
- `SignalDTO` → `signal` table
- `PriceBarDTO` → `price_bar` table

### ⚙️ **Processing DTOs** (Intermediate Processing)
- `TickerLinkDTO` → Transformed to `ArticleTickerDTO`
- `SentimentDTO` → Aggregated into `SignalDTO`

## TickerLinkDTO

### Purpose
Represents the **output of ticker linking algorithms** that identify which tickers are mentioned in articles.

### Fields
```python
class TickerLinkDTO(BaseModel):
    ticker: str                    # e.g., "AAPL"
    confidence: float              # 0.0-1.0 confidence score
    method: Literal['cashtag', 'dict', 'synonym', 'ner']
    matched_terms: list[str]       # e.g., ["AAPL", "Apple"]
    char_spans: Optional[list[tuple[int, int]]]  # Text positions
    article_id: Optional[int]      # Set after article insertion
```

### Usage in Pipeline
1. **Ticker linking algorithm** processes article text
2. **Creates TickerLinkDTO** with detailed linking info
3. **Transforms to ArticleTickerDTO** for database storage
4. **Stores in `article_ticker` table**

### Example
```python
# Processing result from ticker linking
ticker_link = TickerLinkDTO(
    ticker='AAPL',
    confidence=0.95,
    method='cashtag',
    matched_terms=['AAPL', 'Apple'],
    char_spans=[(0, 4), (10, 15)]
)

# Convert to database format
article_ticker = ticker_link_to_article_ticker(ticker_link, article_id=123)
# Stores: article_id=123, ticker='AAPL', confidence=0.95
```

## SentimentDTO

### Purpose
Represents the **output of sentiment analysis** for individual articles.

### Fields
```python
class SentimentDTO(BaseModel):
    prob_pos: float    # Probability of positive sentiment
    prob_neg: float    # Probability of negative sentiment
    prob_neu: float    # Probability of neutral sentiment
    score: float       # Composite score (pos - neg)
    model: str         # Model used (e.g., "bert-base-sentiment")
    model_rev: str     # Model version
```

### Usage in Pipeline
1. **Sentiment analysis model** processes article text
2. **Creates SentimentDTO** with detailed sentiment scores
3. **Aggregates multiple SentimentDTOs** into SignalDTO
4. **Stores aggregated sentiment** in `signal` table

### Example
```python
# Processing result from sentiment analysis
sentiment = SentimentDTO(
    prob_pos=0.75,
    prob_neg=0.15,
    prob_neu=0.10,
    score=0.60,  # 0.75 - 0.15
    model='bert-base-sentiment',
    model_rev='v1.0'
)

# Later aggregated into SignalDTO
signal = SignalDTO(
    ticker='AAPL',
    ts=datetime.now(),
    sentiment=0.65,  # Aggregated from multiple articles
    # ... other fields
)
```

## Why This Design?

### 1. **Separation of Concerns**
- **Processing DTOs**: Rich metadata for algorithms
- **Database DTOs**: Optimized for storage and queries

### 2. **Algorithm Flexibility**
- Ticker linking can use multiple methods (cashtag, NER, etc.)
- Sentiment analysis can use different models
- Processing DTOs capture this metadata

### 3. **Storage Efficiency**
- Database tables store only essential data
- Processing metadata is used during transformation
- Reduces database size and improves query performance

### 4. **Pipeline Clarity**
- Clear distinction between processing and storage
- Easy to add new processing algorithms
- Maintains data integrity

## Complete Data Flow

```
Raw Article Text
    ↓
Ticker Linking Algorithm
    ↓
TickerLinkDTO (processing)
    ↓
Transform to ArticleTickerDTO
    ↓
Store in article_ticker table
```

```
Raw Article Text
    ↓
Sentiment Analysis Model
    ↓
SentimentDTO (processing)
    ↓
Aggregate with other articles
    ↓
Include in SignalDTO
    ↓
Store in signal table
```

## Benefits

1. **Rich Processing Metadata**: Capture algorithm details and confidence scores
2. **Clean Database Schema**: Only store essential data
3. **Algorithm Flexibility**: Easy to switch or combine different algorithms
4. **Performance**: Optimized database queries with minimal data
5. **Maintainability**: Clear separation between processing and storage logic

## Summary

`TickerLinkDTO` and `SentimentDTO` are essential for the data processing pipeline, providing rich metadata during processing while maintaining a clean, efficient database schema. They bridge the gap between complex algorithmic outputs and simple, queryable database records.
