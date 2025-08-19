"""End-to-end example of collector framework usage."""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.base import create_s3_client
from collectors.noop import NoopCollector
from lake.writer import AdvancedLakeWriter, ensure_bucket_exists
from observability.logging import get_logger, setup_logging
from observability.metrics import start_metrics_server


def run_collector_example(
    minio_endpoint: str = "http://localhost:9000",
    minio_access_key: str = "minioadmin",
    minio_secret_key: str = "minioadmin",
    bucket_name: str = "market-pulse-raw",
    hours_back: int = 2,
    start_metrics: bool = False,
) -> None:
    """Run complete collector example.

    Args:
        minio_endpoint: MinIO endpoint URL
        minio_access_key: MinIO access key
        minio_secret_key: MinIO secret key
        bucket_name: S3 bucket name for raw data
        hours_back: How many hours back to collect data
        start_metrics: Whether to start Prometheus metrics server
    """
    # Setup structured logging
    setup_logging(level="INFO", format_json=True)
    logger = get_logger(__name__)

    logger.info("Starting collector example")

    # Start metrics server if requested
    if start_metrics:
        try:
            start_metrics_server(port=8080)
            logger.info("Metrics server started on port 8080")
        except Exception as e:
            logger.warning(f"Failed to start metrics server: {e}")

    try:
        # Create S3 client for MinIO
        s3_client = create_s3_client(
            endpoint_url=minio_endpoint,
            aws_access_key_id=minio_access_key,
            aws_secret_access_key=minio_secret_key,
        )

        # Ensure bucket exists
        ensure_bucket_exists(s3_client, bucket_name)

        # Create collector
        collector = NoopCollector(items_per_hour=30)  # Generate 30 items per hour

        # Create lake writer
        lake_writer = AdvancedLakeWriter(
            s3_client=s3_client,
            bucket=bucket_name,
            source_name=collector.name,
            max_items=100,  # Smaller batches for demo
            max_bytes=1024 * 1024,  # 1MB max
            max_age=30.0,  # 30 seconds max age
        )

        # Define time range
        until_time = datetime.now(timezone.utc)
        since_time = until_time - timedelta(hours=hours_back)

        logger.info(
            "Fetching data from collector",
            extra={
                "collector": collector.name,
                "since": since_time.isoformat(),
                "until": until_time.isoformat(),
                "expected_items": hours_back * 30,
            },
        )

        # Fetch items from collector
        start_time = time.time()
        items = list(collector.fetch(since=since_time, until=until_time))
        fetch_duration = time.time() - start_time

        logger.info(
            "Data fetched successfully",
            extra={
                "items_fetched": len(items),
                "fetch_duration": fetch_duration,
                "items_per_second": (
                    len(items) / fetch_duration if fetch_duration > 0 else 0
                ),
            },
        )

        # Write items to lake with deduplication
        start_time = time.time()
        lake_writer.write_items_with_dedupe(items)
        write_duration = time.time() - start_time

        logger.info(
            "Data written to lake successfully",
            extra={
                "items_written": len(items),
                "write_duration": write_duration,
                "items_per_second": (
                    len(items) / write_duration if write_duration > 0 else 0
                ),
            },
        )

        # List created objects
        from lake.writer import list_lake_objects

        objects = list_lake_objects(
            s3_client=s3_client,
            bucket=bucket_name,
            source=collector.name,
        )

        logger.info(
            "Lake objects created",
            extra={
                "object_count": len(objects),
                "objects": [obj["Key"] for obj in objects],
                "total_size_bytes": sum(obj["Size"] for obj in objects),
            },
        )

        # Print summary
        print("\n" + "=" * 60)
        print("COLLECTOR EXAMPLE SUMMARY")
        print("=" * 60)
        print(f"Collector: {collector.name}")
        print(f"Time range: {hours_back} hours ({since_time} to {until_time})")
        print(f"Items generated: {len(items)}")
        print(f"Objects created: {len(objects)}")
        print(f"Total size: {sum(obj['Size'] for obj in objects):,} bytes")
        print(f"Fetch time: {fetch_duration:.2f}s")
        print(f"Write time: {write_duration:.2f}s")
        print("\nGenerated objects:")
        for obj in objects:
            print(f"  - {obj['Key']} ({obj['Size']:,} bytes)")
        print("=" * 60)

    except Exception as e:
        logger.error("Collector example failed", extra={"error": str(e)})
        raise


