"""Tests for collector framework and base functionality."""

import gzip
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import boto3
import pytest
from moto import mock_aws
from pydantic import AnyUrl

from collectors.base import (
    LakeWriter,
    TokenBucketRateLimiter,
)
from collectors.noop import NoopCollector
from collectors.retry import RateLimitedHttpClient, exponential_jitter, with_retries
from dq.validators import (
    canonicalize_url,
    compute_title_simhash64,
    validate_language,
    validate_text_content,
    validate_url,
)
from lake.writer import BloomFilter, ensure_bucket_exists
from market_pulse.models.dto import IngestItem


class TestTokenBucketRateLimiter:
    """Test token bucket rate limiter."""
    
    def test_initial_capacity(self):
        """Test initial token capacity."""
        limiter = TokenBucketRateLimiter(capacity=10, refill_rate=1.0)
        assert limiter.tokens == 10
        assert limiter.acquire(5) is True
        assert limiter.tokens == 5
    
    def test_acquire_insufficient_tokens(self):
        """Test acquiring more tokens than available."""
        limiter = TokenBucketRateLimiter(capacity=5, refill_rate=1.0)
        assert limiter.acquire(3) is True
        assert limiter.acquire(3) is False  # Only 2 tokens left
    
    def test_token_refill(self):
        """Test token refill over time."""
        limiter = TokenBucketRateLimiter(capacity=10, refill_rate=10.0)  # 10 tokens/sec
        
        # Drain tokens
        limiter.acquire(10)
        assert limiter.tokens == 0
        
        # Mock time passage
        with patch('time.time') as mock_time:
            # time.time() is called multiple times, so provide consistent values
            mock_time.return_value = 0.5  # 0.5 seconds later
            limiter.last_refill = 0  # Reset to time 0
            
            # Should have 5 tokens after 0.5 seconds at 10 tokens/sec
            assert limiter.acquire(5) is True
    
    def test_wait_time_calculation(self):
        """Test wait time calculation."""
        limiter = TokenBucketRateLimiter(capacity=10, refill_rate=2.0)  # 2 tokens/sec
        limiter.tokens = 1
        
        # Need 3 more tokens at 2 tokens/sec = 1.5 seconds
        wait_time = limiter.wait_time(4)
        assert wait_time == 1.5


