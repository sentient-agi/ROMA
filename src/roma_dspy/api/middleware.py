"""Middleware for FastAPI application."""

import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from loguru import logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging HTTP requests and responses.

    Logs:
    - Request method, path, and client IP
    - Response status code and duration
    - Errors and exceptions
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process HTTP request and log details.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler in chain

        Returns:
            HTTP response
        """
        # Start timer
        start_time = time.time()

        # Extract request details
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"
        request_id = request.headers.get("X-Request-ID", "no-request-id")

        # Log request
        logger.info(
            f"Request started: {method} {path}",
            extra={
                "method": method,
                "path": path,
                "client_ip": client_ip,
                "request_id": request_id,
            },
        )

        try:
            # Process request
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log response
            logger.info(
                f"Request completed: {method} {path} - {response.status_code} ({duration_ms:.2f}ms)",
                extra={
                    "method": method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                    "request_id": request_id,
                },
            )

            # Add duration header
            response.headers["X-Process-Time"] = f"{duration_ms:.2f}ms"

            return response

        except Exception as e:
            # Calculate duration
            duration_ms = (time.time() - start_time) * 1000

            # Log error
            logger.error(
                f"Request failed: {method} {path} - {type(e).__name__}: {str(e)} ({duration_ms:.2f}ms)",
                extra={
                    "method": method,
                    "path": path,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                    "request_id": request_id,
                },
                exc_info=True,
            )

            # Re-raise to let FastAPI handle it
            raise


class CORSMiddleware:
    """
    CORS middleware configuration.

    Note: FastAPI has built-in CORSMiddleware, this is just a reference.
    Use fastapi.middleware.cors.CORSMiddleware in main.py instead.
    """

    pass


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiting middleware.

    WARNING: This is a basic implementation suitable only for single-server MVP.
    For production, use Redis-based rate limiting.
    """

    def __init__(self, app, requests_per_minute: int = 60):
        """
        Initialize rate limiter.

        Args:
            app: FastAPI application
            requests_per_minute: Maximum requests per minute per IP
        """
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self._request_counts: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Check rate limit and process request.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/handler

        Returns:
            HTTP response or 429 Too Many Requests
        """
        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Skip rate limiting for health check
        if request.url.path == "/health":
            return await call_next(request)

        # Current time
        now = time.time()
        minute_ago = now - 60

        # Clean old requests
        if client_ip in self._request_counts:
            self._request_counts[client_ip] = [
                req_time
                for req_time in self._request_counts[client_ip]
                if req_time > minute_ago
            ]
        else:
            self._request_counts[client_ip] = []

        # Check limit
        if len(self._request_counts[client_ip]) >= self.requests_per_minute:
            logger.warning(
                f"Rate limit exceeded for {client_ip}",
                extra={
                    "client_ip": client_ip,
                    "requests_in_window": len(self._request_counts[client_ip]),
                    "limit": self.requests_per_minute,
                },
            )
            return Response(
                content='{"error": "Rate limit exceeded. Please try again later."}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        # Record request
        self._request_counts[client_ip].append(now)

        # Process request
        response = await call_next(request)

        # Add rate limit headers
        remaining = self.requests_per_minute - len(self._request_counts[client_ip])
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))
        response.headers["X-RateLimit-Reset"] = str(int(now + 60))

        return response
