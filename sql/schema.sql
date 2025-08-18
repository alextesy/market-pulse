-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS vector;

-- Create ticker table
CREATE TABLE IF NOT EXISTS ticker (
    symbol TEXT PRIMARY KEY,
    name TEXT,
    exchange TEXT,
    cik TEXT,
    aliases JSONB,
    valid_from DATE,
    valid_to DATE
);

-- Create article table with BIGSERIAL
CREATE TABLE IF NOT EXISTS article (
    id BIGSERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    url TEXT UNIQUE,
    url_canonical TEXT,
    published_at TIMESTAMPTZ NOT NULL,
    retrieved_at TIMESTAMPTZ,
    title TEXT,
    text TEXT,
    lang TEXT,
    hash TEXT,
    credibility SMALLINT
);

-- Create article_embed table
CREATE TABLE IF NOT EXISTS article_embed (
    article_id BIGINT REFERENCES article(id) ON DELETE CASCADE,
    embedding VECTOR(384),
    model TEXT,
    dims SMALLINT,
    PRIMARY KEY(article_id)
);

-- Create article_ticker table
CREATE TABLE IF NOT EXISTS article_ticker (
    article_id BIGINT REFERENCES article(id) ON DELETE CASCADE,
    ticker TEXT REFERENCES ticker(symbol),
    confidence REAL,
    method TEXT,
    matched_terms JSONB,
    PRIMARY KEY(article_id, ticker)
);

-- Create price_bar table
CREATE TABLE IF NOT EXISTS price_bar (
    ticker TEXT REFERENCES ticker(symbol),
    ts TIMESTAMPTZ,
    o REAL,
    h REAL,
    l REAL,
    c REAL,
    v BIGINT,
    timeframe TEXT,
    PRIMARY KEY(ticker, ts, timeframe)
);

-- Create signal table
CREATE TABLE IF NOT EXISTS signal (
    id BIGSERIAL,
    ticker TEXT REFERENCES ticker(symbol),
    ts TIMESTAMPTZ NOT NULL,
    sentiment REAL,
    novelty REAL,
    velocity REAL,
    event_tags TEXT[],
    score REAL,
    PRIMARY KEY(id, ts)
);

-- Create signal_contrib table
CREATE TABLE IF NOT EXISTS signal_contrib (
    signal_id BIGINT,
    signal_ts TIMESTAMPTZ,
    article_id BIGINT REFERENCES article(id) ON DELETE CASCADE,
    rank SMALLINT,
    PRIMARY KEY(signal_id, signal_ts, article_id),
    FOREIGN KEY (signal_id, signal_ts) REFERENCES signal(id, ts) ON DELETE CASCADE
);

-- Create sequences for auto-incrementing IDs
CREATE SEQUENCE IF NOT EXISTS signal_id_seq;
ALTER TABLE signal ALTER COLUMN id SET DEFAULT nextval('signal_id_seq');

-- Create TimescaleDB hypertables
SELECT create_hypertable('price_bar', 'ts', chunk_time_interval => interval '1 day', if_not_exists => TRUE);
SELECT create_hypertable('signal', 'ts', chunk_time_interval => interval '1 day', if_not_exists => TRUE);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_article_ticker_ticker ON article_ticker(ticker);
CREATE INDEX IF NOT EXISTS idx_signal_ticker_ts ON signal(ticker, ts DESC);
CREATE INDEX IF NOT EXISTS idx_price_bar_ticker_ts ON price_bar(ticker, ts DESC);
CREATE INDEX IF NOT EXISTS article_embed_embedding_idx ON article_embed USING ivfflat (embedding vector_cosine_ops) WITH (lists=100);