class TestLakeWriter:
    """Test lake writer functionality."""
    
    @pytest.fixture
    def s3_client(self):
        """Create mock S3 client."""
        with mock_aws():
            client = boto3.client(
                "s3",
                region_name="us-east-1",
                aws_access_key_id="testing",
                aws_secret_access_key="testing",
            )
            client.create_bucket(Bucket="test-bucket")
            yield client
    
    @pytest.fixture
    def sample_items(self):
        """Create sample IngestItem objects."""
        base_time = datetime.now(timezone.utc)
        return [
            IngestItem(
                source="noop",
                source_id=f"test-{i}",
                url=AnyUrl(f"https://news.reuters.com/article/{i}"),
                published_at=base_time + timedelta(minutes=i),
                retrieved_at=base_time + timedelta(minutes=i+1),
                title=f"Test Article {i}",
                text=f"This is test article {i} with some content.",
                lang="en",
                license="MIT",
                meta={"test": True}
            )
            for i in range(5)
        ]
    
    def test_lake_writer_creation(self, s3_client):
        """Test lake writer creation."""
        writer = LakeWriter(
            s3_client=s3_client,
            bucket="test-bucket",
            source_name="test",
            max_items=10,
            max_bytes=1024,
            max_age=60,
        )
        
        assert writer.source_name == "test"
        assert writer.max_items == 10
        assert writer.max_bytes == 1024
        assert writer.max_age == 60
    
    def test_write_single_item(self, s3_client, sample_items):
        """Test writing a single item."""
        writer = LakeWriter(
            s3_client=s3_client,
            bucket="test-bucket", 
            source_name="test",
            max_items=1,  # Force immediate flush
        )
        
        writer.write_items([sample_items[0]])
        
        # Check that object was created
        objects = s3_client.list_objects_v2(Bucket="test-bucket")
        assert "Contents" in objects
        assert len(objects["Contents"]) == 1
        
        # Check object key format
        key = objects["Contents"][0]["Key"]
        assert key.startswith("raw/dt=")
        assert "source=test" in key
        assert key.endswith(".jsonl.gz")
    
    def test_write_multiple_items(self, s3_client, sample_items):
        """Test writing multiple items in batch."""
        writer = LakeWriter(
            s3_client=s3_client,
            bucket="test-bucket",
            source_name="test",
            max_items=10,  # Won't flush until manual call
        )
        
        writer.write_items(sample_items)
        
        # Check that shard was created
        objects = s3_client.list_objects_v2(Bucket="test-bucket")
        assert "Contents" in objects
        assert len(objects["Contents"]) == 1
    
    def test_shard_rotation_by_count(self, s3_client, sample_items):
        """Test shard rotation based on item count."""
        writer = LakeWriter(
            s3_client=s3_client,
            bucket="test-bucket",
            source_name="test",
            max_items=2,  # Force rotation after 2 items
        )
        
        writer.write_items(sample_items)  # 5 items, should create 3 shards
        
        objects = s3_client.list_objects_v2(Bucket="test-bucket")
        assert len(objects["Contents"]) == 3  # 2+2+1 items across shards
    
    def test_shard_content_format(self, s3_client, sample_items):
        """Test shard content format and compression."""
        writer = LakeWriter(
            s3_client=s3_client,
            bucket="test-bucket",
            source_name="test",
            max_items=1,
        )
        
        writer.write_items([sample_items[0]])
        
        # Get object and decompress
        objects = s3_client.list_objects_v2(Bucket="test-bucket")
        key = objects["Contents"][0]["Key"]
        
        obj = s3_client.get_object(Bucket="test-bucket", Key=key)
        compressed_data = obj["Body"].read()
        decompressed_data = gzip.decompress(compressed_data).decode("utf-8")
        
        lines = decompressed_data.strip().split("\n")
        assert len(lines) == 2  # 1 data line + 1 footer line
        
        # Check data line format
        data_line = json.loads(lines[0])
        assert "schema_version" in data_line
        assert "payload" in data_line
        assert "fetched_at" in data_line
        assert "producer" in data_line
        
        # Check footer format
        footer_line = json.loads(lines[1])
        assert "_footer" in footer_line
        assert "item_count" in footer_line["_footer"]
        assert "sha256_lines" in footer_line["_footer"]


class TestNoopCollector:
    """Test noop collector."""
    
    def test_collector_interface(self):
        """Test that NoopCollector implements Collector protocol."""
        collector = NoopCollector()
        assert hasattr(collector, "name")
        assert hasattr(collector, "fetch")
        assert collector.name == "noop"
    
    def test_fetch_items_count(self):
        """Test that correct number of items are generated."""
        collector = NoopCollector(items_per_hour=10)
        
        since = datetime.now(timezone.utc) - timedelta(hours=2)
        until = datetime.now(timezone.utc)
        
        items = list(collector.fetch(since, until))
        assert len(items) == 20  # 2 hours * 10 items/hour
    
    def test_fetch_with_default_until(self):
        """Test fetch with default until parameter."""
        collector = NoopCollector(items_per_hour=24)  # 1 item per 2.5 minutes
        
        since = datetime.now(timezone.utc) - timedelta(minutes=10)
        items = list(collector.fetch(since))  # until defaults to now
        
        # Should generate at least 1 item for 10 minutes
        assert len(items) >= 1
    
    def test_item_format(self):
        """Test generated item format and content."""
        collector = NoopCollector()
        
        since = datetime.now(timezone.utc) - timedelta(minutes=10)
        items = list(collector.fetch(since))
        
        assert len(items) > 0
        item = items[0]
        
        # Test IngestItem structure
        assert item.source == "noop"
        assert item.source_id.startswith("noop-")
        assert str(item.url).startswith("https://example.com/article/")
        assert item.lang == "en"
        assert item.license == "CC BY 4.0"
        assert "synthetic" in item.meta
        assert item.meta["synthetic"] is True


