"""CoinGecko API client for low-level operations."""

from __future__ import annotations

import difflib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from roma_dspy.tools.crypto.coingecko.types import (
    CoinGeckoEndpoint,
    API_CONFIGS,
)
from roma_dspy.tools.utils.http_client import AsyncHTTPClient, HTTPClientError
from roma_dspy.tools.value_objects.crypto import (
    PricePoint,
    AssetIdentifier,
)


class CoinGeckoAPIError(Exception):
    """CoinGecko API-specific error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
    ):
        """Initialize CoinGecko API error.

        Args:
            message: Error message
            status_code: HTTP status code
            response_text: API response text
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class CoinGeckoAPIClient:
    """Low-level CoinGecko API client.

    Handles API calls to CoinGecko REST API with automatic retry,
    symbol validation, and fuzzy name resolution.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        use_pro: bool = False,
    ):
        """Initialize CoinGecko API client.

        Args:
            api_key: CoinGecko API key (required for Pro API)
            use_pro: Whether to use Pro API endpoints
        """
        self.api_key = api_key
        self.use_pro = use_pro and api_key is not None

        # Get API configuration
        config_key = "pro" if self.use_pro else "public"
        self.config = API_CONFIGS[config_key]

        # HTTP client
        headers = {}
        if self.api_key:
            headers["x-cg-pro-api-key" if self.use_pro else "x-cg-demo-api-key"] = (
                self.api_key
            )

        self._client = AsyncHTTPClient(
            base_url=self.config.base_url,
            headers=headers,
            timeout=30.0,
            max_retries=3,
        )

        # Coin caches
        self._coins_list: Optional[List[Dict[str, Any]]] = None
        self._coins_by_id: Dict[str, Dict[str, Any]] = {}
        self._coins_by_symbol: Dict[str, List[Dict[str, Any]]] = {}

        logger.info(
            f"Initialized CoinGeckoAPIClient "
            f"({'Pro' if self.use_pro else 'Public'} API)"
        )

    async def __aenter__(self) -> CoinGeckoAPIClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    async def _request(
        self,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make API request.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            API response data

        Raises:
            CoinGeckoAPIError: On API error
        """
        try:
            return await self._client.get(endpoint, params=params)
        except HTTPClientError as e:
            raise CoinGeckoAPIError(
                f"CoinGecko API error: {e}",
                status_code=e.status_code,
                response_text=e.response_text,
            ) from e

    async def load_coins_list(
        self, include_platform: bool = False
    ) -> List[Dict[str, Any]]:
        """Load and cache list of all supported coins.

        Args:
            include_platform: Include platform contract addresses

        Returns:
            List of coin dictionaries with id, symbol, name
        """
        params = {"include_platform": str(include_platform).lower()}
        data = await self._request(CoinGeckoEndpoint.COINS_LIST.value, params=params)

        self._coins_list = data
        self._coins_by_id = {coin["id"]: coin for coin in data}

        # Group by symbol (multiple coins can have same symbol)
        self._coins_by_symbol = {}
        for coin in data:
            symbol = coin["symbol"].lower()
            if symbol not in self._coins_by_symbol:
                self._coins_by_symbol[symbol] = []
            self._coins_by_symbol[symbol].append(coin)

        logger.info(f"Loaded {len(data)} coins from CoinGecko")
        return data

    async def validate_coin_id(self, coin_id: str) -> bool:
        """Validate if coin ID exists.

        Args:
            coin_id: CoinGecko coin ID

        Returns:
            True if coin exists
        """
        if self._coins_list is None:
            await self.load_coins_list()

        return coin_id.lower() in self._coins_by_id

    async def resolve_coin_name_to_id(
        self, name: str, fuzzy_threshold: float = 0.8
    ) -> Optional[str]:
        """Resolve coin name to CoinGecko ID using fuzzy matching.

        Args:
            name: Coin name (e.g., "Bitcoin", "Ethereum")
            fuzzy_threshold: Similarity threshold (0-1)

        Returns:
            Coin ID if found, None otherwise
        """
        if self._coins_list is None:
            await self.load_coins_list()

        name_lower = name.lower()

        # Exact match
        for coin in self._coins_list:
            if coin["name"].lower() == name_lower:
                return coin["id"]

        # Fuzzy match
        best_match = None
        best_ratio = 0.0

        for coin in self._coins_list:
            ratio = difflib.SequenceMatcher(
                None, name_lower, coin["name"].lower()
            ).ratio()

            if ratio > best_ratio and ratio >= fuzzy_threshold:
                best_ratio = ratio
                best_match = coin["id"]

        return best_match

    async def resolve_coin_identifier(self, identifier: str) -> str:
        """Resolve coin name or ID to valid coin ID.

        Args:
            identifier: Coin name or ID

        Returns:
            Valid coin ID

        Raises:
            CoinGeckoAPIError: If coin not found
        """
        identifier_lower = identifier.lower()

        # Check if it's already a valid ID
        if await self.validate_coin_id(identifier_lower):
            return identifier_lower

        # Try resolving as name
        coin_id = await self.resolve_coin_name_to_id(identifier)
        if coin_id:
            return coin_id

        raise CoinGeckoAPIError(f"Coin '{identifier}' not found in CoinGecko database")

    async def get_simple_price(
        self,
        coin_ids: List[str],
        vs_currencies: List[str],
        include_market_cap: bool = True,
        include_24h_vol: bool = True,
        include_24h_change: bool = True,
        include_last_updated: bool = True,
    ) -> Dict[str, Any]:
        """Get simple price data for coins.

        Args:
            coin_ids: List of coin IDs
            vs_currencies: List of quote currencies
            include_market_cap: Include market cap
            include_24h_vol: Include 24h volume
            include_24h_change: Include 24h change
            include_last_updated: Include last updated timestamp

        Returns:
            Price data dictionary
        """
        params = {
            "ids": ",".join(coin_ids),
            "vs_currencies": ",".join(vs_currencies),
            "include_market_cap": str(include_market_cap).lower(),
            "include_24hr_vol": str(include_24h_vol).lower(),
            "include_24hr_change": str(include_24h_change).lower(),
            "include_last_updated_at": str(include_last_updated).lower(),
        }

        return await self._request(CoinGeckoEndpoint.SIMPLE_PRICE.value, params=params)

    async def get_coin_info(
        self,
        coin_id: str,
        localization: bool = False,
        tickers: bool = False,
        market_data: bool = True,
        community_data: bool = False,
        developer_data: bool = False,
        sparkline: bool = False,
    ) -> Dict[str, Any]:
        """Get comprehensive coin information.

        Args:
            coin_id: CoinGecko coin ID
            localization: Include localized descriptions
            tickers: Include ticker data
            market_data: Include market data
            community_data: Include community statistics
            developer_data: Include developer statistics
            sparkline: Include 7-day sparkline

        Returns:
            Comprehensive coin data
        """
        params = {
            "localization": str(localization).lower(),
            "tickers": str(tickers).lower(),
            "market_data": str(market_data).lower(),
            "community_data": str(community_data).lower(),
            "developer_data": str(developer_data).lower(),
            "sparkline": str(sparkline).lower(),
        }

        endpoint = CoinGeckoEndpoint.COIN_INFO.value.format(coin_id=coin_id)
        return await self._request(endpoint, params=params)

    async def get_market_chart(
        self,
        coin_id: str,
        vs_currency: str,
        days: int = 30,
        interval: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get historical market data.

        Args:
            coin_id: CoinGecko coin ID
            vs_currency: Quote currency
            days: Number of days (1, 7, 14, 30, 90, 180, 365, max)
            interval: Data interval (daily for 90+ days)

        Returns:
            Historical price, market cap, and volume data
        """
        params = {"vs_currency": vs_currency, "days": str(days)}

        if interval:
            params["interval"] = interval

        endpoint = CoinGeckoEndpoint.MARKET_CHART.value.format(coin_id=coin_id)
        return await self._request(endpoint, params=params)

    async def get_market_chart_range(
        self,
        coin_id: str,
        vs_currency: str,
        from_timestamp: int,
        to_timestamp: int,
    ) -> Dict[str, Any]:
        """Get historical market data within date range.

        Args:
            coin_id: CoinGecko coin ID
            vs_currency: Quote currency
            from_timestamp: Unix timestamp (start)
            to_timestamp: Unix timestamp (end)

        Returns:
            Historical data for specified range
        """
        params = {
            "vs_currency": vs_currency,
            "from": str(from_timestamp),
            "to": str(to_timestamp),
        }

        endpoint = CoinGeckoEndpoint.MARKET_CHART_RANGE.value.format(coin_id=coin_id)
        return await self._request(endpoint, params=params)

    async def get_coins_markets(
        self,
        vs_currency: str,
        coin_ids: Optional[List[str]] = None,
        category: Optional[str] = None,
        order: str = "market_cap_desc",
        per_page: int = 100,
        page: int = 1,
        sparkline: bool = False,
        price_change_percentage: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get market data for multiple coins.

        Args:
            vs_currency: Quote currency
            coin_ids: List of coin IDs (None = all)
            category: Filter by category
            order: Sort order
            per_page: Results per page (max 250)
            page: Page number
            sparkline: Include sparkline
            price_change_percentage: Include price change (1h, 24h, 7d, etc.)

        Returns:
            List of market data for coins
        """
        params = {
            "vs_currency": vs_currency,
            "order": order,
            "per_page": str(per_page),
            "page": str(page),
            "sparkline": str(sparkline).lower(),
        }

        if coin_ids:
            params["ids"] = ",".join(coin_ids)
        if category:
            params["category"] = category
        if price_change_percentage:
            params["price_change_percentage"] = price_change_percentage

        return await self._request(CoinGeckoEndpoint.COINS_MARKETS.value, params=params)

    async def get_coin_ohlc(
        self, coin_id: str, vs_currency: str, days: int = 30
    ) -> List[List[float]]:
        """Get OHLC candlestick data.

        Args:
            coin_id: CoinGecko coin ID
            vs_currency: Quote currency
            days: Number of days (1, 7, 14, 30, 90, 180, 365, max)

        Returns:
            List of [timestamp, open, high, low, close]
        """
        params = {"vs_currency": vs_currency, "days": str(days)}

        endpoint = CoinGeckoEndpoint.COIN_OHLC.value.format(coin_id=coin_id)
        return await self._request(endpoint, params=params)

    async def search(self, query: str) -> Dict[str, Any]:
        """Search for coins, exchanges, and categories.

        Args:
            query: Search query

        Returns:
            Search results with coins, exchanges, categories
        """
        params = {"query": query}
        return await self._request(CoinGeckoEndpoint.SEARCH.value, params=params)

    async def get_global_data(self) -> Dict[str, Any]:
        """Get global cryptocurrency market data.

        Returns:
            Global market statistics
        """
        return await self._request(CoinGeckoEndpoint.GLOBAL_DATA.value)

    async def get_token_price_by_contract(
        self,
        platform: str,
        contract_address: str,
        vs_currencies: List[str],
        include_market_cap: bool = True,
        include_24h_vol: bool = True,
        include_24h_change: bool = True,
        include_last_updated: bool = True,
    ) -> Dict[str, Any]:
        """Get token price by contract address.

        Args:
            platform: Platform ID (ethereum, binance-smart-chain, etc.)
            contract_address: Token contract address
            vs_currencies: List of quote currencies
            include_market_cap: Include market cap
            include_24h_vol: Include 24h volume
            include_24h_change: Include 24h change
            include_last_updated: Include last updated timestamp

        Returns:
            Token price data
        """
        params = {
            "contract_addresses": contract_address,
            "vs_currencies": ",".join(vs_currencies),
            "include_market_cap": str(include_market_cap).lower(),
            "include_24hr_vol": str(include_24h_vol).lower(),
            "include_24hr_change": str(include_24h_change).lower(),
            "include_last_updated_at": str(include_last_updated).lower(),
        }

        endpoint = CoinGeckoEndpoint.TOKEN_PRICE.value.format(platform=platform)
        return await self._request(endpoint, params=params)

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.close()
        logger.debug("Closed CoinGeckoAPIClient")
