-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;

-- Create tables for market pulse application
CREATE TABLE IF NOT EXISTS article (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT UNIQUE,
    published_at TIMESTAMPTZ NOT NULL,
    title TEXT,
    text TEXT,
    lang TEXT,
    hash TEXT,
    credibility FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create table for article embeddings
CREATE TABLE IF NOT EXISTS article_embed (
    id SERIAL PRIMARY KEY,
    article_id INTEGER REFERENCES article(id),
    embedding VECTOR(384), -- MiniLM-L6-v2 dimension
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create table for article-ticker relationships
CREATE TABLE IF NOT EXISTS article_ticker (
    id SERIAL PRIMARY KEY,
    article_id INTEGER REFERENCES article(id),
    ticker TEXT NOT NULL,
    confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create table for price bars
CREATE TABLE IF NOT EXISTS price_bar (
    id SERIAL,
    ticker TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    o DECIMAL(10,4),
    h DECIMAL(10,4),
    l DECIMAL(10,4),
    c DECIMAL(10,4),
    v BIGINT,
    timeframe TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, ts)
);

-- Create table for signals
CREATE TABLE IF NOT EXISTS signal (
    id SERIAL,
    ticker TEXT NOT NULL,
    ts TIMESTAMPTZ NOT NULL,
    sentiment FLOAT,
    novelty FLOAT,
    velocity FLOAT,
    event_tags TEXT[],
    score FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (id, ts)
);

-- Create hypertables for time-series data
SELECT create_hypertable('signal', 'ts', if_not_exists => TRUE);
SELECT create_hypertable('price_bar', 'ts', if_not_exists => TRUE);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_article_source ON article(source);
CREATE INDEX IF NOT EXISTS idx_article_published_at ON article(published_at);
CREATE INDEX IF NOT EXISTS idx_article_ticker_ticker ON article_ticker(ticker);
CREATE INDEX IF NOT EXISTS idx_article_ticker_article_id ON article_ticker(article_id);
CREATE INDEX IF NOT EXISTS idx_article_embed_article_id ON article_embed(article_id);
CREATE INDEX IF NOT EXISTS idx_signal_ticker_ts ON signal(ticker, ts DESC);
CREATE INDEX IF NOT EXISTS idx_price_bar_ticker_ts ON price_bar(ticker, ts DESC);

-- Create vector index for similarity search
CREATE INDEX IF NOT EXISTS idx_article_embed_embedding ON article_embed USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
