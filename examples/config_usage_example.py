"""Example usage of the configuration system."""

import logging
from market_pulse import get_settings, load_settings

def main():
    """Demonstrate configuration system usage."""
    
    # Method 1: Use global settings (loads from .env + default configs)
    settings = get_settings()
    print(f"Database URL: {settings.postgres_url}")
    print(f"MinIO endpoint: {settings.minio_endpoint}")
    print(f"Scoring weights: {settings.w_sent}, {settings.w_novelty}, {settings.w_velocity}")
    
    # Method 2: Load with custom YAML overrides
    custom_settings = load_settings(["custom_config.yaml"])
    print(f"Custom bucket: {custom_settings.bucket_raw}")
    
    # Access source configurations
    if hasattr(settings, 'sources'):
        print("Data sources:")
        for source_name, source_config in settings.sources.items():
            print(f"  {source_name}: {'enabled' if source_config['enabled'] else 'disabled'}")
    
    # Access scoring configurations
    if hasattr(settings, 'scoring'):
        print("Scoring configuration:")
        print(f"  Weights: {settings.scoring.get('weights', {})}")
        print(f"  Boosts: {settings.scoring.get('boosts', {})}")
        print(f"  Thresholds: {settings.scoring.get('thresholds', {})}")
    
    # Logging is automatically configured
    logger = logging.getLogger(__name__)
    logger.info("Configuration system initialized successfully")

if __name__ == "__main__":
    main()
