"""Base collector interfaces, rate limiting, and lake writer."""

import gzip
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, ClassVar, Iterable, Optional, Protocol

import boto3
from opentelemetry import trace
from prometheus_client import Counter, Histogram
from pydantic import BaseModel

from market_pulse.models.dto import IngestItem

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

# Prometheus metrics
ingest_items_total = Counter(
    "ingest_items_total", "Total ingested items", ["source"]
)
ingest_http_requests_total = Counter(
    "ingest_http_requests_total", "Total HTTP requests", ["source", "code"]
)
ingest_http_latency_seconds = Histogram(
    "ingest_http_latency_seconds", "HTTP request latency", ["source"]
)
ingest_backoff_total = Counter(
    "ingest_backoff_total", "Total backoff events", ["source", "reason"]
)
ingest_shard_bytes = Histogram(
    "ingest_shard_bytes", "Shard size in bytes", ["source"]
)
lake_write_failures_total = Counter(
    "lake_write_failures_total", "Lake write failures", ["source"]
)
ingest_items_dropped_total = Counter(
    "ingest_items_dropped_total", "Dropped items", ["source", "reason"]
)


class Collector(Protocol):
    """Protocol for data collectors."""
    
    name: ClassVar[str]
    
    def fetch(
        self, 
        since: datetime, 
        until: Optional[datetime] = None
    ) -> Iterable[IngestItem]:
        """Fetch items from source between given time range.
        
        Args:
            since: Start time (inclusive, UTC timezone-aware)
            until: End time (exclusive, UTC timezone-aware). Defaults to now()
            
        Yields:
            IngestItem: Validated DTOs from the source
            
        Note:
            No DB calls inside; pure IO + mapping.
            Adapters are stateless - checkpointing maintained externally.
        """
        ...


class LakeObjectMetadata(BaseModel):
    """Metadata for a lake object."""
    
    schema_version: str = "1.0"
    producer: str
    fetched_at: datetime
    trace_id: str
    item_count: int
    sha256_hash: str


class LakeShardFooter(BaseModel):
    """Footer record for shard integrity checking."""
    
    item_count: int
    sha256_lines: str  # SHA256 of all line hashes concatenated


