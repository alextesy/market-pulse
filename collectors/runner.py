"""Collector runner and coordination module."""

import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Type

import yaml
from pydantic import BaseModel

from collectors.base import Collector, create_s3_client
from collectors.noop import NoopCollector
from lake.writer import AdvancedLakeWriter, ensure_bucket_exists
from observability.logging import get_logger, log_collector_progress, setup_logging
from observability.metrics import start_metrics_server


class CollectorConfig(BaseModel):
    """Configuration for a collector."""

    enabled: bool = True
    rate_limit_per_min: int = 60
    timeout: int = 30
    user_agent: str = "MarketPulseBot/0.1"
    retry_attempts: int = 5
    retry_backoff: str = "exponential_jitter"


class LakeConfig(BaseModel):
    """Lake storage configuration."""

    bucket: str = "market-pulse-raw"
    endpoint_url: str = "http://localhost:9000"
    region: str = "us-east-1"
    max_items_per_shard: int = 5000
    max_bytes_per_shard: int = 52428800  # 50MB
    max_age_seconds: int = 120
    enable_dedupe: bool = True
    bloom_filter_size: int = 100000
    bloom_hash_count: int = 5
    temp_cleanup_interval_hours: int = 1


class ObservabilityConfig(BaseModel):
    """Observability configuration."""

    class MetricsConfig(BaseModel):
        enabled: bool = True
        port: int = 8080

    class LoggingConfig(BaseModel):
        level: str = "INFO"
        format: str = "json"
        structured: bool = True

    class TracingConfig(BaseModel):
        enabled: bool = False

    metrics: MetricsConfig = MetricsConfig()
    logging: LoggingConfig = LoggingConfig()
    tracing: TracingConfig = TracingConfig()


