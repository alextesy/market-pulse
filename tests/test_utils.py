"""Tests for utility functions."""

from datetime import datetime, timezone

import pytest  # noqa: F401

from market_pulse.utils import (
    chunk_list,
    filter_none_values,
    format_timestamp,
    safe_json_loads,
    validate_config,
)


class TestValidateConfig:
    """Test configuration validation."""

    def test_valid_config(self):
        """Test valid configuration."""
        config = {"api_key": "test_key", "base_url": "https://api.example.com"}
        assert validate_config(config) is True

    def test_invalid_config_missing_api_key(self):
        """Test invalid configuration missing api_key."""
        config = {"base_url": "https://api.example.com"}
        assert validate_config(config) is False

    def test_invalid_config_missing_base_url(self):
        """Test invalid configuration missing base_url."""
        config = {"api_key": "test_key"}
        assert validate_config(config) is False


class TestFormatTimestamp:
    """Test timestamp formatting."""

    def test_datetime_formatting(self):
        """Test datetime object formatting."""
        dt = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        result = format_timestamp(dt)
        assert result == "2023-01-01T12:00:00+00:00"

    def test_string_formatting(self):
        """Test string timestamp formatting."""
        result = format_timestamp("2023-01-01T12:00:00Z")
        assert result == "2023-01-01T12:00:00+00:00"

    def test_float_formatting(self):
        """Test float timestamp formatting."""
        result = format_timestamp(1672574400.0)  # 2023-01-01 12:00:00 UTC
        assert "2023-01-01" in result

    def test_invalid_type(self):
        """Test invalid timestamp type."""
        with pytest.raises(ValueError):
            format_timestamp(None)


class TestSafeJsonLoads:
    """Test safe JSON parsing."""

    def test_valid_json(self):
        """Test valid JSON parsing."""
        data = '{"key": "value", "number": 42}'
        result = safe_json_loads(data)
        assert result == {"key": "value", "number": 42}

    def test_invalid_json(self):
        """Test invalid JSON parsing."""
        data = '{"key": "value", "number": 42'  # Missing closing brace
        result = safe_json_loads(data)
        assert result is None

    def test_non_string_input(self):
        """Test non-string input."""
        result = safe_json_loads(123)
        assert result is None


class TestFilterNoneValues:
    """Test None value filtering."""

    def test_filter_none_values(self):
        """Test filtering None values."""
        data = {"key1": "value1", "key2": None, "key3": "value3", "key4": None}
        result = filter_none_values(data)
        assert result == {"key1": "value1", "key3": "value3"}

    def test_no_none_values(self):
        """Test data with no None values."""
        data = {"key1": "value1", "key2": "value2"}
        result = filter_none_values(data)
        assert result == data

    def test_all_none_values(self):
        """Test data with all None values."""
        data = {"key1": None, "key2": None}
        result = filter_none_values(data)
        assert result == {}


class TestChunkList:
    """Test list chunking."""

    def test_chunk_list(self):
        """Test basic list chunking."""
        lst = [1, 2, 3, 4, 5, 6, 7, 8]
        result = chunk_list(lst, 3)
        assert result == [[1, 2, 3], [4, 5, 6], [7, 8]]

    def test_chunk_list_exact_size(self):
        """Test chunking with exact size."""
        lst = [1, 2, 3, 4]
        result = chunk_list(lst, 2)
        assert result == [[1, 2], [3, 4]]

    def test_chunk_list_smaller_than_chunk_size(self):
        """Test chunking with list smaller than chunk size."""
        lst = [1, 2]
        result = chunk_list(lst, 5)
        assert result == [[1, 2]]

    def test_empty_list(self):
        """Test chunking empty list."""
        result = chunk_list([], 3)
        assert result == []

    def test_invalid_chunk_size(self):
        """Test invalid chunk size."""
        with pytest.raises(ValueError):
            chunk_list([1, 2, 3], 0)

        with pytest.raises(ValueError):
            chunk_list([1, 2, 3], -1)
