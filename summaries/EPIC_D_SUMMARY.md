Epic D — Collectors & Lake

Goal: Reliable, compliant ingestion from external sources → durable lake (MinIO) → idempotent load into DB. Must be observable, backfillable, and resilient to API hiccups. Non‑goals: paid firehose integrations, full‑text scraping behind paywalls.

Design overview

[SOURCES]
  GDELT / SEC RSS / Stocktwits
      │  (HTTP pull, rate-limited)
      ▼
[Collector adapters]
  - parse → IngestItem DTOs
  - attach metadata (license, source_id)
  - checkpoint `since`
      │
      ▼
[Lake writer]
  - NDJSON shards in MinIO
  - path: s3://raw_events/dt=YYYY/MM/DD/source=<name>/part-<ts>-<uuid>.jsonl.gz
  - rotate by {max_bytes, max_items, max_age}
      │
      ▼
[Raw→DB loader]
  - batch read new objects
  - normalize minimal fields (url_canonical)
  - upsert into `article`
  - record load_manifest to ensure exactly-once

Conventions

Time: all times UTC, tz‑aware. In objects and DB.

File format: newline‑delimited JSON (.jsonl.gz). One DTO per line; last line ends with 
.

Object schema: { schema_version, payload: IngestItem, fetched_at, producer, trace_id }.

Pathing: partition by dt (UTC day) and source to keep listings small.

Idempotency keys: url_canonical + title_simhash64 + optional source_id.

Compliance: store license, source_url (original URL), and retrieved_at for every item. Custom User‑Agent set per source.

Packages & modules

collectors/base.py — interfaces, rate‑limit/backoff, lake writer.

collectors/gdelt.py, collectors/sec.py, collectors/stocktwits.py — adapters.

lake/writer.py — S3/MinIO client, object naming, shard rotation.

loaders/raw_to_db.py — minio→DB upsert pipeline.

dq/validators.py — lightweight row checks (URL, lang, text len).

observability/metrics.py — Prom counters/histograms; OpenTelemetry trace ids.

Metrics (Prometheus names)

ingest_items_total{source}

ingest_http_requests_total{source,code}

ingest_http_latency_seconds_bucket{source}

ingest_backoff_total{source,reason}

ingest_shard_bytes{source}

lake_write_failures_total{source}

loader_rows_upserted_total{source}

loader_duplicates_skipped_total{source}

loader_latency_seconds_bucket{step} (list, read, parse, upsert)

Logging

Structured JSON with trace_id, source, since, until, object_key, counts. Log at INFO for progress, DEBUG for per‑item diagnostics, WARN for partial failures.

