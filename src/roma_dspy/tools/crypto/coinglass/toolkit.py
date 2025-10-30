"""Coinglass derivatives market data toolkit for DSPy agents."""

from __future__ import annotations

from typing import List, Optional

from loguru import logger

from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.tools.crypto.coinglass.client import CoinglassAPIClient, CoinglassAPIError
from roma_dspy.tools.crypto.coinglass.types import CoinglassInterval, CoinglassTimeRange


class CoinglassToolkit(BaseToolkit):
    """Coinglass derivatives market data toolkit.

    Provides access to Coinglass comprehensive cryptocurrency futures market database
    with funding rates, open interest, long/short ratios, and liquidation data.

    Supports:
    - Historical funding rates weighted by open interest (OHLC data)
    - Real-time funding rates across 20+ exchanges
    - Funding rate arbitrage opportunity detection
    - Open interest tracking and historical analysis
    - Taker buy/sell volume ratios (market sentiment)
    - Liquidation data by exchange and position type

    Example:
        ```python
        toolkit = CoinglassToolkit(
            symbols=["BTC", "ETH", "SOL"],
            default_symbol="BTC",
            api_key="your_api_key"
        )

        # Get funding rate arbitrage opportunities
        opps = await toolkit.get_arbitrage_opportunities()

        # Get historical funding rates
        funding = await toolkit.get_funding_rates_weighted_by_oi(
            symbol="BTC",
            interval="8h",
            limit=100
        )
        ```
    """

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        default_symbol: str = "BTC",
        api_key: Optional[str] = None,
        enabled: bool = True,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        **config,
    ):
        """Initialize Coinglass toolkit.

        Args:
            symbols: List of symbols to restrict operations to (None = all symbols)
            default_symbol: Default cryptocurrency symbol (BTC, ETH, etc.)
            api_key: Coinglass API key (optional, uses COINGLASS_API_KEY env var)
            enabled: Whether toolkit is enabled
            include_tools: Specific tools to include
            exclude_tools: Tools to exclude
            **config: Additional toolkit configuration
        """
        # Initialize attributes before super().__init__() which calls _setup_dependencies
        self.symbols = [s.upper() for s in symbols] if symbols else None
        self.default_symbol = default_symbol.upper()

        # Initialize API client before super().__init__()
        self.client = CoinglassAPIClient(api_key=api_key)

        super().__init__(
            enabled=enabled, include_tools=include_tools, exclude_tools=exclude_tools, **config
        )

        logger.info(
            f"Initialized CoinglassToolkit with "
            f"{len(self.symbols) if self.symbols else 'all'} symbols "
            f"(default: {self.default_symbol})"
        )

    def _setup_dependencies(self) -> None:
        """Setup external dependencies."""
        # Warn if API key is not provided
        if not self.client.api_key:
            logger.warning(
                "Coinglass API key not provided. Set COINGLASS_API_KEY environment variable "
                "or pass api_key parameter. Some endpoints may have rate limits or restrictions."
            )

    def _initialize_tools(self) -> None:
        """Initialize toolkit-specific configuration."""
        # Tool registration handled automatically by BaseToolkit
        pass

    def _validate_symbol(self, symbol: str) -> str:
        """Validate and normalize symbol.

        Args:
            symbol: Cryptocurrency symbol

        Returns:
            Normalized symbol (uppercase)

        Raises:
            ValueError: If symbol is not in allowed symbols
        """
        symbol_upper = symbol.upper()

        # Check user-defined symbol filter
        if self.symbols and symbol_upper not in self.symbols:
            raise ValueError(f"Symbol '{symbol_upper}' not in allowed symbols: {self.symbols}")

        return symbol_upper

    # =========================================================================
    # DSPy-Compatible Tool Methods (auto-registered by BaseToolkit)
    # =========================================================================

    async def get_funding_rates_weighted_by_oi(
        self,
        symbol: str = "BTC",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        interval: str = "8h",
        limit: int = 1000,
    ) -> dict:
        """Get historical funding rates weighted by open interest.

        Fetches OHLC (Open, High, Low, Close) data for funding rates aggregated by
        open interest weight over time. Higher open interest exchanges have more weight
        in the calculation, providing a more accurate market-wide funding rate.

        Useful for:
        - Analyzing funding rate trends and cycles
        - Identifying periods of extreme bullish/bearish sentiment
        - Detecting potential market reversals from funding rate extremes
        - Understanding market sentiment through the lens of leverage

        Args:
            symbol: Cryptocurrency symbol (BTC, ETH, SOL, etc.)
            start_time: Start time in milliseconds (Unix timestamp)
            end_time: End time in milliseconds (Unix timestamp)
            interval: Time interval (1m, 3m, 5m, 15m, 30m, 1h, 4h, 6h, 8h, 12h, 1d, 1w)
            limit: Maximum number of records to return (default: 1000)

        Returns:
            dict: Success response with OHLC funding rate data or file_path if large

        Example:
            ```python
            # Get last 100 8-hour funding rate periods for Bitcoin
            data = await toolkit.get_funding_rates_weighted_by_oi(
                symbol="BTC",
                interval="8h",
                limit=100
            )
            ```
        """
        try:
            symbol_validated = self._validate_symbol(symbol)

            # Convert string interval to enum
            try:
                interval_enum = CoinglassInterval(interval)
            except ValueError:
                return self._build_error_response(
                    ValueError(
                        f"Invalid interval '{interval}'. "
                        f"Valid options: {[i.value for i in CoinglassInterval]}"
                    ),
                    tool_name="get_funding_rates_weighted_by_oi",
                    symbol=symbol,
                )

            data = await self.client.get_funding_rates_weighted_by_oi(
                symbol=symbol_validated,
                start_time=start_time,
                end_time=end_time,
                interval=interval_enum,
                limit=limit,
            )

            # Funding rate history can be large - use storage
            return await self._build_success_response(
                data=data,
                storage_data_type="funding_rates",
                storage_prefix=f"{symbol_validated.lower()}_funding_{interval}_{limit}",
                tool_name="get_funding_rates_weighted_by_oi",
                symbol=symbol_validated,
                interval=interval,
                limit=limit,
                data_points=len(data.get("data", [])),
            )

        except (CoinglassAPIError, ValueError) as e:
            return self._build_error_response(
                e,
                tool_name="get_funding_rates_weighted_by_oi",
                symbol=symbol,
                interval=interval,
            )

    async def get_funding_rates_per_exchange(self) -> dict:
        """Get current funding rates across all exchanges for all symbols.

        Retrieves comprehensive real-time funding rate data for each cryptocurrency
        across 20+ major exchanges, separated into stablecoin-margined and token-margined
        contracts. Each entry includes the current funding rate, payment interval,
        and next funding time.

        Useful for:
        - Cross-exchange funding rate comparison
        - Identifying exchange-specific funding rate patterns
        - Finding the best exchange for opening leveraged positions
        - Monitoring funding rate divergence across venues

        Returns:
            dict: Success response with funding rates for all symbols and exchanges

        Example:
            ```python
            rates = await toolkit.get_funding_rates_per_exchange()
            # Access BTC funding rates on Binance:
            # rates['data'][0]['stablecoin_margin_list'][0]
            ```
        """
        try:
            data = await self.client.get_funding_rates_per_exchange()

            # Large dataset - use storage
            return await self._build_success_response(
                data=data,
                storage_data_type="funding_rates",
                storage_prefix="all_exchanges_funding",
                tool_name="get_funding_rates_per_exchange",
                symbols_count=len(data.get("data", [])),
            )

        except CoinglassAPIError as e:
            return self._build_error_response(e, tool_name="get_funding_rates_per_exchange")

    async def get_arbitrage_opportunities(self) -> dict:
        """Get funding rate arbitrage opportunities across exchanges.

        Identifies potential arbitrage opportunities by comparing funding rates
        across different exchanges. Suggests pairs of exchanges where you can
        simultaneously long on one exchange and short on another to profit from
        the funding rate differential.

        Each opportunity includes:
        - Buy and sell exchanges with current funding rates
        - Annualized percentage return (APR)
        - Net funding rate differential
        - Trading fees
        - Price spreads
        - Next funding time

        Useful for:
        - Discovering low-risk market-neutral arbitrage strategies
        - Understanding funding rate inefficiencies across venues
        - Evaluating potential returns from basis trading

        Returns:
            dict: Success response with arbitrage opportunity list

        Example:
            ```python
            opps = await toolkit.get_arbitrage_opportunities()
            for opp in opps['data']:
                print(f"{opp['symbol']}: {opp['apr']}% APR - "
                      f"Buy on {opp['buy']['exchange']}, "
                      f"Sell on {opp['sell']['exchange']}")
            ```
        """
        try:
            data = await self.client.get_arbitrage_opportunities()

            # Arbitrage data usually moderate size
            return await self._build_success_response(
                data=data,
                storage_data_type="arbitrage",
                storage_prefix="funding_arbitrage",
                tool_name="get_arbitrage_opportunities",
                opportunities_count=len(data.get("data", [])),
            )

        except CoinglassAPIError as e:
            return self._build_error_response(e, tool_name="get_arbitrage_opportunities")

    async def get_open_interest_by_exchange(self, symbol: str = "BTC") -> dict:
        """Get current open interest across all exchanges for a specific symbol.

        Retrieves real-time open interest (total value of outstanding futures contracts)
        for a cryptocurrency across all major derivatives exchanges. Open interest is a
        key indicator of market activity and leverage.

        Useful for:
        - Gauging overall market leverage and participation
        - Comparing exchange market share and dominance
        - Identifying shifts in trading venue preferences
        - Assessing market depth and liquidity

        Args:
            symbol: Cryptocurrency symbol (BTC, ETH, SOL, etc.)

        Returns:
            dict: Success response with open interest data per exchange

        Example:
            ```python
            oi = await toolkit.get_open_interest_by_exchange("BTC")
            total_oi = sum(ex['open_interest_usd'] for ex in oi['data'])
            ```
        """
        try:
            symbol_validated = self._validate_symbol(symbol)

            data = await self.client.get_open_interest_exchange_list(symbol=symbol_validated)

            # OI data usually small
            return await self._build_success_response(
                data=data,
                tool_name="get_open_interest_by_exchange",
                symbol=symbol_validated,
                exchanges_count=len(data.get("data", [])),
            )

        except (CoinglassAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_open_interest_by_exchange", symbol=symbol
            )

    async def get_open_interest_history(
        self, symbol: str = "BTC", time_range: str = "1h"
    ) -> dict:
        """Get historical open interest data for all exchanges.

        Retrieves time-series open interest data showing how total futures market
        leverage has changed over time. Historical OI analysis can reveal accumulation/
        distribution patterns and potential market turning points.

        Useful for:
        - Tracking leverage build-up or deleveraging
        - Identifying divergences between price and open interest
        - Understanding market structure changes
        - Detecting institutional accumulation patterns

        Args:
            symbol: Cryptocurrency symbol (BTC, ETH, SOL, etc.)
            time_range: Time range (all, 1m, 5m, 15m, 1h, 4h, 12h, 24h)
                       'all' = 24h intervals for 6 years, others = 30 data points

        Returns:
            dict: Success response with historical OI data or file_path if large

        Example:
            ```python
            # Get 1-hour OI history
            history = await toolkit.get_open_interest_history("BTC", "1h")

            # Get long-term history
            long_term = await toolkit.get_open_interest_history("BTC", "all")
            ```
        """
        try:
            symbol_validated = self._validate_symbol(symbol)

            # Convert string range to enum
            try:
                range_enum = CoinglassTimeRange(time_range)
            except ValueError:
                return self._build_error_response(
                    ValueError(
                        f"Invalid time_range '{time_range}'. "
                        f"Valid options: {[r.value for r in CoinglassTimeRange]}"
                    ),
                    tool_name="get_open_interest_history",
                    symbol=symbol,
                )

            data = await self.client.get_open_interest_history_chart(
                symbol=symbol_validated, time_range=range_enum
            )

            # History can be large - use storage
            return await self._build_success_response(
                data=data,
                storage_data_type="open_interest",
                storage_prefix=f"{symbol_validated.lower()}_oi_history_{time_range}",
                tool_name="get_open_interest_history",
                symbol=symbol_validated,
                time_range=time_range,
                data_points=len(data.get("data", [])),
            )

        except (CoinglassAPIError, ValueError) as e:
            return self._build_error_response(
                e,
                tool_name="get_open_interest_history",
                symbol=symbol,
                time_range=time_range,
            )

    async def get_taker_buy_sell_volume(
        self, symbol: str = "BTC", time_range: str = "1h"
    ) -> dict:
        """Get taker buy/sell volume ratios across exchanges.

        Analyzes the distribution of aggressive buying vs selling pressure by measuring
        taker (market order) volume ratios. High buy ratios indicate bullish aggression,
        while high sell ratios suggest bearish pressure.

        Provides both aggregated metrics and per-exchange breakdowns, allowing you to
        identify which venues are driving market sentiment.

        Useful for:
        - Measuring real-time market sentiment and aggression
        - Identifying accumulation or distribution phases
        - Comparing sentiment across different exchanges
        - Detecting divergences between spot and futures sentiment

        Args:
            symbol: Cryptocurrency symbol (BTC, ETH, SOL, etc.)
            time_range: Time range (5m, 15m, 30m, 1h, 4h, 12h, 24h)

        Returns:
            dict: Success response with buy/sell ratios and volumes

        Example:
            ```python
            volume = await toolkit.get_taker_buy_sell_volume("BTC", "1h")
            buy_ratio = volume['data']['buy_ratio']
            sell_ratio = volume['data']['sell_ratio']
            print(f"Market sentiment: {buy_ratio}% buy vs {sell_ratio}% sell")
            ```
        """
        try:
            symbol_validated = self._validate_symbol(symbol)

            # Convert string range to enum
            try:
                range_enum = CoinglassTimeRange(time_range)
            except ValueError:
                return self._build_error_response(
                    ValueError(
                        f"Invalid time_range '{time_range}'. "
                        f"Valid options: {[r.value for r in CoinglassTimeRange]}"
                    ),
                    tool_name="get_taker_buy_sell_volume",
                    symbol=symbol,
                )

            data = await self.client.get_taker_buy_sell_volume(
                symbol=symbol_validated, range_param=range_enum
            )

            # Volume data usually moderate size
            return await self._build_success_response(
                data=data,
                tool_name="get_taker_buy_sell_volume",
                symbol=symbol_validated,
                time_range=time_range,
            )

        except (CoinglassAPIError, ValueError) as e:
            return self._build_error_response(
                e,
                tool_name="get_taker_buy_sell_volume",
                symbol=symbol,
                time_range=time_range,
            )

    async def get_liquidations_by_exchange(
        self, symbol: str = "BTC", time_range: str = "1h"
    ) -> dict:
        """Get liquidation data across exchanges.

        Tracks forced liquidations of leveraged positions across all major exchanges,
        split between long and short liquidations. High liquidation volumes often
        coincide with volatile price movements and can indicate cascade events.

        Includes both per-exchange data and aggregated totals (marked as 'All' exchange).

        Useful for:
        - Identifying potential cascade liquidation risks
        - Understanding leverage flush-out events
        - Detecting over-leveraged market conditions
        - Timing entries after major liquidation events

        Args:
            symbol: Cryptocurrency symbol (BTC, ETH, SOL, etc.)
            time_range: Time range (5m, 15m, 30m, 1h, 4h, 12h, 24h)

        Returns:
            dict: Success response with liquidation amounts by exchange and position type

        Example:
            ```python
            liq = await toolkit.get_liquidations_by_exchange("BTC", "1h")
            # Find total liquidations
            all_data = [x for x in liq['data'] if x['exchange'] == 'All'][0]
            long_liq = all_data['longLiquidation_usd']
            short_liq = all_data['shortLiquidation_usd']
            print(f"Longs liquidated: ${long_liq:,.0f}")
            print(f"Shorts liquidated: ${short_liq:,.0f}")
            ```
        """
        try:
            symbol_validated = self._validate_symbol(symbol)

            # Convert string range to enum
            try:
                range_enum = CoinglassTimeRange(time_range)
            except ValueError:
                return self._build_error_response(
                    ValueError(
                        f"Invalid time_range '{time_range}'. "
                        f"Valid options: {[r.value for r in CoinglassTimeRange]}"
                    ),
                    tool_name="get_liquidations_by_exchange",
                    symbol=symbol,
                )

            data = await self.client.get_liquidations_by_exchange(
                symbol=symbol_validated, range_param=range_enum
            )

            # Liquidation data usually moderate size
            return await self._build_success_response(
                data=data,
                tool_name="get_liquidations_by_exchange",
                symbol=symbol_validated,
                time_range=time_range,
                exchanges_count=len(data.get("data", [])),
            )

        except (CoinglassAPIError, ValueError) as e:
            return self._build_error_response(
                e,
                tool_name="get_liquidations_by_exchange",
                symbol=symbol,
                time_range=time_range,
            )

    async def __aenter__(self) -> "CoinglassToolkit":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close toolkit and clean up resources."""
        await self.client.close()
        logger.debug("Closed CoinglassToolkit")