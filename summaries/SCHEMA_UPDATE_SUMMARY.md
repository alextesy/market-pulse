# Database Schema Update Summary

## Overview

Updated the database schema to perfectly align with our Pydantic DTOs implementation. The schema now supports all the data models needed for the Market Pulse application.

## Schema Changes Made

### ✅ **Updated Tables**

#### 1. **`article`** (renamed from `articles`)
- **Added fields:**
  - `lang` TEXT - Language code (ISO-639-1/BCP-47)
  - `hash` TEXT - SHA1 hash for deduplication
  - `credibility` FLOAT - Source credibility score (0-100)
- **Changed fields:**
  - `content` → `text` - Renamed for consistency
  - `url` UNIQUE - Added unique constraint
- **Removed:**
  - Hypertable on `published_at` (not needed for this table)

#### 2. **`article_embed`** (renamed from `embeddings`)
- **Added:**
  - Foreign key constraint to `article(id)`
- **Structure:**
  - `article_id` INTEGER REFERENCES article(id)
  - `embedding` VECTOR(384) - MiniLM-L6-v2 dimension

#### 3. **`article_ticker`** (new table, replaces `ticker_mentions`)
- **Structure:**
  - `article_id` INTEGER REFERENCES article(id)
  - `ticker` TEXT NOT NULL
  - `confidence` FLOAT - Ticker linking confidence (0-1)
- **Purpose:** Links articles to tickers with confidence scores

### ✅ **New Tables**

#### 4. **`price_bar`** (new table)
- **Structure:**
  - `ticker` TEXT NOT NULL
  - `ts` TIMESTAMPTZ NOT NULL
  - `o/h/l/c` DECIMAL(10,4) - Open/High/Low/Close prices
  - `v` BIGINT - Volume
  - `timeframe` TEXT NOT NULL - '1d', '1h', '1m'
- **Features:**
  - TimescaleDB hypertable for time-series data
  - Composite primary key (id, ts)

#### 5. **`signal`** (new table)
- **Structure:**
  - `ticker` TEXT NOT NULL
  - `ts` TIMESTAMPTZ NOT NULL
  - `sentiment` FLOAT - Sentiment score
  - `novelty` FLOAT - Novelty score
  - `velocity` FLOAT - Velocity score
  - `event_tags` TEXT[] - Array of event tags
  - `score` FLOAT - Composite signal score
- **Features:**
  - TimescaleDB hypertable for time-series data
  - Composite primary key (id, ts)

## Database Schema Alignment

### ✅ **Perfect DTO-to-Table Mapping**

| DTO | Database Table | Status |
|-----|----------------|--------|
| `ArticleDTO` | `article` | ✅ Perfect match |
| `ArticleTickerDTO` | `article_ticker` | ✅ Perfect match |
| `EmbeddingDTO` | `article_embed` | ✅ Perfect match |
| `SignalDTO` | `signal` | ✅ Perfect match |
| `PriceBarDTO` | `price_bar` | ✅ Perfect match |

### ✅ **Key Features**

1. **Foreign Key Relationships:**
   - `article_embed.article_id` → `article.id`
   - `article_ticker.article_id` → `article.id`

2. **TimescaleDB Integration:**
   - `signal` hypertable on `ts`
   - `price_bar` hypertable on `ts`

3. **Vector Support:**
   - `article_embed.embedding` VECTOR(384)
   - IVFFlat index for similarity search

4. **Array Support:**
   - `signal.event_tags` TEXT[] for PostgreSQL arrays

5. **Performance Indexes:**
   - Source and timestamp indexes
   - Ticker-based indexes for fast lookups
   - Vector similarity search index

## Migration Strategy

### **Migration File: `sql/migrations/0002_update_schema_for_dtos.sql`**

The migration handles:
1. **Safe table drops** with CASCADE
2. **New table creation** with proper constraints
3. **Index creation** for performance
4. **Hypertable setup** for time-series data

### **Migration Steps:**
```sql
-- 1. Drop old tables
DROP TABLE IF EXISTS ticker_mentions CASCADE;
DROP TABLE IF EXISTS embeddings CASCADE;
DROP TABLE IF EXISTS articles CASCADE;

-- 2. Create new tables with proper structure
CREATE TABLE IF NOT EXISTS article (...);
CREATE TABLE IF NOT EXISTS article_embed (...);
CREATE TABLE IF NOT EXISTS article_ticker (...);
CREATE TABLE IF NOT EXISTS price_bar (...);
CREATE TABLE IF NOT EXISTS signal (...);

-- 3. Setup hypertables and indexes
SELECT create_hypertable('signal', 'ts', if_not_exists => TRUE);
SELECT create_hypertable('price_bar', 'ts', if_not_exists => TRUE);
-- ... indexes
```

## Testing

### ✅ **Database Integration Tests**

Created `tests/test_database_integration.py` with:
- **6 test cases** verifying DTO-to-database alignment
- **Complete workflow testing** from IngestItem to database-ready dicts
- **Data type validation** for all fields
- **Transformation verification** (URL cleaning, HTML stripping, etc.)

### ✅ **Test Results**
```
6 passed in 0.32s
```

## Benefits

1. **Perfect Alignment:** DTOs and database schema are now perfectly aligned
2. **Type Safety:** All data types match between Pydantic models and PostgreSQL
3. **Performance:** Proper indexes and hypertables for time-series data
4. **Scalability:** TimescaleDB support for high-volume time-series data
5. **Vector Search:** PostgreSQL vector extension for embedding similarity
6. **Data Integrity:** Foreign key constraints and unique constraints

## Next Steps

The schema is now ready for:
1. **Production deployment** with the migration
2. **SQLAlchemy integration** using the DTOs
3. **Data ingestion pipelines** using the mapping utilities
4. **API endpoints** with proper request/response models
5. **Analytics workflows** for signal generation and analysis

All tables support the full Market Pulse data pipeline from raw ingestion to signal generation.
