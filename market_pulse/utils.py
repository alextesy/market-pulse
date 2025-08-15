"""Utility functions for Market Pulse."""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union


def validate_config(config: Dict[str, Any]) -> bool:
    """Validate configuration dictionary.

    Args:
        config: Configuration dictionary to validate

    Returns:
        True if valid, False otherwise
    """
    required_keys = ["api_key", "base_url"]
    return all(key in config for key in required_keys)


def format_timestamp(ts: Union[datetime, str, float]) -> str:
    """Format timestamp to ISO format.

    Args:
        ts: Timestamp as datetime, string, or float

    Returns:
        ISO formatted timestamp string
    """
    if isinstance(ts, datetime):
        return ts.isoformat()
    elif isinstance(ts, str):
        # Try to parse and reformat
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            return dt.isoformat()
        except ValueError:
            return ts
    elif isinstance(ts, (int, float)):
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.isoformat()
    else:
        raise ValueError(f"Unsupported timestamp type: {type(ts)}")


def safe_json_loads(data: str) -> Optional[Dict[str, Any]]:
    """Safely parse JSON string.

    Args:
        data: JSON string to parse

    Returns:
        Parsed JSON dict or None if parsing fails
    """
    try:
        result = json.loads(data)
        if isinstance(result, dict):
            return result
        return None
    except (json.JSONDecodeError, TypeError):
        return None


def filter_none_values(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove None values from dictionary.

    Args:
        data: Dictionary to filter

    Returns:
        Dictionary with None values removed
    """
    return {k: v for k, v in data.items() if v is not None}


def chunk_list(lst: List[Any], chunk_size: int) -> List[List[Any]]:
    """Split list into chunks of specified size.

    Args:
        lst: List to chunk
        chunk_size: Size of each chunk

    Returns:
        List of chunks
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    return [lst[i : i + chunk_size] for i in range(0, len(lst), chunk_size)]
