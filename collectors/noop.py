"""No-op collector for testing and demonstration."""

import logging
from datetime import datetime, timezone
from typing import ClassVar, Iterable, Optional

from pydantic import AnyUrl

from collectors.base import Collector
from market_pulse.models.dto import IngestItem

logger = logging.getLogger(__name__)


class NoopCollector(Collector):
    """No-operation collector that generates synthetic data for testing."""
    
    name: ClassVar[str] = "noop"
    
    def __init__(self, items_per_hour: int = 10):
        """Initialize noop collector.
        
        Args:
            items_per_hour: Number of synthetic items to generate per hour
        """
        self.items_per_hour = items_per_hour
    
    def fetch(
        self, 
        since: datetime, 
        until: Optional[datetime] = None
    ) -> Iterable[IngestItem]:
        """Generate synthetic IngestItem objects for testing.
        
        Args:
            since: Start time (inclusive, UTC timezone-aware)
            until: End time (exclusive, UTC timezone-aware). Defaults to now()
            
        Yields:
            IngestItem: Synthetic test items
        """
        if until is None:
            until = datetime.now(timezone.utc)
        
        logger.info(
            "NoopCollector fetching synthetic data",
            extra={
                "source": self.name,
                "since": since.isoformat(),
                "until": until.isoformat(),
            }
        )
        
        # Calculate time range in hours
        time_diff = until - since
        hours = time_diff.total_seconds() / 3600.0
        
        # Generate items based on time range
        total_items = max(1, int(hours * self.items_per_hour))
        
        base_time = since
        time_increment = time_diff / total_items if total_items > 1 else time_diff
        
        for i in range(total_items):
            item_time = base_time + (time_increment * i)
            
            # Generate synthetic item
            item = IngestItem(
                source="noop",
                source_id=f"noop-{int(item_time.timestamp())}-{i:04d}",
                url=AnyUrl(f"https://example.com/article/{i:06d}"),
                published_at=item_time,
                retrieved_at=datetime.now(timezone.utc),
                title=f"Synthetic Article {i:04d}: Market Analysis and Trends",
                text=self._generate_synthetic_text(i),
                lang="en",
                license="CC BY 4.0",
                author=f"Test Author {i % 5 + 1}",
                meta={
                    "synthetic": True,
                    "collector_version": "1.0",
                    "item_index": i,
                }
            )
            
            yield item
        
        logger.info(
            "NoopCollector completed",
            extra={
                "source": self.name,
                "items_generated": total_items,
                "time_range_hours": hours,
            }
        )
    
    def _generate_synthetic_text(self, index: int) -> str:
        """Generate synthetic article text.
        
        Args:
            index: Item index for variation
            
        Returns:
            Synthetic article text
        """
        # Rotate through different article templates
        templates = [
            "The stock market showed strong performance today as technology stocks led gains. "
            "Investors are optimistic about upcoming earnings reports and continued economic growth. "
            "Trading volume was above average with significant activity in the tech sector.",
            
            "Market analysts are closely watching inflation indicators as the Federal Reserve "
            "considers future interest rate adjustments. Consumer spending data suggests "
            "resilient economic conditions despite global uncertainties.",
            
            "Energy sector stocks declined following unexpected inventory data. Oil prices "
            "remained volatile as geopolitical tensions continue to influence trading patterns. "
            "Renewable energy stocks showed mixed performance.",
            
            "Biotechnology companies announced promising clinical trial results, driving "
            "significant investor interest. Healthcare stocks outperformed broader market indices "
            "as merger and acquisition activity increased in the sector.",
            
            "Cryptocurrency markets experienced heightened volatility amid regulatory discussions. "
            "Traditional financial institutions continue to explore digital asset integration "
            "while maintaining cautious approaches to risk management.",
        ]
        
        template = templates[index % len(templates)]
        
        # Add some variation based on index
        if index % 7 == 0:
            template += " This represents a significant shift in market sentiment."
        elif index % 5 == 0:
            template += " Experts recommend careful portfolio diversification."
        elif index % 3 == 0:
            template += " Long-term investors may find opportunities in current conditions."
        
        return template


# Example usage and factory function
def create_noop_collector(items_per_hour: int = 10) -> NoopCollector:
    """Factory function to create a NoopCollector.
    
    Args:
        items_per_hour: Number of synthetic items per hour
        
    Returns:
        Configured NoopCollector instance
    """
    return NoopCollector(items_per_hour=items_per_hour)

