"""Binance-specific types and configurations."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List
from pydantic import BaseModel


class BinanceMarketType(str, Enum):
    """Binance market types."""

    SPOT = "spot"
    """Spot trading - immediate settlement with physical asset delivery"""

    USDM = "usdm"
    """USDT-margined futures - cash-settled perpetual and quarterly contracts"""

    COINM = "coinm"
    """Coin-margined futures - settled in the underlying cryptocurrency"""

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value


class MarketConfig(BaseModel):
    """Configuration for a Binance market."""

    base_url: str
    api_prefix: str
    description: str
    features: List[str]


# Market configurations for different Binance API endpoints
MARKET_CONFIGS: Dict[str, MarketConfig] = {
    "spot": MarketConfig(
        base_url="https://api.binance.us",
        api_prefix="/api/v3",
        description="Binance Spot Trading",
        features=["Immediate settlement", "Physical delivery", "Traditional pairs"],
    ),
    "usdm": MarketConfig(
        base_url="https://fapi.binance.com",
        api_prefix="/fapi/v1",
        description="USDⓈ-M Futures (USDT-Margined)",
        features=["Perpetual contracts", "USDT settlement", "High leverage"],
    ),
    "coinm": MarketConfig(
        base_url="https://dapi.binance.com",
        api_prefix="/dapi/v1",
        description="COIN-M Futures (Coin-Margined)",
        features=["Coin settlement", "Traditional futures", "Physical delivery"],
    ),
}


class BinanceEndpoint(str, Enum):
    """Binance API endpoints."""

    # Market data
    TICKER_PRICE = "/ticker/price"
    TICKER_24HR = "/ticker/24hr"
    TICKER_BOOK = "/ticker/bookTicker"
    DEPTH = "/depth"
    TRADES = "/trades"
    KLINES = "/klines"

    # Exchange info
    EXCHANGE_INFO = "/exchangeInfo"
    PING = "/ping"
    TIME = "/time"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value


class BinanceRateLimits:
    """Binance API rate limits."""

    # Requests per minute
    DEFAULT_RPM = 1200
    SPOT_RPM = 1200
    FUTURES_RPM = 2400

    # Weight limits
    DEFAULT_WEIGHT = 1200  # per minute
    ORDER_WEIGHT = 1
    KLINES_WEIGHT = 1
    DEPTH_WEIGHT_MAP = {
        5: 1,
        10: 1,
        20: 1,
        50: 1,
        100: 1,
        500: 5,
        1000: 10,
        5000: 50,
    }
