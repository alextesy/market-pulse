# Infrastructure Setup

This directory contains the infrastructure configuration for the Market Pulse Radar application.

## Services

The docker-compose stack includes the following services:

- **Postgres+Timescale+pgvector**: Database with time-series and vector capabilities
- **MinIO**: S3-compatible object storage
- **FastAPI**: Main application API
- **Prefect**: Workflow orchestration
- **Grafana**: Monitoring dashboards
- **Prometheus**: Metrics collection
- **Loki**: Log aggregation

## Quick Start

1. **Start the stack**:
   ```bash
   make up
   ```

2. **Initialize the database**:
   ```bash
   make init-db
   ```

3. **Run migrations**:
   ```bash
   make migrate
   ```

4. **Access services**:
   - FastAPI: http://localhost:8000/docs
   - Grafana: http://localhost:3000 (admin/admin)
   - Prometheus: http://localhost:9090
   - Prefect: http://localhost:4200
   - MinIO Console: http://localhost:9001 (minioadmin/minioadmin)

## Database Schema

The database includes the following tables:

- `article`: News articles and social posts
- `article_embed`: Vector embeddings for similarity search
- `article_ticker`: Article-ticker relationships
- `price_bar`: OHLCV price data (hypertable)
- `signal`: Computed signals (hypertable)

## Migrations

Alembic is used for database migrations. The initial migration creates the complete schema with:

- All required tables
- TimescaleDB hypertables for time-series data
- pgvector indexes for similarity search
- Proper indexes for performance

To run migrations:
```bash
make migrate
```

## Health Checks

All services include health checks to ensure they're running properly. The docker-compose will wait for dependencies to be healthy before starting dependent services.

## Monitoring

- **Prometheus** scrapes metrics from all services
- **Grafana** provides dashboards for visualization
- **Loki** aggregates logs from all containers

## Configuration

Environment variables are configured in `.env` file. See `.env.example` for the required variables.