class TestRetryDecorator:
    """Test retry and backoff functionality."""
    
    def test_exponential_jitter(self):
        """Test exponential backoff with jitter calculation."""
        # Base case
        delay1 = exponential_jitter(1, base_delay=1.0, max_delay=60.0)
        assert 0.5 <= delay1 <= 1.5  # 1.0 * [0.5, 1.5] jitter range
        
        # Exponential growth
        delay2 = exponential_jitter(2, base_delay=1.0, max_delay=60.0) 
        delay3 = exponential_jitter(3, base_delay=1.0, max_delay=60.0)
        
        # Should generally increase (though jitter may cause some variance)
        assert delay2 > delay1 * 0.8  # Account for jitter
        assert delay3 > delay2 * 0.8
        
        # Max delay cap
        delay_large = exponential_jitter(10, base_delay=1.0, max_delay=5.0)
        assert delay_large <= 5.0 * 1.5  # Max delay * max jitter
    
    def test_successful_request_no_retry(self):
        """Test successful request doesn't trigger retry."""
        call_count = 0
        
        @with_retries(max_tries=3)
        def mock_request():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = mock_request()
        assert result == "success"
        assert call_count == 1
    
    def test_retry_on_retriable_exception(self):
        """Test retry behavior on retriable exceptions."""
        call_count = 0
        
        @with_retries(max_tries=3, retriable_exceptions={ValueError})
        def mock_request():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary error")
            return "success"
        
        with patch('time.sleep'):  # Mock sleep to speed up test
            result = mock_request()
        
        assert result == "success"
        assert call_count == 3
    
    def test_max_retries_exceeded(self):
        """Test behavior when max retries are exceeded."""
        @with_retries(max_tries=2, retriable_exceptions={ValueError})
        def mock_request():
            raise ValueError("Persistent error")
        
        with patch('time.sleep'):
            with pytest.raises(ValueError, match="Persistent error"):
                mock_request()


