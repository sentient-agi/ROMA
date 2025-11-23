"""Integration tests for Binance toolkit."""

import pytest
from decimal import Decimal
from datetime import datetime

from roma_dspy.tools.crypto.binance import BinanceToolkit, BinanceMarketType
from roma_dspy.tools.value_objects.crypto import (
    TrendDirection,
    VolatilityLevel,
    OrderSide,
    Kline,
    Trade,
)
from roma_dspy.tools.utils.statistics import StatisticalAnalyzer


class TestBinanceToolkitIntegration:
    """Test Binance toolkit integration with stats and value objects."""

    def test_toolkit_initialization_with_analysis(self):
        """Test toolkit initialization with analysis enabled."""
        toolkit = BinanceToolkit(
            symbols=["BTCUSDT"],
            default_market="spot",
            enable_analysis=True,
        )

        assert toolkit.enable_analysis is True
        assert toolkit.stats is not None
        assert isinstance(toolkit.stats, StatisticalAnalyzer)
        assert toolkit.default_market == BinanceMarketType.SPOT

    def test_toolkit_initialization_without_analysis(self):
        """Test toolkit initialization without analysis."""
        toolkit = BinanceToolkit(
            symbols=["BTCUSDT"],
            default_market="spot",
            enable_analysis=False,
        )

        assert toolkit.enable_analysis is False
        assert toolkit.stats is None

    def test_stats_analyzer_with_value_objects(self):
        """Test StatisticalAnalyzer returns proper value objects."""
        stats = StatisticalAnalyzer()

        # Test trend classification
        trend = stats.classify_trend_from_change(5.0)
        assert trend == TrendDirection.BULLISH
        assert isinstance(trend, TrendDirection)

        # Test volatility classification
        volatility = stats.classify_volatility_from_change(8.0)
        assert volatility == VolatilityLevel.HIGH
        assert isinstance(volatility, VolatilityLevel)

    def test_kline_analysis_with_value_objects(self):
        """Test kline analysis using Kline value objects."""
        stats = StatisticalAnalyzer()

        # Create mock klines
        klines = [
            Kline(
                open_time=datetime.utcnow(),
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=Decimal("1000"),
                close_time=datetime.utcnow(),
                quote_volume=Decimal("100000"),
                trades_count=50,
                taker_buy_base_volume=Decimal("500"),
                taker_buy_quote_volume=Decimal("50000"),
            ),
            Kline(
                open_time=datetime.utcnow(),
                open=Decimal("103"),
                high=Decimal("108"),
                low=Decimal("102"),
                close=Decimal("107"),
                volume=Decimal("1200"),
                close_time=datetime.utcnow(),
                quote_volume=Decimal("120000"),
                trades_count=60,
                taker_buy_base_volume=Decimal("600"),
                taker_buy_quote_volume=Decimal("60000"),
            ),
        ]

        analysis = stats.calculate_kline_analysis(klines)

        assert analysis["candle_count"] == 2
        assert analysis["bullish_candles"] == 2
        assert analysis["bearish_candles"] == 0
        assert analysis["trend"] == "bullish"
        assert "avg_close" in analysis
        assert "total_volume" in analysis

    def test_trade_analysis_with_value_objects(self):
        """Test trade analysis using Trade value objects."""
        stats = StatisticalAnalyzer()

        # Create mock trades
        trades = [
            Trade(
                id=1,
                symbol="BTCUSDT",
                price=Decimal("50000"),
                quantity=Decimal("0.1"),
                quote_quantity=Decimal("5000"),
                timestamp=datetime.utcnow(),
                is_buyer_maker=True,
            ),
            Trade(
                id=2,
                symbol="BTCUSDT",
                price=Decimal("50100"),
                quantity=Decimal("0.2"),
                quote_quantity=Decimal("10020"),
                timestamp=datetime.utcnow(),
                is_buyer_maker=False,
            ),
        ]

        analysis = stats.calculate_trade_analysis(trades)

        assert analysis["trade_count"] == 2
        assert analysis["buyer_maker_count"] == 1
        assert analysis["seller_maker_count"] == 1
        assert analysis["buyer_maker_ratio"] == 0.5
        assert "price_mean" in analysis
        assert "total_quantity" in analysis

    def test_no_duplicate_enums(self):
        """Ensure no duplicate enums between base crypto and Binance-specific."""
        # Base crypto enums
        assert hasattr(TrendDirection, "BULLISH")
        assert hasattr(VolatilityLevel, "HIGH")
        assert hasattr(OrderSide, "BID")

        # Binance-specific types (should NOT duplicate base enums)
        assert hasattr(BinanceMarketType, "SPOT")

        # Verify they are different types
        assert type(TrendDirection.BULLISH) != type(BinanceMarketType.SPOT)

    def test_toolkit_uses_base_value_objects(self):
        """Ensure toolkit uses base crypto value objects, not duplicates."""
        toolkit = BinanceToolkit(enable_analysis=True)

        # Verify stats returns base value objects
        if toolkit.stats:
            trend = toolkit.stats.classify_trend_from_change(2.5)
            volatility = toolkit.stats.classify_volatility_from_change(3.0)

            # Should be base enum types
            assert (
                type(trend).__module__
                == "src.roma_dspy.tools.value_objects.crypto.trading"
            )
            assert (
                type(volatility).__module__
                == "src.roma_dspy.tools.value_objects.crypto.trading"
            )
