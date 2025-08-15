.RECIPEPREFIX := >

up: ## start local stack
>docker compose -f infra/docker-compose.yml up -d

down: ## stop stack
>docker compose -f infra/docker-compose.yml down -v

logs: ## follow logs
>docker compose -f infra/docker-compose.yml logs -f --tail=200

init-db: ## create schema & extensions
>psql $$POSTGRES_URL -f sql/schema.sql

ingest: ## run all collectors once
>uv run python -m collectors.gdelt && \
>uv run python -m collectors.sec && \
>uv run python -m collectors.stocktwits

score: ## recompute signals for last N hours
>uv run python -m pipelines.scorer --hours 24

backtest: ## run backtest
>uv run python -m pipelines.backtest --window 1d

.PHONY: up down logs init-db ingest score backtest
