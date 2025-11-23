"""Binance API client for low-level operations."""

from __future__ import annotations

import hashlib
import hmac
import time
import urllib.parse
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from roma_dspy.tools.crypto.binance.types import (
    BinanceEndpoint,
    BinanceMarketType,
    MARKET_CONFIGS,
)
from roma_dspy.tools.utils.http_client import AsyncHTTPClient, HTTPClientError
from roma_dspy.tools.value_objects.crypto import (
    BookTicker,
    Kline,
    OrderBookLevel,
    OrderBookSnapshot,
    OrderSide,
    TickerStats,
    Trade,
)


class BinanceAPIError(Exception):
    """Binance API-specific error."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response_text: Optional[str] = None,
    ):
        """Initialize Binance API error.

        Args:
            message: Error message
            status_code: HTTP status code
            response_text: API response text
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_text = response_text


class BinanceAPIClient:
    """Low-level Binance API client.

    Handles authentication, request signing, and API calls to Binance
    across different market types (spot, futures).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        default_market: BinanceMarketType = BinanceMarketType.SPOT,
    ):
        """Initialize Binance API client.

        Args:
            api_key: Binance API key (optional for public endpoints)
            api_secret: Binance API secret (optional for public endpoints)
            default_market: Default market type for requests
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.default_market = default_market

        # HTTP clients per market
        self._clients: Dict[str, AsyncHTTPClient] = {}

        # Symbol caches per market
        self._symbol_cache: Dict[str, Set[str]] = {}

    async def __aenter__(self) -> BinanceAPIClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def _get_client(self, market: BinanceMarketType) -> AsyncHTTPClient:
        """Get or create HTTP client for market.

        Args:
            market: Market type

        Returns:
            HTTP client for the market
        """
        market_str = market.value
        if market_str not in self._clients:
            config = MARKET_CONFIGS[market_str]
            headers = {}
            if self.api_key:
                headers["X-MBX-APIKEY"] = self.api_key

            self._clients[market_str] = AsyncHTTPClient(
                base_url=config.base_url,
                headers=headers,
                timeout=30.0,
                max_retries=3,
            )
            logger.debug(f"Created HTTP client for {market_str} market")

        return self._clients[market_str]

    def _sign_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Sign request with API secret.

        Args:
            params: Request parameters

        Returns:
            Parameters with signature added
        """
        if not self.api_secret:
            raise BinanceAPIError("API secret required for signed endpoints")

        # Add timestamp
        params["timestamp"] = str(int(time.time() * 1000))

        # Create query string
        query_string = urllib.parse.urlencode(params)

        # Generate signature
        signature = hmac.new(
            self.api_secret.encode(), query_string.encode(), hashlib.sha256
        ).hexdigest()

        # Add signature to params
        params["signature"] = signature
        return params

    async def _request(
        self,
        endpoint: str,
        market: Optional[BinanceMarketType] = None,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ) -> Dict[str, Any]:
        """Make API request.

        Args:
            endpoint: API endpoint path
            market: Market type (uses default if None)
            params: Query parameters
            signed: Whether to sign the request

        Returns:
            API response data

        Raises:
            BinanceAPIError: On API error
        """
        market = market or self.default_market
        config = MARKET_CONFIGS[market.value]
        client = self._get_client(market)

        # Add API prefix
        full_path = f"{config.api_prefix}{endpoint}"

        # Sign if required
        if signed:
            params = self._sign_request(params or {})

        try:
            return await client.get(full_path, params=params)
        except HTTPClientError as e:
            raise BinanceAPIError(
                f"Binance API error: {e}",
                status_code=e.status_code,
                response_text=e.response_text,
            ) from e

    async def get_exchange_info(
        self, market: Optional[BinanceMarketType] = None
    ) -> Dict[str, Any]:
        """Get exchange trading rules and symbol information.

        Args:
            market: Market type

        Returns:
            Exchange information
        """
        return await self._request(BinanceEndpoint.EXCHANGE_INFO.value, market=market)

    async def load_symbols(
        self, market: Optional[BinanceMarketType] = None
    ) -> Set[str]:
        """Load and cache valid trading symbols for a market.

        Args:
            market: Market type

        Returns:
            Set of valid symbols
        """
        market = market or self.default_market
        market_str = market.value

        # Get exchange info
        info = await self.get_exchange_info(market)

        # Extract trading symbols
        symbols = {
            s["symbol"] for s in info.get("symbols", []) if s.get("status") == "TRADING"
        }

        # Cache symbols
        self._symbol_cache[market_str] = symbols
        logger.info(f"Loaded {len(symbols)} symbols for {market_str} market")

        return symbols

    async def validate_symbol(
        self, symbol: str, market: Optional[BinanceMarketType] = None
    ) -> bool:
        """Validate if symbol exists and is tradable.

        Args:
            symbol: Trading symbol
            market: Market type

        Returns:
            True if symbol is valid
        """
        market = market or self.default_market
        market_str = market.value

        # Load symbols if not cached
        if market_str not in self._symbol_cache:
            await self.load_symbols(market)

        return symbol.upper() in self._symbol_cache.get(market_str, set())

    async def get_ticker_price(
        self, symbol: str, market: Optional[BinanceMarketType] = None
    ) -> Dict[str, Any]:
        """Get current price for a symbol.

        Args:
            symbol: Trading symbol
            market: Market type

        Returns:
            Price data
        """
        params = {"symbol": symbol.upper()}
        return await self._request(
            BinanceEndpoint.TICKER_PRICE.value, market=market, params=params
        )

    async def get_ticker_24hr(
        self, symbol: str, market: Optional[BinanceMarketType] = None
    ) -> TickerStats:
        """Get 24-hour ticker statistics.

        Args:
            symbol: Trading symbol
            market: Market type

        Returns:
            Ticker statistics
        """
        params = {"symbol": symbol.upper()}
        data = await self._request(
            BinanceEndpoint.TICKER_24HR.value, market=market, params=params
        )

        # Convert timestamps to datetime if present
        open_time = None
        close_time = None
        if data.get("openTime"):
            open_time = datetime.fromtimestamp(data["openTime"] / 1000)
        if data.get("closeTime"):
            close_time = datetime.fromtimestamp(data["closeTime"] / 1000)

        # Parse to TickerStats model
        return TickerStats(
            symbol=data["symbol"],
            price_change=Decimal(str(data["priceChange"])),
            price_change_percent=Decimal(str(data["priceChangePercent"])),
            weighted_avg_price=Decimal(str(data["weightedAvgPrice"])),
            last_price=Decimal(str(data["lastPrice"])),
            last_qty=Decimal(str(data["lastQty"])) if data.get("lastQty") else None,
            open_price=Decimal(str(data["openPrice"])),
            high_price=Decimal(str(data["highPrice"])),
            low_price=Decimal(str(data["lowPrice"])),
            volume=Decimal(str(data["volume"])),
            quote_volume=Decimal(str(data["quoteVolume"])),
            open_time=open_time,
            close_time=close_time,
            first_id=data.get("firstId"),
            last_id=data.get("lastId"),
            count=data.get("count"),
        )

    async def get_ticker(
        self,
        symbol: str,
        window_size: str = "1d",
        market: Optional[BinanceMarketType] = None,
    ) -> TickerStats:
        """Get rolling window ticker statistics.

        Unlike get_ticker_24hr (fixed 24h), this allows custom rolling windows.

        Args:
            symbol: Trading symbol
            window_size: Rolling window size
                - Minutes: 1m, 3m, 5m, 15m, 30m
                - Hours: 1h, 2h, 4h, 6h, 8h, 12h
                - Days: 1d, 3d
                - Week: 1w
            market: Market type

        Returns:
            Ticker statistics for the specified window
        """
        params = {
            "symbol": symbol.upper(),
            "windowSize": window_size,
        }
        data = await self._request(
            BinanceEndpoint.TICKER_24HR.value, market=market, params=params
        )

        # Convert timestamps to datetime if present
        open_time = None
        close_time = None
        if data.get("openTime"):
            open_time = datetime.fromtimestamp(data["openTime"] / 1000)
        if data.get("closeTime"):
            close_time = datetime.fromtimestamp(data["closeTime"] / 1000)

        # Parse to TickerStats model (same structure as 24hr ticker)
        return TickerStats(
            symbol=data["symbol"],
            price_change=Decimal(str(data["priceChange"])),
            price_change_percent=Decimal(str(data["priceChangePercent"])),
            weighted_avg_price=Decimal(str(data["weightedAvgPrice"])),
            last_price=Decimal(str(data["lastPrice"])),
            last_qty=Decimal(str(data["lastQty"])) if data.get("lastQty") else None,
            open_price=Decimal(str(data["openPrice"])),
            high_price=Decimal(str(data["highPrice"])),
            low_price=Decimal(str(data["lowPrice"])),
            volume=Decimal(str(data["volume"])),
            quote_volume=Decimal(str(data["quoteVolume"])),
            open_time=open_time,
            close_time=close_time,
            first_id=data.get("firstId"),
            last_id=data.get("lastId"),
            count=data.get("count"),
        )

    async def get_server_time(
        self, market: Optional[BinanceMarketType] = None
    ) -> Dict[str, Any]:
        """Get Binance server time.

        Useful for timestamp synchronization when making signed requests.

        Args:
            market: Market type

        Returns:
            Server time data with serverTime field (Unix timestamp in milliseconds)
        """
        return await self._request(BinanceEndpoint.TIME.value, market=market)

    async def get_order_book(
        self, symbol: str, limit: int = 100, market: Optional[BinanceMarketType] = None
    ) -> OrderBookSnapshot:
        """Get order book depth.

        Args:
            symbol: Trading symbol
            limit: Number of levels (5, 10, 20, 50, 100, 500, 1000, 5000)
            market: Market type

        Returns:
            Order book snapshot
        """
        params = {"symbol": symbol.upper(), "limit": limit}
        data = await self._request(
            BinanceEndpoint.DEPTH.value, market=market, params=params
        )

        # Parse bids and asks with proper type conversions
        bids = [
            OrderBookLevel(
                price=Decimal(str(price)),
                quantity=Decimal(str(qty)),
                side=OrderSide.BID,
            )
            for price, qty in data["bids"]
        ]
        asks = [
            OrderBookLevel(
                price=Decimal(str(price)),
                quantity=Decimal(str(qty)),
                side=OrderSide.ASK,
            )
            for price, qty in data["asks"]
        ]

        return OrderBookSnapshot(
            symbol=symbol.upper(),
            bids=bids,
            asks=asks,
            timestamp=datetime.now(timezone.utc),
            last_update_id=data.get("lastUpdateId"),
        )

    async def get_recent_trades(
        self, symbol: str, limit: int = 500, market: Optional[BinanceMarketType] = None
    ) -> List[Trade]:
        """Get recent trades.

        Args:
            symbol: Trading symbol
            limit: Number of trades (max 1000)
            market: Market type

        Returns:
            List of trades
        """
        params = {"symbol": symbol.upper(), "limit": limit}
        data = await self._request(
            BinanceEndpoint.TRADES.value, market=market, params=params
        )

        # Parse to Trade models with proper type conversions
        return [
            Trade(
                id=t["id"],
                symbol=symbol.upper(),
                price=Decimal(str(t["price"])),
                quantity=Decimal(str(t["qty"])),
                quote_quantity=Decimal(str(t["quoteQty"]))
                if t.get("quoteQty")
                else None,
                timestamp=datetime.fromtimestamp(t["time"] / 1000),
                is_buyer_maker=t["isBuyerMaker"],
                is_best_match=t.get("isBestMatch"),
            )
            for t in data
        ]

    async def get_klines(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 500,
        market: Optional[BinanceMarketType] = None,
    ) -> List[Kline]:
        """Get candlestick data.

        Args:
            symbol: Trading symbol
            interval: Time interval (1m, 5m, 1h, 1d, etc.)
            limit: Number of candles (max 1000)
            market: Market type

        Returns:
            List of klines
        """
        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        data = await self._request(
            BinanceEndpoint.KLINES.value, market=market, params=params
        )

        # Parse to Kline models with proper type conversions
        # Binance kline format: [open_time, open, high, low, close, volume, close_time,
        #                        quote_volume, trades_count, taker_buy_base, taker_buy_quote, ignore]
        return [
            Kline(
                open_time=datetime.fromtimestamp(k[0] / 1000),
                open=Decimal(str(k[1])),
                high=Decimal(str(k[2])),
                low=Decimal(str(k[3])),
                close=Decimal(str(k[4])),
                volume=Decimal(str(k[5])),
                close_time=datetime.fromtimestamp(k[6] / 1000),
                quote_volume=Decimal(str(k[7])),
                trades_count=int(k[8]),
                taker_buy_base_volume=Decimal(str(k[9])),
                taker_buy_quote_volume=Decimal(str(k[10])),
            )
            for k in data
        ]

    async def get_book_ticker(
        self, symbol: str, market: Optional[BinanceMarketType] = None
    ) -> BookTicker:
        """Get best bid/ask prices.

        Args:
            symbol: Trading symbol
            market: Market type

        Returns:
            Book ticker
        """
        params = {"symbol": symbol.upper()}
        data = await self._request(
            BinanceEndpoint.TICKER_BOOK.value, market=market, params=params
        )

        return BookTicker(
            symbol=data["symbol"],
            bid_price=Decimal(str(data["bidPrice"])),
            bid_qty=Decimal(str(data["bidQty"])),
            ask_price=Decimal(str(data["askPrice"])),
            ask_qty=Decimal(str(data["askQty"])),
            timestamp=datetime.now(timezone.utc),
        )

    async def close(self) -> None:
        """Close all HTTP clients."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
        logger.debug("Closed all Binance API clients")
