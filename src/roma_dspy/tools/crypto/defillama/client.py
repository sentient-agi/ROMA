"""DefiLlama API client for low-level operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from loguru import logger

from roma_dspy.tools.utils.http_client import AsyncHTTPClient, HTTPClientError

# API URLs
DEFAULT_BASE_URL = "https://api.llama.fi"
DEFAULT_PRO_BASE_URL = "https://pro-api.llama.fi"


class DefiLlamaAPIError(Exception):
    """DefiLlama API-specific error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
    ):
        """Initialize DefiLlama API error.

        Args:
            message: Error message
            status_code: HTTP status code
            response_text: API response text
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class DefiLlamaAPIClient:
    """Low-level DefiLlama API client.

    Handles API calls to DefiLlama REST API with automatic retry
    and support for both free and Pro endpoints.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        use_pro: bool = False,
        base_url: str = DEFAULT_BASE_URL,
        pro_base_url: str = DEFAULT_PRO_BASE_URL,
    ):
        """Initialize DefiLlama API client.

        Args:
            api_key: DefiLlama Pro API key (required for Pro endpoints)
            use_pro: Whether to enable Pro API endpoints
            base_url: Base URL for free API
            pro_base_url: Base URL for Pro API
        """
        self.api_key = api_key
        self.use_pro = use_pro and api_key is not None
        self.base_url = base_url
        self.pro_base_url = pro_base_url

        # HTTP client for free API
        self._client = AsyncHTTPClient(
            base_url=self.base_url,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=30.0,
            max_retries=3,
        )

        # HTTP client for Pro API (if enabled)
        if self.use_pro:
            self._pro_client = AsyncHTTPClient(
                base_url=self.pro_base_url,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30.0,
                max_retries=3,
            )
        else:
            self._pro_client = None

        logger.info(
            f"Initialized DefiLlamaAPIClient ({'Pro' if self.use_pro else 'Free'} API)"
        )

    async def __aenter__(self) -> DefiLlamaAPIClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        use_pro_api: bool = False,
    ) -> Any:
        """Make API request.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            use_pro_api: Whether to use Pro API endpoint

        Returns:
            API response data

        Raises:
            DefiLlamaAPIError: On API error
        """
        try:
            if use_pro_api and self.use_pro:
                # Pro API: inject API key into path
                endpoint = f"/{self.api_key}{endpoint}"
                return await self._pro_client.get(endpoint, params=params)
            else:
                return await self._client.get(endpoint, params=params)
        except HTTPClientError as e:
            raise DefiLlamaAPIError(
                f"DefiLlama API error: {e}",
                status_code=e.status_code,
                response_text=e.response_text,
            ) from e

    # =========================================================================
    # TVL & Protocol APIs
    # =========================================================================

    async def get_protocols(self) -> List[Dict[str, Any]]:
        """Get all protocols with current TVL data.

        Returns:
            List of protocol dictionaries
        """
        return await self._request("/protocols")

    async def get_protocol_tvl(self, protocol: str) -> float:
        """Get current TVL for a specific protocol.

        Args:
            protocol: Protocol slug (e.g., "aave", "uniswap")

        Returns:
            Current TVL as a number
        """
        return await self._request(f"/tvl/{protocol}")

    async def get_protocol_detail(self, protocol: str) -> Dict[str, Any]:
        """Get detailed protocol information.

        Args:
            protocol: Protocol slug

        Returns:
            Protocol detail dictionary
        """
        return await self._request(f"/protocol/{protocol}")

    async def get_chains(self) -> List[Dict[str, Any]]:
        """Get current TVL for all chains.

        Returns:
            List of chain dictionaries with TVL
        """
        return await self._request("/v2/chains")

    async def get_chain_historical_tvl(self, chain: str) -> List[Dict[str, Any]]:
        """Get historical TVL for a specific chain.

        Args:
            chain: Chain identifier (e.g., "ethereum", "arbitrum")

        Returns:
            List of historical TVL data points
        """
        return await self._request(f"/v2/historicalChainTvl/{chain}")

    # =========================================================================
    # Fees & Revenue APIs
    # =========================================================================

    async def get_protocol_fees(
        self, protocol: str, data_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get fees data for a protocol.

        Args:
            protocol: Protocol slug
            data_type: Type of data ("dailyFees", "dailyRevenue", etc.)

        Returns:
            Protocol fees dictionary
        """
        params = {}
        if data_type:
            params["dataType"] = data_type
        return await self._request(f"/summary/fees/{protocol}", params=params)

    async def get_chain_fees(
        self, chain: str, data_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get fees overview for a chain.

        Args:
            chain: Chain identifier
            data_type: Type of data

        Returns:
            Chain fees dictionary
        """
        params = {}
        if data_type:
            params["dataType"] = data_type
        return await self._request(f"/overview/fees/{chain}", params=params)

    # =========================================================================
    # Pro API Methods
    # =========================================================================

    async def get_yield_pools(self) -> Dict[str, Any]:
        """Get all yield farming pools (Pro API).

        Returns:
            Yield pools data

        Raises:
            DefiLlamaAPIError: If Pro API not enabled
        """
        if not self.use_pro:
            raise DefiLlamaAPIError("Pro API key required for yield pools data")
        return await self._request("/yields/pools", use_pro_api=True)

    async def get_yield_chart(self, pool_id: str) -> Any:
        """Get historical yield data for a pool (Pro API).

        Args:
            pool_id: Pool identifier

        Returns:
            Yield chart data
        """
        if not self.use_pro:
            raise DefiLlamaAPIError("Pro API key required for yield chart data")
        return await self._request(f"/yields/chart/{pool_id}", use_pro_api=True)

    async def get_yield_pools_borrow(self) -> Any:
        """Get borrow costs APY (Pro API).

        Returns:
            Borrow pools data
        """
        if not self.use_pro:
            raise DefiLlamaAPIError("Pro API key required for borrow yields data")
        return await self._request("/yields/poolsBorrow", use_pro_api=True)

    async def get_yield_perps(self) -> Any:
        """Get funding rates for perps (Pro API).

        Returns:
            Perpetuals data
        """
        if not self.use_pro:
            raise DefiLlamaAPIError("Pro API key required for perpetuals data")
        return await self._request("/yields/perps", use_pro_api=True)

    async def get_active_users(self) -> Dict[str, Any]:
        """Get active user metrics (Pro API).

        Returns:
            Active users data
        """
        if not self.use_pro:
            raise DefiLlamaAPIError("Pro API key required for active users data")
        return await self._request("/api/activeUsers", use_pro_api=True)

    async def get_chain_assets(self) -> Dict[str, Any]:
        """Get asset breakdown across chains (Pro API).

        Returns:
            Chain assets data
        """
        if not self.use_pro:
            raise DefiLlamaAPIError("Pro API key required for chain assets data")
        return await self._request("/api/chainAssets", use_pro_api=True)

    async def get_historical_liquidity(self, token: str) -> Any:
        """Get historical liquidity for a token (Pro API).

        Args:
            token: Token slug (e.g., "usdt", "usdc")

        Returns:
            Historical liquidity data
        """
        if not self.use_pro:
            raise DefiLlamaAPIError(
                "Pro API key required for historical liquidity data"
            )
        return await self._request(
            f"/api/historicalLiquidity/{token}", use_pro_api=True
        )

    async def close(self) -> None:
        """Close HTTP clients."""
        await self._client.close()
        if self._pro_client:
            await self._pro_client.close()
        logger.debug("Closed DefiLlamaAPIClient")
