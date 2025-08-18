"""Integration tests for database connectivity."""

import os
from typing import Generator

import psycopg2
import pytest


@pytest.fixture
def db_connection() -> Generator[psycopg2.extensions.connection, None, None]:
    """Create a database connection for testing."""
    url = os.getenv(
        "POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/market_pulse"
    )
    # Parse the URL to get connection parameters
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "")
        if "@" in url:
            auth, rest = url.split("@", 1)
            if ":" in auth:
                user, password = auth.split(":", 1)
            else:
                user, password = auth, ""
            if ":" in rest:
                host_port, database = rest.split("/", 1)
                if ":" in host_port:
                    host, port = host_port.split(":", 1)
                else:
                    host, port = host_port, "5432"
            else:
                host, port, database = rest, "5432", ""
        else:
            user, password, host, port, database = (
                "",
                "",
                "localhost",
                "5432",
                "market_pulse",
            )
    else:
        user, password, host, port, database = (
            "postgres",
            "postgres",
            "localhost",
            "5432",
            "market_pulse",
        )

    conn = psycopg2.connect(
        host=host, port=port, database=database, user=user, password=password
    )
    yield conn
    conn.close()


@pytest.mark.integration
def test_hypertables_exist(db_connection: psycopg2.extensions.connection) -> None:
    """Test that hypertables exist for signal and price_bar tables."""
    with db_connection.cursor() as cur:
        # Check if signal table is a hypertable
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM timescaledb_information.hypertables 
                WHERE hypertable_name = 'signal'
            );
        """
        )
        result = cur.fetchone()
        assert result is not None
        signal_is_hypertable = result[0]
        assert signal_is_hypertable, "signal table should be a hypertable"

        # Check if price_bar table is a hypertable
        cur.execute(
            """
            SELECT EXISTS (
                SELECT 1 FROM timescaledb_information.hypertables 
                WHERE hypertable_name = 'price_bar'
            );
        """
        )
        result = cur.fetchone()
        assert result is not None
        price_bar_is_hypertable = result[0]
        assert price_bar_is_hypertable, "price_bar table should be a hypertable"


@pytest.mark.integration
def test_extensions_enabled(db_connection: psycopg2.extensions.connection) -> None:
    """Test that required extensions are enabled."""
    with db_connection.cursor() as cur:
        # Check timescaledb extension
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb');"
        )
        result = cur.fetchone()
        assert result is not None
        timescaledb_enabled = result[0]
        assert timescaledb_enabled, "timescaledb extension should be enabled"

        # Check vector extension
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector');"
        )
        result = cur.fetchone()
        assert result is not None
        vector_enabled = result[0]
        assert vector_enabled, "vector extension should be enabled"


@pytest.mark.integration
def test_tables_exist(db_connection: psycopg2.extensions.connection) -> None:
    """Test that all required tables exist."""
    required_tables = [
        "article",
        "article_embed",
        "article_ticker",
        "price_bar",
        "signal",
    ]

    with db_connection.cursor() as cur:
        for table_name in required_tables:
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables 
                    WHERE table_name = %s
                );
            """,
                (table_name,),
            )
            result = cur.fetchone()
            assert result is not None
            table_exists = result[0]
            assert table_exists, f"Table {table_name} should exist"