class TokenBucketRateLimiter:
    """Token bucket rate limiter with configurable capacity and refill rate."""
    
    def __init__(self, capacity: int, refill_rate: float):
        """Initialize rate limiter.
        
        Args:
            capacity: Maximum number of tokens (requests)
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
    
    def acquire(self, tokens: int = 1) -> bool:
        """Attempt to acquire tokens from bucket.
        
        Args:
            tokens: Number of tokens to acquire
            
        Returns:
            True if tokens acquired, False otherwise
        """
        now = time.time()
        elapsed = now - self.last_refill
        
        # Refill tokens based on elapsed time
        self.tokens = min(
            self.capacity, 
            self.tokens + elapsed * self.refill_rate
        )
        self.last_refill = now
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def wait_time(self, tokens: int = 1) -> float:
        """Calculate wait time for tokens to be available.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Wait time in seconds
        """
        if self.tokens >= tokens:
            return 0.0
        
        needed = tokens - self.tokens
        return needed / self.refill_rate


class LakeWriter:
    """Write IngestItem streams to MinIO in NDJSON shards."""
    
    def __init__(
        self,
        s3_client: Any,
        bucket: str,
        source_name: str,
        max_items: int = 5000,
        max_bytes: int = 50 * 1024 * 1024,  # 50MB
        max_age: float = 120.0,  # 120 seconds
    ):
        """Initialize lake writer.
        
        Args:
            s3_client: boto3 S3 client or compatible
            bucket: S3 bucket name
            source_name: Source identifier for partitioning
            max_items: Maximum items per shard
            max_bytes: Maximum bytes per shard (post-gzip)
            max_age: Maximum age in seconds before forced flush
        """
        self.s3_client = s3_client
        self.bucket = bucket
        self.source_name = source_name
        self.max_items = max_items
        self.max_bytes = max_bytes
        self.max_age = max_age
        
        self._current_shard: list[str] = []
        self._current_bytes = 0
        self._shard_start_time = time.time()
        self._line_hashes: list[str] = []
    
    def write_items(self, items: Iterable[IngestItem]) -> None:
        """Write items to lake, handling shard rotation."""
        for item in items:
            try:
                self._add_item_to_shard(item)
                ingest_items_total.labels(source=self.source_name).inc()
                
                if self._should_rotate_shard():
                    self._flush_current_shard()
                    
            except Exception as e:
                logger.warning(
                    "Failed to process item",
                    extra={
                        "source": self.source_name,
                        "error": str(e),
                        "url": str(item.url),
                    }
                )
                ingest_items_dropped_total.labels(
                    source=self.source_name, reason="processing_error"
                ).inc()
        
        # Final flush if there are remaining items
        if self._current_shard:
            self._flush_current_shard()
    
    def _add_item_to_shard(self, item: IngestItem) -> None:
        """Add item to current shard."""
        # Create object with metadata wrapper
        obj = {
            "schema_version": "1.0",
            "payload": item.model_dump(mode="json"),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "producer": f"collector-{self.source_name}",
            "trace_id": trace.get_current_span().get_span_context().trace_id,
        }
        
        line = json.dumps(obj, separators=(",", ":"))
        line_bytes = line.encode("utf-8")
        
        self._current_shard.append(line)
        self._current_bytes += len(line_bytes)
        
        # Track line hash for integrity
        line_hash = hashlib.sha256(line_bytes).hexdigest()
        self._line_hashes.append(line_hash)
    
    def _should_rotate_shard(self) -> bool:
        """Check if current shard should be rotated."""
        return (
            len(self._current_shard) >= self.max_items
            or self._current_bytes >= self.max_bytes
            or (time.time() - self._shard_start_time) >= self.max_age
        )
    
    def _flush_current_shard(self) -> None:
        """Flush current shard to MinIO."""
        if not self._current_shard:
            return
            
        try:
            # Add footer record
            footer = LakeShardFooter(
                item_count=len(self._current_shard),
                sha256_lines=hashlib.sha256(
                    "".join(self._line_hashes).encode()
                ).hexdigest()
            )
            footer_line = json.dumps(
                {"_footer": footer.model_dump()}, separators=(",", ":")
            )
            self._current_shard.append(footer_line)
            
            # Generate object key
            now = datetime.now(timezone.utc)
            dt_partition = now.strftime("%Y/%m/%d")
            timestamp = now.strftime("%Y%m%dT%H%M%SZ")
            rand_suffix = uuid.uuid4().hex[:8]
            
            object_key = (
                f"raw/dt={dt_partition}/source={self.source_name}/"
                f"part-{timestamp}-{rand_suffix}.jsonl.gz"
            )
            
            # Gzip compress content
            content = "\n".join(self._current_shard) + "\n"
            compressed = gzip.compress(content.encode("utf-8"))
            
            # Atomic write: upload to temp key, then copy to final
            temp_key = f"temp/{object_key}-{uuid.uuid4().hex}"
            
            # Upload to temp location
            self.s3_client.put_object(
                Bucket=self.bucket,
                Key=temp_key,
                Body=compressed,
                ContentType="application/gzip",
                ContentEncoding="gzip",
            )
            
            # Atomic move to final location
            self.s3_client.copy_object(
                Bucket=self.bucket,
                CopySource={"Bucket": self.bucket, "Key": temp_key},
                Key=object_key,
            )
            
            # Clean up temp object
            self.s3_client.delete_object(Bucket=self.bucket, Key=temp_key)
            
            # Record metrics
            ingest_shard_bytes.labels(source=self.source_name).observe(
                len(compressed)
            )
            
            logger.info(
                "Shard written successfully",
                extra={
                    "source": self.source_name,
                    "object_key": object_key,
                    "item_count": len(self._current_shard) - 1,  # Exclude footer
                    "compressed_bytes": len(compressed),
                    "trace_id": trace.get_current_span().get_span_context().trace_id,
                }
            )
            
        except Exception as e:
            logger.error(
                "Failed to write shard",
                extra={
                    "source": self.source_name,
                    "error": str(e),
                    "item_count": len(self._current_shard),
                }
            )
            lake_write_failures_total.labels(source=self.source_name).inc()
            raise
        finally:
            # Reset shard state
            self._current_shard = []
            self._current_bytes = 0
            self._shard_start_time = time.time()
            self._line_hashes = []


def create_s3_client(
    endpoint_url: Optional[str] = None,
    aws_access_key_id: Optional[str] = None,
    aws_secret_access_key: Optional[str] = None,
    region_name: str = "us-east-1",
) -> Any:
    """Create S3 client for MinIO or AWS S3.
    
    Args:
        endpoint_url: MinIO endpoint URL (e.g., "http://localhost:9000")
        aws_access_key_id: AWS access key or MinIO access key
        aws_secret_access_key: AWS secret key or MinIO secret key  
        region_name: AWS region name
        
    Returns:
        Configured boto3 S3 client
    """
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=aws_access_key_id,
        aws_secret_access_key=aws_secret_access_key,
        region_name=region_name,
    )

