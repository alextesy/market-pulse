"""Base repository with common database operations."""

import logging
from contextlib import contextmanager
from typing import TypeVar, Generic, Optional, List, Any
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.query import Query

from ..db.session import get_db_session, get_db_session_readonly

logger = logging.getLogger(__name__)

T = TypeVar('T')


class BaseRepository(Generic[T]):
    """Base repository with common database operations."""
    
    def __init__(self, model_class: type[T]):
        self.model_class = model_class
    
    @contextmanager
    def _transaction_with_retry(self, max_retries: int = 3):
        """Context manager for database transactions with retry logic."""
        for attempt in range(max_retries):
            try:
                with get_db_session() as session:
                    yield session
                    return  # Success, exit retry loop
            except (OperationalError, IntegrityError) as e:
                if "deadlock" in str(e).lower() or "serialization" in str(e).lower():
                    if attempt < max_retries - 1:
                        logger.warning(f"Database deadlock/serialization error, retrying (attempt {attempt + 1}/{max_retries})")
                        continue
                raise  # Re-raise if not a retryable error or max retries reached
    
    def get_by_id(self, id: Any) -> Optional[T]:
        """Get entity by primary key."""
        with get_db_session_readonly() as session:
            return session.get(self.model_class, id)
    
    def get_all(self, limit: Optional[int] = None) -> List[T]:
        """Get all entities with optional limit."""
        with get_db_session_readonly() as session:
            query = session.query(self.model_class)
            if limit:
                query = query.limit(limit)
            return query.all()
    
    def create(self, entity: T) -> T:
        """Create a new entity."""
        with self._transaction_with_retry() as session:
            session.add(entity)
            session.flush()  # Get the ID without committing
            return entity
    
    def update(self, entity: T) -> T:
        """Update an existing entity."""
        with self._transaction_with_retry() as session:
            session.merge(entity)
            return entity
    
    def delete(self, entity: T) -> None:
        """Delete an entity."""
        with self._transaction_with_retry() as session:
            session.delete(entity)
    
    def delete_by_id(self, id: Any) -> bool:
        """Delete entity by primary key."""
        with self._transaction_with_retry() as session:
            entity = session.get(self.model_class, id)
            if entity:
                session.delete(entity)
                return True
            return False
    
    def exists(self, id: Any) -> bool:
        """Check if entity exists by primary key."""
        with get_db_session_readonly() as session:
            return session.get(self.model_class, id) is not None
    
    def count(self) -> int:
        """Get total count of entities."""
        with get_db_session_readonly() as session:
            return session.query(self.model_class).count()
    
    def _build_query(self, session: Session, **filters) -> Query:
        """Build a query with optional filters."""
        query = session.query(self.model_class)
        for field, value in filters.items():
            if value is not None:
                if hasattr(self.model_class, field):
                    query = query.filter(getattr(self.model_class, field) == value)
        return query
    
    def find_by(self, **filters) -> List[T]:
        """Find entities by filter criteria."""
        with get_db_session_readonly() as session:
            query = self._build_query(session, **filters)
            return query.all()
    
    def find_one_by(self, **filters) -> Optional[T]:
        """Find single entity by filter criteria."""
        with get_db_session_readonly() as session:
            query = self._build_query(session, **filters)
            return query.first()
