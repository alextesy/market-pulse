# Market Pulse Collectors Framework

The collectors framework provides a robust, production-ready system for ingesting data from external sources into the Market Pulse data lake.

## Overview

The framework implements the Epic D design with the following key components:

- **Collector Protocol**: Standardized interface for all data sources
- **Lake Writer**: Batched, atomic writes to MinIO with shard rotation
- **Rate Limiting**: Token bucket rate limiter with exponential backoff
- **Data Quality**: Validation and canonicalization for deduplication
- **Observability**: Prometheus metrics and structured logging
- **Testing**: Comprehensive test suite with mocking

## Architecture

```
[External Sources] 
        ↓
[Collector Adapters] → [Rate Limiter] → [Data Quality] 
        ↓
[Lake Writer] → [MinIO Storage]
        ↓
[Raw→DB Loader] (future pipeline)
```

## Quick Start

### 1. Start the Infrastructure

```bash
# Start MinIO and other services
make up
```

### 2. Run the Demo

```bash
# Full end-to-end demo
make demo-collectors

# Interface demonstration
make demo-interface

# Data quality validation demo
make demo-validation
```

### 3. Run Collectors

```bash
# Run noop collector for testing
make ingest-noop

# Run all enabled collectors
make ingest
```

### 4. Run Tests

```bash
# Run collector-specific tests
make test-collectors

# Run all tests
make test
```

## Components

### Collector Interface

All collectors implement the `Collector` protocol:

```python
class Collector(Protocol):
    name: ClassVar[str]
    
    def fetch(
        self, 
        since: datetime, 
        until: Optional[datetime] = None
    ) -> Iterable[IngestItem]:
        """Fetch items from source between given time range."""
        ...
```

**Key Properties:**
- Stateless: No internal state, checkpointing handled externally
- Time-bounded: Fetches data for specific time ranges
- Generator: Yields `IngestItem` DTOs for memory efficiency
- Pure: No database calls, only external I/O and mapping

### Lake Writer

The `LakeWriter` handles atomic writes to MinIO with configurable shard rotation:

```python
writer = LakeWriter(
    s3_client=s3_client,
    bucket="market-pulse-raw",
    source_name="gdelt",
    max_items=5000,        # Items per shard
    max_bytes=50_000_000,  # 50MB per shard  
    max_age=120.0          # 120 seconds max age
)

writer.write_items(items)
```

**Features:**
- Atomic writes (temp → final key)
- Gzip compression
- Integrity footers with SHA256 hashes
- Automatic shard rotation
- Prometheus metrics integration

### Object Storage Schema

Objects are stored with the following path structure:

```
s3://bucket/raw/dt=YYYY/MM/DD/source=<name>/part-<timestamp>-<uuid>.jsonl.gz
```

Each object contains:
- NDJSON format (one JSON object per line)
- Metadata wrapper with schema version, trace ID, etc.
- Footer record with item count and integrity hash
- Gzip compression

### Rate Limiting

The framework includes a token bucket rate limiter with exponential backoff:

```python
@with_retries(max_tries=5, retriable_codes={429, 500, 502, 503, 504})
def fetch_data(self):
    # Your HTTP request here
    pass
```

**Features:**
- Configurable capacity and refill rate
- Exponential backoff with jitter
- Automatic retry on retriable errors
- Prometheus metrics for backoff events

### Data Quality

Built-in validation ensures data quality:

```python
result = validate_ingest_item(item)
if not result.is_valid:
    for error in result.errors:
        logger.warning(f"Quality issue: {error}")
```

**Validations:**
- URL format and suspicious pattern detection
- Text length and content quality checks  
- Language code validation
- Timestamp consistency
- URL canonicalization for deduplication

### Configuration

Configuration is managed through `configs/sources.yaml`:

```yaml
sources:
  gdelt:
    enabled: true
    rate_limit_per_min: 60
    timeout: 30
    user_agent: "MarketPulseBot/0.1"
    retry_attempts: 5

lake:
  bucket: "market-pulse-raw"
  endpoint_url: "http://localhost:9000"
  max_items_per_shard: 5000
  enable_dedupe: true

observability:
  metrics:
    enabled: true
    port: 8080
  logging:
    level: "INFO"
    format: "json"
```

## Metrics

The framework exposes Prometheus metrics:

### Collector Metrics
- `ingest_items_total{source}` - Total items ingested
- `ingest_http_requests_total{source,code}` - HTTP requests by status
- `ingest_http_latency_seconds{source}` - Request latency distribution
- `ingest_backoff_total{source,reason}` - Backoff events
- `ingest_items_dropped_total{source,reason}` - Dropped items

### Lake Metrics  
- `ingest_shard_bytes{source}` - Shard size distribution
- `lake_write_failures_total{source}` - Write failures

