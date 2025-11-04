"""API client for ROMA-DSPy visualization APIs with retry logic."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

import httpx
from loguru import logger

from roma_dspy.tui.core.config import ApiConfig


class ApiClient:
    """Async HTTP client for visualization APIs with retry logic."""

    def __init__(self, config: ApiConfig) -> None:
        """Initialize API client.

        Args:
            config: API configuration
        """
        self.config = config
        self.base_url = config.base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(config.timeout),
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5
            )
        )
        logger.info(f"API Client initialized: {self.base_url}")

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
        logger.debug("API Client closed")

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: API path
            **kwargs: Additional request parameters

        Returns:
            Response JSON

        Raises:
            httpx.HTTPError: If request fails after retries
        """
        url = f"{self.base_url}{path}"
        last_error = None

        for attempt in range(self.config.max_retries):
            try:
                logger.debug(f"Request {method} {url} (attempt {attempt + 1}/{self.config.max_retries})")
                response = await self.client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()

            except httpx.HTTPError as e:
                last_error = e
                if attempt < self.config.max_retries - 1:
                    delay = self.config.retry_delay * (2 ** attempt)  # Exponential backoff
                    logger.warning(f"Request failed: {e}. Retrying in {delay}s...")
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Request failed after {self.config.max_retries} attempts: {e}")

        # If we get here, all retries failed
        raise last_error

    async def _get(self, path: str) -> Dict[str, Any]:
        """Make GET request with retry.

        Args:
            path: API path

        Returns:
            Response JSON
        """
        return await self._request_with_retry("GET", path)

    async def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request with retry.

        Args:
            path: API path
            payload: Request payload

        Returns:
            Response JSON
        """
        return await self._request_with_retry("POST", path, json=payload)

    async def fetch_execution_data(self, execution_id: str) -> Dict[str, Any]:
        """Fetch consolidated execution data.

        Args:
            execution_id: Execution ID

        Returns:
            Execution data with tasks, traces, etc.
        """
        logger.info(f"Fetching execution data: {execution_id}")
        return await self._get(f"/api/v1/executions/{execution_id}/data")

    async def fetch_lm_traces(self, execution_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Fetch LM traces.

        Args:
            execution_id: Execution ID
            limit: Maximum number of traces

        Returns:
            List of LM trace records
        """
        logger.info(f"Fetching LM traces: {execution_id} (limit={limit})")
        return await self._get(f"/api/v1/executions/{execution_id}/lm-traces?limit={limit}")

    async def fetch_metrics(self, execution_id: str) -> Dict[str, Any]:
        """Fetch aggregated metrics.

        Args:
            execution_id: Execution ID

        Returns:
            Metrics data
        """
        logger.info(f"Fetching metrics: {execution_id}")
        return await self._get(f"/api/v1/executions/{execution_id}/metrics")

    async def fetch_toolkit_metrics(self, execution_id: str) -> Dict[str, Any]:
        """Fetch toolkit metrics.

        Args:
            execution_id: Execution ID

        Returns:
            Toolkit metrics data
        """
        logger.info(f"Fetching toolkit metrics: {execution_id}")
        return await self._get(f"/api/v1/executions/{execution_id}/toolkit-metrics")

    async def list_executions(
        self,
        status: str | None = None,
        profile: str | None = None,
        experiment_name: str | None = None,
        offset: int = 0,
        limit: int = 100
    ) -> Dict[str, Any]:
        """List executions with optional filtering.

        Args:
            status: Filter by status (pending, running, completed, failed, cancelled)
            profile: Filter by profile name
            experiment_name: Filter by experiment name
            offset: Pagination offset
            limit: Maximum number of results

        Returns:
            Response containing total count and list of executions
        """
        logger.info(f"Listing executions (status={status}, profile={profile}, experiment={experiment_name})")

        # Build query parameters
        params = []
        if status:
            params.append(f"status={status}")
        if profile:
            params.append(f"profile={profile}")
        if experiment_name:
            params.append(f"experiment_name={experiment_name}")
        if offset:
            params.append(f"offset={offset}")
        if limit:
            params.append(f"limit={limit}")

        query_string = "&".join(params)
        path = f"/api/v1/executions?{query_string}" if query_string else "/api/v1/executions"

        return await self._get(path)

    async def fetch_all_parallel(self, execution_id: str) -> tuple[Dict[str, Any], List[Dict[str, Any]], Dict[str, Any]]:
        """Fetch all data in parallel.

        Args:
            execution_id: Execution ID

        Returns:
            Tuple of (execution_data, lm_traces, metrics)
        """
        logger.info(f"Fetching all data in parallel: {execution_id}")
        results = await asyncio.gather(
            self.fetch_execution_data(execution_id),
            self.fetch_lm_traces(execution_id),
            self.fetch_metrics(execution_id),
            return_exceptions=True
        )

        # Handle any exceptions
        execution_data = results[0] if not isinstance(results[0], Exception) else {}
        lm_traces = results[1] if not isinstance(results[1], Exception) else []
        metrics = results[2] if not isinstance(results[2], Exception) else {}

        if isinstance(results[0], Exception):
            logger.error(f"Failed to fetch execution data: {results[0]}")
        if isinstance(results[1], Exception):
            logger.error(f"Failed to fetch LM traces: {results[1]}")
        if isinstance(results[2], Exception):
            logger.error(f"Failed to fetch metrics: {results[2]}")

        return execution_data, lm_traces, metrics
