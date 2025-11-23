"""Generic async HTTP client for ROMA-DSPy toolkits."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx
from loguru import logger


class HTTPClientError(Exception):
    """HTTP client error with status code and response details."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
    ):
        """Initialize HTTP client error.

        Args:
            message: Error message
            status_code: HTTP status code if available
            response_text: Response text if available
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class AsyncHTTPClient:
    """Generic async HTTP client with retry logic and rate limiting.

    Provides a reusable HTTP client for toolkits that need to make
    API requests with proper error handling, retries, and timeouts.
    """

    def __init__(
        self,
        base_url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        rate_limit: Optional[float] = None,
    ):
        """Initialize async HTTP client.

        Args:
            base_url: Base URL for all requests
            headers: Default headers to include in all requests
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (exponential backoff)
            rate_limit: Minimum seconds between requests (None = no rate limiting)
        """
        self.base_url = base_url.rstrip("/")
        self.default_headers = headers or {}
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.rate_limit = rate_limit

        self._client: Optional[httpx.AsyncClient] = None
        self._last_request_time: float = 0.0

    async def __aenter__(self) -> AsyncHTTPClient:
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _ensure_client(self) -> None:
        """Ensure HTTP client is initialized."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.default_headers,
                timeout=self.timeout,
            )

    async def get(
        self,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make GET request.

        Args:
            path: URL path (relative to base_url)
            params: Query parameters
            headers: Additional headers for this request

        Returns:
            Parsed JSON response

        Raises:
            HTTPClientError: On request failure
        """
        return await self._request("GET", path, params=params, headers=headers)

    async def post(
        self,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make POST request.

        Args:
            path: URL path (relative to base_url)
            json_data: JSON body
            params: Query parameters
            headers: Additional headers for this request

        Returns:
            Parsed JSON response

        Raises:
            HTTPClientError: On request failure
        """
        return await self._request(
            "POST", path, json_data=json_data, params=params, headers=headers
        )

    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting if configured."""
        if self.rate_limit is None:
            return

        import time

        current_time = time.time()
        time_since_last = current_time - self._last_request_time

        if time_since_last < self.rate_limit:
            await asyncio.sleep(self.rate_limit - time_since_last)

        self._last_request_time = time.time()

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic.

        Args:
            method: HTTP method
            path: URL path
            params: Query parameters
            json_data: JSON body
            headers: Additional headers

        Returns:
            Parsed JSON response

        Raises:
            HTTPClientError: On request failure after retries
        """
        await self._ensure_client()

        # Apply rate limiting
        await self._apply_rate_limit()

        # Merge headers
        request_headers = {**self.default_headers}
        if headers:
            request_headers.update(headers)

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries + 1):
            try:
                logger.debug(
                    f"Making {method} request to {path} (attempt {attempt + 1})"
                )

                response = await self._client.request(
                    method=method,
                    url=path,
                    params=params,
                    json=json_data,
                    headers=request_headers,
                )

                response.raise_for_status()

                # Parse JSON response
                try:
                    return response.json()
                except Exception as e:
                    raise HTTPClientError(
                        f"Invalid JSON response: {e}",
                        status_code=response.status_code,
                        response_text=response.text,
                    )

            except httpx.HTTPStatusError as e:
                last_error = HTTPClientError(
                    f"HTTP {e.response.status_code}: {e.response.text}",
                    status_code=e.response.status_code,
                    response_text=e.response.text,
                )

                # Don't retry client errors (4xx)
                if 400 <= e.response.status_code < 500:
                    logger.error(f"Client error (no retry): {last_error}")
                    raise last_error

            except httpx.RequestError as e:
                last_error = HTTPClientError(f"Request failed: {e}")

            except Exception as e:
                last_error = HTTPClientError(f"Unexpected error: {e}")

            # Exponential backoff before retry
            if attempt < self.max_retries:
                delay = self.retry_delay * (2**attempt)
                logger.debug(f"Retrying after {delay}s delay")
                await asyncio.sleep(delay)

        # All retries exhausted
        logger.error(f"Request failed after {self.max_retries + 1} attempts")
        raise last_error

    def update_headers(self, headers: Dict[str, str]) -> None:
        """Update default headers.

        Args:
            headers: Headers to merge with existing defaults
        """
        self.default_headers.update(headers)

        # Update client headers if initialized
        if self._client is not None:
            self._client.headers.update(headers)

    async def close(self) -> None:
        """Close HTTP client and clean up resources."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.debug("HTTP client closed")
