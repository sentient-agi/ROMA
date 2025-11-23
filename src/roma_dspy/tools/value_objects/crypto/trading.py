"""Trading-specific value objects for crypto exchanges."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from enum import Enum

from pydantic import BaseModel, Field, field_validator, computed_field


class OrderSide(str, Enum):
    """Order book side."""

    BID = "bid"
    ASK = "ask"


class OrderType(str, Enum):
    """Order types."""

    LIMIT = "limit"
    MARKET = "market"
    STOP_LOSS = "stop_loss"
    STOP_LOSS_LIMIT = "stop_loss_limit"
    TAKE_PROFIT = "take_profit"
    TAKE_PROFIT_LIMIT = "take_profit_limit"


class OrderStatus(str, Enum):
    """Order execution status."""

    NEW = "new"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"


class TrendDirection(str, Enum):
    """Price trend direction."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    SIDEWAYS = "sideways"
    NEUTRAL = "neutral"


class VolatilityLevel(str, Enum):
    """Market volatility level."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


class OrderBookLevel(BaseModel):
    """Single order book price level.

    Represents a price level in the order book with
    the total quantity available at that price.
    """

    price: Decimal = Field(description="Price level")
    quantity: Decimal = Field(description="Quantity available at this price")
    side: OrderSide = Field(description="Bid or ask side")

    @field_validator("price", "quantity", mode="before")
    @classmethod
    def validate_decimal(cls, v) -> Decimal:
        """Convert string/number to Decimal."""
        if v is None:
            return Decimal("0")
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v

    class Config:
        """Pydantic config."""

        use_enum_values = True


class OrderBookSnapshot(BaseModel):
    """Order book depth snapshot.

    Contains bids and asks at various price levels,
    providing a view of current market depth and liquidity.
    """

    symbol: str = Field(description="Trading pair symbol")
    bids: List[OrderBookLevel] = Field(
        default_factory=list, description="Buy orders (highest first)"
    )
    asks: List[OrderBookLevel] = Field(
        default_factory=list, description="Sell orders (lowest first)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Snapshot timestamp"
    )
    last_update_id: Optional[int] = Field(
        None, description="Last update sequence number"
    )

    @computed_field
    @property
    def best_bid(self) -> Optional[OrderBookLevel]:
        """Get best bid (highest buy price)."""
        return self.bids[0] if self.bids else None

    @computed_field
    @property
    def best_ask(self) -> Optional[OrderBookLevel]:
        """Get best ask (lowest sell price)."""
        return self.asks[0] if self.asks else None

    @computed_field
    @property
    def spread(self) -> Optional[Decimal]:
        """Calculate bid-ask spread."""
        if self.best_bid and self.best_ask:
            return self.best_ask.price - self.best_bid.price
        return None

    @computed_field
    @property
    def mid_price(self) -> Optional[Decimal]:
        """Calculate mid-market price."""
        if self.best_bid and self.best_ask:
            return (self.best_bid.price + self.best_ask.price) / Decimal("2")
        return None


class Trade(BaseModel):
    """Individual trade execution.

    Represents a completed trade transaction on an exchange.
    """

    id: int = Field(description="Trade ID")
    symbol: str = Field(description="Trading pair symbol")
    price: Decimal = Field(description="Execution price")
    quantity: Decimal = Field(description="Trade quantity")
    quote_quantity: Optional[Decimal] = Field(
        None, description="Quote asset quantity (price * quantity)"
    )
    timestamp: datetime = Field(description="Trade execution time")
    is_buyer_maker: bool = Field(
        description="True if buyer placed limit order (passive)"
    )
    is_best_match: Optional[bool] = Field(
        None, description="True if trade from best price match"
    )

    @field_validator("price", "quantity", "quote_quantity", mode="before")
    @classmethod
    def validate_decimal(cls, v) -> Optional[Decimal]:
        """Convert string/number to Decimal."""
        if v is None:
            return None
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class Kline(BaseModel):
    """Candlestick (K-line) OHLCV data.

    Standard OHLCV (Open, High, Low, Close, Volume) candlestick
    used for technical analysis and charting.
    """

    open_time: datetime = Field(description="Candle open time")
    open: Decimal = Field(description="Opening price")
    high: Decimal = Field(description="Highest price")
    low: Decimal = Field(description="Lowest price")
    close: Decimal = Field(description="Closing price")
    volume: Decimal = Field(description="Base asset volume")
    close_time: datetime = Field(description="Candle close time")
    quote_volume: Optional[Decimal] = Field(None, description="Quote asset volume")
    trades_count: Optional[int] = Field(None, description="Number of trades in period")
    taker_buy_base_volume: Optional[Decimal] = Field(
        None, description="Taker buy base asset volume"
    )
    taker_buy_quote_volume: Optional[Decimal] = Field(
        None, description="Taker buy quote asset volume"
    )

    @field_validator(
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
        "taker_buy_base_volume",
        "taker_buy_quote_volume",
        mode="before",
    )
    @classmethod
    def validate_decimal(cls, v) -> Optional[Decimal]:
        """Convert string/number to Decimal."""
        if v is None:
            return None
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v

    @computed_field
    @property
    def is_bullish(self) -> bool:
        """Check if candle is bullish (close > open)."""
        return self.close > self.open

    @computed_field
    @property
    def body_size(self) -> Decimal:
        """Calculate candle body size (absolute difference between open and close)."""
        return abs(self.close - self.open)

    @computed_field
    @property
    def wick_high(self) -> Decimal:
        """Calculate upper wick size."""
        return self.high - max(self.open, self.close)

    @computed_field
    @property
    def wick_low(self) -> Decimal:
        """Calculate lower wick size."""
        return min(self.open, self.close) - self.low


class TickerStats(BaseModel):
    """24-hour ticker statistics.

    Comprehensive statistics for a trading pair over a rolling 24-hour window.
    """

    symbol: str = Field(description="Trading pair symbol")
    price_change: Decimal = Field(description="Absolute price change")
    price_change_percent: Decimal = Field(description="Price change percentage")
    weighted_avg_price: Decimal = Field(
        description="Volume-weighted average price (VWAP)"
    )
    last_price: Decimal = Field(description="Last traded price")
    last_qty: Optional[Decimal] = Field(None, description="Last trade quantity")
    open_price: Decimal = Field(description="Opening price")
    high_price: Decimal = Field(description="Highest price")
    low_price: Decimal = Field(description="Lowest price")
    volume: Decimal = Field(description="Base asset volume")
    quote_volume: Decimal = Field(description="Quote asset volume")
    open_time: Optional[datetime] = Field(None, description="Statistics period start")
    close_time: Optional[datetime] = Field(None, description="Statistics period end")
    first_id: Optional[int] = Field(None, description="First trade ID")
    last_id: Optional[int] = Field(None, description="Last trade ID")
    count: Optional[int] = Field(None, description="Number of trades")

    @field_validator(
        "price_change",
        "price_change_percent",
        "weighted_avg_price",
        "last_price",
        "last_qty",
        "open_price",
        "high_price",
        "low_price",
        "volume",
        "quote_volume",
        mode="before",
    )
    @classmethod
    def validate_decimal(cls, v) -> Optional[Decimal]:
        """Convert string/number to Decimal."""
        if v is None:
            return None
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v

    @computed_field
    @property
    def trend(self) -> TrendDirection:
        """Determine price trend based on change percentage."""
        if self.price_change_percent > Decimal("1"):
            return TrendDirection.BULLISH
        elif self.price_change_percent < Decimal("-1"):
            return TrendDirection.BEARISH
        else:
            return TrendDirection.SIDEWAYS


class BookTicker(BaseModel):
    """Best bid/ask prices and quantities.

    Real-time top-of-book prices, essential for spread analysis
    and execution cost estimation.
    """

    symbol: str = Field(description="Trading pair symbol")
    bid_price: Decimal = Field(description="Best bid price")
    bid_qty: Decimal = Field(description="Best bid quantity")
    ask_price: Decimal = Field(description="Best ask price")
    ask_qty: Decimal = Field(description="Best ask quantity")
    timestamp: Optional[datetime] = Field(None, description="Update timestamp")

    @field_validator("bid_price", "bid_qty", "ask_price", "ask_qty", mode="before")
    @classmethod
    def validate_decimal(cls, v) -> Decimal:
        """Convert string/number to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v

    @computed_field
    @property
    def spread(self) -> Decimal:
        """Calculate bid-ask spread."""
        return self.ask_price - self.bid_price

    @computed_field
    @property
    def spread_percent(self) -> Decimal:
        """Calculate spread as percentage of bid price."""
        if self.bid_price > 0:
            return (self.spread / self.bid_price) * Decimal("100")
        return Decimal("0")

    @computed_field
    @property
    def mid_price(self) -> Decimal:
        """Calculate mid-market price."""
        return (self.bid_price + self.ask_price) / Decimal("2")
