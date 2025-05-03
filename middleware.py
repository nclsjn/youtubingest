#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FastAPI Middleware classes for Youtubingest.

Includes Rate Limiting, Metrics Collection, and Content Security.
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from typing import Dict, Any, List, Optional

from fastapi import Request, Response, status, FastAPI
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

# Import config for settings
from config import config
from logging_config import StructuredLogger

# Use StructuredLogger instead of standard logger
logger = StructuredLogger(__name__)


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting requests based on client IP address.

    Implements a sliding window rate limiting strategy using a deque per IP.
    Also includes basic IP banning for persistent offenders.
    """

    def __init__(self, app: FastAPI,
                 requests_limit: int = config.RATE_LIMIT_REQUESTS,
                 window_seconds: int = config.RATE_LIMIT_WINDOW_SECONDS,
                 ban_threshold: int = 50, # Example: Ban after 50 blocks
                 ban_duration_seconds: int = 3600 # Example: Ban for 1 hour
                 ):
        """Initialize the rate limiter middleware.

        Args:
            app: The FastAPI application instance.
            requests_limit: Maximum number of requests allowed per IP within the window.
            window_seconds: The time window duration in seconds.
            ban_threshold: Number of times an IP must be blocked before being banned.
            ban_duration_seconds: Duration in seconds for which an IP is banned.
        """
        super().__init__(app)
        # Store request timestamps for each IP: {ip: deque([ts1, ts2, ...])}
        self.requests: Dict[str, deque[float]] = defaultdict(deque)
        self.requests_limit = requests_limit
        self.window_seconds = window_seconds
        # Store banned IPs and their unban time: {ip: unban_timestamp}
        self.banned_ips: Dict[str, float] = {}
        # Store block counts for potential banning: {ip: block_count}
        self.block_counts: Dict[str, int] = defaultdict(int)
        self.ban_threshold = ban_threshold
        self.ban_duration_seconds = ban_duration_seconds
        self._lock = asyncio.Lock() # Protect shared state access

        logger.info(
            f"Rate limiter initialized: {requests_limit} req / {window_seconds}s per IP. Ban threshold: {ban_threshold} blocks.",
            limit=requests_limit,
            window=window_seconds,
            ban_threshold=ban_threshold
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request, applying rate limiting logic.

        Args:
            request: The incoming FastAPI request.
            call_next: The next middleware or endpoint handler in the chain.

        Returns:
            Response: Either the response from the next handler or a 429/403 error response.
        """
        client_ip = self._get_client_ip(request)
        path = request.url.path

        # Skip rate limiting for static assets and health checks for reliability
        if path.startswith(("/static/", "/favicon.ico", "/health")):
            return await call_next(request)

        current_time = time.monotonic()

        async with self._lock:
            # --- Check Ban Status ---
            unban_time = self.banned_ips.get(client_ip)
            if unban_time:
                if current_time < unban_time:
                    logger.warning(
                        f"Banned IP attempted access: {client_ip}. Banned until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(unban_time))}",
                        client_ip=client_ip,
                        path=path,
                        unban_time=unban_time
                    )
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Access temporarily denied due to excessive requests.", "error_code": "IP_BANNED"}
                    )
                else:
                    # Ban expired, remove from ban list and reset block count
                    del self.banned_ips[client_ip]
                    self.block_counts[client_ip] = 0
                    logger.info(f"IP ban expired for {client_ip}.", client_ip=client_ip)

            # --- Rate Limit Check ---
            ip_requests = self.requests[client_ip]

            # Remove timestamps older than the window
            while ip_requests and ip_requests[0] <= current_time - self.window_seconds:
                ip_requests.popleft()

            # Check if limit is exceeded
            if len(ip_requests) >= self.requests_limit:
                self.block_counts[client_ip] += 1
                block_count = self.block_counts[client_ip]

                logger.warning(
                    f"Rate limit exceeded for {client_ip} ({len(ip_requests)} requests). Block count: {block_count}",
                    client_ip=client_ip,
                    requests_count=len(ip_requests),
                    limit=self.requests_limit,
                    path=path,
                    block_count=block_count
                )

                # --- Apply Ban if Threshold Reached ---
                if block_count >= self.ban_threshold:
                    ban_until = current_time + self.ban_duration_seconds
                    self.banned_ips[client_ip] = ban_until
                    logger.error(
                        f"IP {client_ip} banned until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ban_until))} due to {block_count} blocks.",
                        client_ip=client_ip,
                        violations=block_count,
                        ban_duration_seconds=self.ban_duration_seconds
                    )
                    # Deny access immediately after banning
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={"detail": "Access temporarily denied due to excessive requests.", "error_code": "IP_BANNED"}
                    )

                # Calculate Retry-After header value (seconds until oldest request expires)
                retry_after = 1 # Default minimum
                if ip_requests:
                     retry_after = max(1, int(self.window_seconds - (current_time - ip_requests[0])) + 1)

                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": "Rate limit exceeded. Please try again later.", "error_code": "RATE_LIMITED"},
                    headers={"Retry-After": str(retry_after)}
                )
            else:
                # Record current request timestamp
                ip_requests.append(current_time)
                # Reset block count on successful request if previously blocked
                if self.block_counts[client_ip] > 0:
                     logger.info(f"Rate limit access restored for {client_ip}. Resetting block count.", client_ip=client_ip)
                     self.block_counts[client_ip] = 0


        # Proceed with the request if not rate-limited or banned
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Log errors happening *after* the rate limiter check
            logger.error(f"Error processing request for {client_ip} after rate limit check: {e}", client_ip=client_ip, path=path, exc_info=True)
            # Re-raise the exception to be handled by FastAPI's error handling
            raise

    def _get_client_ip(self, request: Request) -> str:
        """Extract the client IP address from the request.

        Considers proxy headers like 'X-Forwarded-For' and 'X-Real-IP'.

        Args:
            request: The FastAPI request object.

        Returns:
            str: The determined client IP address, or "unknown".
        """
        # Check standard proxy headers first
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Take the first IP in the list (client's original IP)
            client_ip = forwarded_for.split(",")[0].strip()
            return client_ip

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            client_ip = real_ip.strip()
            return client_ip

        # Fallback to the direct client connection information
        if request.client and request.client.host:
            return request.client.host

        return "unknown"

    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics about the rate limiter.

        Returns:
            dict: Statistics including tracked IPs, banned IPs, limits, etc.
        """
        current_time = time.monotonic()
        # Clean up expired bans before reporting stats
        expired_bans = [ip for ip, unban_time in self.banned_ips.items() if current_time >= unban_time]
        for ip in expired_bans:
            if ip in self.banned_ips: del self.banned_ips[ip]
            if ip in self.block_counts: del self.block_counts[ip] # Reset count when ban expires

        return {
            "limit_per_window": self.requests_limit,
            "window_seconds": self.window_seconds,
            "tracked_ips_count": len(self.requests),
            "banned_ips_count": len(self.banned_ips),
            "ban_threshold": self.ban_threshold,
            "ban_duration_seconds": self.ban_duration_seconds,
            # Optionally include details about current blocks/bans if needed for monitoring
            # "current_block_counts": dict(self.block_counts),
            # "currently_banned_ips": list(self.banned_ips.keys()),
        }


class SecurityAndMetricsMiddleware(BaseHTTPMiddleware):
    """Combined middleware for security checks, response headers, and metrics collection.

    Handles:
    1. Content length limits for request bodies
    2. Security headers for responses
    3. Metrics collection for request/response statistics
    """

    # Limit the size of response times deque to prevent unbounded memory growth
    MAX_RESPONSE_TIMES = 1000

    def __init__(self, app: FastAPI, max_content_length: int = config.MAX_CONTENT_LENGTH):
        """Initialize the combined middleware.

        Args:
            app: The FastAPI application instance
            max_content_length: Maximum allowed request content length in bytes
        """
        super().__init__(app)
        self.max_content_length = max_content_length

        # Metrics tracking
        self.stats = {
            "total_requests": 0,
            "success_requests": 0,
            "client_error_requests": 0,
            "server_error_requests": 0,
            "status_codes": defaultdict(int),
            "paths": defaultdict(int),
            "response_times_ms": deque(maxlen=self.MAX_RESPONSE_TIMES),
            "start_time": time.monotonic()
        }
        self._lock = asyncio.Lock()

        logger.info(f"SecurityAndMetricsMiddleware initialized. Max content length: {max_content_length / (1024*1024):.2f} MB")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process the request with security checks and metrics collection."""
        start_time = time.monotonic()
        path = request.url.path
        method = request.method
        client_ip = request.client.host if request.client else "unknown"
        is_static = path.startswith(("/static/", "/favicon.ico"))

        # --- Security Check: Content Length ---
        if method in ("POST", "PUT", "PATCH"):
            content_length_header = request.headers.get("content-length")
            if content_length_header:
                try:
                    content_length = int(content_length_header)
                    if content_length > self.max_content_length:
                        logger.warning(
                            f"Request body too large: {content_length} bytes > {self.max_content_length} bytes limit.",
                            client_ip=client_ip,
                            path=path,
                            method=method
                        )
                        return JSONResponse(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            content={
                                "detail": f"Request body is too large. Maximum allowed size is {self.max_content_length / (1024*1024):.1f} MB.",
                                "error_code": "CONTENT_TOO_LARGE"
                            }
                        )
                except ValueError:
                    logger.warning(f"Invalid Content-Length header: {content_length_header}")

        # --- Process Request ---
        response = None
        status_code = 500  # Default if exception occurs
        try:
            response = await call_next(request)
            status_code = response.status_code

            # --- Add Security Headers ---
            if not is_static:
                # Basic security headers
                response.headers["X-Content-Type-Options"] = "nosniff"
                response.headers["X-Frame-Options"] = "SAMEORIGIN"
                response.headers["X-XSS-Protection"] = "1; mode=block"
                response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

                # Content Security Policy for HTML responses
                content_type = response.headers.get("content-type", "")
                if "text/html" in content_type:
                    csp_policy = [
                        "default-src 'self'",
                        "script-src 'self' https://cdnjs.cloudflare.com",
                        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
                        "font-src 'self' https://fonts.gstatic.com",
                        "img-src 'self' data:",
                        "connect-src 'self'",
                        "frame-ancestors 'self'",
                        "object-src 'none'",
                        "base-uri 'self'",
                        "form-action 'self'"
                    ]
                    response.headers["Content-Security-Policy"] = "; ".join(csp_policy)

        except Exception as exc:
            logger.error(
                "Exception during request processing",
                path=path, method=method, client_ip=client_ip, error=str(exc),
                exc_info=True
            )
            status_code = getattr(exc, "status_code", 500)
            raise
        finally:
            # --- Record Metrics ---
            process_time_ms = (time.monotonic() - start_time) * 1000

            async with self._lock:
                self.stats["total_requests"] += 1

                if 200 <= status_code < 400:
                    self.stats["success_requests"] += 1
                elif 400 <= status_code < 500:
                    self.stats["client_error_requests"] += 1
                else:
                    self.stats["server_error_requests"] += 1

                self.stats["status_codes"][status_code] += 1

                if not is_static:
                    self.stats["paths"][path] += 1
                    self.stats["response_times_ms"].append(process_time_ms)

            # Log request completion
            log_level = logging.INFO
            if status_code >= 500:
                log_level = logging.ERROR
            elif status_code >= 400:
                log_level = logging.WARNING

            log_msg = {
                "path": path,
                "method": method,
                "status_code": status_code,
                "duration_ms": round(process_time_ms, 2),
                "client_ip": client_ip
            }

            if log_level == logging.ERROR:
                logger.error("Request completed", **log_msg)
            elif log_level == logging.WARNING:
                logger.warning("Request completed", **log_msg)
            else:
                logger.info("Request completed", **log_msg)

            # Log slow responses
            if process_time_ms > 3000:
                logger.warning(f"Slow response: {method} {path}", **log_msg)

        # Return response or fallback error
        if response:
            return response
        else:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": "Internal Server Error", "error_code": "UNHANDLED_EXCEPTION"}
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get collected metrics statistics."""
        with self._lock:
            stats_copy = self.stats.copy()
            response_times = list(stats_copy["response_times_ms"])

        uptime = time.monotonic() - stats_copy["start_time"]
        total_requests = stats_copy["total_requests"]

        metrics = {
            "uptime_seconds": round(uptime, 1),
            "total_requests": total_requests,
            "requests_per_second": round(total_requests / max(1, uptime), 2),
            "success_requests": stats_copy["success_requests"],
            "client_error_requests": stats_copy["client_error_requests"],
            "server_error_requests": stats_copy["server_error_requests"],
            "status_codes": dict(stats_copy["status_codes"]),
            "top_paths": dict(
                sorted(stats_copy["paths"].items(), key=lambda item: item[1], reverse=True)[:10]
            ),
            "response_time_stats_ms": {}
        }

        if response_times:
            count = len(response_times)
            avg = sum(response_times) / count
            min_rt = min(response_times)
            max_rt = max(response_times)
            sorted_times = sorted(response_times)
            p95 = sorted_times[int(count * 0.95)] if count > 20 else None
            p99 = sorted_times[int(count * 0.99)] if count > 100 else None

            metrics["response_time_stats_ms"] = {
                "count": count,
                "average": round(avg, 2),
                "min": round(min_rt, 2),
                "max": round(max_rt, 2),
                "p95": round(p95, 2) if p95 is not None else None,
                "p99": round(p99, 2) if p99 is not None else None
            }
        else:
            metrics["response_time_stats_ms"] = {"count": 0}

        return metrics