class TestRateLimitedHttpClient:
    """Test rate-limited HTTP client."""
    
    @patch('httpx.Client')
    def test_client_creation(self, mock_client_class):
        """Test HTTP client creation with proper configuration."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        client = RateLimitedHttpClient(
            source_name="test",
            rate_limit_per_minute=60,
            user_agent="TestBot/1.0"
        )
        
        # Check client was created with correct headers
        mock_client_class.assert_called_once()
        call_kwargs = mock_client_class.call_args[1]
        assert "User-Agent" in call_kwargs["headers"]
        assert call_kwargs["headers"]["User-Agent"] == "TestBot/1.0"
    
    @patch('httpx.Client')
    @patch('time.sleep')
    def test_rate_limiting(self, mock_sleep, mock_client_class):
        """Test that rate limiting is enforced."""
        mock_client = Mock()
        mock_response = Mock()
        mock_response.status_code = 200
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client
        
        # Create client with very low rate limit
        client = RateLimitedHttpClient(
            source_name="test",
            rate_limit_per_minute=1,  # 1 request per minute
        )
        
        # Force rate limiter to be empty
        client.rate_limiter.tokens = 0
        
        # This should trigger rate limiting
        client.get("https://example.com")
        
        # Check that sleep was called (rate limiting triggered)
        mock_sleep.assert_called()


class TestDataQualityValidators:
    """Test data quality validation functions."""
    
    def test_url_validation_success(self):
        """Test successful URL validation."""
        result = validate_url("https://news.reuters.com/article")
        assert result.is_valid
        assert len(result.errors) == 0
    
    def test_url_validation_failures(self):
        """Test URL validation failure cases."""
        # Invalid scheme
        result = validate_url("ftp://example.com")
        assert not result.is_valid
        assert any("Invalid URL scheme" in error for error in result.errors)
        
        # Suspicious pattern
        result = validate_url("https://localhost/test")
        assert not result.is_valid
        assert any("Suspicious URL pattern" in error for error in result.errors)
        
        # Missing domain
        result = validate_url("https://")
        assert not result.is_valid
        assert any("missing domain" in error for error in result.errors)
    
    def test_language_validation(self):
        """Test language code validation."""
        # Valid languages
        assert validate_language("en").is_valid
        assert validate_language("es").is_valid
        assert validate_language("zh-cn").is_valid
        
        # Invalid language
        result = validate_language("invalid")
        assert not result.is_valid
        assert any("Unknown language code" in error for error in result.errors)
    
    def test_text_content_validation(self):
        """Test text content validation."""
        # Valid text
        valid_text = "This is a valid article with sufficient length."
        result = validate_text_content(valid_text)
        assert result.is_valid
        
        # Too short
        result = validate_text_content("Short")
        assert not result.is_valid
        assert any("too short" in error for error in result.errors)
        
        # Empty text
        result = validate_text_content("")
        assert not result.is_valid
        assert any("empty" in error for error in result.errors)
    
    def test_canonicalize_url(self):
        """Test URL canonicalization for deduplication."""
        # Remove tracking parameters
        original = "https://example.com/article?utm_source=twitter&id=123"
        canonical = canonicalize_url(original)
        assert canonical == "https://example.com/article?id=123"
        
        # Normalize case and trailing slash
        original = "HTTPS://EXAMPLE.COM/Article/"
        canonical = canonicalize_url(original)
        assert canonical == "https://example.com/Article"
    
    def test_title_simhash(self):
        """Test title simhash computation."""
        title1 = "Breaking: Market News Update"
        title2 = "Breaking: Market News Update"
        title3 = "Completely Different Article Title"
        
        hash1 = compute_title_simhash64(title1)
        hash2 = compute_title_simhash64(title2)
        hash3 = compute_title_simhash64(title3)
        
        # Same titles should have same hash
        assert hash1 == hash2
        
        # Different titles should have different hashes
        assert hash1 != hash3
        
        # Hashes should be 16 hex characters (64 bits)
        assert len(hash1) == 16
        assert all(c in "0123456789abcdef" for c in hash1)


class TestAdvancedLakeWriter:
    """Test advanced lake writer with deduplication."""
    
    @pytest.fixture
    def s3_client(self):
        """Create mock S3 client."""
        with mock_aws():
            client = boto3.client(
                "s3", 
                region_name="us-east-1",
                aws_access_key_id="testing",
                aws_secret_access_key="testing",
            )
            client.create_bucket(Bucket="test-bucket")
            yield client
    
    def test_bloom_filter(self):
        """Test Bloom filter functionality."""
        bf = BloomFilter(size=1000, hash_count=3)
        
        # Add item
        bf.add("test_item")
        assert bf.might_contain("test_item")
        
        # Item not added should (usually) return False
        assert not bf.might_contain("different_item")
    
    def test_ensure_bucket_exists_creates_bucket(self, s3_client):
        """Test bucket creation when it doesn't exist."""
        # Delete the bucket created in fixture
        s3_client.delete_bucket(Bucket="test-bucket")
        
        # This should create the bucket
        ensure_bucket_exists(s3_client, "test-bucket")
        
        # Verify bucket exists
        response = s3_client.head_bucket(Bucket="test-bucket")
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200
    
    def test_ensure_bucket_exists_already_exists(self, s3_client):
        """Test no-op when bucket already exists."""
        # Should not raise an exception
        ensure_bucket_exists(s3_client, "test-bucket")
        
        # Bucket should still exist
        response = s3_client.head_bucket(Bucket="test-bucket")
        assert response["ResponseMetadata"]["HTTPStatusCode"] == 200


if __name__ == "__main__":
    pytest.main([__file__])
