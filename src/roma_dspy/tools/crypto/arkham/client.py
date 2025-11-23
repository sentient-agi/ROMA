"""Arkham Intelligence API client.

Low-level async HTTP client for Arkham Intelligence blockchain analytics API.
Handles authentication, rate limiting, and response parsing.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from loguru import logger

from roma_dspy.tools.utils.http_client import AsyncHTTPClient, HTTPClientError
from roma_dspy.tools.value_objects.crypto import ErrorType
from roma_dspy.tools.crypto.arkham.types import ArkhamAPIError


class ArkhamAPIClient:
    """Async client for Arkham Intelligence API.

    Provides low-level access to Arkham Intelligence blockchain analytics endpoints
    with dual rate limiting (standard 20 req/sec, heavy 1 req/sec for data-intensive endpoints).

    Rate Limits:
        - Standard endpoints: 20 requests/second (0.05s minimum between requests)
        - Heavy endpoints: 1 request/second (1.0s minimum between requests)
          Heavy endpoints: /token/top_flow/{id}, /transfers

    Authentication:
        All requests require API-Key header with valid Arkham API key.
    """

    # API endpoint templates
    _ENDPOINTS = {
        "top_tokens": "/token/top",
        "token_holders": "/token/holders/{pricing_id}",
        "token_flow": "/token/top_flow/{pricing_id}",
        "supported_chains": "/chains",
        "transfers": "/transfers",
        "balances": "/balances/address/{address}",
    }

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.arkm.com",
        timeout: float = 30.0,
    ):
        """Initialize Arkham API client.

        Args:
            api_key: Arkham API key (reads from ARKHAM_API_KEY if None)
            base_url: Base URL for API endpoints
            timeout: Request timeout in seconds
        """
        self.api_key = api_key or os.getenv("ARKHAM_API_KEY")
        if not self.api_key:
            raise ValueError(
                "Arkham API key required. Set ARKHAM_API_KEY environment variable "
                "or pass api_key parameter."
            )

        self.base_url = base_url
        self.timeout = timeout

        # Initialize HTTP client with Arkham headers and rate limiting
        # Arkham API: 20 req/sec standard = 0.05s between requests
        self._client = AsyncHTTPClient(
            base_url=base_url,
            headers={
                "API-Key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=timeout,
            rate_limit=0.05,  # 20 requests/second
        )

    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_heavy_endpoint: bool = False,
    ) -> Dict[str, Any]:
        """Make API request to Arkham Intelligence.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            use_heavy_endpoint: Use heavy endpoint (currently ignored, same rate limit)

        Returns:
            dict: JSON response from API

        Raises:
            ArkhamAPIError: If API returns error response
        """
        try:
            response = await self._client.get(endpoint, params=params)
            return response

        except HTTPClientError as e:
            # Map HTTP errors to ArkhamAPIError with appropriate ErrorType
            if e.status_code == 401:
                error_type = ErrorType.AUTHENTICATION_ERROR
            elif e.status_code == 429:
                error_type = ErrorType.RATE_LIMIT_ERROR
            elif e.status_code == 404:
                error_type = ErrorType.NOT_FOUND_ERROR
            elif e.status_code and 500 <= e.status_code < 600:
                error_type = ErrorType.API_ERROR
            else:
                error_type = ErrorType.NETWORK_ERROR

            raise ArkhamAPIError(
                message=str(e),
                status_code=e.status_code,
                error_type=error_type,
            ) from e

        except Exception as e:
            raise ArkhamAPIError(
                message=f"Unexpected error during API request: {e}",
                error_type=ErrorType.UNKNOWN_ERROR,
            ) from e

    async def get_top_tokens(
        self,
        timeframe: str = "24h",
        order_by_agg: str = "volume",
        order_by_desc: bool = True,
        order_by_percent: bool = False,
        from_index: int = 0,
        size: int = 10,
        chains: Optional[str] = None,
        min_volume: Optional[float] = None,
        max_volume: Optional[float] = None,
        min_market_cap: Optional[float] = None,
        max_market_cap: Optional[float] = None,
        num_reference_periods: str = "auto",
        token_ids: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get top tokens by various metrics.

        Args:
            timeframe: Time period ("1h", "6h", "12h", "24h", "7d")
            order_by_agg: Metric to sort by (volume, inflow, outflow, etc.)
            order_by_desc: Sort descending
            order_by_percent: Sort by percentage change
            from_index: Pagination offset
            size: Number of results
            chains: Comma-separated chain list
            min_volume: Minimum volume filter
            max_volume: Maximum volume filter
            min_market_cap: Minimum market cap filter
            max_market_cap: Maximum market cap filter
            num_reference_periods: Reference periods for comparison
            token_ids: Comma-separated token IDs

        Returns:
            dict: API response with tokens data
        """
        params = {
            "timeframe": timeframe,
            "orderByAgg": order_by_agg,
            "orderByDesc": "true" if order_by_desc else "false",
            "orderByPercent": "true" if order_by_percent else "false",
            "from": from_index,
            "size": size,
            "numReferencePeriods": num_reference_periods,
        }

        # Add optional filters
        if chains:
            params["chains"] = chains
        if min_volume is not None:
            params["minVolume"] = min_volume
        if max_volume is not None:
            params["maxVolume"] = max_volume
        if min_market_cap is not None:
            params["minMarketCap"] = min_market_cap
        if max_market_cap is not None:
            params["maxMarketCap"] = max_market_cap
        if token_ids:
            params["tokenIds"] = token_ids

        return await self._request(self._ENDPOINTS["top_tokens"], params)

    async def get_token_holders(
        self,
        pricing_id: str,
        group_by_entity: bool = False,
    ) -> Dict[str, Any]:
        """Get token holder distribution by CoinGecko pricing ID.

        Args:
            pricing_id: CoinGecko pricing ID (e.g., "bitcoin", "ethereum")
            group_by_entity: Group results by entity

        Returns:
            dict: API response with holder data
        """
        params = {}
        if group_by_entity:
            params["groupByEntity"] = group_by_entity

        endpoint = self._ENDPOINTS["token_holders"].format(pricing_id=pricing_id)
        return await self._request(endpoint, params)

    async def get_token_top_flow(
        self,
        pricing_id: str,
        time_last: str = "24h",
        chains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get top token flows (inflows/outflows) by pricing ID.

        Note: This endpoint has 1 req/sec rate limit.

        Args:
            pricing_id: CoinGecko pricing ID
            time_last: Time period (e.g., "24h", "7d")
            chains: Optional comma-separated chain list

        Returns:
            dict: API response with flow data
        """
        params = {
            "timeLast": time_last,
            "id": pricing_id,
        }

        if chains:
            params["chains"] = chains

        endpoint = self._ENDPOINTS["token_flow"].format(pricing_id=pricing_id)
        return await self._request(endpoint, params, use_heavy_endpoint=True)

    async def get_supported_chains(self) -> Dict[str, Any]:
        """Get list of supported blockchain networks.

        Returns:
            dict: API response with supported chains
        """
        return await self._request(self._ENDPOINTS["supported_chains"])

    async def get_transfers(
        self,
        base: Optional[str] = None,
        chains: Optional[str] = None,
        flow: Optional[str] = None,
        from_addresses: Optional[str] = None,
        to_addresses: Optional[str] = None,
        tokens: Optional[str] = None,
        counterparties: Optional[str] = None,
        time_last: Optional[str] = None,
        time_gte: Optional[str] = None,
        time_lte: Optional[str] = None,
        value_gte: Optional[float] = None,
        value_lte: Optional[float] = None,
        usd_gte: Optional[float] = None,
        usd_lte: Optional[float] = None,
        sort_key: Optional[str] = None,
        sort_dir: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Get transfers with filtering options.

        Note: This endpoint has 1 req/sec rate limit.

        Args:
            base: Filter by entity or address
            chains: Comma-separated chain list
            flow: Transfer direction ("in", "out", "self", "all")
            from_addresses: Comma-separated sender addresses/entities
            to_addresses: Comma-separated receiver addresses/entities
            tokens: Comma-separated token addresses/IDs
            counterparties: Comma-separated counterparty addresses/entities
            time_last: Recent duration filter (e.g., "24h", "7d")
            time_gte: Filter from timestamp (milliseconds)
            time_lte: Filter to timestamp (milliseconds)
            value_gte: Minimum raw token value
            value_lte: Maximum raw token value
            usd_gte: Minimum USD value
            usd_lte: Maximum USD value
            sort_key: Sort field ("time", "value", "usd")
            sort_dir: Sort direction ("asc", "desc")
            limit: Maximum results
            offset: Pagination offset

        Returns:
            dict: API response with transfer data
        """
        params = {
            "limit": limit,
            "offset": offset,
        }

        # Add optional filters using correct API parameter names
        if base:
            params["base"] = base
        if chains:
            params["chains"] = chains
        if flow:
            params["flow"] = flow
        if from_addresses:
            params["from"] = from_addresses
        if to_addresses:
            params["to"] = to_addresses
        if tokens:
            params["tokens"] = tokens
        if counterparties:
            params["counterparties"] = counterparties
        if time_last:
            params["timeLast"] = time_last
        if time_gte:
            params["timeGte"] = time_gte
        if time_lte:
            params["timeLte"] = time_lte
        if value_gte is not None:
            params["valueGte"] = value_gte
        if value_lte is not None:
            params["valueLte"] = value_lte
        if usd_gte is not None:
            params["usdGte"] = usd_gte
        if usd_lte is not None:
            params["usdLte"] = usd_lte
        if sort_key:
            params["sortKey"] = sort_key
        if sort_dir:
            params["sortDir"] = sort_dir

        return await self._request(
            self._ENDPOINTS["transfers"], params, use_heavy_endpoint=True
        )

    async def get_token_balances(
        self,
        address: str,
        chains: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get token balances for a wallet address.

        Args:
            address: Wallet address to query
            chains: Optional comma-separated chain list

        Returns:
            dict: API response with balance data
        """
        params = {}
        if chains:
            params["chains"] = chains

        endpoint = self._ENDPOINTS["balances"].format(address=address)
        return await self._request(endpoint, params)

    async def aclose(self) -> None:
        """Close HTTP client and clean up resources."""
        await self._client.close()  # AsyncHTTPClient uses close() not aclose()
        logger.debug("Closed Arkham API client")
