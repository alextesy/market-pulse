up: ## start local stack
	docker-compose -f infra/docker-compose.yml up -d

down: ## stop stack
	docker-compose -f infra/docker-compose.yml down -v

logs: ## follow logs
	docker-compose -f infra/docker-compose.yml logs -f --tail=200

init-db: ## create schema & extensions
	psql $$POSTGRES_URL -f sql/schema.sql

ingest: ## run all collectors once
	uv run python -m collectors.gdelt && \
	uv run python -m collectors.sec && \
	uv run python -m collectors.stocktwits

score: ## recompute signals for last N hours
	uv run python -m pipelines.scorer --hours 24

backtest: ## run backtest
	uv run python -m pipelines.backtest --window 1d

# CI and testing commands
test: ## run tests
	uv run pytest

test-cov: ## run tests with coverage
	uv run pytest --cov --cov-report=html --cov-report=term-missing

lint: ## run linting
	uv run ruff check .
	uv run black --check --diff .

lint-fix: ## run linting and fix issues
	uv run ruff check --fix .
	uv run black .

typecheck: ## run type checking
	uv run mypy .

security: ## run security checks
	uv run bandit -r market_pulse/ tests/ --exclude .venv,scripts/ || echo "Security check completed with warnings"

ci: ## run all CI checks locally
	$(MAKE) lint
	$(MAKE) typecheck
	$(MAKE) test

.PHONY: up down logs init-db ingest score backtest test test-cov lint lint-fix typecheck security ci
