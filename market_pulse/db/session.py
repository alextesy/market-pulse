"""Database session management for Market Pulse."""

import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Database URL from environment
DATABASE_URL = os.getenv("POSTGRES_URL", "postgresql://localhost/market_pulse")

# Create engine with appropriate configuration
engine: Engine = create_engine(
    DATABASE_URL,
    poolclass=StaticPool,  # Use static pool for better performance
    pool_pre_ping=True,  # Verify connections before use
    echo=False,  # Set to True for SQL debugging
)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """Context manager for database sessions with automatic cleanup."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def get_db_session_readonly() -> Generator[Session, None, None]:
    """Context manager for read-only database sessions."""
    session = SessionLocal()
    try:
        # Set transaction isolation level for read-only operations
        session.execute(text("SET TRANSACTION ISOLATION LEVEL READ COMMITTED"))
        yield session
    finally:
        session.close()


def test_connection() -> bool:
    """Test database connection."""
    try:
        with get_db_session() as session:
            session.execute(text("SELECT 1"))
            return True
    except Exception:
        return False


def create_tables():
    """Create all tables defined in models."""
    from .models import Base

    Base.metadata.create_all(bind=engine)


def drop_tables():
    """Drop all tables defined in models."""
    from .models import Base

    Base.metadata.drop_all(bind=engine)
