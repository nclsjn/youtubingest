#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Logging configuration for Youtubingest.

Provides structured JSON logging capabilities and setup functions.
"""

import logging
import logging.handlers
import json
import sys
import os
from typing import Dict, Any, Optional

class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging.

    This formatter converts log records into JSON objects with standardized fields,
    making logs easier to parse and analyze with log management tools.
    """

    def format(self, record):
        """Format the log record as a JSON object."""
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "name": record.name,
            "file": record.filename,
            "line": record.lineno,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info)
            }

        # Add any custom fields attached to the record
        extra_data = getattr(record, "data", None)
        if isinstance(extra_data, dict):
            for key, value in extra_data.items():
                log_data[key] = value

        return json.dumps(log_data)


class StructuredLogger:
    """Logger that supports structured logging with additional context data."""

    def __init__(self, name: str, extra: Optional[Dict[str, Any]] = None):
        """Initialize the structured logger."""
        self.logger = logging.getLogger(name)
        self.extra = extra or {}

    def _log(self, level: int, message: str, exc_info=None, **kwargs):
        """Internal method to handle logging with extra data."""
        extra_data = {**self.extra}
        if kwargs:
            extra_data.update(kwargs)
        self.logger.log(level, message, exc_info=exc_info, extra={"data": extra_data})

    def debug(self, message: str, **kwargs):
        """Log a debug message with structured data."""
        self._log(logging.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log an info message with structured data."""
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log a warning message with structured data."""
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exc_info=True, **kwargs):
        """Log an error message with structured data."""
        self._log(logging.ERROR, message, exc_info=exc_info, **kwargs)

    def critical(self, message: str, exc_info=True, **kwargs):
        """Log a critical message with structured data."""
        self._log(logging.CRITICAL, message, exc_info=exc_info, **kwargs)


def setup_logging(log_level_console=logging.INFO, log_level_file=logging.DEBUG, structured=True):
    """Configure logging to console and a rotating file."""
    log_file = "youtubingest_backend.log"
    root_logger = logging.getLogger()

    # Remove any existing handlers to avoid duplicates
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    # Create formatter based on config
    formatter = JSONFormatter() if structured else logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Set up file logging
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level_file)
        root_logger.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create log file '{log_file}': {e}", file=sys.stderr)

    # Set up console logging
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level_console)
    root_logger.addHandler(console_handler)

    # Set root logger level
    root_logger.setLevel(min(log_level_console, log_level_file))

    # Log setup completion
    logging.getLogger(__name__).info("Logging setup complete.")
