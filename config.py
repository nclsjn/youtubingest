#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Configuration module for Youtubingest.

Defines configuration parameters and loads values from environment variables.
"""

import os
import logging
from datetime import timedelta
from typing import List, Dict, Any

# Initialize a basic logger for config loading issues
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default configuration values
_CONFIG_DEFAULTS: Dict[str, Any] = {
    # API Configuration
    "API_KEY": "",
    "API_KEY_ENV_VAR": "YOUTUBE_API_KEY",
    "API_KEY_SALT_ENV_VAR": "YOUTUBE_API_KEY_SALT",
    "API_KEY_PASSWORD_ENV_VAR": "YOUTUBE_API_KEY_PASSWORD",

    # YouTube API Settings
    "BATCH_SIZE": 50,  # Max allowed by YouTube API for video details
    "TRANSCRIPT_LANGUAGES": ("en", "fr", "es", "pt", "it", "de"),  # Preferred order
    "MIN_DURATION_SECONDS": 20,  # Ignore very short videos

    # Rate Limiting & Timeouts
    "MIN_DELAY_MS": 100,  # Min delay between API calls
    "MAX_DELAY_MS": 400,  # Max delay between API calls
    "API_RETRY_ATTEMPTS": 3,
    "API_RETRY_BASE_DELAY_MS": 1000,
    "API_TIMEOUT_SECONDS": 20.0,  # Timeout for a single API request
    "NETWORK_TIMEOUT_SECONDS": 30.0,  # General network timeout (e.g., semaphore wait)

    # Content Limits
    "MAX_SEARCH_RESULTS": 50,  # Limit results for search queries
    "DEFAULT_TRANSCRIPT_INTERVAL_SECONDS": 10,  # Default grouping interval
    "MAX_VIDEOS_PER_REQUEST": 200,  # Global limit on videos processed per /ingest request

    # Concurrency & Resource Management
    "TRANSCRIPT_SEMAPHORE_LIMIT": 5,  # Concurrent transcript fetches
    "TRANSCRIPT_TIMEOUT_SECONDS": 15.0,  # Timeout for fetching/formatting one transcript
    "THREAD_POOL_MIN_SIZE": 4,
    "THREAD_POOL_MAX_SIZE": 16,

    # Caching
    "RESOLVE_CACHE_SIZE": 128,  # Cache size for channel handle/user -> ID resolution
    "RESOLVE_CACHE_TTL_SECONDS": 3600,  # 1 hour TTL for channel resolution cache
    "URL_PARSE_CACHE_SIZE": 256,  # Cache size for URL parsing
    "PLAYLIST_ITEM_CACHE_SIZE": 32,  # Cache size for playlist item pages
    "PLAYLIST_ITEM_CACHE_TTL_SECONDS": 1800,  # 30 min TTL for playlist item cache
    "TEXT_CLEANING_CACHE_SIZE": 1024,  # Cache size for text cleaning functions
    "CACHE_EVICTION_PERCENT": 20,  # Percentage of entries to evict when cache is full

    # Memory Management
    "MEMORY_PRESSURE_THRESHOLD_MB": 500,  # Process memory threshold for warnings/cache clearing
    "SYSTEM_LOW_MEMORY_THRESHOLD_MB": 200,  # System available memory threshold
    "MEMORY_CHECK_INTERVAL_SECONDS": 60,  # How often to check memory

    # Web Server
    "DEFAULT_ENCODING": "utf-8",
    "RATE_LIMIT_REQUESTS": 30,  # Max requests per IP per window
    "RATE_LIMIT_WINDOW_SECONDS": 60,  # Rate limit window duration
    "MAX_CONTENT_LENGTH": 15 * 1024 * 1024,  # 15MB max POST body size
    "STATIC_CACHE_MAX_AGE": 86400,  # 1 day cache for static files

    # Circuit Breaker
    "CIRCUIT_BREAKER_THRESHOLD": 5,  # Failures before opening circuit
    "CIRCUIT_BREAKER_RESET_TIMEOUT": 300,  # Seconds before trying half-open state
    "CIRCUIT_HALF_OPEN_REQUESTS": 3,  # Successful requests needed in half-open to close

    # CORS
    "ALLOWED_ORIGINS": [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://youtubingest.example.com"  # Example, replace in production
    ],
}


class Config:
    """Configuration class that loads values from environment variables."""

    def __init__(self, load_from_env=True):
        """Initialize configuration with default values and optionally from environment.

        Args:
            load_from_env: Whether to load values from environment variables
        """
        # Set all default values as attributes
        for key, value in _CONFIG_DEFAULTS.items():
            setattr(self, key, value)

        # Convert MIN_DURATION_SECONDS to timedelta
        self.MIN_DURATION = timedelta(seconds=self.MIN_DURATION_SECONDS)

        # Load from environment if requested
        if load_from_env:
            self.load_from_env()

    def load_from_env(self):
        """Load configuration values from environment variables."""
        # Load API key
        self.API_KEY = os.environ.get(self.API_KEY_ENV_VAR, self.API_KEY)

        # Load CORS origins
        env_origins = os.environ.get("ALLOWED_ORIGINS", "")
        if env_origins:
            try:
                origins = [origin.strip() for origin in env_origins.split(",")]
                self.ALLOWED_ORIGINS = [o for o in origins if o]
                logger.info(f"CORS origins set from environment: {self.ALLOWED_ORIGINS}")
            except Exception as e:
                logger.error(f"Failed to parse ALLOWED_ORIGINS from environment: {e}")

        # Load numeric values with type conversion
        self._load_int_from_env("BATCH_SIZE")
        self._load_int_from_env("MIN_DELAY_MS")
        self._load_int_from_env("MAX_DELAY_MS")
        self._load_int_from_env("API_RETRY_ATTEMPTS")
        self._load_int_from_env("API_RETRY_BASE_DELAY_MS")
        self._load_float_from_env("API_TIMEOUT_SECONDS")
        self._load_float_from_env("NETWORK_TIMEOUT_SECONDS")
        self._load_int_from_env("MAX_SEARCH_RESULTS")
        self._load_int_from_env("DEFAULT_TRANSCRIPT_INTERVAL_SECONDS")
        self._load_int_from_env("MAX_VIDEOS_PER_REQUEST")
        self._load_int_from_env("TRANSCRIPT_SEMAPHORE_LIMIT")
        self._load_float_from_env("TRANSCRIPT_TIMEOUT_SECONDS")

        # Update MIN_DURATION if MIN_DURATION_SECONDS was changed
        if self._load_int_from_env("MIN_DURATION_SECONDS"):
            self.MIN_DURATION = timedelta(seconds=self.MIN_DURATION_SECONDS)

        # Warn if API key is missing
        if not self.API_KEY:
            logger.warning(f"API key not found in env var {self.API_KEY_ENV_VAR}.")

    def _load_int_from_env(self, key):
        """Load an integer value from environment variable.

        Args:
            key: The configuration key to load

        Returns:
            bool: True if the value was loaded, False otherwise
        """
        env_value = os.environ.get(key)
        if env_value is not None:
            try:
                setattr(self, key, int(env_value))
                return True
            except ValueError:
                logger.warning(f"Invalid integer value for {key}: {env_value}")
        return False

    def _load_float_from_env(self, key):
        """Load a float value from environment variable.

        Args:
            key: The configuration key to load

        Returns:
            bool: True if the value was loaded, False otherwise
        """
        env_value = os.environ.get(key)
        if env_value is not None:
            try:
                setattr(self, key, float(env_value))
                return True
            except ValueError:
                logger.warning(f"Invalid float value for {key}: {env_value}")
        return False


# Create a single instance of Config to be imported by other modules
config = Config(load_from_env=True)
