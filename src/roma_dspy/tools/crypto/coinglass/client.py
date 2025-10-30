"""Coinglass API client for low-level operations."""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

from loguru import logger

from roma_dspy.tools.crypto.coinglass.types import (
    CoinglassEndpoint,
    CoinglassInterval,
    CoinglassTimeRange,
    DEFAULT_API_CONFIG,
)
from roma_dspy.tools.utils.http_client import AsyncHTTPClient, HTTPClientError


class CoinglassAPIError(Exception):
    """Coinglass API-specific error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
    ):
        """Initialize Coinglass API error.

        Args:
            message: Error message
            status_code: HTTP status code
            response_text: API response text
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class CoinglassAPIClient:
    """Low-level Coinglass API client.

    Handles API calls to Coinglass REST API with automatic retry,
    error handling, and rate limiting.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
    ):
        """Initialize Coinglass API client.

        Args:
            api_key: Coinglass API key (fetched from COINGLASS_API_KEY env if not provided)
        """
        self.api_key = api_key or os.getenv("COINGLASS_API_KEY", "")
        self.config = DEFAULT_API_CONFIG

        # HTTP client
        headers = {}
        if self.api_key:
            headers[self.config.api_key_header] = self.api_key
        headers["Content-Type"] = "application/json"

        self._client = AsyncHTTPClient(
            base_url=self.config.base_url,
            headers=headers,
            timeout=30.0,
            max_retries=3,
        )

        logger.info("Initialized CoinglassAPIClient")

    async def __aenter__(self) -> CoinglassAPIClient:
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
            CoinglassAPIError: On API error
        """
        try:
            return await self._client.get(endpoint, params=params)
        except HTTPClientError as e:
            raise CoinglassAPIError(
                f"Coinglass API error: {e}",
                status_code=e.status_code,
                response_text=e.response_text,
            ) from e

    # =========================================================================
    # Funding Rate Endpoints
    # =========================================================================

    async def get_funding_rates_weighted_by_oi(
        self,
        symbol: str = "BTC",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        interval: CoinglassInterval = CoinglassInterval.EIGHT_HOURS,
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """Get historical funding rates weighted by open interest.

        This endpoint returns OHLC (Open, High, Low, Close) data for funding rates
        aggregated by open interest weight over time. Each data point includes a timestamp
        and the corresponding OHLC values for the specified time interval.

        Args:
            symbol: The cryptocurrency symbol (default: "BTC")
            start_time: Start time in milliseconds (optional)
            end_time: End time in milliseconds (optional)
            interval: Time interval for data aggregation (default: 8h)
            limit: Maximum number of records to return (default: 1000)

        Returns:
            dict: API response with:
                - code: Response code ("0" for success)
                - data: List of OHLC objects with time, open, high, low, close

        Raises:
            CoinglassAPIError: On API error
        """
        params: Dict[str, Any] = {
            "symbol": symbol,
            "interval": str(interval),
            "limit": limit,
        }
        if start_time is not None:
            params["start_time"] = start_time
        if end_time is not None:
            params["end_time"] = end_time

        return await self._request(
            CoinglassEndpoint.FUNDING_RATE_OI_WEIGHT_HISTORY.value, params=params
        )

    async def get_funding_rates_per_exchange(self) -> Dict[str, Any]:
        """Get current funding rates across all exchanges for all symbols.

        This endpoint returns comprehensive funding rate data for each cryptocurrency
        across multiple exchanges, separated into stablecoin-margined and token-margined
        contracts. Each exchange entry includes the current funding rate, funding interval,
        and next funding time.

        Returns:
            dict: API response with:
                - code: Response code ("0" for success)
                - data: List of symbol objects with stablecoin_margin_list and token_margin_list

        Raises:
            CoinglassAPIError: On API error
        """
        return await self._request(CoinglassEndpoint.FUNDING_RATE_EXCHANGE_LIST.value, params={})

    async def get_arbitrage_opportunities(self) -> Dict[str, Any]:
        """Get funding rate arbitrage opportunities across exchanges.

        This endpoint identifies potential arbitrage opportunities by comparing funding rates
        across different exchanges. It suggests pairs of exchanges where you can buy on one
        and sell on another to profit from the funding rate differential. Includes calculated
        APR, fees, spreads, and next funding time.

        Returns:
            dict: API response with:
                - code: Response code ("0" for success)
                - data: List of arbitrage opportunity objects with buy/sell exchange pairs

        Raises:
            CoinglassAPIError: On API error
        """
        return await self._request(CoinglassEndpoint.FUNDING_RATE_ARBITRAGE.value, params={})

    # =========================================================================
    # Open Interest Endpoints
    # =========================================================================

    async def get_open_interest_exchange_list(self, symbol: str = "BTC") -> Dict[str, Any]:
        """Get open interest data for all exchanges for a specific symbol.

        Args:
            symbol: The cryptocurrency symbol (default: "BTC")

        Returns:
            dict: API response with:
                - code: Response code ("0" for success)
                - data: List of exchange objects with open interest data

        Raises:
            CoinglassAPIError: On API error
        """
        params = {"symbol": symbol}
        return await self._request(
            CoinglassEndpoint.OPEN_INTEREST_EXCHANGE_LIST.value, params=params
        )

    async def get_open_interest_history_chart(
        self, symbol: str = "BTC", time_range: CoinglassTimeRange = CoinglassTimeRange.ONE_HOUR
    ) -> Dict[str, Any]:
        """Get historical open interest data for all exchanges for a specific symbol.

        Args:
            symbol: The cryptocurrency symbol (default: "BTC")
            time_range: Time range for the data (default: "1h")
                       "all" means 24h interval going back 6 years, others give 30 entries

        Returns:
            dict: API response with:
                - code: Response code ("0" for success)
                - data: Historical open interest data

        Raises:
            CoinglassAPIError: On API error
        """
        params = {"symbol": symbol, "range": str(time_range)}
        return await self._request(
            CoinglassEndpoint.OPEN_INTEREST_HISTORY_CHART.value, params=params
        )

    # =========================================================================
    # Long/Short Ratio Endpoints
    # =========================================================================

    async def get_taker_buy_sell_volume(
        self,
        symbol: str = "BTC",
        range_param: CoinglassTimeRange = CoinglassTimeRange.ONE_HOUR,
    ) -> Dict[str, Any]:
        """Get taker buy/sell volume ratios across exchanges.

        This endpoint returns the buy and sell volume ratios for a given symbol
        across multiple exchanges, showing the distribution of taker buying vs selling pressure.

        Args:
            symbol: The cryptocurrency symbol (default: "BTC")
            range_param: Time range for the data (default: "1h")

        Returns:
            dict: API response with:
                - code: Response code ("0" for success)
                - msg: Success or error message
                - data: Dictionary with overall ratios and exchange_list

        Raises:
            CoinglassAPIError: On API error
        """
        params = {
            "symbol": symbol,
            "range": str(range_param),
        }
        return await self._request(CoinglassEndpoint.TAKER_BUY_SELL_VOLUME.value, params=params)

    async def get_liquidations_by_exchange(
        self,
        symbol: str = "BTC",
        range_param: CoinglassTimeRange = CoinglassTimeRange.ONE_HOUR,
    ) -> Dict[str, Any]:
        """Get liquidation data across exchanges.

        This endpoint returns liquidation data for all exchanges, showing total liquidations
        split between long and short positions for a specific symbol.

        Args:
            symbol: The cryptocurrency symbol (default: "BTC")
            range_param: Time range for the data (default: "1h")

        Returns:
            dict: API response with:
                - code: Response code ("0" for success)
                - data: List of exchange objects with liquidation amounts

        Raises:
            CoinglassAPIError: On API error
        """
        params = {
            "symbol": symbol,
            "range": str(range_param),
        }
        return await self._request(CoinglassEndpoint.LIQUIDATION_EXCHANGE_LIST.value, params=params)

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.close()
        logger.debug("Closed CoinglassAPIClient")