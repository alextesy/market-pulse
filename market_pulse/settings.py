"""Configuration settings for Market Pulse using pydantic-settings."""

import logging
import logging.config
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import AnyUrl, BaseModel, Field, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class SourceConfig(BaseModel):
    """Configuration for a data source."""

    enabled: bool = True
    schedule: str = "hourly"
    rate_limit_per_min: int = 60
    fields_keep: List[str] = Field(default_factory=list)
    forms: Optional[List[str]] = None  # For SEC sources


class ScoringConfig(BaseModel):
    """Configuration for scoring parameters."""

    weights: Dict[str, float] = Field(default_factory=dict)
    boosts: Dict[str, float] = Field(default_factory=dict)
    thresholds: Dict[str, float] = Field(default_factory=dict)

    @field_validator("weights")
    @classmethod
    def validate_weights(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Validate that weights sum to approximately 1.0."""
        total = sum(v.values())
        if not (0.9 <= total <= 1.1):
            logging.warning(f"Weights sum to {total:.3f}, should be close to 1.0")
        return v


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    # Core database and storage
    postgres_url: PostgresDsn
    minio_endpoint: AnyUrl
    minio_access_key: str
    minio_secret_key: SecretStr
    bucket_raw: str = "raw_events"
    bucket_clean: str = "clean_events"
    bucket_features: str = "features"

    # Model configuration
    sentence_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    finbert_model: str = "ProsusAI/finbert"
    embed_dims: int = 384

    # Scoring weights (can be overridden by YAML)
    w_sent: float = 0.4
    w_novelty: float = 0.3
    w_velocity: float = 0.3
    event_tag_boosts: Dict[str, float] = Field(default_factory=dict)

    # Time windows
    novelty_lookback_hours: int = 24
    velocity_baseline_days: int = 30

    # Configuration file paths
    config_dir: str = "configs"
    sources_config: str = "sources.yaml"
    scoring_config: str = "scoring.yaml"
    logging_config: str = "logging.yaml"

    # Optional API keys (for external services)
    av_api_key: Optional[str] = None
    stwits_token: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="allow",  # Allow extra fields for dynamic config loading
    )

    @field_validator("embed_dims")
    @classmethod
    def validate_embed_dims(cls, v: int) -> int:
        """Validate embedding dimensions match model."""
        if v != 384:
            logging.warning(
                f"Embedding dimensions {v} may not match model requirements"
            )
        return v

    @field_validator("w_sent", "w_novelty", "w_velocity")
    @classmethod
    def validate_weights(cls, v: float) -> float:
        """Validate individual weights are reasonable."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Weight {v} must be between 0.0 and 1.0")
        return v


def load_yaml_config(file_path: Path) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    if not file_path.exists():
        logging.warning(f"Config file {file_path} not found")
        return {}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logging.error(f"Failed to load config file {file_path}: {e}")
        return {}


def load_settings(yaml_paths: Optional[List[str]] = None) -> Settings:
    """Load settings with YAML configuration override support.

    Precedence: ENV vars > YAML files > Settings defaults

    Args:
        yaml_paths: Optional list of YAML config file paths to load

    Returns:
        Configured Settings instance
    """
    # Collect all YAML overrides
    yaml_overrides = {}

    # Load default configs first (lowest precedence)
    # Get config directory from environment or use default
    config_dir = Path(os.environ.get("CONFIG_DIR", "configs"))
    if config_dir.exists():
        # Load sources config
        sources_path = config_dir / "sources.yaml"
        if sources_path.exists():
            sources_data = load_yaml_config(sources_path)
            yaml_overrides["sources"] = sources_data

        # Load scoring config
        scoring_path = config_dir / "scoring.yaml"
        if scoring_path.exists():
            scoring_data = load_yaml_config(scoring_path)
            # Update scoring weights from YAML
            if "weights" in scoring_data:
                weights = scoring_data["weights"]
                if "sentiment" in weights:
                    yaml_overrides["w_sent"] = weights["sentiment"]
                if "novelty" in weights:
                    yaml_overrides["w_novelty"] = weights["novelty"]
                if "velocity" in weights:
                    yaml_overrides["w_velocity"] = weights["velocity"]

            # Update event tag boosts
            if "boosts" in scoring_data:
                yaml_overrides["event_tag_boosts"] = scoring_data["boosts"]

            # Store full scoring config
            yaml_overrides["scoring"] = scoring_data

        # Load logging config
        logging_path = config_dir / "logging.yaml"
        if logging_path.exists():
            logging_data = load_yaml_config(logging_path)
            # Configure logging
            try:
                # Ensure logs directory exists
                logs_dir = Path("logs")
                logs_dir.mkdir(exist_ok=True)

                logging.config.dictConfig(logging_data)
                logging.info("Logging configured from YAML")
            except Exception as e:
                logging.error(f"Failed to configure logging from YAML: {e}")

    # Load custom YAML configurations (higher precedence)
    if yaml_paths:
        for yaml_path in yaml_paths:
            config_data = load_yaml_config(Path(yaml_path))
            if config_data:
                # Update YAML overrides with custom data
                for key, value in config_data.items():
                    yaml_overrides[key] = value

    # Create settings (ENV vars take precedence)
    settings = Settings()

    # Apply YAML overrides after creation (but don't override ENV vars)
    for key, value in yaml_overrides.items():
        if hasattr(settings, key):
            # Check if this value was set by environment variable
            env_key = key.upper()
            if env_key not in os.environ:
                setattr(settings, key, value)
        else:
            # For dynamic attributes like 'sources' and 'scoring'
            setattr(settings, key, value)

    # Validate final configuration
    _validate_settings(settings)

    return settings


def _validate_settings(settings: Settings) -> None:
    """Validate settings and log warnings for potential issues."""
    # Check weight sum
    weight_sum = settings.w_sent + settings.w_novelty + settings.w_velocity
    if not (0.9 <= weight_sum <= 1.1):
        logging.warning(
            f"Scoring weights sum to {weight_sum:.3f}, should be close to 1.0"
        )

    # Check model compatibility
    if (
        settings.sentence_model == "sentence-transformers/all-MiniLM-L6-v2"
        and settings.embed_dims != 384
    ):
        logging.warning(
            f"Model {settings.sentence_model} expects 384 dimensions, got {settings.embed_dims}"
        )

    # Check thresholds if available
    if hasattr(settings, "scoring") and "thresholds" in settings.scoring:
        thresholds = settings.scoring["thresholds"]
        if "rising_velocity_z" in thresholds and thresholds["rising_velocity_z"] < 1.0:
            logging.warning("rising_velocity_z threshold < 1.0 may be too sensitive")
        if "fresh_novelty" in thresholds and not (
            0.0 <= thresholds["fresh_novelty"] <= 1.0
        ):
            logging.warning("fresh_novelty threshold should be between 0.0 and 1.0")


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance, creating it if necessary."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings() -> None:
    """Reset the global settings instance (mainly for testing)."""
    global _settings
    _settings = None
