# CI/CD Pipeline

This document describes the Continuous Integration and Continuous Deployment setup for the Market Pulse project.

## Overview

The CI pipeline runs on every push to `main`/`dev` branches and on every Pull Request. It ensures code quality, type safety, and test coverage.

## CI Jobs

### 1. Lint Job
- **Purpose**: Ensures code follows style guidelines
- **Tools**: `ruff` and `black`
- **Runs**: On every PR and push
- **Failure**: Prevents merge if code doesn't meet style standards

### 2. Type Check Job
- **Purpose**: Ensures type safety across the codebase
- **Tools**: `mypy` with strict mode
- **Runs**: On every PR and push
- **Failure**: Prevents merge if type errors are found

### 3. Test Job
- **Purpose**: Runs unit tests with coverage reporting
- **Tools**: `pytest` with `pytest-cov`
- **Matrix**: Currently Python 3.11 (expandable to 3.12)
- **Coverage**: Reports to Codecov
- **Failure**: Prevents merge if tests fail

### 4. Integration Test Job
- **Purpose**: Tests integration with external services (database)
- **Tools**: `pytest` with PostgreSQL service
- **Dependencies**: Requires lint, typecheck, and test jobs to pass first
- **Failure**: Prevents merge if integration tests fail

### 5. Security Check Job
- **Purpose**: Identifies potential security vulnerabilities
- **Tools**: `bandit`
- **Output**: SARIF format for GitHub Security tab
- **Failure**: Non-blocking (warnings only)

## Local Development

### Running CI Checks Locally

```bash
# Run all CI checks
make ci

# Run individual checks
make lint          # Run linting
make typecheck     # Run type checking
make test          # Run tests
make test-cov      # Run tests with coverage
make security      # Run security checks
```

### Pre-commit Hooks

The project uses pre-commit hooks to catch issues before they reach CI:

```bash
# Install pre-commit hooks
pre-commit install

# Run pre-commit on all files
pre-commit run --all-files
```

## Testing the CI Pipeline

### Manual Testing

You can manually trigger a test PR creation to validate the CI pipeline:

1. Go to the "Actions" tab in GitHub
2. Select "Test PR Creation" workflow
3. Click "Run workflow"
4. Choose the test type:
   - `basic`: Creates a normal PR that should pass all checks
   - `lint-error`: Creates a PR with intentional lint errors
   - `type-error`: Creates a PR with intentional type errors
   - `test-failure`: Creates a PR with intentional test failures

### Expected Results

- **Basic test**: All CI jobs should pass (green checkmarks)
- **Error tests**: The corresponding job should fail (red X) while others may pass

## Configuration

### CI Configuration Files

- `.github/workflows/ci.yml`: Main CI workflow
- `.github/workflows/test-pr.yml`: Test PR creation workflow
- `pyproject.toml`: Tool configurations (ruff, black, mypy)
- `pytest.ini`: Pytest configuration
- `.pre-commit-config.yaml`: Pre-commit hooks configuration

### Environment Variables

The CI uses the following environment variables:

- `POSTGRES_URL`: Database connection string for integration tests
- `PYTHON_VERSION`: Python version to test against (default: 3.11)

### Caching

The CI pipeline caches:
- `uv` dependencies (`.venv` and `.uv/cache`)
- Cache keys are based on `pyproject.toml` and `uv.lock` hashes

## Troubleshooting

### Common Issues

1. **Lint failures**: Run `make lint-fix` to automatically fix most issues
2. **Type check failures**: Add proper type hints or use `# type: ignore` comments
3. **Test failures**: Check test output for specific failure reasons
4. **Integration test failures**: Ensure database service is properly configured

### Debugging Locally

```bash
# Run with verbose output
uv run pytest -v

# Run specific test file
uv run pytest tests/test_utils.py -v

# Run with coverage and show missing lines
uv run pytest --cov --cov-report=term-missing
```

## Future Enhancements

- [ ] Add Python 3.12 to the test matrix
- [ ] Add performance benchmarks
- [ ] Add dependency vulnerability scanning
- [ ] Add automated dependency updates
- [ ] Add deployment to staging environment
- [ ] Add automated changelog generation

## Acceptance Criteria

The CI pipeline is considered successful when:

- [x] All jobs pass on a clean PR
- [x] Lint job fails on code style violations
- [x] Type check job fails on type errors
- [x] Test job fails on test failures
- [x] Integration tests run with database service
- [x] Security checks run and report results
- [x] Coverage reporting works
- [x] Caching improves build times
- [x] Pre-commit hooks work locally
