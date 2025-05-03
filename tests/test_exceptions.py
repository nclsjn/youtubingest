"""
Tests for the exceptions module.
"""
import unittest
import sys
import os
from fastapi import HTTPException

# Add the parent directory to the path so we can import the application modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from exceptions import (
    AppBaseError, InvalidInputError, ResourceNotFoundError, QuotaExceededError,
    APIConfigurationError, CircuitOpenError, RateLimitedError, handle_exception
)


class TestAppBaseError(unittest.TestCase):
    """Test cases for the AppBaseError class."""

    def test_app_base_error_defaults(self):
        """Test the default values of AppBaseError."""
        error = AppBaseError("Test error")
        self.assertEqual(str(error), "Test error")
        self.assertEqual(error.error_code, "APPBASEERROR")
        self.assertEqual(error.http_status_code, 500)
        self.assertIsNone(error.retry_after)

    def test_app_base_error_custom_values(self):
        """Test custom values for AppBaseError."""
        error = AppBaseError(
            "Custom error",
            error_code="CUSTOM_ERROR",
            http_status_code=400,
            retry_after=30
        )
        self.assertEqual(str(error), "Custom error")
        self.assertEqual(error.error_code, "CUSTOM_ERROR")
        self.assertEqual(error.http_status_code, 400)
        self.assertEqual(error.retry_after, 30)


class TestSpecificErrors(unittest.TestCase):
    """Test cases for specific error classes."""

    def test_invalid_input_error(self):
        """Test InvalidInputError."""
        error = InvalidInputError("Invalid input")
        self.assertEqual(str(error), "Invalid input")
        self.assertEqual(error.error_code, "INVALID_INPUT")
        self.assertEqual(error.http_status_code, 400)
        self.assertIsNone(error.retry_after)

    def test_resource_not_found_error(self):
        """Test ResourceNotFoundError."""
        error = ResourceNotFoundError("Resource not found")
        self.assertEqual(str(error), "Resource not found")
        self.assertEqual(error.error_code, "RESOURCE_NOT_FOUND")
        self.assertEqual(error.http_status_code, 404)
        self.assertIsNone(error.retry_after)

    def test_quota_exceeded_error(self):
        """Test QuotaExceededError."""
        error = QuotaExceededError("Quota exceeded")
        self.assertEqual(str(error), "Quota exceeded")
        self.assertEqual(error.error_code, "QUOTA_EXCEEDED")
        self.assertEqual(error.http_status_code, 403)
        self.assertEqual(error.retry_after, 3600)

    def test_api_configuration_error(self):
        """Test APIConfigurationError."""
        error = APIConfigurationError("API configuration error")
        self.assertEqual(str(error), "API configuration error")
        self.assertEqual(error.error_code, "API_CONFIG_ERROR")
        self.assertEqual(error.http_status_code, 503)
        self.assertIsNone(error.retry_after)

    def test_circuit_open_error(self):
        """Test CircuitOpenError."""
        error = CircuitOpenError("Circuit open")
        self.assertEqual(str(error), "Circuit open")
        self.assertEqual(error.error_code, "SERVICE_UNAVAILABLE")
        self.assertEqual(error.http_status_code, 503)
        self.assertEqual(error.retry_after, 60)

    def test_rate_limited_error(self):
        """Test RateLimitedError."""
        error = RateLimitedError("Rate limited")
        self.assertEqual(str(error), "Rate limited")
        self.assertEqual(error.error_code, "RATE_LIMITED")
        self.assertEqual(error.http_status_code, 429)
        self.assertEqual(error.retry_after, 30)


class TestHandleException(unittest.TestCase):
    """Test cases for the handle_exception function."""

    def test_handle_app_base_error(self):
        """Test handling an AppBaseError."""
        error = AppBaseError(
            "Test error",
            error_code="TEST_ERROR",
            http_status_code=418,
            retry_after=42
        )
        http_exception = handle_exception(error)

        self.assertIsInstance(http_exception, HTTPException)
        self.assertEqual(http_exception.status_code, 418)
        self.assertEqual(http_exception.detail, "Test error")
        self.assertEqual(http_exception.headers["X-Error-Code"], "TEST_ERROR")
        self.assertEqual(http_exception.headers["Retry-After"], "42")

    def test_handle_http_exception(self):
        """Test handling an HTTPException."""
        http_exception = HTTPException(
            status_code=404,
            detail="Not found",
            headers={"X-Custom-Header": "Value"}
        )
        result = handle_exception(http_exception)

        self.assertIs(result, http_exception)

    def test_handle_value_error(self):
        """Test handling a ValueError."""
        error = ValueError("Invalid value")
        http_exception = handle_exception(error)

        self.assertIsInstance(http_exception, HTTPException)
        self.assertEqual(http_exception.status_code, 400)
        self.assertEqual(http_exception.detail, "Invalid value")
        self.assertEqual(http_exception.headers["X-Error-Code"], "INVALID_INPUT")

    def test_handle_generic_exception(self):
        """Test handling a generic Exception."""
        error = Exception("Generic error")
        http_exception = handle_exception(error)

        self.assertIsInstance(http_exception, HTTPException)
        self.assertEqual(http_exception.status_code, 500)
        # The actual implementation only includes the exception type, not the message
        self.assertEqual(http_exception.detail, "Internal server error: Exception")
        self.assertEqual(http_exception.headers["X-Error-Code"], "INTERNAL_SERVER_ERROR")


if __name__ == '__main__':
    unittest.main()
