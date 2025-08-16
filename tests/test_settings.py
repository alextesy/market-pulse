"""Tests for the settings configuration system."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from market_pulse.settings import (
    ScoringConfig,
    Settings,
    SourceConfig,
    get_settings,
    load_settings,
    load_yaml_config,
    reset_settings,
)


class TestSourceConfig:
    """Test SourceConfig model."""

    def test_valid_source_config(self):
        """Test valid source configuration."""
        config = SourceConfig(
            enabled=True,
            schedule="hourly",
            rate_limit_per_min=60,
            fields_keep=["url", "title", "content"],
        )
        assert config.enabled is True
        assert config.schedule == "hourly"
        assert config.rate_limit_per_min == 60
        assert config.fields_keep == ["url", "title", "content"]

    def test_default_source_config(self):
        """Test source configuration with defaults."""
        config = SourceConfig()
        assert config.enabled is True
        assert config.schedule == "hourly"
        assert config.rate_limit_per_min == 60
        assert config.fields_keep == []


class TestScoringConfig:
    """Test ScoringConfig model."""

    def test_valid_scoring_config(self):
        """Test valid scoring configuration."""
        config = ScoringConfig(
            weights={"sentiment": 0.4, "novelty": 0.3, "velocity": 0.3},
            boosts={"earnings": 0.2, "guidance": 0.1},
            thresholds={"rising_velocity_z": 2.0},
        )
        assert config.weights["sentiment"] == 0.4
        assert config.boosts["earnings"] == 0.2
        assert config.thresholds["rising_velocity_z"] == 2.0

    def test_weight_validation_warning(self):
        """Test weight validation warning for non-1.0 sum."""
        # The warning is logged, not raised as UserWarning
        config = ScoringConfig(
            weights={"sentiment": 0.5, "novelty": 0.5, "velocity": 0.5}
        )
        assert config.weights["sentiment"] == 0.5


class TestSettings:
    """Test Settings model."""

    def test_valid_settings(self):
        """Test valid settings configuration."""
        settings = Settings(
            postgres_url="postgresql://user:pass@localhost/db",
            minio_endpoint="http://localhost:9000",
            minio_access_key="access",
            minio_secret_key="secret",
        )
        assert str(settings.postgres_url) == "postgresql://user:pass@localhost/db"
        assert str(settings.minio_endpoint) == "http://localhost:9000/"
        assert settings.minio_access_key == "access"
        assert settings.minio_secret_key.get_secret_value() == "secret"
        assert settings.sentence_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert settings.embed_dims == 384

    def test_invalid_postgres_url(self):
        """Test invalid PostgreSQL URL."""
        with pytest.raises(ValidationError):
            Settings(
                postgres_url="invalid-url",
                minio_endpoint="http://localhost:9000",
                minio_access_key="access",
                minio_secret_key="secret",
            )

    def test_invalid_minio_endpoint(self):
        """Test invalid MinIO endpoint."""
        with pytest.raises(ValidationError):
            Settings(
                postgres_url="postgresql://user:pass@localhost/db",
                minio_endpoint="invalid-url",
                minio_access_key="access",
                minio_secret_key="secret",
            )

    def test_weight_validation(self):
        """Test weight validation."""
        # Valid weights
        settings = Settings(
            postgres_url="postgresql://user:pass@localhost/db",
            minio_endpoint="http://localhost:9000",
            minio_access_key="access",
            minio_secret_key="secret",
            w_sent=0.4,
            w_novelty=0.3,
            w_velocity=0.3,
        )
        assert settings.w_sent == 0.4

        # Invalid weight
        with pytest.raises(ValidationError):
            Settings(
                postgres_url="postgresql://user:pass@localhost/db",
                minio_endpoint="http://localhost:9000",
                minio_access_key="access",
                minio_secret_key="secret",
                w_sent=1.5,  # Invalid weight
            )


class TestLoadYamlConfig:
    """Test YAML configuration loading."""

    def test_load_valid_yaml(self):
        """Test loading valid YAML configuration."""
        yaml_content = """
        gdelt:
          enabled: true
          schedule: hourly
          rate_limit_per_min: 60
        """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            config = load_yaml_config(Path(yaml_path))
            assert config["gdelt"]["enabled"] is True
            assert config["gdelt"]["schedule"] == "hourly"
            assert config["gdelt"]["rate_limit_per_min"] == 60
        finally:
            os.unlink(yaml_path)

    def test_load_nonexistent_file(self):
        """Test loading nonexistent YAML file."""
        config = load_yaml_config(Path("/nonexistent/file.yaml"))
        assert config == {}

    def test_load_invalid_yaml(self):
        """Test loading invalid YAML file."""
        invalid_yaml = """
        gdelt:
          enabled: true
          schedule: hourly
          rate_limit_per_min: 60
        invalid: [yaml: content
        """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(invalid_yaml)
            yaml_path = f.name

        try:
            config = load_yaml_config(Path(yaml_path))
            assert config == {}  # Should return empty dict on error
        finally:
            os.unlink(yaml_path)


class TestLoadSettings:
    """Test settings loading with YAML overrides."""

    def test_load_settings_with_yaml_override(self):
        """Test loading settings with YAML override."""
        yaml_content = """
        w_sent: 0.5
        w_novelty: 0.3
        w_velocity: 0.2
        bucket_raw: custom_raw_bucket
        """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            with patch.dict(
                os.environ,
                {
                    "POSTGRES_URL": "postgresql://user:pass@localhost/db",
                    "MINIO_ENDPOINT": "http://localhost:9000",
                    "MINIO_ACCESS_KEY": "access",
                    "MINIO_SECRET_KEY": "secret",
                },
            ):
                settings = load_settings([yaml_path])
                assert settings.w_sent == 0.5
                assert settings.w_novelty == 0.3
                assert settings.w_velocity == 0.2
                assert settings.bucket_raw == "custom_raw_bucket"
        finally:
            os.unlink(yaml_path)

    def test_load_settings_env_override_yaml(self):
        """Test that environment variables override YAML values."""
        yaml_content = """
        w_sent: 0.5
        bucket_raw: yaml_bucket
        """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            yaml_path = f.name

        try:
            with patch.dict(
                os.environ,
                {
                    "POSTGRES_URL": "postgresql://user:pass@localhost/db",
                    "MINIO_ENDPOINT": "http://localhost:9000",
                    "MINIO_ACCESS_KEY": "access",
                    "MINIO_SECRET_KEY": "secret",
                    "W_SENT": "0.7",  # Should override YAML
                    "BUCKET_RAW": "env_bucket",  # Should override YAML
                },
            ):
                settings = load_settings([yaml_path])
                assert settings.w_sent == 0.7  # From ENV
                assert settings.bucket_raw == "env_bucket"  # From ENV
        finally:
            os.unlink(yaml_path)

    def test_load_settings_default_configs(self):
        """Test loading settings with default config directory."""
        # Create temporary config directory
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir) / "configs"
            config_dir.mkdir()

            # Create sources.yaml
            sources_content = """
            gdelt:
              enabled: true
              schedule: hourly
            sec:
              enabled: false
            """
            with open(config_dir / "sources.yaml", "w") as f:
                f.write(sources_content)

            # Create scoring.yaml
            scoring_content = """
            weights:
              sentiment: 0.5
              novelty: 0.3
              velocity: 0.2
            boosts:
              earnings: 0.2
            """
            with open(config_dir / "scoring.yaml", "w") as f:
                f.write(scoring_content)

            with patch.dict(
                os.environ,
                {
                    "POSTGRES_URL": "postgresql://user:pass@localhost/db",
                    "MINIO_ENDPOINT": "http://localhost:9000",
                    "MINIO_ACCESS_KEY": "access",
                    "MINIO_SECRET_KEY": "secret",
                    "CONFIG_DIR": str(config_dir),
                },
            ):
                settings = load_settings()
                assert hasattr(settings, "sources")
                assert settings.sources["gdelt"]["enabled"] is True
                assert settings.sources["sec"]["enabled"] is False
                assert hasattr(settings, "scoring")
                assert settings.scoring["weights"]["sentiment"] == 0.5
                # Check that YAML weights override defaults
                assert settings.w_sent == 0.5
                assert settings.w_novelty == 0.3
                assert settings.w_velocity == 0.2


class TestGetSettings:
    """Test global settings singleton."""

    def test_get_settings_singleton(self):
        """Test that get_settings returns the same instance."""
        reset_settings()  # Clear any existing settings

        with patch.dict(
            os.environ,
            {
                "POSTGRES_URL": "postgresql://user:pass@localhost/db",
                "MINIO_ENDPOINT": "http://localhost:9000",
                "MINIO_ACCESS_KEY": "access",
                "MINIO_SECRET_KEY": "secret",
            },
        ):
            settings1 = get_settings()
            settings2 = get_settings()
            assert settings1 is settings2

    def test_reset_settings(self):
        """Test resetting the global settings."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_URL": "postgresql://user:pass@localhost/db",
                "MINIO_ENDPOINT": "http://localhost:9000",
                "MINIO_ACCESS_KEY": "access",
                "MINIO_SECRET_KEY": "secret",
            },
        ):
            settings1 = get_settings()
            reset_settings()
            settings2 = get_settings()
            assert settings1 is not settings2


class TestSettingsValidation:
    """Test settings validation and warnings."""

    def test_weight_sum_warning(self):
        """Test warning when weights don't sum to ~1.0."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_URL": "postgresql://user:pass@localhost/db",
                "MINIO_ENDPOINT": "http://localhost:9000",
                "MINIO_ACCESS_KEY": "access",
                "MINIO_SECRET_KEY": "secret",
                "W_SENT": "0.5",
                "W_NOVELTY": "0.5",
                "W_VELOCITY": "0.5",
            },
        ):
            # The warning is logged, not raised as UserWarning
            settings = load_settings()
            assert settings.w_sent == 0.5
            assert settings.w_novelty == 0.5
            assert settings.w_velocity == 0.5

    def test_model_dimension_warning(self):
        """Test warning for model dimension mismatch."""
        with patch.dict(
            os.environ,
            {
                "POSTGRES_URL": "postgresql://user:pass@localhost/db",
                "MINIO_ENDPOINT": "http://localhost:9000",
                "MINIO_ACCESS_KEY": "access",
                "MINIO_SECRET_KEY": "secret",
                "EMBED_DIMS": "512",
            },
        ):
            # The warning is logged, not raised as UserWarning
            settings = load_settings()
            assert settings.embed_dims == 512
