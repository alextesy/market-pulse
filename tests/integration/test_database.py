"""Integration tests for database connectivity."""

import pytest
import psycopg
import os
from typing import Generator


@pytest.fixture
def db_connection() -> Generator[psycopg.Connection, None, None]:
    """Create a database connection for testing."""
    url = os.getenv("POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/market_pulse")
    with psycopg.connect(url) as conn:
        yield conn


def test_hypertables_exist(db_connection: psycopg.Connection):
    """Test that hypertables exist for signal and price_bar tables."""
    with db_connection.cursor() as cur:
        # Check if signal table is a hypertable
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM timescaledb_information.hypertables 
                WHERE hypertable_name = 'signal'
            );
        """)
        signal_is_hypertable = cur.fetchone()[0]
        assert signal_is_hypertable, "signal table should be a hypertable"
        
        # Check if price_bar table is a hypertable
        cur.execute("""
            SELECT EXISTS (
                SELECT 1 FROM timescaledb_information.hypertables 
                WHERE hypertable_name = 'price_bar'
            );
        """)
        price_bar_is_hypertable = cur.fetchone()[0]
        assert price_bar_is_hypertable, "price_bar table should be a hypertable"


def test_extensions_enabled(db_connection: psycopg.Connection):
    """Test that required extensions are enabled."""
    with db_connection.cursor() as cur:
        # Check timescaledb extension
        cur.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb');")
        timescaledb_enabled = cur.fetchone()[0]
        assert timescaledb_enabled, "timescaledb extension should be enabled"
        
        # Check vector extension
        cur.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector');")
        vector_enabled = cur.fetchone()[0]
        assert vector_enabled, "vector extension should be enabled"


def test_tables_exist(db_connection: psycopg.Connection):
    """Test that all required tables exist."""
    required_tables = ['article', 'article_embed', 'article_ticker', 'price_bar', 'signal']
    
    with db_connection.cursor() as cur:
        for table_name in required_tables:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = %s
                );
            """, (table_name,))
            table_exists = cur.fetchone()[0]
            assert table_exists, f"Table {table_name} should exist"
