"""Binance cryptocurrency trading toolkit for DSPy agents."""

from __future__ import annotations

from typing import List, Optional, Dict, Any
from decimal import Decimal

from loguru import logger

from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.tools.crypto.binance.client import BinanceAPIClient, BinanceAPIError
from roma_dspy.tools.crypto.binance.types import BinanceMarketType
from roma_dspy.tools.utils.statistics import StatisticalAnalyzer


class BinanceToolkit(BaseToolkit):
    """Binance cryptocurrency market data toolkit.

    Provides access to Binance spot and futures markets with real-time
    price data, order book depth, trade history, and candlestick data.

    Supports multiple market types:
    - spot: Traditional spot trading with immediate settlement
    - usdm: USDT-margined futures with high leverage
    - coinm: Coin-margined futures with cryptocurrency settlement

    Example:
        ```python
        toolkit = BinanceToolkit(
            symbols=["BTCUSDT", "ETHUSDT"],
            default_market="spot",
            api_key=os.getenv("BINANCE_API_KEY")
        )

        # Get current price
        price = await toolkit.get_current_price("BTCUSDT")

        # Get order book
        book = await toolkit.get_order_book("BTCUSDT", limit=100)
        ```
    """

    def __init__(
        self,
        symbols: Optional[List[str]] = None,
        default_market: str = "spot",
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        enabled: bool = True,
        include_tools: Optional[List[str]] = None,
        exclude_tools: Optional[List[str]] = None,
        enable_analysis: bool = False,
        **config,
    ):
        """Initialize Binance toolkit.

        Args:
            symbols: List of symbols to restrict operations to (None = all symbols)
            default_market: Default market type (spot, usdm, coinm)
            api_key: Binance API key (optional for public endpoints)
            api_secret: Binance API secret (optional for public endpoints)
            enabled: Whether toolkit is enabled
            include_tools: Specific tools to include
            exclude_tools: Tools to exclude
            enable_analysis: Whether to include statistical analysis in responses
            **config: Additional toolkit configuration
        """
        super().__init__(
            enabled=enabled,
            include_tools=include_tools,
            exclude_tools=exclude_tools,
            **config,
        )

        # Convert market string to enum
        self.default_market = BinanceMarketType(default_market)
        self.symbols = [s.upper() for s in symbols] if symbols else None
        self.enable_analysis = enable_analysis

        # Initialize API client
        self.client = BinanceAPIClient(
            api_key=api_key, api_secret=api_secret, default_market=self.default_market
        )

        # Initialize statistical analyzer if analysis is enabled
        self.stats = StatisticalAnalyzer() if enable_analysis else None

        logger.info(
            f"Initialized BinanceToolkit for {self.default_market.value} market "
            f"with {len(self.symbols) if self.symbols else 'all'} symbols "
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

    async def _validate_symbol(self, symbol: str, market: Optional[str] = None) -> str:
        """Validate and normalize symbol.

        Args:
            symbol: Trading symbol
            market: Market type (uses default if None)

        Returns:
            Normalized symbol

        Raises:
            ValueError: If symbol is invalid
        """
        symbol = symbol.upper()
        market_enum = BinanceMarketType(market) if market else self.default_market

        # Check user-defined symbol filter
        if self.symbols and symbol not in self.symbols:
            raise ValueError(
                f"Symbol '{symbol}' not in allowed symbols: {self.symbols}"
            )

        # Validate against Binance
        is_valid = await self.client.validate_symbol(symbol, market_enum)
        if not is_valid:
            raise ValueError(
                f"Symbol '{symbol}' not found on Binance {market_enum.value} market"
            )

        return symbol

    # =========================================================================
    # DSPy-Compatible Tool Methods (auto-registered by BaseToolkit)
    # =========================================================================

    async def get_current_price(
        self, symbol: str, market: Optional[str] = None
    ) -> dict:
        """Get current price for a trading symbol.

        Fetches the most recent trading price from the specified market.
        Essential for real-time price monitoring and trading decisions.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT", "ETHUSDT")
            market: Market type - "spot", "usdm", or "coinm" (default: spot)

        Returns:
            dict: Price data with symbol, price, and market info

        Example:
            ```python
            price = await toolkit.get_current_price("BTCUSDT")
            print(f"BTC: ${price['price']}")
            ```
        """
        try:
            symbol = await self._validate_symbol(symbol, market)
            market_enum = BinanceMarketType(market) if market else self.default_market

            data = await self.client.get_ticker_price(symbol, market_enum)

            # Price data is small, no storage needed
            return await self._build_success_response(
                data={"price": str(data["price"])},
                tool_name="get_current_price",
                symbol=symbol,
                market=market_enum.value,
            )

        except (BinanceAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_current_price", symbol=symbol
            )

    async def get_ticker_stats(self, symbol: str, market: Optional[str] = None) -> dict:
        """Get 24-hour ticker statistics.

        Retrieves comprehensive price movement statistics including
        price changes, volume, high/low, and trade count.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            market: Market type (default: spot)

        Returns:
            dict: 24-hour statistics

        Example:
            ```python
            stats = await toolkit.get_ticker_stats("BTCUSDT")
            print(f"24h change: {stats['price_change_percent']}%")
            ```
        """
        try:
            symbol = await self._validate_symbol(symbol, market)
            market_enum = BinanceMarketType(market) if market else self.default_market

            ticker = await self.client.get_ticker_24hr(symbol, market_enum)

            data = {
                "symbol": ticker.symbol,
                "price_change": str(ticker.price_change),
                "price_change_percent": str(ticker.price_change_percent),
                "last_price": str(ticker.last_price),
                "high_price": str(ticker.high_price),
                "low_price": str(ticker.low_price),
                "volume": str(ticker.volume),
                "quote_volume": str(ticker.quote_volume),
                "weighted_avg_price": str(ticker.weighted_avg_price),
                "count": ticker.count,
                "trend": ticker.trend.value,
            }

            # Add analysis if enabled
            analysis = None
            if self.enable_analysis and self.stats:
                change_pct = float(ticker.price_change_percent)
                volume = float(ticker.volume)

                analysis = {
                    "volatility": self.stats.classify_volatility_from_change(
                        change_pct
                    ).value,
                    "volume_rating": self.stats.calculate_volume_rating(volume),
                    "price_momentum": "positive"
                    if change_pct > 0
                    else "negative"
                    if change_pct < 0
                    else "neutral",
                }

            # Ticker stats are small, no storage needed
            response = await self._build_success_response(
                data=data,
                tool_name="get_ticker_stats",
                symbol=symbol,
                market=market_enum.value,
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (BinanceAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_ticker_stats", symbol=symbol
            )

    async def get_order_book(
        self, symbol: str, limit: int = 100, market: Optional[str] = None
    ) -> dict:
        """Get order book depth.

        Retrieves current bids and asks showing market depth and liquidity.
        Essential for analyzing trading opportunities and market conditions.

        Args:
            symbol: Trading symbol
            limit: Number of levels (5, 10, 20, 50, 100, 500, 1000, 5000)
            market: Market type (default: spot)

        Returns:
            dict: Order book with bids, asks, and spread info

        Example:
            ```python
            book = await toolkit.get_order_book("BTCUSDT", limit=20)
            print(f"Spread: ${book['spread']}")
            ```
        """
        try:
            symbol = await self._validate_symbol(symbol, market)
            market_enum = BinanceMarketType(market) if market else self.default_market

            book = await self.client.get_order_book(symbol, limit, market_enum)

            # Prepare summary metadata
            summary = {
                "symbol": book.symbol,
                "bids_count": len(book.bids),
                "asks_count": len(book.asks),
                "best_bid": str(book.best_bid.price) if book.best_bid else None,
                "best_ask": str(book.best_ask.price) if book.best_ask else None,
                "spread": str(book.spread) if book.spread else None,
                "mid_price": str(book.mid_price) if book.mid_price else None,
            }

            # Convert order book to dict format for storage
            book_data = {
                "symbol": book.symbol,
                "timestamp": book.timestamp.isoformat() if book.timestamp else None,
                "last_update_id": book.last_update_id,
                "bids": [
                    {"price": str(level.price), "quantity": str(level.quantity)}
                    for level in book.bids
                ],
                "asks": [
                    {"price": str(level.price), "quantity": str(level.quantity)}
                    for level in book.asks
                ],
            }

            # Order book can be large with high limits - use storage
            return await self._build_success_response(
                data=book_data,
                storage_data_type="order_books",
                storage_prefix=f"{symbol}_book_l{limit}",
                tool_name="get_order_book",
                limit=limit,
                market=market_enum.value,
                **summary,  # Add summary as metadata
            )

        except (BinanceAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_order_book", symbol=symbol
            )

    async def get_recent_trades(
        self, symbol: str, limit: int = 100, market: Optional[str] = None
    ) -> dict:
        """Get recent trades.

        Retrieves the most recent executed trades for market activity analysis.

        Args:
            symbol: Trading symbol
            limit: Number of trades (max 1000)
            market: Market type (default: spot)

        Returns:
            dict: Recent trades list with statistics

        Example:
            ```python
            trades = await toolkit.get_recent_trades("BTCUSDT", limit=50)
            print(f"Latest trade: ${trades['latest_price']}")
            ```
        """
        try:
            symbol = await self._validate_symbol(symbol, market)
            market_enum = BinanceMarketType(market) if market else self.default_market

            trades = await self.client.get_recent_trades(symbol, limit, market_enum)

            if not trades:
                return await self._build_success_response(
                    data=[],
                    tool_name="get_recent_trades",
                    symbol=symbol,
                    trades_count=0,
                    market=market_enum.value,
                )

            # Calculate statistics
            latest = trades[-1]
            prices = [float(t.price) for t in trades]

            summary = {
                "trades_count": len(trades),
                "latest_price": str(latest.price),
                "avg_price": str(sum(prices) / len(prices)),
                "min_price": str(min(prices)),
                "max_price": str(max(prices)),
            }

            # Convert trades to dict format for storage
            trades_data = [
                {
                    "id": t.id,
                    "symbol": t.symbol,
                    "price": str(t.price),
                    "quantity": str(t.quantity),
                    "quote_quantity": str(t.quote_quantity)
                    if t.quote_quantity
                    else None,
                    "timestamp": t.timestamp.isoformat(),
                    "is_buyer_maker": t.is_buyer_maker,
                    "is_best_match": t.is_best_match,
                }
                for t in trades
            ]

            # Trades can be large with high limits - use storage
            return await self._build_success_response(
                data=trades_data,
                storage_data_type="trades",
                storage_prefix=f"{symbol}_trades_l{limit}",
                tool_name="get_recent_trades",
                market=market_enum.value,
                **summary,  # Add summary as metadata
            )

        except (BinanceAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_recent_trades", symbol=symbol
            )

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        market: Optional[str] = None,
    ) -> dict:
        """Get candlestick (K-line) data.

        Retrieves OHLCV data for technical analysis and charting.

        Args:
            symbol: Trading symbol
            interval: Time interval (1m, 5m, 15m, 1h, 4h, 1d, 1w, etc.)
            limit: Number of candles (max 1000)
            market: Market type (default: spot)

        Returns:
            dict: Candlestick data with OHLCV values

        Example:
            ```python
            candles = await toolkit.get_klines("BTCUSDT", interval="1h", limit=24)
            print(f"24h candles: {candles['count']}")
            ```
        """
        try:
            symbol = await self._validate_symbol(symbol, market)
            market_enum = BinanceMarketType(market) if market else self.default_market

            klines = await self.client.get_klines(symbol, interval, limit, market_enum)

            if not klines:
                return await self._build_success_response(
                    data=[],
                    tool_name="get_klines",
                    symbol=symbol,
                    count=0,
                    interval=interval,
                    market=market_enum.value,
                )

            latest = klines[-1]

            # Prepare summary metadata
            summary = {
                "count": len(klines),
                "interval": interval,
                "latest_close": str(latest.close),
                "latest_high": str(latest.high),
                "latest_low": str(latest.low),
                "latest_volume": str(latest.volume),
                "trend": "bullish" if latest.is_bullish else "bearish",
            }

            # Convert klines to dict format for storage
            klines_data = [
                {
                    "open_time": k.open_time.isoformat(),
                    "open": str(k.open),
                    "high": str(k.high),
                    "low": str(k.low),
                    "close": str(k.close),
                    "volume": str(k.volume),
                    "close_time": k.close_time.isoformat(),
                    "quote_volume": str(k.quote_volume),
                    "trades_count": k.trades_count,
                    "taker_buy_base_volume": str(k.taker_buy_base_volume),
                    "taker_buy_quote_volume": str(k.taker_buy_quote_volume),
                }
                for k in klines
            ]

            # Add analysis if enabled
            analysis = None
            if self.enable_analysis and self.stats:
                # Use StatisticalAnalyzer for comprehensive kline analysis
                kline_analysis = self.stats.calculate_kline_analysis(klines)

                analysis = {
                    "avg_close": str(kline_analysis["avg_close"]),
                    "price_range_high": str(kline_analysis["price_range_high"]),
                    "price_range_low": str(kline_analysis["price_range_low"]),
                    "price_range": str(kline_analysis["price_range"]),
                    "total_volume": str(kline_analysis["total_volume"]),
                    "avg_return_pct": f"{kline_analysis['avg_return_pct']:.2f}",
                    "volatility": f"{kline_analysis['volatility']:.2f}",
                    "momentum": kline_analysis["trend"],
                    "bullish_candles": kline_analysis["bullish_candles"],
                    "bearish_candles": kline_analysis["bearish_candles"],
                    "bullish_ratio": f"{kline_analysis['bullish_ratio']:.2f}",
                }

            # Klines can be large - use storage with full data
            response = await self._build_success_response(
                data=klines_data,
                storage_data_type="klines",
                storage_prefix=f"{symbol}_{interval}_l{limit}",
                tool_name="get_klines",
                symbol=symbol,
                market=market_enum.value,
                **summary,  # Add summary as metadata
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (BinanceAPIError, ValueError) as e:
            return self._build_error_response(e, tool_name="get_klines", symbol=symbol)

    async def get_book_ticker(self, symbol: str, market: Optional[str] = None) -> dict:
        """Get best bid/ask prices.

        Retrieves the top-of-book prices for spread analysis.

        Args:
            symbol: Trading symbol
            market: Market type (default: spot)

        Returns:
            dict: Best bid/ask with spread

        Example:
            ```python
            ticker = await toolkit.get_book_ticker("BTCUSDT")
            print(f"Spread: {ticker['spread_percent']}%")
            ```
        """
        try:
            symbol = await self._validate_symbol(symbol, market)
            market_enum = BinanceMarketType(market) if market else self.default_market

            ticker = await self.client.get_book_ticker(symbol, market_enum)

            data = {
                "symbol": ticker.symbol,
                "bid_price": str(ticker.bid_price),
                "bid_qty": str(ticker.bid_qty),
                "ask_price": str(ticker.ask_price),
                "ask_qty": str(ticker.ask_qty),
                "spread": str(ticker.spread),
                "spread_percent": str(ticker.spread_percent),
                "mid_price": str(ticker.mid_price),
            }

            # Book ticker is small, no storage needed
            return await self._build_success_response(
                data=data,
                tool_name="get_book_ticker",
                symbol=symbol,
                market=market_enum.value,
            )

        except (BinanceAPIError, ValueError) as e:
            return self._build_error_response(
                e, tool_name="get_book_ticker", symbol=symbol
            )

    async def get_ticker(
        self, symbol: str, window_size: str = "1d", market: Optional[str] = None
    ) -> dict:
        """Get rolling window ticker statistics.

        Unlike get_ticker_stats (fixed 24h), this allows custom time windows
        for more flexible market analysis.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT", "ETHUSDT")
            window_size: Rolling window size
                - Minutes: 1m, 3m, 5m, 15m, 30m
                - Hours: 1h, 2h, 4h, 6h, 8h, 12h
                - Days: 1d, 3d
                - Week: 1w
            market: Market type (default: spot)

        Returns:
            dict: Rolling window statistics

        Example:
            ```python
            # Get 1-hour rolling stats
            stats = await toolkit.get_ticker("BTCUSDT", window_size="1h")
            print(f"1h change: {stats['data']['price_change_percent']}%")
            ```
        """
        try:
            symbol = await self._validate_symbol(symbol, market)
            market_enum = BinanceMarketType(market) if market else self.default_market

            ticker = await self.client.get_ticker(symbol, window_size, market_enum)

            data = {
                "symbol": ticker.symbol,
                "window_size": window_size,
                "price_change": str(ticker.price_change),
                "price_change_percent": str(ticker.price_change_percent),
                "last_price": str(ticker.last_price),
                "high_price": str(ticker.high_price),
                "low_price": str(ticker.low_price),
                "volume": str(ticker.volume),
                "quote_volume": str(ticker.quote_volume),
                "weighted_avg_price": str(ticker.weighted_avg_price),
                "count": ticker.count,
                "trend": ticker.trend.value,
            }

            # Add analysis if enabled
            analysis = None
            if self.enable_analysis and self.stats:
                change_pct = float(ticker.price_change_percent)
                volume = float(ticker.volume)

                analysis = {
                    "volatility": self.stats.classify_volatility_from_change(
                        change_pct
                    ).value,
                    "volume_rating": self.stats.calculate_volume_rating(volume),
                    "price_momentum": "positive"
                    if change_pct > 0
                    else "negative"
                    if change_pct < 0
                    else "neutral",
                }

            response = await self._build_success_response(
                data=data,
                tool_name="get_ticker",
                symbol=symbol,
                window_size=window_size,
                market=market_enum.value,
            )

            if analysis:
                response["analysis"] = analysis

            return response

        except (BinanceAPIError, ValueError) as e:
            return self._build_error_response(e, tool_name="get_ticker", symbol=symbol)

    async def get_exchange_info(self, market: Optional[str] = None) -> dict:
        """Get exchange trading rules and symbol information.

        Retrieves comprehensive exchange metadata including available symbols,
        trading rules (min/max quantities, price filters), rate limits, and more.
        Useful for validating trading parameters and discovering available symbols.

        Args:
            market: Market type (default: spot)

        Returns:
            dict: Exchange information or file path for large responses

        Example:
            ```python
            info = await toolkit.get_exchange_info()
            if info["success"]:
                print(f"Total symbols: {info['symbols_count']}")
                # Access full data via file_path if stored
            ```
        """
        try:
            market_enum = BinanceMarketType(market) if market else self.default_market

            data = await self.client.get_exchange_info(market_enum)

            # Exchange info can be large (5000+ symbols) - use storage
            return await self._build_success_response(
                data=data,
                storage_data_type="exchange_info",
                storage_prefix=f"{market_enum.value}_exchange_info",
                tool_name="get_exchange_info",
                market=market_enum.value,
                symbols_count=len(data.get("symbols", [])),
            )

        except BinanceAPIError as e:
            return self._build_error_response(e, tool_name="get_exchange_info")

    async def get_server_time(self, market: Optional[str] = None) -> dict:
        """Get Binance server time.

        Retrieves the current server time in Unix timestamp format.
        Useful for timestamp synchronization when making signed requests
        or analyzing time-sensitive market data.

        Args:
            market: Market type (default: spot)

        Returns:
            dict: Server time data with serverTime field (Unix timestamp in milliseconds)

        Example:
            ```python
            time_data = await toolkit.get_server_time()
            if time_data["success"]:
                server_time_ms = time_data['data']['serverTime']
                print(f"Server time: {server_time_ms}")
            ```
        """
        try:
            market_enum = BinanceMarketType(market) if market else self.default_market

            data = await self.client.get_server_time(market_enum)

            return await self._build_success_response(
                data=data,
                tool_name="get_server_time",
                market=market_enum.value,
            )

        except BinanceAPIError as e:
            return self._build_error_response(e, tool_name="get_server_time")

    async def __aenter__(self) -> "BinanceToolkit":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.aclose()

    async def aclose(self) -> None:
        """Close toolkit and clean up resources."""
        await self.client.close()
        logger.debug("Closed BinanceToolkit")
