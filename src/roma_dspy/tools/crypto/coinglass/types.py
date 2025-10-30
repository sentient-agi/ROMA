"""Coinglass-specific types and configurations."""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CoinglassEndpoint(str, Enum):
    """Coinglass API endpoints."""

    # Funding Rate endpoints
    FUNDING_RATE_OI_WEIGHT_HISTORY = "/futures/funding-rate/oi-weight-history"
    FUNDING_RATE_EXCHANGE_LIST = "/futures/funding-rate/exchange-list"
    FUNDING_RATE_ARBITRAGE = "/futures/funding-rate/arbitrage"

    # Open Interest endpoints
    OPEN_INTEREST_EXCHANGE_LIST = "/futures/open-interest/exchange-list"
    OPEN_INTEREST_HISTORY_CHART = "/futures/open-interest/exchange-history-chart"

    # Long/Short Ratio endpoints
    TAKER_BUY_SELL_VOLUME = "/futures/taker-buy-sell-volume/exchange-list"
    LIQUIDATION_EXCHANGE_LIST = "/futures/liquidation/exchange-list"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value


class CoinglassInterval(str, Enum):
    """Time intervals for Coinglass funding rate data aggregation."""

    ONE_MINUTE = "1m"
    THREE_MINUTES = "3m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    SIX_HOURS = "6h"
    EIGHT_HOURS = "8h"
    TWELVE_HOURS = "12h"
    ONE_DAY = "1d"
    ONE_WEEK = "1w"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value


class CoinglassTimeRange(str, Enum):
    """Time ranges for aggregated Coinglass data queries."""

    ALL = "all"  # 24h interval, 6 years back
    ONE_MINUTE = "1m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    FOUR_HOURS = "4h"
    TWELVE_HOURS = "12h"
    TWENTY_FOUR_HOURS = "24h"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value


class APIConfig(BaseModel):
    """Configuration for Coinglass API."""

    base_url: str = "https://open-api-v4.coinglass.com/api"
    api_key_header: str = "CG-API-KEY"
    rate_limit_per_minute: int = 60  # Conservative default
    description: str = "Coinglass Derivatives Market Data API"


class FundingRateOHLC(BaseModel):
    """OHLC data point for funding rates weighted by open interest."""

    time: int = Field(..., description="Unix timestamp in milliseconds")
    open: float = Field(..., description="Opening funding rate")
    high: float = Field(..., description="Highest funding rate in interval")
    low: float = Field(..., description="Lowest funding rate in interval")
    close: float = Field(..., description="Closing funding rate")


class ExchangeFundingRate(BaseModel):
    """Funding rate data for a single exchange."""

    exchange: str = Field(..., description="Exchange name")
    funding_rate_interval: int = Field(..., description="Hours between funding payments")
    funding_rate: float = Field(..., description="Current funding rate")
    next_funding_time: int = Field(..., description="Next funding timestamp in milliseconds")


class FundingRateMarginList(BaseModel):
    """List of funding rates for a specific margin type."""

    stablecoin_margin_list: List[ExchangeFundingRate] = Field(
        default_factory=list, description="Stablecoin-margined contracts"
    )
    token_margin_list: List[ExchangeFundingRate] = Field(
        default_factory=list, description="Token-margined contracts"
    )


class SymbolFundingRates(BaseModel):
    """Funding rates for a cryptocurrency symbol across exchanges."""

    symbol: str = Field(..., description="Cryptocurrency symbol (e.g., BTC, ETH)")
    stablecoin_margin_list: List[ExchangeFundingRate] = Field(
        default_factory=list, description="Stablecoin-margined contracts"
    )
    token_margin_list: List[ExchangeFundingRate] = Field(
        default_factory=list, description="Token-margined contracts"
    )


class ArbitrageExchange(BaseModel):
    """Exchange information for arbitrage opportunity."""

    exchange: str = Field(..., description="Exchange name")
    open_interest_usd: float = Field(..., description="Open interest in USD")
    funding_rate_interval: int = Field(..., description="Hours between funding payments")
    funding_rate: float = Field(..., description="Current funding rate")


class ArbitrageOpportunity(BaseModel):
    """Funding rate arbitrage opportunity between two exchanges."""

    symbol: str = Field(..., description="Cryptocurrency symbol")
    buy: ArbitrageExchange = Field(..., description="Exchange to buy on")
    sell: ArbitrageExchange = Field(..., description="Exchange to sell on")
    apr: float = Field(..., description="Annualized percentage return")
    funding: float = Field(..., description="Net funding rate differential")
    fee: float = Field(..., description="Trading fee cost")
    spread: float = Field(..., description="Price spread between exchanges")
    next_funding_time: int = Field(..., description="Next funding timestamp in milliseconds")


class ExchangeOpenInterest(BaseModel):
    """Open interest data for a single exchange."""

    exchange: str = Field(..., description="Exchange name")
    open_interest_usd: float = Field(..., description="Open interest in USD")
    open_interest: Optional[float] = Field(None, description="Open interest in base currency")
    percentage: Optional[float] = Field(None, description="Percentage of total OI")


class TakerVolumeExchange(BaseModel):
    """Taker buy/sell volume data for a single exchange."""

    exchange: str = Field(..., description="Exchange name")
    buy_ratio: float = Field(..., description="Buy ratio percentage")
    sell_ratio: float = Field(..., description="Sell ratio percentage")
    buy_vol_usd: float = Field(..., description="Buy volume in USD")
    sell_vol_usd: float = Field(..., description="Sell volume in USD")


class TakerVolumeData(BaseModel):
    """Aggregated taker buy/sell volume data."""

    symbol: str = Field(..., description="Cryptocurrency symbol")
    buy_ratio: float = Field(..., description="Overall buy ratio percentage")
    sell_ratio: float = Field(..., description="Overall sell ratio percentage")
    buy_vol_usd: float = Field(..., description="Total buy volume in USD")
    sell_vol_usd: float = Field(..., description="Total sell volume in USD")
    exchange_list: List[TakerVolumeExchange] = Field(
        default_factory=list, description="Per-exchange volume data"
    )


class LiquidationExchange(BaseModel):
    """Liquidation data for a single exchange."""

    model_config = ConfigDict(populate_by_name=True)

    exchange: str = Field(..., description="Exchange name (including 'All' for aggregated)")
    liquidation_usd: float = Field(..., description="Total liquidation amount in USD")
    long_liquidation_usd: float = Field(
        ..., description="Long position liquidations in USD", alias="longLiquidation_usd"
    )
    short_liquidation_usd: float = Field(
        ..., description="Short position liquidations in USD", alias="shortLiquidation_usd"
    )


# API configuration instance
DEFAULT_API_CONFIG = APIConfig()