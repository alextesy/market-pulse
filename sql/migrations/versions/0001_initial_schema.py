"""Initial schema setup

Revision ID: 0001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable required extensions
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    
    # Create article table
    op.create_table('article',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.Text(), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('lang', sa.Text(), nullable=True),
        sa.Column('hash', sa.Text(), nullable=True),
        sa.Column('credibility', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_article_source'), 'article', ['source'], unique=False)
    op.create_index(op.f('ix_article_published_at'), 'article', ['published_at'], unique=False)
    op.create_index(op.f('ix_article_url'), 'article', ['url'], unique=True)
    
    # Create article_embed table
    op.create_table('article_embed',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=True),
        sa.Column('embedding', sa.Text(), nullable=True),  # Will be converted to VECTOR(384) after table creation
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['article_id'], ['article.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_article_embed_article_id'), 'article_embed', ['article_id'], unique=False)
    
    # Create article_ticker table
    op.create_table('article_ticker',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('article_id', sa.Integer(), nullable=True),
        sa.Column('ticker', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['article_id'], ['article.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_article_ticker_article_id'), 'article_ticker', ['article_id'], unique=False)
    op.create_index(op.f('ix_article_ticker_ticker'), 'article_ticker', ['ticker'], unique=False)
    
    # Create price_bar table
    op.create_table('price_bar',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.Text(), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('o', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('h', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('l', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('c', sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column('v', sa.BigInteger(), nullable=True),
        sa.Column('timeframe', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id', 'ts')
    )
    op.create_index(op.f('ix_price_bar_ticker_ts'), 'price_bar', ['ticker', 'ts'], unique=False)
    
    # Create signal table
    op.create_table('signal',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('ticker', sa.Text(), nullable=False),
        sa.Column('ts', sa.DateTime(timezone=True), nullable=False),
        sa.Column('sentiment', sa.Float(), nullable=True),
        sa.Column('novelty', sa.Float(), nullable=True),
        sa.Column('velocity', sa.Float(), nullable=True),
        sa.Column('event_tags', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('score', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id', 'ts')
    )
    op.create_index(op.f('ix_signal_ticker_ts'), 'signal', ['ticker', 'ts'], unique=False)
    
    # Create hypertables for time-series data
    op.execute("SELECT create_hypertable('signal', 'ts', if_not_exists => TRUE)")
    op.execute("SELECT create_hypertable('price_bar', 'ts', if_not_exists => TRUE)")
    
    # Convert embedding column to VECTOR type and create index
    op.execute("ALTER TABLE article_embed ALTER COLUMN embedding TYPE vector(384) USING embedding::vector(384)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_article_embed_embedding ON article_embed USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)")


def downgrade() -> None:
    # Drop hypertables first
    op.execute("DROP TABLE IF EXISTS signal CASCADE")
    op.execute("DROP TABLE IF EXISTS price_bar CASCADE")
    
    # Drop regular tables
    op.drop_index(op.f('ix_signal_ticker_ts'), table_name='signal')
    op.drop_table('signal')
    op.drop_index(op.f('ix_price_bar_ticker_ts'), table_name='price_bar')
    op.drop_table('price_bar')
    op.drop_index(op.f('ix_article_ticker_ticker'), table_name='article_ticker')
    op.drop_index(op.f('ix_article_ticker_article_id'), table_name='article_ticker')
    op.drop_table('article_ticker')
    op.drop_index(op.f('ix_article_embed_article_id'), table_name='article_embed')
    op.drop_table('article_embed')
    op.drop_index(op.f('ix_article_url'), table_name='article')
    op.drop_index(op.f('ix_article_published_at'), table_name='article')
    op.drop_index(op.f('ix_article_source'), table_name='article')
    op.drop_table('article')
