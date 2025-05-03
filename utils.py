#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
General utilities and helper classes for Youtubingest.

Includes Circuit Breaker, Memory Monitor, Retry Logic, LRU Cache,
Performance Timer, and Secure API Key Manager.
"""

import asyncio
import functools
import os
import random
import re
from logging_config import StructuredLogger
import time
import psutil
from base64 import b64decode, b64encode, urlsafe_b64encode
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from googleapiclient.errors import HttpError

# Import config and exceptions from the current package
from config import config
from exceptions import (
    QuotaExceededError, ResourceNotFoundError, RateLimitedError,
    CircuitOpenError, TransientError, CriticalError, TimeoutExceededError
)
# Import text processing functions needed for cache clearing
from text_processing import (
    extract_urls, clean_title, clean_description,
    format_duration, _format_timestamp
)

# Import cache_manager only when needed in clear_caches_if_needed method


logger = StructuredLogger(__name__)

# --- Circuit Breaker ---

class CircuitBreaker:
    """Implements the Circuit Breaker pattern to prevent cascading failures.

    Monitors for failures in the protected operation. If failures exceed the
    threshold, the circuit "opens" and fast-fails requests until a timeout
    period passes. After the timeout, it allows a limited number of test requests
    through (half-open state) to see if the underlying problem has been resolved.
    """

    STATE_CLOSED = "closed"
    STATE_OPEN = "open"
    STATE_HALF_OPEN = "half-open"

    def __init__(self, name: str, failure_threshold: int = config.CIRCUIT_BREAKER_THRESHOLD,
                 reset_timeout: int = config.CIRCUIT_BREAKER_RESET_TIMEOUT,
                 half_open_max_requests: int = config.CIRCUIT_HALF_OPEN_REQUESTS):
        """Initialize a new circuit breaker.

        Args:
            name: Unique identifier for this circuit breaker instance.
            failure_threshold: Number of consecutive failures before opening the circuit.
            reset_timeout: Seconds to wait in the open state before transitioning to half-open.
            half_open_max_requests: Number of successful requests required in half-open state to close the circuit.
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.half_open_max_requests = half_open_max_requests

        self._failures = 0
        self._state = self.STATE_CLOSED
        self._last_failure_time = 0.0
        self._success_count_in_half_open = 0
        self._active_requests_in_half_open = 0 # Track requests specifically in half-open
        self._lock = asyncio.Lock()

        logger.info(
            f"Circuit breaker '{name}' initialized",
            breaker_name=name,
            threshold=failure_threshold,
            reset_timeout=reset_timeout,
            half_open_max=half_open_max_requests
        )

    @property
    def state(self):
        return self._state

    async def __call__(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Execute the function with circuit breaker protection.

        Args:
            func: The async function to execute.
            *args: Positional arguments for the function.
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function if successful.

        Raises:
            CircuitOpenError: If the circuit is open or half-open limit is reached.
            Any exception raised by the executed function.
        """
        async with self._lock:
            current_time = time.monotonic()

            # Check if we need to transition from open to half-open
            if self._state == self.STATE_OPEN and (current_time - self._last_failure_time) > self.reset_timeout:
                self._state = self.STATE_HALF_OPEN
                self._success_count_in_half_open = 0
                self._active_requests_in_half_open = 0
                logger.info(
                    f"Circuit breaker '{self.name}' entering half-open state",
                    breaker_name=self.name,
                    state=self.STATE_HALF_OPEN
                )

            # Determine if execution is allowed based on state
            if self._state == self.STATE_OPEN:
                logger.warning(
                    f"Circuit breaker '{self.name}' is open, failing fast",
                    breaker_name=self.name,
                    state=self.STATE_OPEN
                )
                raise CircuitOpenError(f"Circuit breaker '{self.name}' is open")
            elif self._state == self.STATE_HALF_OPEN and self._active_requests_in_half_open >= self.half_open_max_requests:
                 logger.warning(
                    f"Circuit breaker '{self.name}' half-open limit reached, failing fast",
                    breaker_name=self.name,
                    state=self.STATE_HALF_OPEN,
                    active_requests=self._active_requests_in_half_open
                )
                 raise CircuitOpenError(f"Circuit breaker '{self.name}' half-open limit reached")

            # If closed or half-open (below limit), allow execution
            if self._state == self.STATE_HALF_OPEN:
                self._active_requests_in_half_open += 1

        # Execute the function outside the lock to allow concurrency
        try:
            result = await func(*args, **kwargs)
        except Exception as e:
            # Handle failure
            async with self._lock:
                if self._state == self.STATE_HALF_OPEN:
                    self._active_requests_in_half_open -= 1 # Decrement active count on failure too
                    # Failure in half-open state trips back to open
                    self._state = self.STATE_OPEN
                    self._last_failure_time = time.monotonic()
                    logger.error(
                        f"Circuit breaker '{self.name}' failed in half-open state, returning to open",
                        breaker_name=self.name,
                        state=self.STATE_OPEN,
                        error=str(e)
                    )
                elif self._state == self.STATE_CLOSED:
                    self._failures += 1
                    self._last_failure_time = time.monotonic()
                    logger.warning(
                        f"Circuit breaker '{self.name}' recorded failure {self._failures}/{self.failure_threshold}",
                        breaker_name=self.name,
                        failure_count=self._failures,
                        threshold=self.failure_threshold,
                        error=str(e),
                        state=self.STATE_CLOSED
                    )
                    # Trip to open if threshold reached
                    if self._failures >= self.failure_threshold:
                        self._state = self.STATE_OPEN
                        logger.error(
                            f"Circuit breaker '{self.name}' opened due to failure threshold",
                            breaker_name=self.name,
                            state=self.STATE_OPEN,
                            failures=self._failures,
                            error=str(e)
                        )
            raise e # Re-raise the original exception
        else:
            # Handle success
            async with self._lock:
                if self._state == self.STATE_HALF_OPEN:
                    self._active_requests_in_half_open -= 1
                    self._success_count_in_half_open += 1
                    logger.debug(
                        f"Circuit breaker '{self.name}' half-open success {self._success_count_in_half_open}/{self.half_open_max_requests}",
                        breaker_name=self.name,
                        success_count=self._success_count_in_half_open,
                        required=self.half_open_max_requests
                    )
                    # Close the circuit if enough successes in half-open
                    if self._success_count_in_half_open >= self.half_open_max_requests:
                        self._state = self.STATE_CLOSED
                        self._failures = 0
                        logger.info(
                            f"Circuit breaker '{self.name}' reset to closed after half-open success",
                            breaker_name=self.name,
                            state=self.STATE_CLOSED
                        )
                elif self._state == self.STATE_CLOSED:
                    # Reset failure count on success in closed state
                    if self._failures > 0:
                        logger.info(
                            f"Circuit breaker '{self.name}' resetting failure count after success",
                            breaker_name=self.name,
                            state=self.STATE_CLOSED,
                            previous_failures=self._failures
                        )
                        self._failures = 0
            return result

    def get_stats(self) -> Dict[str, Any]:
        """Return the current status and statistics of the circuit breaker.

        Returns:
            dict: Statistics including name, state, failures, threshold, etc.
        """
        # Access protected attributes directly as this is an internal method
        return {
            "name": self.name,
            "state": self._state,
            "failures": self._failures,
            "threshold": self.failure_threshold,
            "last_failure_time": self._last_failure_time,
            "reset_timeout_seconds": self.reset_timeout,
            "success_count_in_half_open": self._success_count_in_half_open if self._state == self.STATE_HALF_OPEN else 0,
            "active_requests_in_half_open": self._active_requests_in_half_open if self._state == self.STATE_HALF_OPEN else 0,
            "half_open_required_successes": self.half_open_max_requests
        }


# --- Memory Monitor ---

class MemoryMonitor:
    """Monitors system and process memory usage to prevent out-of-memory conditions.

    Provides methods to check memory usage and trigger cache clearing when
    memory pressure is detected. Relies on the 'psutil' library if available.
    """

    _psutil_available = False
    _last_check_time = 0.0
    _check_interval = config.MEMORY_CHECK_INTERVAL_SECONDS
    _warning_issued = False
    _critical_issued = False
    _memory_pressure = False
    _process = None # Cache psutil process object

    try:
        import psutil
        _psutil_available = True
        _process = psutil.Process(os.getpid())
        logger.info("psutil found. Detailed memory monitoring enabled.")
    except ImportError:
        logger.warning("psutil not found. Memory monitoring will be limited.")
    except Exception as e:
        logger.error(f"Failed to initialize psutil Process: {e}. Limited monitoring.")
        _psutil_available = False # Treat as unavailable if Process init fails

    @classmethod
    def get_process_memory_mb(cls) -> float:
        """Get the current memory usage (RSS) of this process in megabytes.

        Returns:
            float: Memory usage in MB, or 0.0 if unavailable.
        """
        if not cls._psutil_available or not cls._process:
            # Fallback using resource module if psutil is unavailable (Unix-like only)
            try:
                import resource
                usage = resource.getrusage(resource.RUSAGE_SELF)
                # ru_maxrss is in KB on Linux, Bytes on macOS - needs check or assumption
                # Assuming KB for broader compatibility, convert to MB
                return usage.ru_maxrss / 1024.0
            except (ImportError, AttributeError, Exception):
                 # resource module not available or failed
                return 0.0

        try:
            # Use cached process object
            return cls._process.memory_info().rss / (1024 * 1024)
        except psutil.NoSuchProcess:
             logger.warning("psutil.NoSuchProcess encountered, attempting re-init.")
             try:
                 cls._process = psutil.Process(os.getpid())
                 return cls._process.memory_info().rss / (1024 * 1024)
             except Exception as e:
                 logger.error(f"Error re-initializing or reading process memory: {e}")
                 cls._psutil_available = False # Disable psutil if re-init fails
                 return 0.0
        except Exception as e:
            logger.debug(f"Error reading process memory: {e}")
            return 0.0

    @classmethod
    def get_system_available_memory_mb(cls) -> float:
        """Get the amount of available system memory in megabytes.

        Returns:
            float: Available memory in MB, or float('inf') if unavailable.
        """
        if not cls._psutil_available:
            return float("inf") # Indicate unavailable

        try:
            return cls.psutil.virtual_memory().available / (1024 * 1024)
        except Exception as e:
            logger.debug(f"Error reading system available memory: {e}")
            return float("inf")

    @classmethod
    def get_memory_percent(cls) -> float:
        """Get the percentage of system memory currently in use.

        Returns:
            float: Percentage of memory used (0-100), or 0.0 if unavailable.
        """
        if not cls._psutil_available:
            return 0.0

        try:
            return cls.psutil.virtual_memory().percent
        except Exception as e:
            logger.debug(f"Error reading system memory percentage: {e}")
            return 0.0

    @classmethod
    def check_memory_pressure(cls, force_check: bool = False) -> bool:
        """Check if the system or process is under memory pressure based on configured thresholds.

        Args:
            force_check: If True, bypass the check interval and perform the check immediately.

        Returns:
            bool: True if memory pressure is detected, False otherwise.
        """
        current_time = time.monotonic()
        if not force_check and (current_time - cls._last_check_time < cls._check_interval):
            return cls._memory_pressure # Return cached state within interval

        cls._last_check_time = current_time

        process_memory = cls.get_process_memory_mb()
        system_memory_available = cls.get_system_available_memory_mb()
        memory_percent_used = cls.get_memory_percent()

        # Determine pressure based on thresholds
        is_under_pressure = (
            (process_memory > config.MEMORY_PRESSURE_THRESHOLD_MB) or
            (cls._psutil_available and system_memory_available < config.SYSTEM_LOW_MEMORY_THRESHOLD_MB) or
            (cls._psutil_available and memory_percent_used > 90.0) # Example: 90% system usage
        )
        cls._memory_pressure = is_under_pressure

        # Logging based on state changes or severity
        log_details = {
            "process_memory_mb": round(process_memory, 2),
            "system_available_mb": round(system_memory_available, 2) if cls._psutil_available else "N/A",
            "system_used_percent": round(memory_percent_used, 1) if cls._psutil_available else "N/A",
            "under_pressure": is_under_pressure
        }

        # Critical pressure logging (e.g., > 95% usage)
        if cls._psutil_available and memory_percent_used > 95.0:
            if not cls._critical_issued:
                logger.critical("CRITICAL memory pressure detected", **log_details)
                cls._critical_issued = True
                cls._warning_issued = True # Critical implies warning
        # Warning pressure logging
        elif is_under_pressure:
            if not cls._warning_issued:
                logger.warning("Memory pressure detected", **log_details)
                cls._warning_issued = True
            # Reset critical flag if pressure drops below critical level but is still high
            cls._critical_issued = False
        # Pressure resolved logging
        elif cls._warning_issued or cls._critical_issued: # Log only if previously under pressure
            logger.info("Memory pressure resolved", **log_details)
            cls._warning_issued = False
            cls._critical_issued = False

        return is_under_pressure

    @classmethod
    async def clear_caches_if_needed(cls, force_clear: bool = False) -> bool:
        """Clear various application caches if memory pressure is detected or forced.

        Args:
            force_clear: If True, clear caches regardless of memory pressure state.

        Returns:
            bool: True if caches were cleared, False otherwise.
        """
        if force_clear or cls.check_memory_pressure(force_check=True): # Force check before clearing
            action = "Forcing cache clear" if force_clear else "High memory pressure detected, clearing caches"
            logger.warning(action + "...")

            try:
                # Use the centralized cache manager to clear all caches
                from cache_manager import cache_manager
                results = await cache_manager.clear_all_caches()

                # Run garbage collection
                try:
                    import gc
                    gc.collect()
                    logger.debug("Garbage collection triggered.")
                except Exception as e:
                    logger.warning(f"Garbage collection failed: {e}")

                # Log results
                cache_count = len(results)
                logger.info(f"Cache clearing finished. {cache_count} caches were cleared.")
                return True

            except ImportError:
                logger.warning("Cache manager not available. Using legacy cache clearing.")
                # Fall back to legacy cache clearing if cache_manager is not available
                return await cls._legacy_clear_caches()
            except Exception as e:
                logger.error(f"Error clearing caches: {e}", exc_info=True)
                return False

        return False

    @classmethod
    async def _legacy_clear_caches(cls) -> bool:
        """Legacy method to clear caches without using the cache manager.

        Returns:
            bool: True if caches were cleared, False otherwise.
        """
        logger.debug("Using legacy cache clearing method...")
        caches_cleared_count = 0

        # Clear function caches
        cached_functions_to_clear = [
            extract_urls, clean_title, clean_description,
            format_duration, _format_timestamp
        ]
        for func in cached_functions_to_clear:
            try:
                if hasattr(func, "cache_clear"):
                    func.cache_clear()
                    caches_cleared_count += 1
            except Exception as e:
                logger.warning(f"Failed to clear cache for function {func.__name__}: {e}")

        # Run garbage collection
        try:
            import gc
            gc.collect()
        except Exception:
            pass

        logger.info(f"Legacy cache clearing finished. {caches_cleared_count} function caches cleared.")
        return caches_cleared_count > 0

    @classmethod
    def get_full_memory_stats(cls) -> Dict[str, Any]:
        """Get detailed memory statistics for monitoring purposes.

        Returns:
            dict: Detailed statistics about process and system memory.
        """
        stats = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "psutil_available": cls._psutil_available,
            "process_memory_mb": cls.get_process_memory_mb(),
            "under_pressure": cls._memory_pressure,
            "warning_issued": cls._warning_issued,
            "critical_issued": cls._critical_issued,
        }

        if cls._psutil_available:
            try:
                vm = cls.psutil.virtual_memory()
                stats["system"] = {
                    "total_mb": vm.total / (1024 * 1024),
                    "available_mb": vm.available / (1024 * 1024),
                    "used_mb": vm.used / (1024 * 1024),
                    "percent_used": vm.percent,
                }
                # Add process specific details if process object is valid
                if cls._process:
                     try:
                         p_info = cls._process.as_dict(attrs=['cpu_percent', 'num_threads', 'create_time'])
                         stats["process"] = {
                             "cpu_percent": p_info.get('cpu_percent', 0.0),
                             "threads": p_info.get('num_threads', 0),
                             "uptime_seconds": time.time() - p_info.get('create_time', time.time())
                         }
                     except (psutil.NoSuchProcess, Exception) as proc_e:
                         logger.debug(f"Could not get detailed process info: {proc_e}")
                         stats["process"] = {"error": str(proc_e)}

            except Exception as e:
                logger.debug(f"Error collecting detailed system/process stats: {e}")
                stats["system"] = {"error": str(e)}
                stats["process"] = {"error": str(e)}
        else:
             stats["system"] = {"message": "psutil not available"}
             stats["process"] = {"message": "psutil not available"}


        return stats


# --- Retry Logic ---

class RetryableRequest:
    """Handles requests with retry logic, exponential backoff, and jitter.

    Provides static methods to execute functions (sync or async) with automatic
    retries for specified exceptions.
    """

    @staticmethod
    async def execute_with_retry(
        func: Callable[..., Any],
        *args: Any,
        max_retries: int = config.API_RETRY_ATTEMPTS,
        base_delay_ms: int = config.API_RETRY_BASE_DELAY_MS,
        timeout_seconds: float = config.API_TIMEOUT_SECONDS,
        retry_on_exceptions: Tuple[type[Exception], ...] = (HttpError, RateLimitedError, TransientError, asyncio.TimeoutError),
        jitter_factor: float = 0.5,
        operation_name: Optional[str] = None,
        **kwargs: Any
    ) -> Any:
        """Execute a function with retry logic, timeout, backoff, and jitter.

        Args:
            func: The function (sync or async) to execute.
            *args: Positional arguments for the function.
            max_retries: Maximum number of retry attempts.
            base_delay_ms: Base delay between retries in milliseconds.
            timeout_seconds: Timeout for each attempt in seconds.
            retry_on_exceptions: Tuple of exception types that should trigger a retry.
            jitter_factor: Factor for randomizing delay (0.0 to 1.0). 0 = no jitter.
            operation_name: Optional name for logging purposes. Defaults to func name.
            **kwargs: Keyword arguments for the function.

        Returns:
            The result of the function if successful.

        Raises:
            The last exception encountered after all retries failed.
            TimeoutExceededError: If an attempt times out.
            QuotaExceededError: If a 403 quota error is detected.
            ResourceNotFoundError: If a 404 error is detected.
            Any other non-retryable exception raised by the function.
        """
        last_exception: Optional[Exception] = None
        op_name = operation_name or getattr(func, '__name__', 'unknown_operation')
        current_max_retries = max_retries

        # Check global quota status if available (less ideal, assumes global state)
        quota_is_reached = False
        if 'api_client' in globals() and globals()['api_client'] and hasattr(globals()['api_client'], 'quota_reached'):
             quota_is_reached = globals()['api_client'].quota_reached

        if quota_is_reached:
            current_max_retries = min(max_retries, 1) # Limit retries if quota known to be hit
            logger.warning(
                f"Quota likely reached, limiting retries for '{op_name}' to {current_max_retries}",
                operation=op_name,
                max_retries=current_max_retries
            )

        for attempt in range(current_max_retries + 1):
            try:
                logger.debug(f"Attempt {attempt + 1}/{current_max_retries + 1} for operation '{op_name}'")
                # Execute sync or async function with timeout
                if asyncio.iscoroutinefunction(func):
                    result = await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
                else:
                    loop = asyncio.get_running_loop()
                    # Use functools.partial to pass args/kwargs correctly to executor
                    partial_func = functools.partial(func, *args, **kwargs)
                    result = await asyncio.wait_for(
                        loop.run_in_executor(None, partial_func),
                        timeout=timeout_seconds
                    )
                return result # Success

            except asyncio.TimeoutError:
                last_exception = TimeoutExceededError(f"Operation '{op_name}' timed out after {timeout_seconds} seconds on attempt {attempt + 1}")
                logger.warning(
                    f"Timeout in '{op_name}' (attempt {attempt + 1}) after {timeout_seconds}s",
                    operation=op_name,
                    timeout=timeout_seconds,
                    attempt=attempt + 1
                )
                # Timeout is considered a retryable transient error

            except retry_on_exceptions as e:
                last_exception = e
                status_code = getattr(getattr(e, "resp", None), "status", None)
                uri = getattr(e, "uri", "Unknown URI")
                is_quota_error = False

                # Specific handling for HttpError
                if isinstance(e, HttpError):
                    if status_code == 403:
                        # Check content for quota exceeded details
                        content_bytes = getattr(e, "content", b"")
                        try:
                            content_str = content_bytes.decode(config.DEFAULT_ENCODING, errors="replace")
                            if "quotaExceeded" in content_str or "servingLimitExceeded" in content_str:
                                is_quota_error = True
                                last_exception = QuotaExceededError(f"YouTube API quota exceeded (URI: {uri}). Attempt {attempt + 1}.")
                                # Set global flag if possible (less ideal)
                                if 'api_client' in globals() and globals()['api_client']:
                                    globals()['api_client'].quota_reached = True
                                logger.critical(f"QuotaExceededError detected for '{op_name}' on attempt {attempt + 1}", operation=op_name)
                        except Exception as decode_err:
                             logger.warning(f"Could not decode HttpError content: {decode_err}")
                    elif status_code == 404:
                        last_exception = ResourceNotFoundError(f"YouTube resource not found (404) at URI: {uri}. Attempt {attempt + 1}.")
                        logger.warning(f"ResourceNotFoundError detected for '{op_name}' on attempt {attempt + 1}", operation=op_name)
                        raise last_exception # 404 is usually not retryable

                    # Check for other non-retryable HTTP status codes (e.g., 400, 401)
                    elif status_code is not None and status_code < 500 and status_code != 429: # 429 is often retryable
                         logger.error(f"Unrecoverable API error {status_code} for '{op_name}' (URI: {uri}): {e}. Attempt {attempt + 1}.")
                         raise e # Raise non-retryable client errors immediately

                # If it's a Quota error, stop retrying immediately
                if is_quota_error:
                    raise last_exception

                # Log the retryable error
                logger.warning(
                    f"Retryable error in '{op_name}' (attempt {attempt + 1}): {type(e).__name__}",
                    operation=op_name,
                    attempt=attempt + 1,
                    error_type=type(e).__name__,
                    error_details=str(e)
                )
                # Fall through to retry logic if not quota/404/client error

            except CriticalError as critical_e:
                # Do not retry critical errors
                logger.error(f"Critical error during '{op_name}': {critical_e}", operation=op_name, error=str(critical_e), exc_info=True)
                raise critical_e
            except Exception as unexpected_e:
                # Handle unexpected errors - treat as potentially non-retryable
                logger.error(f"Unexpected error during '{op_name}': {unexpected_e}", operation=op_name, error=str(unexpected_e), exc_info=True)
                raise unexpected_e # Re-raise unexpected errors immediately

            # --- Retry Delay Logic ---
            if attempt < current_max_retries:
                # Exponential backoff: delay = base * (2 ** attempt)
                delay_factor = 2 ** attempt
                base_delay = base_delay_ms / 1000.0 # Convert to seconds

                # Apply jitter: delay * (1 +/- jitter_factor)
                jitter = (random.random() * 2 - 1) * jitter_factor # Random number between -jitter_factor and +jitter_factor
                delay_seconds = base_delay * delay_factor * (1 + jitter)

                # Clamp delay to a reasonable maximum (e.g., 60 seconds)
                max_delay_seconds = 60.0
                actual_delay = max(0.1, min(delay_seconds, max_delay_seconds)) # Ensure minimum delay

                logger.info(
                    f"Retrying '{op_name}' in {actual_delay:.2f} seconds (attempt {attempt + 2}/{current_max_retries + 1})",
                    operation=op_name,
                    delay_seconds=actual_delay,
                    next_attempt=attempt + 2,
                    total_attempts=current_max_retries + 1
                )
                await asyncio.sleep(actual_delay)
            else:
                # Max retries reached
                logger.error(
                    f"Operation '{op_name}' failed after {current_max_retries + 1} attempts.",
                    operation=op_name,
                    max_retries=current_max_retries,
                    final_error_type=type(last_exception).__name__,
                    final_error=str(last_exception)
                )
                # Raise the last encountered exception
                if last_exception:
                    raise last_exception
                else:
                    # Should not happen if loop completed, but as a fallback
                    raise RuntimeError(f"Operation '{op_name}' failed after max retries with no specific exception recorded.")

        # Should be unreachable if loop completes correctly
        raise RuntimeError(f"Retry logic exited unexpectedly for operation '{op_name}'.")

    @staticmethod
    def create_retry_policy(service_name: str, default_max_retries: Optional[int] = None) -> Dict[str, Any]:
        """Create a dictionary representing a standard retry policy based on config.

        Args:
            service_name: Name of the service for potential logging/context.
            default_max_retries: Override the default max retries from config if provided.

        Returns:
            dict: A dictionary containing retry policy parameters.
        """
        max_retries = default_max_retries if default_max_retries is not None else config.API_RETRY_ATTEMPTS

        return {
            "max_retries": max_retries,
            "base_delay_ms": config.API_RETRY_BASE_DELAY_MS,
            "timeout_seconds": config.API_TIMEOUT_SECONDS,
            "jitter_factor": 0.5, # Default jitter factor
            "service_name": service_name # Include service name for context
        }


# --- Performance Timer ---

@contextmanager
def performance_timer(operation_name: str, threshold_ms: float = 100.0):
    """Context manager for timing operations with threshold-based logging.

    Logs the duration of the enclosed code block. Logs at INFO level if duration
    exceeds threshold_ms, WARNING if it significantly exceeds it, otherwise DEBUG.

    Args:
        operation_name: A descriptive name for the operation being timed.
        threshold_ms: Threshold in milliseconds. Durations above this will be logged
                      at INFO level or higher. Defaults to 100ms.

    Yields:
        None
    """
    start_time = time.monotonic()
    try:
        yield
    finally:
        end_time = time.monotonic()
        duration_ms = (end_time - start_time) * 1000

        log_data = {
            "operation": operation_name,
            "duration_ms": round(duration_ms, 2),
            "threshold_ms": threshold_ms
        }

        # Log level depends on duration relative to threshold
        if duration_ms > threshold_ms * 10: # Significantly slow
            logger.warning(f"SLOW OPERATION: '{operation_name}' took {duration_ms:.2f}ms", extra={"data": log_data})
        elif duration_ms > threshold_ms: # Moderately slow
            logger.info(f"Performance watch: '{operation_name}' took {duration_ms:.2f}ms", extra={"data": log_data})
        else: # Normal speed
            logger.debug(f"Performance: '{operation_name}' completed in {duration_ms:.2f}ms", extra={"data": log_data})


# --- LRU Cache ---

class LRUCache:
    """Thread-safe Least Recently Used (LRU) Cache with Time-To-Live (TTL) support.

    Provides a dictionary-like object with a maximum size. When the cache is full,
    it discards the least recently used items. Optional TTL ensures items expire
    after a set duration. Designed for use with asyncio (uses asyncio.Lock).
    """

    def __init__(self, maxsize: int = 128, ttl_seconds: Optional[float] = None,
                 eviction_percent: int = config.CACHE_EVICTION_PERCENT):
        """Initialize the LRU cache.

        Args:
            maxsize: The maximum number of items to store in the cache. Must be > 0.
            ttl_seconds: Optional time-to-live in seconds for cached items.
                         If None, items do not expire based on time.
            eviction_percent: Percentage (1-100) of cache to evict when full.
                              Defaults to config value.
        """
        if maxsize <= 0:
            raise ValueError("LRUCache maxsize must be greater than 0")
        self.maxsize = maxsize
        self.ttl_seconds = ttl_seconds
        # Clamp eviction_percent between 1 and 100
        self.eviction_percent = max(1, min(int(eviction_percent), 100))
        self._num_to_evict = max(1, int(self.maxsize * (self.eviction_percent / 100.0)))

        self._cache = OrderedDict() # Stores key: value
        self._expiry = {} if ttl_seconds is not None else None # Stores key: expiry_timestamp
        self._lock = asyncio.Lock() # Ensure thread-safety for async operations

        # Statistics tracking
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "ttl_expirations": 0,
        }
        logger.debug(f"LRUCache initialized: maxsize={maxsize}, ttl={ttl_seconds}s")

    async def get(self, key: Any) -> Optional[Any]:
        """Retrieve an item from the cache. Returns None if not found or expired.

        Args:
            key: The key of the item to retrieve.

        Returns:
            The cached value if found and valid, otherwise None.
        """
        async with self._lock:
            # Check if key exists
            if key not in self._cache:
                self._stats["misses"] += 1
                return None

            # Check TTL if enabled
            if self._expiry is not None:
                expiry_time = self._expiry.get(key)
                if expiry_time is not None and time.monotonic() > expiry_time:
                    # Item expired
                    self._stats["ttl_expirations"] += 1
                    self._stats["misses"] += 1
                    # Clean up expired item
                    self._cache.pop(key, None)
                    self._expiry.pop(key, None)
                    return None

            # Item found and valid, move to end (most recent)
            value = self._cache[key]
            self._cache.move_to_end(key)
            self._stats["hits"] += 1
            return value

    async def put(self, key: Any, value: Any) -> None:
        """Add or update an item in the cache.

        Args:
            key: The key of the item to store.
            value: The value to store.
        """
        async with self._lock:
            # Check if eviction is needed before adding a new key
            if key not in self._cache and len(self._cache) >= self.maxsize:
                self._evict_lru_items()

            # Add/update the item
            self._cache[key] = value
            self._cache.move_to_end(key)

            # Update expiry time if TTL is enabled
            if self._expiry is not None:
                self._expiry[key] = time.monotonic() + self.ttl_seconds

    def _evict_lru_items(self) -> None:
        """Internal method to evict least recently used items.

        Removes the oldest items from the cache based on the eviction_percent setting.
        This method is called automatically when the cache is full and a new item
        is being added.
        """
        # Evict items until enough space is made or cache is empty
        for _ in range(self._num_to_evict):
            if not self._cache:
                break
            # popitem(last=False) removes the first (oldest) item
            old_key, _ = self._cache.popitem(last=False)
            if self._expiry is not None:
                self._expiry.pop(old_key, None)
            self._stats["evictions"] += 1

    async def clear(self) -> int:
        """Remove all items from the cache.

        Returns:
            int: The number of items removed.
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            if self._expiry is not None:
                self._expiry.clear()
            return count

    async def size(self) -> int:
        """Get the current number of items in the cache.

        Returns:
            int: The current cache size.
        """
        async with self._lock:
            return len(self._cache)

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache usage statistics.

        Returns:
            dict: A dictionary containing cache statistics.
        """
        async with self._lock:
            stats = self._stats.copy()
            stats["size"] = len(self._cache)
            stats["maxsize"] = self.maxsize
            stats["ttl_enabled"] = self.ttl_seconds is not None
            total_lookups = stats["hits"] + stats["misses"]
            stats["hit_ratio"] = (stats["hits"] / total_lookups) if total_lookups > 0 else 0.0
            return stats

    async def remove(self, key: Any) -> bool:
        """Remove a specific item from the cache by key.

        Args:
            key: The key of the item to remove.

        Returns:
            bool: True if the item was found and removed, False otherwise.
        """
        async with self._lock:
            if key in self._cache:
                self._cache.pop(key)
                if self._expiry is not None:
                    self._expiry.pop(key, None)
                return True
            return False


# --- Secure API Key Manager ---

class SecureApiKeyManager:
    """Manages API keys with optional encryption using Fernet.

    Retrieves the API key from environment variables. If encryption password and
    salt are provided via environment variables, it can encrypt the key for storage
    or decrypt a stored encrypted key.
    """

    def __init__(self, encrypted_key: Optional[str] = None,
                 key_env_var: str = config.API_KEY_ENV_VAR,
                 key_salt_env_var: str = config.API_KEY_SALT_ENV_VAR,
                 key_password_env_var: str = config.API_KEY_PASSWORD_ENV_VAR):
        """Initialize the secure API key manager.

        Args:
            encrypted_key: Optional pre-encrypted API key (base64 encoded).
            key_env_var: Environment variable name for the plain API key.
            key_salt_env_var: Environment variable name for the encryption salt.
            key_password_env_var: Environment variable name for the encryption password.
        """
        self.encrypted_key_input = encrypted_key # Store provided encrypted key if any
        self.key_env_var = key_env_var
        self.key_salt_env_var = key_salt_env_var
        self.key_password_env_var = key_password_env_var

        self._key: Optional[str] = None # Stores the decrypted/plain key
        self._fernet: Optional[Fernet] = None
        self._encryption_available = False
        self._initialized = False

        self._initialize_encryption()

    def _initialize_encryption(self) -> None:
        """Sets up the Fernet cipher if password and salt are available."""
        try:
            password = os.environ.get(self.key_password_env_var, "").encode(config.DEFAULT_ENCODING)
            # Use provided salt or generate/store one (less secure if generated each time)
            # A fixed salt stored securely is better. Using UUID as fallback for demo.
            salt_str = os.environ.get(self.key_salt_env_var)
            if salt_str:
                salt = salt_str.encode(config.DEFAULT_ENCODING)
                logger.info(f"Using encryption salt from env var: {self.key_salt_env_var}")
            else:
                # Generate a salt - WARNING: This makes stored keys non-portable if salt changes!
                salt = os.urandom(16) # Generate random salt if none provided
                logger.warning(f"No salt in env var {self.key_salt_env_var}. Generated temporary salt. Encrypted keys may not be reusable.")
                # Optionally, save the generated salt back to env or a file here if needed.

            if password and salt:
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=100000, # NIST recommended minimum
                    backend=default_backend()
                )
                encryption_key = urlsafe_b64encode(kdf.derive(password))
                self._fernet = Fernet(encryption_key)
                self._encryption_available = True
                logger.info("API key encryption initialized successfully.")
            else:
                logger.info(f"Encryption password or salt missing. API key will be handled in plain text.")
                self._encryption_available = False

        except ImportError:
            logger.warning("Cryptography package not available. API key encryption disabled.")
            self._encryption_available = False
        except Exception as e:
            logger.error(f"Error initializing API key encryption: {e}", exc_info=True)
            self._encryption_available = False

    def get_key(self) -> str:
        """Get the API key, decrypting if necessary.

        Retrieves from environment or decrypts the provided encrypted key.

        Returns:
            str: The API key, or an empty string if not found or decryption fails.
        """
        if self._key is None and not self._initialized:
            plain_key_from_env = os.environ.get(self.key_env_var, "")

            if self.encrypted_key_input and self._encryption_available and self._fernet:
                try:
                    self._key = self._decrypt_key(self.encrypted_key_input)
                    logger.info("API key successfully decrypted.")
                except Exception as e:
                    logger.error(f"Failed to decrypt provided API key: {e}. Checking environment variable '{self.key_env_var}'.")
                    # Fallback to environment variable if decryption fails
                    self._key = plain_key_from_env
            else:
                 # Use plain key from environment if no encrypted key provided or encryption unavailable
                 self._key = plain_key_from_env

            self._initialized = True # Mark as initialized even if key is empty

            if not self._key:
                 logger.warning(f"API key is missing or could not be retrieved/decrypted.")

        return self._key if self._key is not None else ""

    def _encrypt_key(self, key: str) -> Optional[str]:
        """Encrypt an API key using the initialized Fernet cipher.

        Args:
            key: The plain text API key to encrypt.

        Returns:
            str: The encrypted key as a base64 encoded string, or None if encryption failed.
        """
        if not self._encryption_available or not self._fernet:
            logger.warning("Encryption not available, cannot encrypt key.")
            return None
        if not key:
            return None

        try:
            encrypted_bytes = self._fernet.encrypt(key.encode(config.DEFAULT_ENCODING))
            return b64encode(encrypted_bytes).decode(config.DEFAULT_ENCODING)
        except Exception as e:
            logger.error(f"Failed to encrypt API key: {e}", exc_info=True)
            return None

    def _decrypt_key(self, encrypted_b64: str) -> str:
        """Decrypt an encrypted API key using the initialized Fernet cipher.

        Args:
            encrypted_b64: The encrypted API key as a base64 encoded string.

        Returns:
            str: The decrypted API key.

        Raises:
            ValueError: If encryption is not available.
            cryptography.fernet.InvalidToken: If decryption fails (invalid key or token).
            Exception: For other potential errors during decoding/decryption.
        """
        if not self._encryption_available or not self._fernet:
            raise ValueError("Encryption not available, cannot decrypt key.")
        if not encrypted_b64:
            raise ValueError("Encrypted key input is empty.")

        try:
            encrypted_bytes = b64decode(encrypted_b64)
            decrypted_bytes = self._fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode(config.DEFAULT_ENCODING)
        except InvalidToken as it:
             logger.error(f"Invalid token during decryption. Check password/salt/key format. Error: {it}")
             raise # Re-raise specific crypto error
        except Exception as e:
            logger.error(f"Failed to decode or decrypt API key: {e}", exc_info=True)
            raise # Re-raise other errors

    def validate_key(self, key_to_validate: Optional[str] = None) -> bool:
        """Validate that the API key exists and has a reasonable format.

        Args:
            key_to_validate: Optional key string to validate. If None, uses the managed key.

        Returns:
            bool: True if the key seems plausible, False otherwise.
        """
        key = key_to_validate if key_to_validate is not None else self.get_key()

        if not key:
            logger.error("API key validation failed: Key is missing.")
            return False

        # Basic length check (YouTube API keys are typically 39 chars)
        min_len, max_len = 30, 50
        if not (min_len <= len(key) <= max_len):
            logger.warning(f"API key validation warning: Key length ({len(key)}) is outside expected range ({min_len}-{max_len}).")
            # Return True but log warning, as length isn't a definitive check

        # Check for potentially invalid characters (basic check)
        # YouTube keys are typically alphanumeric with _ and -
        if not re.match(r'^[A-Za-z0-9_-]+$', key):
             logger.warning("API key validation warning: Key contains potentially invalid characters.")
             # Return True but log warning

        return True

    def obfuscate_key(self, key_to_obfuscate: Optional[str] = None) -> str:
        """Return an obfuscated version of the key suitable for logging.

        Args:
            key_to_obfuscate: Optional key string to obfuscate. If None, uses the managed key.

        Returns:
            str: Obfuscated key (e.g., "AIza...abc") or "[MISSING]".
        """
        key = key_to_obfuscate if key_to_obfuscate is not None else self.get_key()

        if not key:
            return "[MISSING]"

        # Show first 4 and last 3 characters
        if len(key) > 7:
            return f"{key[:4]}...{key[-3:]}"
        elif len(key) > 0:
             return f"{key[0]}...{'*'*(len(key)-1)}" # Show only first char if very short
        else:
             return "[EMPTY]" # Should not happen if !key check passed, but defensively