### Data Quality Metrics
- `dq_validation_failures_total{source,check}` - Validation failures
- `dq_items_quarantined_total{source,reason}` - Quarantined items

Access metrics at: `http://localhost:8080/metrics`

## Logging

Structured JSON logging with OpenTelemetry trace correlation:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "INFO", 
  "logger": "collectors.gdelt",
  "message": "Collector run completed",
  "source": "gdelt",
  "items_processed": 1250,
  "duration": 45.2,
  "trace_id": "abc123...",
  "span_id": "def456..."
}
```

## Testing

### Unit Tests

```bash
# Run all collector tests
pytest tests/test_collectors.py -v

# Run specific test class
pytest tests/test_collectors.py::TestTokenBucketRateLimiter -v
```

### Integration Tests (with Docker)

```bash
# Start services
make up

# Run integration tests  
pytest tests/test_collectors.py::TestLakeWriter -v
```

### Mocking for Development

The framework includes extensive mocking support:

- `@mock_s3` for S3/MinIO operations
- `httpx.MockTransport` for HTTP requests
- In-memory rate limiters for fast tests

## Implementation Checklist

### ✅ Completed (D1 Foundation)

- [x] Collector Protocol interface
- [x] Lake writer with shard rotation  
- [x] Rate limiting and backoff decorators
- [x] Prometheus metrics and structured logging
- [x] Data quality validators
- [x] Comprehensive test suite
- [x] Example noop collector
- [x] End-to-end demo
- [x] Configuration system
- [x] Makefile commands

### 🔄 Next Steps (D2+)

- [ ] GDELT collector implementation
- [ ] SEC RSS collector implementation  
- [ ] Stocktwits collector implementation
- [ ] Raw→DB loader pipeline
- [ ] Prefect workflow integration
- [ ] Advanced deduplication with simhash
- [ ] Collector health checks and monitoring

## Usage Examples

### Basic Collector Run

```python
from collectors.runner import CollectorRunner

runner = CollectorRunner("configs/sources.yaml")
result = runner.run_collector("noop", since=datetime.now() - timedelta(hours=2))
print(f"Collected {result['items_collected']} items")
```

### Custom Collector Implementation

```python
class MyCollector(Collector):
    name: ClassVar[str] = "mycollector"
    
    def fetch(self, since: datetime, until: Optional[datetime] = None) -> Iterable[IngestItem]:
        # Implement your data fetching logic
        for item_data in self.fetch_from_api(since, until):
            yield IngestItem(
                source=self.name,
                url=item_data["url"],
                title=item_data["title"],
                # ... other fields
            )
```

### Direct Lake Writer Usage

```python
from collectors.base import create_s3_client, LakeWriter
from collectors.noop import NoopCollector

s3_client = create_s3_client(endpoint_url="http://localhost:9000")
writer = LakeWriter(s3_client, "my-bucket", "test-source")
collector = NoopCollector()

items = collector.fetch(since=datetime.now() - timedelta(hours=1))
writer.write_items(items)
```

## Security & Compliance

The framework implements several security and compliance features:

- **User-Agent**: Descriptive user agent with contact information
- **Rate Limiting**: Respects API rate limits and terms of service
- **License Tracking**: Stores license information for each item
- **Source Attribution**: Maintains original URLs and retrieval timestamps
- **No Paywall Scraping**: Designed for public APIs and feeds only

## Performance Characteristics

- **Memory Efficient**: Streaming processing with generators
- **Batched Writes**: Configurable shard sizes for optimal throughput
- **Compression**: Gzip compression reduces storage costs by ~70%
- **Parallel Processing**: Thread-safe components for concurrent collection
- **Backpressure Handling**: Rate limiting prevents API abuse

## Troubleshooting

### Common Issues

1. **MinIO Connection Errors**
   ```bash
   # Check MinIO is running
   docker ps | grep minio
   
   # Check endpoint configuration
   curl http://localhost:9000/minio/health/live
   ```

2. **Rate Limiting Issues**
   ```python
   # Adjust rate limits in configuration
   rate_limit_per_min: 30  # Reduce from 60
   ```

3. **Memory Usage**
   ```python
   # Reduce shard sizes
   max_items_per_shard: 1000  # Reduce from 5000
   max_bytes_per_shard: 10000000  # Reduce from 50MB
   ```

4. **Test Failures**
   ```bash
   # Install test dependencies
   uv sync
   
   # Run with verbose output
   pytest tests/test_collectors.py -v -s
   ```

## Contributing

When adding new collectors:

1. Implement the `Collector` protocol
2. Add comprehensive tests with mocking
3. Update configuration schema
4. Add Prometheus metrics
5. Include data quality validations
6. Update this documentation

See existing collectors like `NoopCollector` for reference implementation patterns.

