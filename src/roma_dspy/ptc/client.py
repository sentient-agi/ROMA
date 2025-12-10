"""
PTC HTTP Client

HTTP client for communicating with PTC service from ROMA.
Handles execution plan submission, result retrieval, and error handling.
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
import httpx
from loguru import logger

from .schemas import PTCExecutionPlan, PTCArtifactResult, ExecutionStatus
from .cache import PTCCacheManager


class PTCClientError(Exception):
    """Base exception for PTC client errors."""
    pass


class PTCTimeoutError(PTCClientError):
    """PTC execution timed out."""
    pass


class PTCServiceError(PTCClientError):
    """PTC service returned an error."""
    pass


class PTCClient:
    """
    HTTP client for PTC service.

    Handles:
    - Sending PTCExecutionPlan to PTC service
    - Receiving PTCArtifactResult from PTC service
    - Cache integration
    - Retry logic with exponential backoff
    - Timeout handling
    """

    def __init__(
        self,
        service_url: str,
        cache_manager: Optional[PTCCacheManager] = None,
        timeout: int = 600,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        """
        Initialize PTC client.

        Args:
            service_url: Base URL of PTC service (e.g., "http://localhost:8001")
            cache_manager: Optional cache manager instance
            timeout: Request timeout in seconds (default: 600)
            max_retries: Maximum retry attempts (default: 3)
            retry_delay: Initial retry delay in seconds (default: 1.0)
        """
        self.service_url = service_url.rstrip("/")
        self.cache_manager = cache_manager or PTCCacheManager()
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # HTTP client configuration
        self.client_config = {
            "timeout": httpx.Timeout(timeout, connect=10.0),
            "limits": httpx.Limits(max_connections=10, max_keepalive_connections=5),
        }

    async def execute(self, plan: PTCExecutionPlan) -> PTCArtifactResult:
        """
        Execute PTC plan with caching and retry logic.

        Args:
            plan: Execution plan to send to PTC

        Returns:
            Artifact result from PTC (possibly from cache)

        Raises:
            PTCTimeoutError: If execution times out
            PTCServiceError: If PTC service returns an error
            PTCClientError: For other client-side errors
        """
        logger.info(f"Executing PTC plan: {plan.execution_id}")

        # Check cache first
        cached_result = await self.cache_manager.get(plan)
        if cached_result:
            logger.info(f"Cache hit for execution {plan.execution_id}")
            return cached_result

        # Execute with retry logic
        result = await self._execute_with_retry(plan)

        # Cache successful results
        if result.success:
            await self.cache_manager.set(plan, result)

        return result

    async def _execute_with_retry(self, plan: PTCExecutionPlan) -> PTCArtifactResult:
        """
        Execute plan with exponential backoff retry.

        Args:
            plan: Execution plan

        Returns:
            Artifact result from PTC

        Raises:
            PTCTimeoutError: If all retries fail due to timeout
            PTCServiceError: If all retries fail due to service error
        """
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff: 1s, 2s, 4s, 8s...
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    logger.info(
                        f"Retry attempt {attempt + 1}/{self.max_retries} "
                        f"after {delay}s delay (execution_id: {plan.execution_id})"
                    )
                    await asyncio.sleep(delay)

                return await self._execute_once(plan)

            except httpx.TimeoutException as e:
                last_exception = PTCTimeoutError(
                    f"PTC execution timed out after {self.timeout}s: {e}"
                )
                logger.warning(f"Timeout on attempt {attempt + 1}: {e}")

            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    # Retry on 5xx server errors
                    last_exception = PTCServiceError(
                        f"PTC service error ({e.response.status_code}): {e.response.text}"
                    )
                    logger.warning(f"Server error on attempt {attempt + 1}: {e}")
                else:
                    # Don't retry on 4xx client errors
                    raise PTCServiceError(
                        f"PTC request failed ({e.response.status_code}): {e.response.text}"
                    ) from e

            except Exception as e:
                last_exception = PTCClientError(f"Unexpected error: {e}")
                logger.error(f"Unexpected error on attempt {attempt + 1}: {e}")

        # All retries exhausted
        logger.error(f"All {self.max_retries} retry attempts failed for {plan.execution_id}")
        raise last_exception

    async def _execute_once(self, plan: PTCExecutionPlan) -> PTCArtifactResult:
        """
        Execute plan once (single attempt).

        Args:
            plan: Execution plan

        Returns:
            Artifact result from PTC

        Raises:
            httpx exceptions on failure
        """
        async with httpx.AsyncClient(**self.client_config) as client:
            # Send execution plan
            logger.debug(f"Sending plan to {self.service_url}/execute")
            response = await client.post(
                f"{self.service_url}/execute",
                json=plan.model_dump(mode="json"),
                headers={"Content-Type": "application/json"},
            )

            # Raise on HTTP errors
            response.raise_for_status()

            # Parse response
            result = PTCArtifactResult.model_validate(response.json())

            logger.info(
                f"Received result for {plan.execution_id}: "
                f"status={result.status}, artifacts={len(result.artifacts)}, "
                f"duration={result.duration_seconds:.2f}s"
            )

            return result

    async def health_check(self) -> Dict[str, Any]:
        """
        Check PTC service health.

        Returns:
            Health check response from PTC service

        Raises:
            PTCClientError: If health check fails
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.service_url}/health")
                response.raise_for_status()
                return response.json()

        except Exception as e:
            raise PTCClientError(f"Health check failed: {e}") from e

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get PTC service statistics.

        Returns:
            Statistics from PTC service (if supported)

        Raises:
            PTCClientError: If stats retrieval fails
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.service_url}/stats")
                response.raise_for_status()
                return response.json()

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Stats endpoint not implemented
                return {"error": "Stats endpoint not available"}
            raise PTCClientError(f"Stats retrieval failed: {e}") from e

        except Exception as e:
            raise PTCClientError(f"Stats retrieval failed: {e}") from e

    async def close(self):
        """Close client resources (placeholder for future cleanup)."""
        # Currently no persistent connections to close
        # This is here for future compatibility
        pass

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
