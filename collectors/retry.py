"""Retry and backoff decorators for resilient data collection."""

import functools
import logging
import random
import time
from typing import Any, Callable, Optional, Set, TypeVar

import httpx

from collectors.base import ingest_backoff_total

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Default retriable HTTP status codes
DEFAULT_RETRIABLE_CODES = {429, 500, 502, 503, 504}


def exponential_jitter(attempt: int, base_delay: float = 1.0, max_delay: float = 60.0) -> float:
    """Calculate exponential backoff with jitter.
    
    Args:
        attempt: Current attempt number (1-based)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        
    Returns:
        Delay in seconds with jitter applied
    """
    # Exponential backoff: base_delay * 2^(attempt-1)
    delay = base_delay * (2 ** (attempt - 1))
    delay = min(delay, max_delay)
    
    # Add jitter: random value between 0.5 and 1.5 times the delay
    jitter_factor = 0.5 + random.random()
    return delay * jitter_factor


def with_retries(
    backoff: Callable[[int], float] = exponential_jitter,
    max_tries: int = 5,
    retriable_codes: Optional[Set[int]] = None,
    retriable_exceptions: Optional[Set[type]] = None,
    source_name: Optional[str] = None,
) -> Callable[[F], F]:
    """Decorator for retrying HTTP requests with exponential backoff.
    
    Args:
        backoff: Function to calculate delay given attempt number
        max_tries: Maximum number of attempts
        retriable_codes: HTTP status codes that trigger retry
        retriable_exceptions: Exception types that trigger retry
        source_name: Source name for metrics (will try to infer if None)
        
    Returns:
        Decorated function with retry logic
    """
    if retriable_codes is None:
        retriable_codes = DEFAULT_RETRIABLE_CODES
    
    if retriable_exceptions is None:
        retriable_exceptions = {
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.ReadError,
            ConnectionError,
        }
    
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Try to infer source name from self.name if not provided
            inferred_source = source_name
            if inferred_source is None and args and hasattr(args[0], "name"):
                inferred_source = args[0].name
            
            last_exception = None
            
            for attempt in range(1, max_tries + 1):
                try:
                    result = func(*args, **kwargs)
                    
                    # Check for retriable HTTP status codes in httpx.Response
                    if hasattr(result, "status_code") and result.status_code in retriable_codes:
                        raise httpx.HTTPStatusError(
                            f"HTTP {result.status_code}",
                            request=getattr(result, "request", None),
                            response=result,
                        )
                    
                    return result
                    
                except Exception as e:
                    last_exception = e
                    
                    # Check if exception is retriable
                    is_retriable = (
                        type(e) in retriable_exceptions
                        or (hasattr(e, "response") and 
                            hasattr(e.response, "status_code") and
                            e.response.status_code in retriable_codes)
                    )
                    
                    if not is_retriable or attempt == max_tries:
                        logger.error(
                            "Request failed after retries",
                            extra={
                                "source": inferred_source,
                                "attempt": attempt,
                                "max_tries": max_tries,
                                "error": str(e),
                            }
                        )
                        raise e
                    
                    # Calculate backoff delay
                    delay = backoff(attempt)
                    
                    # Determine backoff reason
                    reason = "exception"
                    if hasattr(e, "response") and hasattr(e.response, "status_code"):
                        if e.response.status_code == 429:
                            reason = "rate_limit"
                        elif e.response.status_code >= 500:
                            reason = "server_error"
                    
                    logger.warning(
                        "Request failed, retrying",
                        extra={
                            "source": inferred_source,
                            "attempt": attempt,
                            "max_tries": max_tries,
                            "delay": delay,
                            "reason": reason,
                            "error": str(e),
                        }
                    )
                    
                    # Record backoff metric
                    if inferred_source:
                        ingest_backoff_total.labels(
                            source=inferred_source, reason=reason
                        ).inc()
                    
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            raise last_exception or RuntimeError("Unexpected retry loop exit")
        
        return wrapper
    
    return decorator


class RateLimitedHttpClient:
    """HTTP client with built-in rate limiting and retry logic."""
    
    def __init__(
        self,
        source_name: str,
        rate_limit_per_minute: int = 60,
        timeout: float = 30.0,
        user_agent: Optional[str] = None,
    ):
        """Initialize rate-limited HTTP client.
        
        Args:
            source_name: Source identifier for metrics and logging
            rate_limit_per_minute: Maximum requests per minute
            timeout: Request timeout in seconds
            user_agent: Custom User-Agent header
        """
        from collectors.base import (
            TokenBucketRateLimiter,
            ingest_http_latency_seconds,
            ingest_http_requests_total,
        )
        
        self.source_name = source_name
        self.rate_limiter = TokenBucketRateLimiter(
            capacity=rate_limit_per_minute,
            refill_rate=rate_limit_per_minute / 60.0,  # tokens per second
        )
        
        # Configure HTTP client
        headers = {}
        if user_agent:
            headers["User-Agent"] = user_agent
        else:
            headers["User-Agent"] = "MarketPulseBot/0.1 (contact: admin@example.com)"
        
        self.client = httpx.Client(
            timeout=timeout,
            headers=headers,
        )
        
        # Metrics references
        self.requests_total = ingest_http_requests_total
        self.latency_histogram = ingest_http_latency_seconds
    
    @with_retries()
    def get(self, url: str, **kwargs) -> httpx.Response:
        """Make GET request with rate limiting and retries.
        
        Args:
            url: Request URL
            **kwargs: Additional arguments for httpx.get()
            
        Returns:
            httpx.Response object
        """
        # Wait for rate limit
        while not self.rate_limiter.acquire():
            wait_time = self.rate_limiter.wait_time()
            time.sleep(min(wait_time, 1.0))  # Cap wait time at 1 second per check
        
        # Make request with timing
        start_time = time.time()
        try:
            response = self.client.get(url, **kwargs)
            response.raise_for_status()
            
            # Record successful request
            self.requests_total.labels(
                source=self.source_name,
                code=response.status_code
            ).inc()
            
            return response
            
        except Exception as e:
            # Record failed request
            status_code = "unknown"
            if hasattr(e, "response") and hasattr(e.response, "status_code"):
                status_code = str(e.response.status_code)
            
            self.requests_total.labels(
                source=self.source_name,
                code=status_code
            ).inc()
            
            raise
        finally:
            # Record latency
            elapsed = time.time() - start_time
            self.latency_histogram.labels(source=self.source_name).observe(elapsed)
    
    def close(self) -> None:
        """Close the HTTP client."""
        self.client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