def demonstrate_collector_interface() -> None:
    """Demonstrate the collector interface with different scenarios."""
    setup_logging(level="INFO", format_json=False)  # Human-readable for demo

    print("\n" + "=" * 60)
    print("COLLECTOR INTERFACE DEMONSTRATION")
    print("=" * 60)

    # Create collector instances
    collectors = [
        NoopCollector(items_per_hour=60),  # 1 per minute
        NoopCollector(items_per_hour=120),  # 2 per minute
    ]

    # Test different time ranges
    test_cases = [
        ("1 hour", timedelta(hours=1)),
        ("30 minutes", timedelta(minutes=30)),
        ("2 hours", timedelta(hours=2)),
    ]

    for collector in collectors:
        print(
            f"\nTesting {collector.name} collector (rate: {collector.items_per_hour}/hour)"
        )
        print("-" * 40)

        for description, time_delta in test_cases:
            since = datetime.now(timezone.utc) - time_delta
            until = datetime.now(timezone.utc)

            items = list(collector.fetch(since=since, until=until))

            print(f"  {description:12} -> {len(items):3} items")

            # Show first item details
            if items:
                item = items[0]
                print(f"    Sample: {item.source_id} | {item.title[:40]}...")

    print("\n" + "=" * 60)


def test_data_quality_validation() -> None:
    """Demonstrate data quality validation."""
    from pydantic import AnyUrl

    from dq.validators import validate_ingest_item
    from market_pulse.models.dto import IngestItem

    setup_logging(level="INFO", format_json=False)

    print("\n" + "=" * 60)
    print("DATA QUALITY VALIDATION DEMONSTRATION")
    print("=" * 60)

    # Create test items with various quality issues
    test_items = [
        # Valid item
        IngestItem(
            source="noop",
            source_id="valid-001",
            url=AnyUrl("https://example.com/valid-article"),
            published_at=datetime.now(timezone.utc) - timedelta(minutes=10),
            retrieved_at=datetime.now(timezone.utc),
            title="Valid Article Title With Sufficient Length",
            text="This is a valid article with sufficient text content to pass validation checks.",
            lang="en",
            license="MIT",
        ),
        # Item with quality issues
        IngestItem(
            source="noop",
            source_id="invalid-001",
            url=AnyUrl("https://localhost/suspicious-url"),  # Suspicious URL
            published_at=datetime.now(timezone.utc)
            + timedelta(minutes=10),  # Future publish date
            retrieved_at=datetime.now(timezone.utc),
            title="Bad",  # Too short
            text="Short",  # Too short
            lang="xx",  # Invalid language
            license="Unknown",
        ),
    ]

    for i, item in enumerate(test_items):
        print(f"\nValidating Item {i+1}: {item.source_id}")
        print("-" * 30)

        result = validate_ingest_item(item)

        if result.is_valid:
            print("✅ PASSED - Item is valid")
        else:
            print("❌ FAILED - Quality issues found:")
            for error in result.errors:
                print(f"   • {error}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run collector framework examples")
    parser.add_argument(
        "--demo",
        choices=["full", "interface", "validation"],
        default="full",
        help="Which demo to run",
    )
    parser.add_argument(
        "--minio-endpoint", default="http://localhost:9000", help="MinIO endpoint URL"
    )
    parser.add_argument("--bucket", default="market-pulse-raw", help="S3 bucket name")
    parser.add_argument("--hours", type=int, default=2, help="Hours of data to collect")
    parser.add_argument(
        "--metrics", action="store_true", help="Start Prometheus metrics server"
    )

    args = parser.parse_args()

    if args.demo == "full":
        run_collector_example(
            minio_endpoint=args.minio_endpoint,
            bucket_name=args.bucket,
            hours_back=args.hours,
            start_metrics=args.metrics,
        )
    elif args.demo == "interface":
        demonstrate_collector_interface()
    elif args.demo == "validation":
        test_data_quality_validation()

    print("\nDemo completed successfully! 🎉")
