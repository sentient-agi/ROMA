"""CoinGecko-specific types and configurations."""

from __future__ import annotations

from enum import Enum
from typing import Dict
from pydantic import BaseModel


class CoinGeckoEndpoint(str, Enum):
    """CoinGecko API endpoints."""

    # Simple price
    SIMPLE_PRICE = "/simple/price"
    TOKEN_PRICE = "/simple/token_price/{platform}"

    # Coins
    COIN_INFO = "/coins/{coin_id}"
    MARKET_CHART = "/coins/{coin_id}/market_chart"
    MARKET_CHART_RANGE = "/coins/{coin_id}/market_chart/range"
    COIN_OHLC = "/coins/{coin_id}/ohlc"

    # Markets
    COINS_MARKETS = "/coins/markets"
    COINS_LIST = "/coins/list"

    # Search
    SEARCH = "/search"

    # Global
    GLOBAL_DATA = "/global"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value


class APIConfig(BaseModel):
    """Configuration for CoinGecko API."""

    base_url: str
    description: str
    rate_limit_per_minute: int = 50  # Free tier limit


# API configurations
API_CONFIGS: Dict[str, APIConfig] = {
    "public": APIConfig(
        base_url="https://api.coingecko.com/api/v3",
        description="CoinGecko Public API",
        rate_limit_per_minute=50,
    ),
    "pro": APIConfig(
        base_url="https://pro-api.coingecko.com/api/v3",
        description="CoinGecko Pro API",
        rate_limit_per_minute=500,
    ),
}
