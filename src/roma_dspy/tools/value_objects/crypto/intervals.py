"""Time interval enums for crypto market data."""

from __future__ import annotations

from enum import Enum


class TimeInterval(str, Enum):
    """Standardized time intervals for candlestick/OHLCV data.

    These intervals are commonly supported across multiple exchanges
    and data providers (Binance, Coinbase, CoinGecko, etc.).
    """

    # Sub-minute (rare, exchange-specific)
    SECOND_1 = "1s"

    # Minutes
    MINUTE_1 = "1m"
    MINUTE_3 = "3m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"

    # Hours
    HOUR_1 = "1h"
    HOUR_2 = "2h"
    HOUR_4 = "4h"
    HOUR_6 = "6h"
    HOUR_8 = "8h"
    HOUR_12 = "12h"

    # Days
    DAY_1 = "1d"
    DAY_3 = "3d"

    # Weeks/Months
    WEEK_1 = "1w"
    MONTH_1 = "1M"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value

    @property
    def in_seconds(self) -> int:
        """Convert interval to seconds."""
        mapping = {
            "1s": 1,
            "1m": 60,
            "3m": 180,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "2h": 7200,
            "4h": 14400,
            "6h": 21600,
            "8h": 28800,
            "12h": 43200,
            "1d": 86400,
            "3d": 259200,
            "1w": 604800,
            "1M": 2592000,  # Approximate (30 days)
        }
        return mapping.get(self.value, 0)

    @property
    def in_minutes(self) -> float:
        """Convert interval to minutes."""
        return self.in_seconds / 60

    @property
    def in_hours(self) -> float:
        """Convert interval to hours."""
        return self.in_seconds / 3600


class ChartPeriod(str, Enum):
    """Chart period ranges for historical data queries.

    Common period ranges used across different APIs for historical
    data lookups (last 24h, 7d, 30d, etc.).
    """

    HOUR_1 = "1h"
    HOUR_24 = "24h"
    DAY_7 = "7d"
    DAY_14 = "14d"
    DAY_30 = "30d"
    DAY_90 = "90d"
    DAY_180 = "180d"
    YEAR_1 = "1y"
    ALL = "all"

    def __str__(self) -> str:
        """Return the value for string representation."""
        return self.value
