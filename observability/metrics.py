"""Prometheus metrics for Market Pulse collectors and pipelines."""

import logging

from prometheus_client import Counter, Histogram, start_http_server

logger = logging.getLogger(__name__)

# Collector metrics (already defined in base.py, re-exported here for convenience)

# Loader metrics (for raw→DB pipeline)
loader_rows_upserted_total = Counter(
    "loader_rows_upserted_total", "Total rows upserted to DB", ["source"]
)

loader_duplicates_skipped_total = Counter(
    "loader_duplicates_skipped_total", "Total duplicate rows skipped", ["source"]
)

loader_latency_seconds = Histogram(
    "loader_latency_seconds", "Loader operation latency", ["step"]
)

# Pipeline processing metrics
pipeline_items_processed_total = Counter(
    "pipeline_items_processed_total",
    "Total items processed by pipeline",
    ["stage", "source"],
)

pipeline_items_failed_total = Counter(
    "pipeline_items_failed_total",
    "Total items failed in pipeline",
    ["stage", "source", "reason"],
)

pipeline_processing_latency_seconds = Histogram(
    "pipeline_processing_latency_seconds",
    "Pipeline processing latency",
    ["stage", "source"],
)

# Data quality metrics
dq_validation_failures_total = Counter(
    "dq_validation_failures_total",
    "Total data quality validation failures",
    ["source", "check"],
)

dq_items_quarantined_total = Counter(
    "dq_items_quarantined_total",
    "Total items quarantined due to quality issues",
    ["source", "reason"],
)

# Storage metrics
storage_objects_created_total = Counter(
    "storage_objects_created_total",
    "Total storage objects created",
    ["bucket", "prefix"],
)

storage_operations_latency_seconds = Histogram(
    "storage_operations_latency_seconds",
    "Storage operation latency",
    ["operation", "bucket"],
)


def start_metrics_server(port: int = 8080) -> None:
    """Start Prometheus metrics HTTP server.

    Args:
        port: Port to serve metrics on
    """
    try:
        start_http_server(port)
        logger.info(f"Prometheus metrics server started on port {port}")
    except Exception as e:
        logger.error(f"Failed to start metrics server: {e}")
        raise


def get_all_metrics_info() -> dict:
    """Get information about all defined metrics.

    Returns:
        Dictionary with metric names and descriptions
    """
    metrics = {
        # Collector metrics
        "ingest_items_total": "Total ingested items by source",
        "ingest_http_requests_total": "Total HTTP requests by source and status code",
        "ingest_http_latency_seconds": "HTTP request latency distribution by source",
        "ingest_backoff_total": "Total backoff events by source and reason",
        "ingest_shard_bytes": "Shard size distribution in bytes by source",
        "lake_write_failures_total": "Total lake write failures by source",
        "ingest_items_dropped_total": "Total dropped items by source and reason",
        # Loader metrics
        "loader_rows_upserted_total": "Total rows upserted to DB by source",
        "loader_duplicates_skipped_total": "Total duplicate rows skipped by source",
        "loader_latency_seconds": "Loader operation latency by step",
        # Pipeline metrics
        "pipeline_items_processed_total": "Total items processed by pipeline stage and source",
        "pipeline_items_failed_total": "Total items failed in pipeline by stage, source, and reason",
        "pipeline_processing_latency_seconds": "Pipeline processing latency by stage and source",
        # Data quality metrics
        "dq_validation_failures_total": "Total data quality validation failures by source and check",
        "dq_items_quarantined_total": "Total items quarantined by source and reason",
        # Storage metrics
        "storage_objects_created_total": "Total storage objects created by bucket and prefix",
        "storage_operations_latency_seconds": "Storage operation latency by operation and bucket",
    }

    return metrics
