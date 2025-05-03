#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Custom exception classes and error handling utilities for Youtubingest.

Provides a centralized error handling system with custom exceptions,
error mapping, and helper functions for consistent error responses.
"""

from typing import Dict, Any, Optional, Type, Tuple
from fastapi import HTTPException, status


# --- Base Exception Classes ---

class AppBaseError(Exception):
    """Base class for all application-specific exceptions.

    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code
        http_status_code: HTTP status code to use in API responses
        retry_after: Optional seconds to wait before retrying (for rate limits)
    """

    def __init__(self, message: str, error_code: Optional[str] = None,
                http_status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
                retry_after: Optional[int] = None):
        """Initialize the exception.

        Args:
            message: Human-readable error message
            error_code: Machine-readable error code
            http_status_code: HTTP status code to use in API responses
            retry_after: Optional seconds to wait before retrying
        """
        self.message = message
        self.error_code = error_code or self.__class__.__name__.upper()
        self.http_status_code = http_status_code
        self.retry_after = retry_after
        super().__init__(message)

    def to_http_exception(self) -> HTTPException:
        """Convert this exception to a FastAPI HTTPException.

        Returns:
            HTTPException: FastAPI exception with appropriate status and headers
        """
        headers = {"X-Error-Code": self.error_code}
        if self.retry_after:
            headers["Retry-After"] = str(self.retry_after)

        return HTTPException(
            status_code=self.http_status_code,
            detail=self.message,
            headers=headers
        )


class TransientError(AppBaseError):
    """Base class for retryable errors that might be temporary."""
    pass


class CriticalError(AppBaseError):
    """Base class for non-retryable errors that indicate a serious problem."""
    pass


# --- API-Related Exceptions ---

class QuotaExceededError(AppBaseError):
    """Raised when the YouTube API quota has been exhausted."""

    def __init__(self, message: str = "YouTube API quota exceeded"):
        super().__init__(
            message=message,
            error_code="QUOTA_EXCEEDED",
            http_status_code=status.HTTP_403_FORBIDDEN,
            retry_after=3600  # Suggest retry after 1 hour
        )


class ResourceNotFoundError(AppBaseError):
    """Raised when a requested YouTube resource cannot be found."""

    def __init__(self, message: str = "Resource not found"):
        super().__init__(
            message=message,
            error_code="RESOURCE_NOT_FOUND",
            http_status_code=status.HTTP_404_NOT_FOUND
        )


class RateLimitedError(TransientError):
    """Raised when requests are being rate limited."""

    def __init__(self, message: str = "API rate limit reached", retry_after: int = 30):
        super().__init__(
            message=message,
            error_code="RATE_LIMITED",
            http_status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            retry_after=retry_after
        )


class APIConfigurationError(CriticalError):
    """Raised when there's an issue with the API configuration."""

    def __init__(self, message: str = "API configuration error"):
        super().__init__(
            message=message,
            error_code="API_CONFIG_ERROR",
            http_status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )


class CircuitOpenError(TransientError):
    """Raised when the circuit breaker is open and preventing requests."""

    def __init__(self, message: str = "Service temporarily unavailable due to API issues"):
        super().__init__(
            message=message,
            error_code="SERVICE_UNAVAILABLE",
            http_status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            retry_after=60
        )


class InvalidInputError(AppBaseError):
    """Raised when the user input is invalid."""

    def __init__(self, message: str = "Invalid input"):
        super().__init__(
            message=message,
            error_code="INVALID_INPUT",
            http_status_code=status.HTTP_400_BAD_REQUEST
        )


class TimeoutExceededError(TransientError):
    """Raised when an operation times out."""

    def __init__(self, message: str = "Operation timed out"):
        super().__init__(
            message=message,
            error_code="TIMEOUT",
            http_status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            retry_after=10
        )


# --- Error Handling Utilities ---

def handle_exception(exception: Exception) -> HTTPException:
    """Convert any exception to an appropriate HTTPException.

    Args:
        exception: The exception to handle

    Returns:
        HTTPException: FastAPI exception with appropriate status and headers
    """
    if isinstance(exception, AppBaseError):
        # Our custom exceptions already know how to convert themselves
        return exception.to_http_exception()

    elif isinstance(exception, ValueError):
        # Treat ValueError as InvalidInputError
        return InvalidInputError(str(exception)).to_http_exception()

    elif isinstance(exception, HTTPException):
        # Already a FastAPI HTTPException, just return it
        return exception

    else:
        # Unknown exception, treat as internal server error
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {type(exception).__name__}",
            headers={"X-Error-Code": "INTERNAL_SERVER_ERROR"}
        )
