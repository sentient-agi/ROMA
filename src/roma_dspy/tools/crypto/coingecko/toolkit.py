"""CoinGecko cryptocurrency market data toolkit for DSPy agents."""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from decimal import Decimal

from loguru import logger

from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.tools.crypto.coingecko.client import (
    CoinGeckoAPIClient,
    CoinGeckoAPIError,
)
from roma_dspy.tools.utils.statistics import StatisticalAnalyzer


class CoinGeckoToolkit(BaseToolkit):
    """CoinGecko cryptocurrency market data toolkit.

    Provides access to CoinGecko's comprehensive cryptocurrency database with
    17,000+ coins, real-time prices, historical data, and market analytics.

    Supports:
    - Real-time prices in 100+ currencies
    - Historical price and market data
    - OHLCV candlestick data
    - Market rankings and statistics
    - Search and discovery
    - Contract address lookups
    - Global market metrics

    Example:
        ```python
        toolkit = CoinGeckoToolkit(
            coins=["bitcoin", "ethereum"],
            default_vs_currency="usd",
            enable_analysis=True
        )

        # Get current price
        price = await toolkit.get_coin_price("bitcoin")

        # Get historical data
        chart = await toolkit.get_coin_market_chart("bitcoin", days=30)
        ```
    """

    def __init__(
        self,
        coins: Optional[List[str]] = None,
        default_vs_currency: str = "usd",
        api_key: Optional[str] = None,
        use_pro: bool = False,
        enabled: bool = True,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        enable_analysis: bool = False,
        **config,
    ):
        """Initialize CoinGecko toolkit.

        Args:
            coins: List of coin IDs to restrict operations to (None = all coins)
            default_vs_currency: Default quote currency (usd, eur, btc, etc.)
            api_key: CoinGecko API key (optional for public endpoints)
            use_pro: Whether to use Pro API (requires api_key)
            enabled: Whether toolkit is enabled
            include_tools: Specific tools to include
            exclude_tools: Tools to exclude
            enable_analysis: Whether to include statistical analysis
            **config: Additional toolkit configuration
        """
        super().__init__(
            enabled=enabled,
            include_tools=include_tools,
            exclude_tools=exclude_tools,
            **config,
        )

        self.coins = [c.lower() for c in coins] if coins else None
        self.default_vs_currency = default_vs_currency.lower()
        self.enable_analysis = enable_analysis

        # Initialize API client
        self.client = CoinGeckoAPIClient(api_key=api_key, use_pro=use_pro)

        # Initialize statistical analyzer if analysis is enabled
        self.stats = StatisticalAnalyzer() if enable_analysis else None

        logger.info(
            f"Initialized CoinGeckoToolkit with "
            f"{len(self.coins) if self.coins else 'all'} coins "
            f"(analysis={'enabled' if enable_analysis else 'disabled'})"
        )

    def _setup_dependencies(self) -> None:
        """Setup external dependencies."""
        # No external dependencies needed
        pass

    def _initialize_tools(self) -> None:
        """Initialize toolkit-specific configuration."""
        # Tool registration handled automatically by BaseToolkit
        pass

    async def _validate_coin(self, coin_identifier: str) -> str:
        """Validate and normalize coin identifier.

        Args:
            coin_identifier: Coin name or ID

        Returns:
            Normalized coin ID

        Raises:
            ValueError: If coin is invalid
        """
        coin_id = await self.client.resolve_coin_identifier(coin_identifier)

        # Check user-defined coin filter
        if self.coins and coin_id not in self.coins:
            raise ValueError(f"Coin '{coin_id}' not in allowed coins: {self.coins}")

        return coin_id

    def _parse_date_to_timestamp(self, date_str: str) -> int:
        """Parse date string to Unix timestamp.

        Args:
            date_str: Date in ISO format or Unix timestamp

        Returns:
            Unix timestamp (seconds)
        """
        # If already a timestamp
        if date_str.isdigit():
            return int(date_str)

        # Parse ISO format
        from dateutil import parser

        dt = parser.parse(date_str)
        return int(dt.timestamp())

    # =========================================================================
    # DSPy-Compatible Tool Methods (auto-registered by BaseToolkit)
    # =========================================================================

    async def get_coin_price(
        self, coin_name_or_id: str, vs_currency: Optional[str] = None
    ) -> dict:
        """Get current price and market data for a cryptocurrency.

        Fetches real-time pricing with market cap, volume, and 24h changes.

        Args:
            coin_name_or_id: Coin name or ID (e.g., "bitcoin", "ethereum")
            vs_currency: Quote currency (usd, eur, btc, etc.)

        Returns:
            dict: Price data with market metrics

        Example:
            ```python
            price = await toolkit.get_coin_price("bitcoin", "usd")
            print(f"BTC: ${price['data']['bitcoin']['usd']}")
            ```
        """
        try:
            coin_id = await self._validate_coin(coin_name_or_id)
            vs_curr = (vs_currency or self.default_vs_currency).lower()

            data = await self.client.get_simple_price(
                coin_ids=[coin_id],
                vs_currencies=[vs_curr],
                include_market_cap=True,
                include_24h_vol=True,
                include_24h_change=True,
                include_last_updated=True,
            )

            # Add analysis if enabled
            analysis = None
            if self.enable_analysis and self.stats and coin_id in data:
                coin_data = data[coin_id]
                change_key = f"{vs_curr}_24h_change"

                if change_key in coin_data:
                    change_pct = coin_data[change_key]
                    analysis = {
                        "trend": self.stats.classify_trend_from_change(
                            change_pct
                        ).value,
                        "volatility": self.stats.classify_volatility_from_change(
                            abs(change_pct)
                        ).value,
                    }

            # Build response (prices usually small, no storage needed)
            response = await self._build_success_response(
                data=data,
                tool_name="get_coin_price",
                coin_id=coin_id,
                vs_currency=vs_curr,
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (CoinGeckoAPIError, ValueError) as e:
            return self._build_error_response(
                e,
                tool_name="get_coin_price",
                coin_id=coin_name_or_id,
                vs_currency=vs_currency or self.default_vs_currency,
            )

    async def get_coin_info(self, coin_name_or_id: str) -> dict:
        """Get comprehensive information about a cryptocurrency.

        Retrieves detailed metadata including descriptions, links, rankings,
        and market data.

        Args:
            coin_name_or_id: Coin name or ID

        Returns:
            dict: Comprehensive coin information

        Example:
            ```python
            info = await toolkit.get_coin_info("bitcoin")
            print(f"Description: {info['data']['description']['en'][:100]}")
            ```
        """
        try:
            coin_id = await self._validate_coin(coin_name_or_id)

            data = await self.client.get_coin_info(
                coin_id=coin_id,
                localization=False,
                tickers=False,
                market_data=True,
                community_data=False,
                developer_data=False,
                sparkline=False,
            )

            # Coin info can be large, use storage
            return await self._build_success_response(
                data=data,
                storage_data_type="coin_info",
                storage_prefix=f"{coin_id}_info",
                tool_name="get_coin_info",
                coin_id=coin_id,
            )

        except (CoinGeckoAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_coin_info", coin_id=coin_name_or_id
            )

    async def get_coin_market_chart(
        self,
        coin_name_or_id: str,
        vs_currency: Optional[str] = None,
        days: int = 30,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> dict:
        """Get historical market data (price, market cap, volume).

        Retrieves time-series data for technical analysis and charting.
        Supports both days-based and date-range queries.

        Args:
            coin_name_or_id: Coin name or ID
            vs_currency: Quote currency
            days: Number of days (1, 7, 14, 30, 90, 180, 365, max)
            from_date: Start date (ISO format or Unix timestamp)
            to_date: End date (ISO format or Unix timestamp)

        Returns:
            dict: Historical price, market_cap, and total_volume arrays

        Example:
            ```python
            # Using days parameter
            chart = await toolkit.get_coin_market_chart("ethereum", days=7)

            # Using date range
            chart = await toolkit.get_coin_market_chart(
                "bitcoin",
                from_date="2024-01-01",
                to_date="2024-01-31"
            )
            prices = chart['data']['prices']  # [[timestamp, price], ...]
            ```
        """
        try:
            coin_id = await self._validate_coin(coin_name_or_id)
            vs_curr = (vs_currency or self.default_vs_currency).lower()

            # Use date range if provided, otherwise use days
            if from_date and to_date:
                # Convert dates to Unix timestamps if needed
                from_ts = self._parse_date_to_timestamp(from_date)
                to_ts = self._parse_date_to_timestamp(to_date)

                data = await self.client.get_market_chart_range(
                    coin_id=coin_id,
                    vs_currency=vs_curr,
                    from_timestamp=from_ts,
                    to_timestamp=to_ts,
                )
            else:
                data = await self.client.get_market_chart(
                    coin_id=coin_id, vs_currency=vs_curr, days=days
                )

            # Add analysis if enabled
            analysis = None
            if self.enable_analysis and self.stats and "prices" in data:
                prices = [p[1] for p in data["prices"]]
                price_stats = self.stats.calculate_price_statistics(prices)

                analysis = {
                    "price_min": price_stats.get("min"),
                    "price_max": price_stats.get("max"),
                    "price_mean": price_stats.get("mean"),
                    "volatility": price_stats.get("std_dev"),
                }

            # Market charts are large - use storage
            response = await self._build_success_response(
                data=data,
                storage_data_type="market_charts",
                storage_prefix=f"{coin_id}_{vs_curr}_{days}d",
                tool_name="get_coin_market_chart",
                coin_id=coin_id,
                vs_currency=vs_curr,
                days=days,
                data_points=len(data.get("prices", [])),
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (CoinGeckoAPIError, ValueError) as e:
            return self._build_error_response(
                e,
                tool_name="get_coin_market_chart",
                coin_id=coin_name_or_id,
                vs_currency=vs_currency or self.default_vs_currency,
            )

    async def get_coins_markets(
        self,
        vs_currency: Optional[str] = None,
        coin_ids: Optional[List[str]] = None,
        per_page: int = 100,
        page: int = 1,
    ) -> dict:
        """Get market data for multiple cryptocurrencies.

        Retrieves rankings, prices, volumes, and market caps for multiple coins.

        Args:
            vs_currency: Quote currency
            coin_ids: List of coin IDs (None = top coins)
            per_page: Results per page (max 250)
            page: Page number

        Returns:
            dict: List of market data for coins

        Example:
            ```python
            markets = await toolkit.get_coins_markets(per_page=50)
            for coin in markets['data']:
                print(f"{coin['name']}: ${coin['current_price']}")
            ```
        """
        try:
            vs_curr = (vs_currency or self.default_vs_currency).lower()

            # Validate coin IDs if provided
            if coin_ids:
                validated_ids = []
                for coin_id in coin_ids:
                    try:
                        validated_id = await self._validate_coin(coin_id)
                        validated_ids.append(validated_id)
                    except ValueError:
                        logger.warning(f"Skipping invalid coin: {coin_id}")
                coin_ids = validated_ids if validated_ids else None

            data = await self.client.get_coins_markets(
                vs_currency=vs_curr,
                coin_ids=coin_ids,
                per_page=per_page,
                page=page,
            )

            # Markets data can be large - use storage
            return await self._build_success_response(
                data=data,
                storage_data_type="markets",
                storage_prefix=f"markets_{vs_curr}_p{page}",
                tool_name="get_coins_markets",
                vs_currency=vs_curr,
                count=len(data),
                page=page,
                per_page=per_page,
            )

        except (CoinGeckoAPIError, ValueError) as e:
            return self._build_error_response(
                e,
                tool_name="get_coins_markets",
                vs_currency=vs_currency or self.default_vs_currency,
            )

    async def get_historical_price(
        self,
        coin_name_or_id: str,
        vs_currency: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> dict:
        """Get historical price data for a specific date range.

        Convenience method for fetching price history within a date range.
        Wrapper around get_coin_market_chart with date range parameters.

        Args:
            coin_name_or_id: Coin name or ID
            vs_currency: Quote currency
            from_date: Start date (ISO format or Unix timestamp)
            to_date: End date (ISO format or Unix timestamp)

        Returns:
            dict: Historical price data with analysis

        Example:
            ```python
            history = await toolkit.get_historical_price(
                "bitcoin",
                from_date="2024-01-01",
                to_date="2024-01-31"
            )
            ```
        """
        if not from_date or not to_date:
            return self._build_error_response(
                ValueError("Both from_date and to_date are required"),
                tool_name="get_historical_price",
                coin_id=coin_name_or_id,
            )

        # Delegate to get_coin_market_chart with date range
        return await self.get_coin_market_chart(
            coin_name_or_id=coin_name_or_id,
            vs_currency=vs_currency,
            from_date=from_date,
            to_date=to_date,
        )

    async def get_multiple_coins_data(
        self,
        coin_names_or_ids: List[str],
        vs_currency: Optional[str] = None,
    ) -> dict:
        """Fetch current price data for multiple cryptocurrencies.

        Convenience method for batch fetching multiple coins.
        Wrapper around get_coins_markets with specific coin IDs.

        Args:
            coin_names_or_ids: List of coin names or IDs
            vs_currency: Quote currency

        Returns:
            dict: Market data for all requested coins

        Example:
            ```python
            portfolio = ["bitcoin", "ethereum", "cardano"]
            data = await toolkit.get_multiple_coins_data(portfolio, "usd")
            ```
        """
        try:
            # Validate all coins first
            validated_ids = []
            for coin in coin_names_or_ids:
                try:
                    coin_id = await self._validate_coin(coin)
                    validated_ids.append(coin_id)
                except ValueError as e:
                    logger.warning(f"Skipping invalid coin '{coin}': {e}")

            if not validated_ids:
                return self._build_error_response(
                    ValueError("No valid coins found"),
                    tool_name="get_multiple_coins_data",
                    requested_coins=coin_names_or_ids,
                )

            # Delegate to get_coins_markets
            return await self.get_coins_markets(
                vs_currency=vs_currency,
                coin_ids=validated_ids,
                per_page=len(validated_ids),
            )

        except Exception as e:
            return self._build_error_response(
                e,
                tool_name="get_multiple_coins_data",
                requested_coins=coin_names_or_ids,
            )

    async def get_coin_ohlc(
        self, coin_name_or_id: str, vs_currency: Optional[str] = None, days: int = 30
    ) -> dict:
        """Get OHLC candlestick data.

        Retrieves open, high, low, close data for technical analysis.

        Args:
            coin_name_or_id: Coin name or ID
            vs_currency: Quote currency
            days: Number of days (1, 7, 14, 30, 90, 180, 365)

        Returns:
            dict: OHLC data as [[timestamp, open, high, low, close], ...]

        Example:
            ```python
            ohlc = await toolkit.get_coin_ohlc("bitcoin", days=7)
            for candle in ohlc['data']:
                timestamp, o, h, l, c = candle
                print(f"Open: {o}, Close: {c}")
            ```
        """
        try:
            coin_id = await self._validate_coin(coin_name_or_id)
            vs_curr = (vs_currency or self.default_vs_currency).lower()

            data = await self.client.get_coin_ohlc(
                coin_id=coin_id, vs_currency=vs_curr, days=days
            )

            # Add analysis if enabled
            analysis = None
            if self.enable_analysis and self.stats and data:
                closes = [candle[4] for candle in data]  # Close prices
                highs = [candle[2] for candle in data]
                lows = [candle[3] for candle in data]

                analysis = {
                    "close_mean": float(sum(closes) / len(closes)),
                    "high_max": max(highs),
                    "low_min": min(lows),
                    "price_range": max(highs) - min(lows),
                }

            # OHLC data can be large - use storage
            response = await self._build_success_response(
                data=data,
                storage_data_type="ohlc",
                storage_prefix=f"{coin_id}_{vs_curr}_{days}d_ohlc",
                tool_name="get_coin_ohlc",
                coin_id=coin_id,
                vs_currency=vs_curr,
                days=days,
                count=len(data),
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (CoinGeckoAPIError, ValueError) as e:
            return self._build_error_response(
                e,
                tool_name="get_coin_ohlc",
                coin_id=coin_name_or_id,
                vs_currency=vs_currency or self.default_vs_currency,
            )

    async def search_coins_exchanges_categories(self, query: str) -> dict:
        """Search for coins, exchanges, and categories.

        Performs fuzzy search across CoinGecko database.

        Args:
            query: Search query

        Returns:
            dict: Search results with coins, exchanges, categories

        Example:
            ```python
            results = await toolkit.search_coins_exchanges_categories("bitcoin")
            for coin in results['data']['coins']:
                print(f"{coin['name']} ({coin['symbol']})")
            ```
        """
        try:
            data = await self.client.search(query=query)

            # Search results usually small, no storage needed
            return await self._build_success_response(
                data=data,
                tool_name="search_coins_exchanges_categories",
                query=query,
                coins_found=len(data.get("coins", [])),
                exchanges_found=len(data.get("exchanges", [])),
                categories_found=len(data.get("categories", [])),
            )

        except CoinGeckoAPIError as e:
            return self._build_error_response(
                e, tool_name="search_coins_exchanges_categories", query=query
            )

    async def get_global_crypto_data(self) -> dict:
        """Get global cryptocurrency market statistics.

        Retrieves overall market metrics including total market cap,
        trading volume, and market dominance.

        Returns:
            dict: Global market statistics

        Example:
            ```python
            global_data = await toolkit.get_global_crypto_data()
            total_mcap = global_data['data']['data']['total_market_cap']['usd']
            print(f"Total Market Cap: ${total_mcap:,.0f}")
            ```
        """
        try:
            data = await self.client.get_global_data()

            # Global data is small, no storage needed
            return await self._build_success_response(
                data=data,
                tool_name="get_global_crypto_data",
            )

        except CoinGeckoAPIError as e:
            return self._build_error_response(e, tool_name="get_global_crypto_data")

    async def get_token_price_by_contract(
        self,
        platform: str,
        contract_address: str,
        vs_currency: Optional[str] = None,
    ) -> dict:
        """Get token price by contract address.

        Looks up token by smart contract address on specified platform.

        Args:
            platform: Platform ID (ethereum, binance-smart-chain, polygon-pos, etc.)
            contract_address: Token contract address
            vs_currency: Quote currency

        Returns:
            dict: Token price data

        Example:
            ```python
            # Get USDT price on Ethereum
            price = await toolkit.get_token_price_by_contract(
                platform="ethereum",
                contract_address="0xdac17f958d2ee523a2206206994597c13d831ec7",
                vs_currency="usd"
            )
            ```
        """
        try:
            vs_curr = (vs_currency or self.default_vs_currency).lower()

            data = await self.client.get_token_price_by_contract(
                platform=platform.lower(),
                contract_address=contract_address,
                vs_currencies=[vs_curr],
            )

            # Token price is small, no storage needed
            return await self._build_success_response(
                data=data,
                tool_name="get_token_price_by_contract",
                platform=platform,
                contract_address=contract_address,
                vs_currency=vs_curr,
            )

        except CoinGeckoAPIError as e:
            return self._build_error_response(
                e,
                tool_name="get_token_price_by_contract",
                platform=platform,
                contract_address=contract_address,
            )

    async def __aenter__(self) -> "CoinGeckoToolkit":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close toolkit and clean up resources."""
        await self.client.close()
        logger.debug("Closed CoinGeckoToolkit")
