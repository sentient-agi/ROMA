"""Statistical analysis utilities for crypto toolkits."""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, Any, List, Optional, Union

import numpy as np

from roma_dspy.tools.value_objects.crypto import (
    Kline,
    Trade,
    TrendDirection,
    VolatilityLevel,
)


class StatisticalAnalyzer:
    """Statistical analysis helper for cryptocurrency data.

    Provides statistical analysis functions using NumPy for efficient computation.
    Works with both raw data and crypto value objects.
    """

    @staticmethod
    def classify_trend_from_change(change_percent: float) -> TrendDirection:
        """Classify price trend from percentage change.

        Args:
            change_percent: Price change percentage

        Returns:
            TrendDirection enum value
        """
        if change_percent > 1.0:
            return TrendDirection.BULLISH
        elif change_percent < -1.0:
            return TrendDirection.BEARISH
        else:
            return TrendDirection.SIDEWAYS

    @staticmethod
    def classify_volatility_from_change(change_percent: float) -> VolatilityLevel:
        """Classify volatility level from percentage change.

        Args:
            change_percent: Price change percentage

        Returns:
            VolatilityLevel enum value
        """
        abs_change = abs(change_percent)

        if abs_change > 10.0:
            return VolatilityLevel.EXTREME
        elif abs_change > 5.0:
            return VolatilityLevel.HIGH
        elif abs_change > 2.0:
            return VolatilityLevel.MODERATE
        else:
            return VolatilityLevel.LOW

    @staticmethod
    def calculate_price_statistics(
        prices: Union[List[Union[float, Decimal]], np.ndarray],
    ) -> Dict[str, float]:
        """Calculate basic price statistics.

        Args:
            prices: List or array of price values

        Returns:
            Dictionary with min, max, mean, median, range, std_dev, variance
        """
        if not len(prices):
            return {}

        # Convert to numpy array
        if isinstance(prices, list):
            price_array = np.array([float(p) for p in prices])
        else:
            price_array = np.asarray(prices, dtype=float)

        return {
            "min": float(np.min(price_array)),
            "max": float(np.max(price_array)),
            "mean": float(np.mean(price_array)),
            "median": float(np.median(price_array)),
            "std_dev": float(np.std(price_array)),
            "variance": float(np.var(price_array)),
            "range": float(np.max(price_array) - np.min(price_array)),
            "coefficient_of_variation": float(
                np.std(price_array) / np.mean(price_array)
            )
            if np.mean(price_array) != 0
            else 0.0,
        }

    @staticmethod
    def calculate_volume_rating(
        volume: float, thresholds: Optional[Dict[str, float]] = None
    ) -> str:
        """Calculate volume rating based on thresholds.

        Args:
            volume: Trading volume
            thresholds: Custom thresholds dict with keys: very_high, high, moderate

        Returns:
            Volume rating: "very_high", "high", "moderate", or "low"
        """
        if thresholds is None:
            thresholds = {"very_high": 10000.0, "high": 1000.0, "moderate": 100.0}

        if volume >= thresholds.get("very_high", 10000.0):
            return "very_high"
        elif volume >= thresholds.get("high", 1000.0):
            return "high"
        elif volume >= thresholds.get("moderate", 100.0):
            return "moderate"
        else:
            return "low"

    @staticmethod
    def calculate_kline_analysis(klines: List[Kline]) -> Dict[str, Any]:
        """Analyze OHLCV kline/candlestick data using value objects.

        Args:
            klines: List of Kline value objects

        Returns:
            Dictionary with OHLCV analysis including price range, volume, returns
        """
        if not klines:
            return {}

        closes = np.array([float(k.close) for k in klines])
        highs = np.array([float(k.high) for k in klines])
        lows = np.array([float(k.low) for k in klines])
        volumes = np.array([float(k.volume) for k in klines])

        # Calculate returns
        if len(closes) > 1:
            returns = np.diff(closes) / closes[:-1] * 100
            avg_return = float(np.mean(returns))
            volatility = float(np.std(returns))
        else:
            avg_return = 0.0
            volatility = 0.0

        # Count bullish/bearish candles
        bullish_count = sum(1 for k in klines if k.is_bullish)
        bearish_count = len(klines) - bullish_count

        analysis = {
            "candle_count": len(klines),
            "price_range_high": float(np.max(highs)),
            "price_range_low": float(np.min(lows)),
            "price_range": float(np.max(highs) - np.min(lows)),
            "avg_close": float(np.mean(closes)),
            "median_close": float(np.median(closes)),
            "total_volume": float(np.sum(volumes)),
            "avg_volume": float(np.mean(volumes)),
            "avg_return_pct": avg_return,
            "volatility": volatility,
            "trend": "bullish"
            if avg_return > 0
            else "bearish"
            if avg_return < 0
            else "sideways",
            "bullish_candles": bullish_count,
            "bearish_candles": bearish_count,
            "bullish_ratio": bullish_count / len(klines) if klines else 0.0,
        }

        return analysis

    @staticmethod
    def calculate_trade_analysis(trades: List[Trade]) -> Dict[str, Any]:
        """Analyze trade data using value objects.

        Args:
            trades: List of Trade value objects

        Returns:
            Dictionary with trade analysis
        """
        if not trades:
            return {}

        prices = np.array([float(t.price) for t in trades])
        quantities = np.array([float(t.quantity) for t in trades])
        quote_quantities = np.array(
            [float(t.quote_quantity) for t in trades if t.quote_quantity]
        )

        # Separate buyer/seller maker trades
        buyer_maker_trades = [t for t in trades if t.is_buyer_maker]
        seller_maker_trades = [t for t in trades if not t.is_buyer_maker]

        analysis = {
            "trade_count": len(trades),
            "price_min": float(np.min(prices)),
            "price_max": float(np.max(prices)),
            "price_mean": float(np.mean(prices)),
            "price_median": float(np.median(prices)),
            "total_quantity": float(np.sum(quantities)),
            "avg_quantity": float(np.mean(quantities)),
            "total_quote_quantity": float(np.sum(quote_quantities))
            if len(quote_quantities) > 0
            else 0.0,
            "buyer_maker_count": len(buyer_maker_trades),
            "seller_maker_count": len(seller_maker_trades),
            "buyer_maker_ratio": len(buyer_maker_trades) / len(trades)
            if trades
            else 0.0,
        }

        return analysis

    @staticmethod
    def calculate_simple_moving_average(
        prices: Union[List[float], np.ndarray], window: int
    ) -> Optional[float]:
        """Calculate simple moving average.

        Args:
            prices: List or array of price values
            window: Window size for moving average

        Returns:
            SMA value or None if insufficient data
        """
        if len(prices) < window:
            return None

        price_array = np.asarray(prices, dtype=float)
        return float(np.mean(price_array[-window:]))

    @staticmethod
    def calculate_exponential_moving_average(
        prices: Union[List[float], np.ndarray], span: int
    ) -> Optional[float]:
        """Calculate exponential moving average.

        Args:
            prices: List or array of price values
            span: Span for EMA calculation

        Returns:
            EMA value or None if insufficient data
        """
        if len(prices) < span:
            return None

        price_array = np.asarray(prices, dtype=float)
        alpha = 2 / (span + 1)
        ema = price_array[0]

        for price in price_array[1:]:
            ema = alpha * price + (1 - alpha) * ema

        return float(ema)

    @staticmethod
    def calculate_rsi(
        prices: Union[List[float], np.ndarray], period: int = 14
    ) -> Optional[float]:
        """Calculate Relative Strength Index.

        Args:
            prices: List or array of price values
            period: RSI period (default 14)

        Returns:
            RSI value (0-100) or None if insufficient data
        """
        if len(prices) < period + 1:
            return None

        price_array = np.asarray(prices, dtype=float)
        deltas = np.diff(price_array)

        # Separate gains and losses
        gains = np.where(deltas > 0, deltas, 0)[-period:]
        losses = np.where(deltas < 0, -deltas, 0)[-period:]

        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return float(rsi)

    @staticmethod
    def calculate_bollinger_bands(
        prices: Union[List[float], np.ndarray], window: int = 20, num_std: float = 2.0
    ) -> Optional[Dict[str, float]]:
        """Calculate Bollinger Bands.

        Args:
            prices: List or array of price values
            window: Window size for moving average
            num_std: Number of standard deviations for bands

        Returns:
            Dictionary with upper, middle, lower bands or None
        """
        if len(prices) < window:
            return None

        price_array = np.asarray(prices, dtype=float)
        recent_prices = price_array[-window:]

        sma = np.mean(recent_prices)
        std_dev = np.std(recent_prices)

        return {
            "upper": float(sma + (num_std * std_dev)),
            "middle": float(sma),
            "lower": float(sma - (num_std * std_dev)),
            "std_dev": float(std_dev),
        }

    @staticmethod
    def calculate_returns(prices: Union[List[float], np.ndarray]) -> np.ndarray:
        """Calculate percentage returns.

        Args:
            prices: List or array of price values

        Returns:
            Array of percentage returns
        """
        price_array = np.asarray(prices, dtype=float)
        returns = np.diff(price_array) / price_array[:-1] * 100
        return returns

    @staticmethod
    def calculate_sharpe_ratio(
        returns: Union[List[float], np.ndarray], risk_free_rate: float = 0.0
    ) -> float:
        """Calculate Sharpe ratio.

        Args:
            returns: List or array of returns
            risk_free_rate: Risk-free rate (default 0)

        Returns:
            Sharpe ratio
        """
        returns_array = np.asarray(returns, dtype=float)
        excess_returns = returns_array - risk_free_rate

        if np.std(excess_returns) == 0:
            return 0.0

        return float(np.mean(excess_returns) / np.std(excess_returns))

    @staticmethod
    def calculate_max_drawdown(
        prices: Union[List[float], np.ndarray],
    ) -> Dict[str, float]:
        """Calculate maximum drawdown.

        Args:
            prices: List or array of price values

        Returns:
            Dictionary with max_drawdown, max_drawdown_pct, peak, trough
        """
        price_array = np.asarray(prices, dtype=float)
        running_max = np.maximum.accumulate(price_array)
        drawdowns = (price_array - running_max) / running_max * 100

        max_dd_idx = np.argmin(drawdowns)
        max_dd_pct = float(drawdowns[max_dd_idx])

        # Find peak before max drawdown
        peak_idx = np.argmax(price_array[: max_dd_idx + 1])

        return {
            "max_drawdown": float(running_max[max_dd_idx] - price_array[max_dd_idx]),
            "max_drawdown_pct": max_dd_pct,
            "peak_price": float(price_array[peak_idx]),
            "trough_price": float(price_array[max_dd_idx]),
            "peak_index": int(peak_idx),
            "trough_index": int(max_dd_idx),
        }

    @staticmethod
    def analyze_price_trends(
        prices: Union[List[float], np.ndarray], window: Optional[int] = None
    ) -> Dict[str, Any]:
        """Analyze price trends using linear regression.

        Args:
            prices: List or array of price values
            window: Optional window size (uses all data if None)

        Returns:
            Dictionary with trend_direction, momentum_pct, volatility
        """
        if not len(prices):
            return {
                "trend_direction": "sideways",
                "momentum_pct": 0.0,
                "volatility": 0.0,
            }

        price_array = np.asarray(prices, dtype=float)

        # Use window if specified
        if window and len(price_array) > window:
            price_array = price_array[-window:]

        # Calculate linear regression slope
        x = np.arange(len(price_array))
        if len(price_array) >= 2:
            slope, intercept = np.polyfit(x, price_array, 1)
            avg_price = np.mean(price_array)
            momentum_pct = (slope / avg_price * 100) if avg_price > 0 else 0.0

            # Determine trend direction
            if momentum_pct > 1.0:
                trend_direction = "growing"
            elif momentum_pct < -1.0:
                trend_direction = "declining"
            else:
                trend_direction = "sideways"

            # Calculate volatility (coefficient of variation)
            volatility = (
                (np.std(price_array) / avg_price * 100) if avg_price > 0 else 0.0
            )
        else:
            trend_direction = "sideways"
            momentum_pct = 0.0
            volatility = 0.0

        return {
            "trend_direction": trend_direction,
            "momentum_pct": round(float(momentum_pct), 2),
            "volatility": round(float(volatility), 2),
        }
