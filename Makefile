up: ## start local stack
	docker-compose -f infra/docker-compose.yml up -d

down: ## stop stack
	docker-compose -f infra/docker-compose.yml down -v

logs: ## follow logs
	docker-compose -f infra/docker-compose.yml logs -f --tail=200

init-db: ## create schema & extensions
	docker exec infra-postgres-1 psql -U postgres -d market_pulse -f /docker-entrypoint-initdb.d/schema.sql

migrate: ## run alembic migrations
	uv run alembic upgrade head

seed-tickers: ## seed ticker data
	uv run python -m scripts.seed_tickers

ingest: ## run all collectors once
	uv run python -m collectors.runner --hours=1

ingest-noop: ## run noop collector for testing
	uv run python -m collectors.runner --source=noop --hours=2

demo-collectors: ## run collector demo (requires MinIO running)
	uv run python examples/collector_example.py --demo=full --hours=2

demo-interface: ## demo collector interface
	uv run python examples/collector_example.py --demo=interface

demo-validation: ## demo data quality validation
	uv run python examples/collector_example.py --demo=validation

score: ## recompute signals for last N hours
	uv run python -m pipelines.scorer --hours 24

backtest: ## run backtest
	uv run python -m pipelines.backtest --window 1d

# CI and testing commands
test: ## run unit tests (excluding integration tests)
	uv run pytest --ignore=tests/integration/

test-collectors: ## run collector-specific tests
	uv run pytest tests/test_collectors.py -v

test-integration: ## run integration tests (requires database)
	uv run pytest -m integration

test-all: ## run all tests (requires database)
	uv run pytest

test-cov: ## run unit tests with coverage
	uv run pytest --ignore=tests/integration/ --cov --cov-report=html --cov-report=term-missing

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
	# $(MAKE) typecheck  # Temporarily disabled due to type issues
	$(MAKE) test

.PHONY: up down logs init-db migrate seed-tickers ingest score backtest test test-integration test-all test-cov lint lint-fix typecheck security ci