class CollectorRunner:
    """Coordinate collector runs with configuration and observability."""

    def __init__(self, config_path: str = "configs/sources.yaml"):
        """Initialize collector runner.

        Args:
            config_path: Path to configuration YAML file
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.logger = get_logger(__name__)

        # Available collectors registry
        self.collectors_registry: Dict[str, Type[Collector]] = {
            "noop": NoopCollector,
            # Future collectors will be added here:
            # "gdelt": GdeltCollector,
            # "sec": SecCollector,
            # "stocktwits": StocktwitsCollector,
        }

        # Setup observability
        self._setup_observability()

        # Create S3 client
        self.s3_client = create_s3_client(
            endpoint_url=self.config["lake"]["endpoint_url"],
            region_name=self.config["lake"]["region"],
        )

        # Ensure bucket exists
        ensure_bucket_exists(self.s3_client, self.config["lake"]["bucket"])

    def _load_config(self) -> dict:
        """Load configuration from YAML file."""
        try:
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f)
        except Exception:
            # Fallback to minimal config
            return {
                "sources": {"noop": {"enabled": True, "items_per_hour": 30}},
                "lake": LakeConfig().model_dump(),
                "observability": ObservabilityConfig().model_dump(),
            }

    def _setup_observability(self) -> None:
        """Setup logging and metrics based on configuration."""
        obs_config = ObservabilityConfig(**self.config.get("observability", {}))

        # Setup logging
        setup_logging(
            level=obs_config.logging.level,
            format_json=(obs_config.logging.format == "json"),
        )

        # Start metrics server
        if obs_config.metrics.enabled:
            try:
                start_metrics_server(port=obs_config.metrics.port)
            except Exception as e:
                self.logger.warning(f"Failed to start metrics server: {e}")

    def get_enabled_collectors(self) -> List[str]:
        """Get list of enabled collector names."""
        enabled = []
        sources = self.config.get("sources", {})

        for source_name, source_config in sources.items():
            if source_config.get("enabled", False):
                enabled.append(source_name)

        return enabled

    def create_collector(self, source_name: str) -> Optional[Collector]:
        """Create collector instance from configuration.

        Args:
            source_name: Name of the source/collector

        Returns:
            Configured collector instance or None if not available
        """
        if source_name not in self.collectors_registry:
            self.logger.warning(f"Collector {source_name} not implemented yet")
            return None

        source_config = self.config["sources"].get(source_name, {})
        collector_class = self.collectors_registry[source_name]

        # Special handling for noop collector
        if source_name == "noop":
            items_per_hour = source_config.get("items_per_hour", 30)
            return collector_class(items_per_hour=items_per_hour)

        # For other collectors, pass full config
        return collector_class(**source_config)

    def create_lake_writer(self, source_name: str) -> AdvancedLakeWriter:
        """Create lake writer for a source.

        Args:
            source_name: Name of the source

        Returns:
            Configured lake writer
        """
        lake_config = LakeConfig(**self.config["lake"])

        return AdvancedLakeWriter(
            s3_client=self.s3_client,
            bucket=lake_config.bucket,
            source_name=source_name,
            max_items=lake_config.max_items_per_shard,
            max_bytes=lake_config.max_bytes_per_shard,
            max_age=lake_config.max_age_seconds,
            temp_cleanup_interval=lake_config.temp_cleanup_interval_hours * 3600,
        )

    def run_collector(
        self,
        source_name: str,
        since: datetime,
        until: Optional[datetime] = None,
    ) -> dict:
        """Run a single collector.

        Args:
            source_name: Name of the collector to run
            since: Start time for collection
            until: End time for collection (defaults to now)

        Returns:
            Dictionary with run results
        """
        if until is None:
            until = datetime.now(timezone.utc)

        self.logger.info(
            "Starting collector run",
            extra={
                "source": source_name,
                "since": since.isoformat(),
                "until": until.isoformat(),
            },
        )

        # Create collector
        collector = self.create_collector(source_name)
        if collector is None:
            return {
                "source": source_name,
                "status": "error",
                "error": "Collector not available",
            }

        # Create lake writer
        lake_writer = self.create_lake_writer(source_name)

        try:
            # Fetch items
            start_time = time.time()
            items = list(collector.fetch(since=since, until=until))
            fetch_duration = time.time() - start_time

            # Write to lake
            start_time = time.time()
            if self.config["lake"].get("enable_dedupe", True):
                lake_writer.write_items_with_dedupe(items)
            else:
                lake_writer.write_items(items)
            write_duration = time.time() - start_time

            # Log results
            log_collector_progress(
                self.logger,
                source=source_name,
                since=since,
                until=until,
                items_processed=len(items),
            )

            return {
                "source": source_name,
                "status": "success",
                "items_collected": len(items),
                "fetch_duration": fetch_duration,
                "write_duration": write_duration,
                "total_duration": fetch_duration + write_duration,
            }

        except Exception as e:
            self.logger.error(
                "Collector run failed",
                extra={
                    "source": source_name,
                    "error": str(e),
                },
            )
            return {
                "source": source_name,
                "status": "error",
                "error": str(e),
            }

    def run_all_collectors(
        self,
        since: datetime,
        until: Optional[datetime] = None,
    ) -> List[dict]:
        """Run all enabled collectors.

        Args:
            since: Start time for collection
            until: End time for collection (defaults to now)

        Returns:
            List of run results for each collector
        """
        results = []
        enabled_collectors = self.get_enabled_collectors()

        self.logger.info(
            "Starting batch collector run",
            extra={
                "collectors": enabled_collectors,
                "since": since.isoformat(),
                "until": until.isoformat() if until else None,
            },
        )

        for source_name in enabled_collectors:
            result = self.run_collector(source_name, since, until)
            results.append(result)

        # Log summary
        successful = sum(1 for r in results if r["status"] == "success")
        total_items = sum(r.get("items_collected", 0) for r in results)

        self.logger.info(
            "Batch collector run completed",
            extra={
                "total_collectors": len(results),
                "successful_collectors": successful,
                "failed_collectors": len(results) - successful,
                "total_items_collected": total_items,
            },
        )

        return results


def main() -> None:
    """Main entry point for collector runner."""
    import argparse

    parser = argparse.ArgumentParser(description="Run Market Pulse collectors")
    parser.add_argument(
        "--config", default="configs/sources.yaml", help="Configuration file path"
    )
    parser.add_argument("--source", help="Run specific collector only")
    parser.add_argument(
        "--hours", type=int, default=1, help="Hours of data to collect (default: 1)"
    )
    parser.add_argument("--since", help="Start time (ISO format)")
    parser.add_argument("--until", help="End time (ISO format)")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be collected without running",
    )

    args = parser.parse_args()

    # Create runner
    runner = CollectorRunner(config_path=args.config)

    # Parse time arguments
    if args.since:
        since = datetime.fromisoformat(args.since.replace("Z", "+00:00"))
    else:
        since = datetime.now(timezone.utc) - timedelta(hours=args.hours)

    if args.until:
        until = datetime.fromisoformat(args.until.replace("Z", "+00:00"))
    else:
        until = None

    # Show configuration in dry-run mode
    if args.dry_run:
        print("Collector Runner Configuration:")
        print(f"  Config file: {args.config}")
        print(f"  Enabled collectors: {runner.get_enabled_collectors()}")
        print(f"  Time range: {since} to {until or 'now'}")
        return

    # Run collectors
    if args.source:
        result = runner.run_collector(args.source, since, until)
        print(f"Result: {result}")
    else:
        results = runner.run_all_collectors(since, until)
        print(f"Results: {results}")


if __name__ == "__main__":
    main()
