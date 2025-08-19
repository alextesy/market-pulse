"""Structured logging configuration and utilities."""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

from opentelemetry import trace


class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON.
        
        Args:
            record: Log record to format
            
        Returns:
            JSON-formatted log string
        """
        # Base log structure
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add trace information if available
        span = trace.get_current_span()
        if span.is_recording():
            span_context = span.get_span_context()
            log_entry["trace_id"] = format(span_context.trace_id, "032x")
            log_entry["span_id"] = format(span_context.span_id, "016x")
        
        # Add extra fields from record
        if hasattr(record, "extra") and record.extra:
            log_entry.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add source code location for non-INFO levels
        if record.levelno > logging.INFO:
            log_entry["location"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }
        
        return json.dumps(log_entry, separators=(",", ":"))


def setup_logging(
    level: str = "INFO",
    format_json: bool = True,
    include_stdlib: bool = False,
) -> None:
    """Configure structured logging for the application.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format_json: Whether to use JSON formatting
        include_stdlib: Whether to include stdlib logger output
    """
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    
    if format_json:
        formatter = StructuredFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    
    # Configure third-party loggers
    if not include_stdlib:
        # Reduce noise from common libraries
        logging.getLogger("boto3").setLevel(logging.WARNING)
        logging.getLogger("botocore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("opentelemetry").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with structured logging capabilities.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


def log_collector_progress(
    logger: logging.Logger,
    source: str,
    since: datetime,
    until: Optional[datetime],
    items_processed: int,
    items_dropped: int = 0,
    errors: int = 0,
) -> None:
    """Log structured collector progress information.
    
    Args:
        logger: Logger instance
        source: Source name
        since: Start timestamp
        until: End timestamp (optional)
        items_processed: Number of items successfully processed
        items_dropped: Number of items dropped due to errors
        errors: Number of errors encountered
    """
    logger.info(
        "Collector run completed",
        extra={
            "source": source,
            "since": since.isoformat(),
            "until": until.isoformat() if until else None,
            "items_processed": items_processed,
            "items_dropped": items_dropped,
            "errors": errors,
            "success_rate": items_processed / (items_processed + items_dropped) if (items_processed + items_dropped) > 0 else 0.0,
        }
    )


def log_lake_write(
    logger: logging.Logger,
    source: str,
    object_key: str,
    item_count: int,
    compressed_bytes: int,
    duration: float,
) -> None:
    """Log structured lake write information.
    
    Args:
        logger: Logger instance
        source: Source name
        object_key: S3 object key
        item_count: Number of items in shard
        compressed_bytes: Size of compressed shard
        duration: Write duration in seconds
    """
    logger.info(
        "Lake shard written",
        extra={
            "source": source,
            "object_key": object_key,
            "item_count": item_count,
            "compressed_bytes": compressed_bytes,
            "duration": duration,
            "items_per_second": item_count / duration if duration > 0 else 0,
            "bytes_per_second": compressed_bytes / duration if duration > 0 else 0,
        }
    )


def log_data_quality_issue(
    logger: logging.Logger,
    source: str,
    item_url: str,
    validation_errors: list[str],
    action: str = "dropped",
) -> None:
    """Log structured data quality issue.
    
    Args:
        logger: Logger instance
        source: Source name
        item_url: URL of problematic item
        validation_errors: List of validation error messages
        action: Action taken (dropped, quarantined, etc.)
    """
    logger.warning(
        "Data quality issue detected",
        extra={
            "source": source,
            "item_url": item_url,
            "validation_errors": validation_errors,
            "action": action,
            "error_count": len(validation_errors),
        }
    )


def log_pipeline_stage(
    logger: logging.Logger,
    stage: str,
    source: str,
    items_in: int,
    items_out: int,
    duration: float,
    errors: int = 0,
) -> None:
    """Log structured pipeline stage completion.
    
    Args:
        logger: Logger instance
        stage: Pipeline stage name
        source: Source name
        items_in: Number of items input to stage
        items_out: Number of items output from stage
        duration: Stage duration in seconds
        errors: Number of errors in stage
    """
    logger.info(
        "Pipeline stage completed",
        extra={
            "stage": stage,
            "source": source,
            "items_in": items_in,
            "items_out": items_out,
            "items_filtered": items_in - items_out,
            "duration": duration,
            "errors": errors,
            "items_per_second": items_in / duration if duration > 0 else 0,
            "success_rate": (items_in - errors) / items_in if items_in > 0 else 0.0,
        }
    )

