# CI Fixes Summary

## Problem
The GitHub Actions CI was failing because integration tests were trying to connect to a PostgreSQL database that wasn't available in the CI environment. The error was:

```
psycopg.OperationalError: connection failed: connection to server at "127.0.0.1", port 5432 failed: Connection refused
```

## Root Cause
1. **Main test job** was running all tests including integration tests
2. **Integration tests** require a running database with TimescaleDB and pgvector extensions
3. **CI environment** didn't have a database set up for the main test job
4. **Integration test job** was using regular PostgreSQL instead of TimescaleDB

## Solution

### 1. Separated Unit and Integration Tests

**Updated `.github/workflows/ci.yml`:**
- **Main test job**: Now runs only unit tests using `pytest -m "not integration"`
- **Integration test job**: Runs only integration tests using `pytest -m integration`
- **Proper database setup**: Integration job now uses TimescaleDB with extensions

### 2. Added Integration Test Markers

**Updated `tests/integration/test_database.py`:**
- Added `@pytest.mark.integration` to all integration test functions
- Tests are now properly categorized and can be selectively run

### 3. Fixed Database Setup in CI

**Updated integration test job:**
- **Database image**: Changed from `postgres:16` to `timescale/timescaledb:latest-pg16`
- **Database name**: Changed from `market` to `market_pulse` to match schema
- **Extensions**: Added steps to enable TimescaleDB and pgvector extensions
- **Migrations**: Added step to run Alembic migrations before tests
- **PostgreSQL client**: Added installation of `postgresql-client` for `psql` commands

### 4. Updated Makefile Commands

**Updated `Makefile`:**
- `make test`: Now runs only unit tests (excluding integration)
- `make test-integration`: Runs only integration tests (requires database)
- `make test-all`: Runs all tests (requires database)
- `make test-cov`: Runs unit tests with coverage

## Configuration Changes

### GitHub Actions Workflow
```yaml
# Main test job
- name: Run unit tests (excluding integration tests)
  run: uv run pytest -m "not integration" --cov --cov-report=xml --cov-report=term-missing

# Integration test job
services:
  postgres:
    image: timescale/timescaledb:latest-pg16
    env:
      POSTGRES_DB: market_pulse
      # ... other config

steps:
  - name: Install PostgreSQL client
    run: sudo apt-get update && sudo apt-get install -y postgresql-client
  
  - name: Initialize database
    run: |
      psql $POSTGRES_URL -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
      psql $POSTGRES_URL -c "CREATE EXTENSION IF NOT EXISTS vector;"
  
  - name: Run migrations
    run: uv run alembic upgrade head
  
  - name: Run integration tests
    run: uv run pytest -m integration -v
```

### Test Markers
```python
@pytest.mark.integration
def test_hypertables_exist(db_connection: psycopg.Connection) -> None:
    # Test implementation
```

## Benefits

1. **Faster CI**: Unit tests run quickly without database setup
2. **Proper separation**: Integration tests only run when database is available
3. **Correct database**: Integration tests use TimescaleDB with required extensions
4. **Flexible testing**: Can run unit tests, integration tests, or both as needed
5. **Better organization**: Tests are properly categorized and marked

## Test Commands

- **Local development**: `make test` (unit tests only)
- **Local with database**: `make test-integration` (integration tests only)
- **Local complete**: `make test-all` (all tests)
- **CI**: Automatically runs unit tests in main job, integration tests in separate job

## Result

✅ **CI now passes** with proper separation of concerns:
- Unit tests run quickly without database dependencies
- Integration tests run in dedicated environment with proper database setup
- All tests pass both locally and in CI
- Code quality checks remain comprehensive
