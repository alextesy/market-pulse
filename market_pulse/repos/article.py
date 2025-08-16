"""Article repository with upsert and relationship management."""

from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy import text, and_
from sqlalchemy.orm import Session

from .base import BaseRepository
from ..db.models import Article, ArticleTicker
from ..models.dto import ArticleDTO, TickerLinkDTO


class ArticleRepository(BaseRepository[Article]):
    """Repository for Article entities with upsert and relationship management."""
    
    def __init__(self):
        super().__init__(Article)
    
    def upsert_by_url(self, dto: ArticleDTO) -> int:
        """Upsert article by URL with ON CONFLICT handling."""
        with self._transaction_with_retry() as session:
            # Try to find existing article by URL
            existing = session.query(Article).filter(Article.url == dto.url).first()
            
            if existing:
                # Update existing article
                existing.source = dto.source
                existing.url_canonical = dto.url
                existing.published_at = dto.published_at
                existing.retrieved_at = datetime.utcnow()
                existing.title = dto.title
                existing.text = dto.text
                existing.lang = dto.lang
                existing.hash = dto.hash
                existing.credibility = dto.credibility
                session.flush()
                return existing.id
            else:
                # Create new article
                article = Article(
                    source=dto.source,
                    url=dto.url,
                    url_canonical=dto.url,
                    published_at=dto.published_at,
                    retrieved_at=datetime.utcnow(),
                    title=dto.title,
                    text=dto.text,
                    lang=dto.lang,
                    hash=dto.hash,
                    credibility=dto.credibility
                )
                session.add(article)
                session.flush()
                return article.id
    
    def bulk_insert_links(self, article_id: int, links: List[TickerLinkDTO]) -> None:
        """Bulk insert article-ticker relationships."""
        if not links:
            return
        
        with self._transaction_with_retry() as session:
            # Delete existing links for this article
            session.query(ArticleTicker).filter(ArticleTicker.article_id == article_id).delete()
            
            # Insert new links
            article_links = []
            for link in links:
                article_link = ArticleTicker(
                    article_id=article_id,
                    ticker=link.ticker,
                    confidence=link.confidence,
                    method=link.method,
                    matched_terms={"terms": link.matched_terms}
                )
                article_links.append(article_link)
            
            session.add_all(article_links)
            session.flush()
    
    def get_by_url(self, url: str) -> Optional[Article]:
        """Get article by URL."""
        with get_db_session_readonly() as session:
            return session.query(Article).filter(Article.url == url).first()
    
    def get_recent_articles(self, limit: int = 100) -> List[Article]:
        """Get recent articles ordered by published_at."""
        with get_db_session_readonly() as session:
            return session.query(Article).order_by(Article.published_at.desc()).limit(limit).all()
    
    def get_articles_by_ticker(self, ticker: str, limit: int = 100) -> List[Article]:
        """Get articles by ticker symbol."""
        with get_db_session_readonly() as session:
            return session.query(Article).join(ArticleTicker).filter(
                ArticleTicker.ticker == ticker
            ).order_by(Article.published_at.desc()).limit(limit).all()
    
    def get_articles_by_source(self, source: str, limit: int = 100) -> List[Article]:
        """Get articles by source."""
        with get_db_session_readonly() as session:
            return session.query(Article).filter(
                Article.source == source
            ).order_by(Article.published_at.desc()).limit(limit).all()
    
    def get_articles_by_date_range(self, start_date: datetime, end_date: datetime, limit: int = 100) -> List[Article]:
        """Get articles within a date range."""
        with get_db_session_readonly() as session:
            return session.query(Article).filter(
                and_(
                    Article.published_at >= start_date,
                    Article.published_at <= end_date
                )
            ).order_by(Article.published_at.desc()).limit(limit).all()
    
    def get_article_with_tickers(self, article_id: int) -> Optional[Dict[str, Any]]:
        """Get article with its associated tickers."""
        with get_db_session_readonly() as session:
            article = session.query(Article).filter(Article.id == article_id).first()
            if not article:
                return None
            
            tickers = session.query(ArticleTicker).filter(ArticleTicker.article_id == article_id).all()
            
            return {
                "article": article,
                "tickers": tickers
            }
    
    def delete_old_articles(self, cutoff_date: datetime) -> int:
        """Delete articles older than cutoff date."""
        with self._transaction_with_retry() as session:
            result = session.query(Article).filter(Article.published_at < cutoff_date).delete()
            return result
    
    def get_article_stats(self) -> Dict[str, Any]:
        """Get article statistics."""
        with get_db_session_readonly() as session:
            total_count = session.query(Article).count()
            source_counts = session.query(
                Article.source, 
                session.query(Article).filter(Article.source == Article.source).count()
            ).distinct().all()
            
            return {
                "total_articles": total_count,
                "by_source": dict(source_counts)
            }
