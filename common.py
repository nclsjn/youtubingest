#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Common imports and utilities for Youtubingest.

This module centralizes frequently used imports to reduce duplication
and provides common utility functions used across the application.
"""

# Standard library imports
import asyncio
import functools
import html
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, Callable

# Third-party imports
import emoji
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

# Internal imports
from config import config
from exceptions import (
    APIConfigurationError, CircuitOpenError, InvalidInputError,
    QuotaExceededError, RateLimitedError, ResourceNotFoundError,
    TimeoutExceededError, TransientError, CriticalError
)

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Common HTTP status codes
HTTP_200_OK = status.HTTP_200_OK
HTTP_400_BAD_REQUEST = status.HTTP_400_BAD_REQUEST
HTTP_401_UNAUTHORIZED = status.HTTP_401_UNAUTHORIZED
HTTP_403_FORBIDDEN = status.HTTP_403_FORBIDDEN
HTTP_404_NOT_FOUND = status.HTTP_404_NOT_FOUND
HTTP_429_TOO_MANY_REQUESTS = status.HTTP_429_TOO_MANY_REQUESTS
HTTP_500_INTERNAL_SERVER_ERROR = status.HTTP_500_INTERNAL_SERVER_ERROR
HTTP_503_SERVICE_UNAVAILABLE = status.HTTP_503_SERVICE_UNAVAILABLE

# Common error responses for OpenAPI documentation
ERROR_RESPONSES = {
    400: {"description": "Invalid input parameters"},
    403: {"description": "Forbidden (e.g., Quota Exceeded, API Key Issue)"},
    404: {"description": "Resource not found"},
    413: {"description": "Request entity too large"},
    429: {"description": "Rate limit exceeded"},
    500: {"description": "Internal server error"},
    503: {"description": "Service unavailable (e.g., initialization failed, circuit open)"}
}

# Common utility functions
def is_true(value: str) -> bool:
    """Check if a string value represents a boolean True.
    
    Args:
        value: String value to check
        
    Returns:
        bool: True if the value represents a boolean True
    """
    if not value:
        return False
    return value.lower() in ("true", "1", "yes", "y", "on")
