"""Embedding repository for article vector embeddings."""

from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import and_, func, text

from ..db.models import Article, ArticleEmbed
from ..db.session import get_db_session_readonly
from ..models.dto import EmbeddingDTO
from .base import BaseRepository


class EmbedRepository(BaseRepository[ArticleEmbed]):
    """Repository for ArticleEmbed entities with vector similarity search."""

    def __init__(self):
        super().__init__(ArticleEmbed)

    def upsert(self, article_id: int, dto: EmbeddingDTO) -> ArticleEmbed:
        """Upsert embedding for an article."""
        with self._transaction_with_retry() as session:
            # Try to find existing embedding
            existing = (
                session.query(ArticleEmbed)
                .filter(ArticleEmbed.article_id == article_id)
                .first()
            )

            if existing:
                # Update existing embedding
                existing.embedding = dto.embedding
                existing.model = dto.model
                existing.dims = dto.dims
                session.flush()
                return existing
            else:
                # Create new embedding
                embed = ArticleEmbed(
                    article_id=article_id,
                    embedding=dto.embedding,
                    model=dto.model,
                    dims=dto.dims,
                )
                session.add(embed)
                session.flush()
                return embed

    def get_by_article_id(self, article_id: int) -> Optional[ArticleEmbed]:
        """Get embedding by article ID."""
        with get_db_session_readonly() as session:
            return (
                session.query(ArticleEmbed)
                .filter(ArticleEmbed.article_id == article_id)
                .first()
            )

    def find_similar_articles(
        self, embedding: List[float], limit: int = 10, threshold: float = 0.7
    ) -> List[Tuple[ArticleEmbed, float]]:
        """Find articles with similar embeddings using cosine similarity."""
        with get_db_session_readonly() as session:
            # Use vector cosine similarity
            query = (
                session.query(
                    ArticleEmbed,
                    func.cosine_similarity(ArticleEmbed.embedding, embedding).label(
                        "similarity"
                    ),
                )
                .filter(
                    func.cosine_similarity(ArticleEmbed.embedding, embedding)
                    > threshold
                )
                .order_by(text("similarity DESC"))
                .limit(limit)
            )

            return query.all()

    def find_similar_articles_by_article_id(
        self, article_id: int, limit: int = 10, threshold: float = 0.7
    ) -> List[Tuple[ArticleEmbed, float]]:
        """Find articles similar to a given article."""
        with get_db_session_readonly() as session:
            # Get the source article's embedding
            source_embed = (
                session.query(ArticleEmbed)
                .filter(ArticleEmbed.article_id == article_id)
                .first()
            )
            if not source_embed:
                return []

            # Find similar articles (excluding the source article)
            query = (
                session.query(
                    ArticleEmbed,
                    func.cosine_similarity(
                        ArticleEmbed.embedding, source_embed.embedding
                    ).label("similarity"),
                )
                .filter(
                    and_(
                        ArticleEmbed.article_id != article_id,
                        func.cosine_similarity(
                            ArticleEmbed.embedding, source_embed.embedding
                        )
                        > threshold,
                    )
                )
                .order_by(text("similarity DESC"))
                .limit(limit)
            )

            return query.all()

    def get_recent_embeddings_for_ticker(
        self, ticker: str, since_ts: datetime, limit: int = 100
    ) -> List[ArticleEmbed]:
        """Get recent embeddings for articles mentioning a specific ticker."""
        with get_db_session_readonly() as session:
            return (
                session.query(ArticleEmbed)
                .join(Article)
                .join(Article.tickers)
                .filter(
                    and_(
                        Article.tickers.any(ticker=ticker),
                        Article.published_at >= since_ts,
                    )
                )
                .order_by(Article.published_at.desc())
                .limit(limit)
                .all()
            )

    def bulk_insert_embeddings(self, embeddings: List[EmbeddingDTO]) -> None:
        """Bulk insert embeddings."""
        if not embeddings:
            return

        with self._transaction_with_retry() as session:
            embed_objects = []
            for dto in embeddings:
                embed = ArticleEmbed(
                    article_id=dto.article_id,
                    embedding=dto.embedding,
                    model=dto.model,
                    dims=dto.dims,
                )
                embed_objects.append(embed)

            session.add_all(embed_objects)
            session.flush()

    def get_embeddings_by_model(
        self, model: str, limit: int = 100
    ) -> List[ArticleEmbed]:
        """Get embeddings by model type."""
        with get_db_session_readonly() as session:
            return (
                session.query(ArticleEmbed)
                .filter(ArticleEmbed.model == model)
                .limit(limit)
                .all()
            )

    def get_embedding_stats(self) -> dict:
        """Get embedding statistics."""
        with get_db_session_readonly() as session:
            total_count = session.query(ArticleEmbed).count()
            model_counts = (
                session.query(
                    ArticleEmbed.model,
                    session.query(ArticleEmbed)
                    .filter(ArticleEmbed.model == ArticleEmbed.model)
                    .count(),
                )
                .distinct()
                .all()
            )

            return {"total_embeddings": total_count, "by_model": dict(model_counts)}

    def delete_embeddings_by_article_ids(self, article_ids: List[int]) -> int:
        """Delete embeddings for specific article IDs."""
        with self._transaction_with_retry() as session:
            result = (
                session.query(ArticleEmbed)
                .filter(ArticleEmbed.article_id.in_(article_ids))
                .delete(synchronize_session=False)
            )
            return result
