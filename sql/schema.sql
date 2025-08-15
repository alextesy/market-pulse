-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;

-- Create tables for market pulse application
CREATE TABLE IF NOT EXISTS articles (
    id SERIAL,
    source TEXT NOT NULL,
    title TEXT,
    content TEXT,
    url TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, published_at)
);

-- Create hypertable for time-series data
SELECT create_hypertable('articles', 'published_at', if_not_exists => TRUE);

-- Create table for ticker mentions
CREATE TABLE IF NOT EXISTS ticker_mentions (
    id SERIAL,
    article_id INTEGER,
    ticker TEXT NOT NULL,
    sentiment_score FLOAT,
    mention_count INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id, created_at)
);

-- Create hypertable for ticker mentions
SELECT create_hypertable('ticker_mentions', 'created_at', if_not_exists => TRUE);

-- Create table for embeddings
CREATE TABLE IF NOT EXISTS embeddings (
    id SERIAL PRIMARY KEY,
    article_id INTEGER,
    embedding vector(384), -- MiniLM-L6-v2 dimension
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source);
CREATE INDEX IF NOT EXISTS idx_articles_published_at ON articles(published_at);
CREATE INDEX IF NOT EXISTS idx_ticker_mentions_ticker ON ticker_mentions(ticker);
CREATE INDEX IF NOT EXISTS idx_embeddings_article_id ON embeddings(article_id);
