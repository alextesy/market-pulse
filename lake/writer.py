"""S3/MinIO lake writer with advanced shard management."""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from botocore.exceptions import ClientError

from collectors.base import LakeWriter

logger = logging.getLogger(__name__)


class AdvancedLakeWriter(LakeWriter):
    """Extended lake writer with cleanup and monitoring capabilities."""
    
    def __init__(
        self,
        s3_client: Any,
        bucket: str,
        source_name: str,
        max_items: int = 5000,
        max_bytes: int = 50 * 1024 * 1024,  # 50MB
        max_age: float = 120.0,  # 120 seconds
        temp_cleanup_interval: float = 3600.0,  # 1 hour
    ):
        """Initialize advanced lake writer.
        
        Args:
            s3_client: boto3 S3 client or compatible
            bucket: S3 bucket name
            source_name: Source identifier for partitioning
            max_items: Maximum items per shard
            max_bytes: Maximum bytes per shard (post-gzip)
            max_age: Maximum age in seconds before forced flush
            temp_cleanup_interval: Interval for cleaning up temp objects
        """
        super().__init__(s3_client, bucket, source_name, max_items, max_bytes, max_age)
        self.temp_cleanup_interval = temp_cleanup_interval
        self._last_cleanup = time.time()
    
    def write_items_with_dedupe(
        self, 
        items, 
        bloom_filter_size: int = 100000,
        bloom_hash_count: int = 5
    ) -> None:
        """Write items with in-memory Bloom filter deduplication.
        
        Args:
            items: Iterable of IngestItem objects
            bloom_filter_size: Size of Bloom filter bit array
            bloom_hash_count: Number of hash functions for Bloom filter
        """
        # Simple Bloom filter implementation
        bloom_filter = BloomFilter(bloom_filter_size, bloom_hash_count)
        dedupe_count = 0
        
        for item in items:
            # Create deduplication key from canonical URL
            from dq.validators import canonicalize_url
            dedupe_key = canonicalize_url(str(item.url))
            
            if bloom_filter.might_contain(dedupe_key):
                logger.debug(
                    "Potential duplicate detected",
                    extra={
                        "source": self.source_name,
                        "url": dedupe_key,
                    }
                )
                dedupe_count += 1
                continue
            
            bloom_filter.add(dedupe_key)
            self._add_item_to_shard(item)
            
            if self._should_rotate_shard():
                self._flush_current_shard()
        
        # Final flush
        if self._current_shard:
            self._flush_current_shard()
        
        # Cleanup temp objects periodically
        if time.time() - self._last_cleanup > self.temp_cleanup_interval:
            self._cleanup_temp_objects()
        
        if dedupe_count > 0:
            logger.info(
                "Deduplication summary",
                extra={
                    "source": self.source_name,
                    "duplicates_skipped": dedupe_count,
                }
            )
    
    def _cleanup_temp_objects(self) -> None:
        """Clean up old temporary objects."""
        try:
            # List all objects in temp/ prefix
            paginator = self.s3_client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=self.bucket, Prefix="temp/")
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=1)
            deleted_count = 0
            
            for page in pages:
                if "Contents" not in page:
                    continue
                    
                for obj in page["Contents"]:
                    if obj["LastModified"].replace(tzinfo=timezone.utc) < cutoff_time:
                        try:
                            self.s3_client.delete_object(
                                Bucket=self.bucket,
                                Key=obj["Key"]
                            )
                            deleted_count += 1
                        except ClientError as e:
                            logger.warning(
                                "Failed to delete temp object",
                                extra={
                                    "key": obj["Key"],
                                    "error": str(e),
                                }
                            )
            
            self._last_cleanup = time.time()
            
            if deleted_count > 0:
                logger.info(
                    "Cleaned up temp objects",
                    extra={
                        "deleted_count": deleted_count,
                        "cutoff_time": cutoff_time.isoformat(),
                    }
                )
                
        except Exception as e:
            logger.error(
                "Failed to cleanup temp objects",
                extra={"error": str(e)}
            )


class BloomFilter:
    """Simple Bloom filter for deduplication."""
    
    def __init__(self, size: int, hash_count: int):
        """Initialize Bloom filter.
        
        Args:
            size: Size of bit array
            hash_count: Number of hash functions
        """
        self.size = size
        self.hash_count = hash_count
        self.bit_array = [False] * size
    
    def _hash(self, item: str, seed: int) -> int:
        """Hash function with seed."""
        import hashlib
        hash_obj = hashlib.md5(f"{item}:{seed}".encode())
        return int(hash_obj.hexdigest(), 16) % self.size
    
    def add(self, item: str) -> None:
        """Add item to Bloom filter."""
        for i in range(self.hash_count):
            index = self._hash(item, i)
            self.bit_array[index] = True
    
    def might_contain(self, item: str) -> bool:
        """Check if item might be in the set (may have false positives)."""
        for i in range(self.hash_count):
            index = self._hash(item, i)
            if not self.bit_array[index]:
                return False
        return True


def ensure_bucket_exists(s3_client: Any, bucket_name: str) -> None:
    """Ensure S3 bucket exists, create if it doesn't.
    
    Args:
        s3_client: boto3 S3 client
        bucket_name: Name of bucket to ensure exists
    """
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        logger.info(f"Bucket {bucket_name} exists")
    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        if error_code == "404":
            try:
                s3_client.create_bucket(Bucket=bucket_name)
                logger.info(f"Created bucket {bucket_name}")
            except ClientError as create_error:
                logger.error(
                    f"Failed to create bucket {bucket_name}: {create_error}"
                )
                raise
        else:
            logger.error(f"Error checking bucket {bucket_name}: {e}")
            raise


def list_lake_objects(
    s3_client: Any,
    bucket: str,
    source: Optional[str] = None,
    date_prefix: Optional[str] = None,
) -> list[dict]:
    """List objects in the lake with optional filtering.
    
    Args:
        s3_client: boto3 S3 client
        bucket: Bucket name
        source: Optional source filter
        date_prefix: Optional date prefix (YYYY/MM/DD format)
        
    Returns:
        List of object metadata dictionaries
    """
    prefix = "raw/"
    if date_prefix:
        prefix += f"dt={date_prefix}/"
    if source:
        prefix += f"source={source}/"
    
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
        
        objects = []
        for page in pages:
            if "Contents" in page:
                objects.extend(page["Contents"])
        
        return objects
        
    except ClientError as e:
        logger.error(f"Failed to list objects with prefix {prefix}: {e}")
        raise

