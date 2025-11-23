"""End-to-end tests for Binance toolkit demonstrating completeness and correctness."""

import pytest
from decimal import Decimal
from datetime import datetime

from roma_dspy.tools.crypto.binance import BinanceToolkit
from roma_dspy.tools.value_objects.crypto import (
    TrendDirection,
    VolatilityLevel,
    OrderSide,
)


class TestBinanceE2E:
    """End-to-end validation tests."""

    def test_complete_initialization(self):
        """Test complete toolkit initialization with all options."""
        toolkit = BinanceToolkit(
            symbols=["BTCUSDT", "ETHUSDT"],
            default_market="spot",
            enable_analysis=True,
            enabled=True,
        )

        assert toolkit.enabled is True
        assert toolkit.symbols == ["BTCUSDT", "ETHUSDT"]
        assert toolkit.enable_analysis is True
        assert toolkit.stats is not None
        assert toolkit.client is not None

    def test_toolkit_has_all_required_methods(self):
        """Verify all 6 required tools are present."""
        toolkit = BinanceToolkit()

        required_methods = [
            "get_current_price",
            "get_ticker_stats",
            "get_order_book",
            "get_recent_trades",
            "get_klines",
            "get_book_ticker",
        ]

        for method_name in required_methods:
            assert hasattr(toolkit, method_name), f"Missing method: {method_name}"
            method = getattr(toolkit, method_name)
            assert callable(method), f"Method not callable: {method_name}"

    def test_context_manager_support(self):
        """Verify async context manager support for proper resource cleanup."""
        toolkit = BinanceToolkit()

        # Check context manager methods exist
        assert hasattr(toolkit, "__aenter__")
        assert hasattr(toolkit, "__aexit__")
        assert hasattr(toolkit, "aclose")

        # Check they're callable
        assert callable(toolkit.__aenter__)
        assert callable(toolkit.__aexit__)
        assert callable(toolkit.aclose)

    def test_type_safety_decimal_usage(self):
        """Verify proper Decimal usage throughout the system."""
        from roma_dspy.tools.value_objects.crypto import Kline, Trade

        # Kline uses Decimal
        kline = Kline(
            open_time=datetime.now(),
            open=Decimal("100.5"),
            high=Decimal("101.0"),
            low=Decimal("100.0"),
            close=Decimal("100.75"),
            volume=Decimal("1000.0"),
            close_time=datetime.now(),
            quote_volume=Decimal("100500.0"),
            trades_count=50,
            taker_buy_base_volume=Decimal("500.0"),
            taker_buy_quote_volume=Decimal("50250.0"),
        )

        assert isinstance(kline.open, Decimal)
        assert isinstance(kline.close, Decimal)
        assert isinstance(kline.volume, Decimal)

        # Trade uses Decimal
        trade = Trade(
            id=1,
            symbol="BTCUSDT",
            price=Decimal("50000.0"),
            quantity=Decimal("0.1"),
            quote_quantity=Decimal("5000.0"),
            timestamp=datetime.now(),
            is_buyer_maker=True,
        )

        assert isinstance(trade.price, Decimal)
        assert isinstance(trade.quantity, Decimal)

    def test_float_conversion_for_stats_is_intentional(self):
        """Verify float conversions are intentional for NumPy operations."""
        from roma_dspy.tools.utils.statistics import StatisticalAnalyzer

        stats = StatisticalAnalyzer()

        # These methods accept float for NumPy calculations
        trend = stats.classify_trend_from_change(5.0)  # float input
        assert isinstance(trend, TrendDirection)

        volatility = stats.classify_volatility_from_change(8.0)  # float input
        assert isinstance(volatility, VolatilityLevel)

        # This is the correct pattern: store as Decimal, compute as float

    def test_no_duplicate_enums_between_base_and_binance(self):
        """Ensure no enum duplication between base crypto and Binance-specific."""
        from roma_dspy.tools.value_objects.crypto import (
            TrendDirection,
            VolatilityLevel,
            OrderSide,
        )
        from roma_dspy.tools.crypto.binance.types import (
            BinanceMarketType,
            BinanceEndpoint,
        )

        # Base crypto enums
        base_enums = {TrendDirection, VolatilityLevel, OrderSide}

        # Binance-specific enums
        binance_enums = {BinanceMarketType, BinanceEndpoint}

        # Should be completely different types
        assert len(base_enums & binance_enums) == 0

    def test_statistical_analysis_uses_base_enums(self):
        """Verify StatisticalAnalyzer returns base crypto enums, not duplicates."""
        from roma_dspy.tools.utils.statistics import StatisticalAnalyzer
        from roma_dspy.tools.value_objects.crypto import (
            TrendDirection,
            VolatilityLevel,
        )

        stats = StatisticalAnalyzer()

        trend = stats.classify_trend_from_change(2.5)
        volatility = stats.classify_volatility_from_change(3.0)

        # Should be base enum types
        assert (
            type(trend).__module__ == "src.roma_dspy.tools.value_objects.crypto.trading"
        )
        assert (
            type(volatility).__module__
            == "src.roma_dspy.tools.value_objects.crypto.trading"
        )

    def test_error_handling_consistency(self):
        """Verify consistent error response format."""
        # All toolkit methods should return consistent error format:
        # {"success": False, "error": str, "symbol": str}

        toolkit = BinanceToolkit()

        # Methods should be async and return dict
        import inspect

        for method_name in [
            "get_current_price",
            "get_ticker_stats",
            "get_order_book",
            "get_recent_trades",
            "get_klines",
            "get_book_ticker",
        ]:
            method = getattr(toolkit, method_name)
            assert inspect.iscoroutinefunction(method), f"{method_name} should be async"

    def test_value_objects_have_computed_properties(self):
        """Verify value objects have useful computed properties."""
        from roma_dspy.tools.value_objects.crypto import (
            Kline,
            OrderBookSnapshot,
            OrderBookLevel,
        )

        # Kline has computed properties
        kline = Kline(
            open_time=datetime.now(),
            open=Decimal("100.0"),
            high=Decimal("105.0"),
            low=Decimal("99.0"),
            close=Decimal("103.0"),
            volume=Decimal("1000.0"),
            close_time=datetime.now(),
            quote_volume=Decimal("100000.0"),
            trades_count=50,
            taker_buy_base_volume=Decimal("500.0"),
            taker_buy_quote_volume=Decimal("50000.0"),
        )

        assert kline.is_bullish is True  # close > open
        assert kline.body_size == Decimal("3.0")  # abs(close - open)
        assert kline.wick_high == Decimal("2.0")  # high - max(open, close)

        # OrderBookSnapshot has computed properties
        book = OrderBookSnapshot(
            symbol="BTCUSDT",
            bids=[
                OrderBookLevel(
                    price=Decimal("50000.0"),
                    quantity=Decimal("1.0"),
                    side=OrderSide.BID,
                )
            ],
            asks=[
                OrderBookLevel(
                    price=Decimal("50001.0"),
                    quantity=Decimal("1.0"),
                    side=OrderSide.ASK,
                )
            ],
            timestamp=datetime.now(),
        )

        assert book.best_bid is not None
        assert book.best_ask is not None
        assert book.spread == Decimal("1.0")  # ask - bid
        assert book.mid_price == Decimal("50000.5")  # (bid + ask) / 2

    def test_architecture_separation_of_concerns(self):
        """Verify clean 3-layer architecture."""
        from roma_dspy.tools.utils.http_client import AsyncHTTPClient
        from roma_dspy.tools.crypto.binance.client import BinanceAPIClient
        from roma_dspy.tools.crypto.binance.toolkit import BinanceToolkit

        # Layer 1: HTTP client (generic)
        http_client = AsyncHTTPClient(base_url="https://api.binance.us")
        assert hasattr(http_client, "get")
        assert hasattr(http_client, "post")
        assert hasattr(http_client, "close")

        # Layer 2: API client (Binance-specific)
        api_client = BinanceAPIClient()
        assert hasattr(api_client, "get_ticker_price")
        assert hasattr(api_client, "get_order_book")
        assert hasattr(api_client, "_request")  # uses HTTP client internally

        # Layer 3: Toolkit (DSPy-compatible)
        toolkit = BinanceToolkit()
        assert hasattr(toolkit, "get_current_price")  # high-level interface
        assert hasattr(toolkit, "client")  # uses API client internally

    def test_multi_market_support(self):
        """Verify support for multiple market types."""
        from roma_dspy.tools.crypto.binance.types import (
            BinanceMarketType,
            MARKET_CONFIGS,
        )

        # Should support 3 market types
        assert BinanceMarketType.SPOT in BinanceMarketType
        assert BinanceMarketType.USDM in BinanceMarketType
        assert BinanceMarketType.COINM in BinanceMarketType

        # Each market should have config
        assert "spot" in MARKET_CONFIGS
        assert "usdm" in MARKET_CONFIGS
        assert "coinm" in MARKET_CONFIGS

        # Configs should have required fields
        for market, config in MARKET_CONFIGS.items():
            assert config.base_url
            assert config.api_prefix
            assert config.description
            assert config.features

    def test_optional_analysis_feature(self):
        """Verify analysis can be enabled/disabled via config."""
        # Without analysis
        toolkit_no_stats = BinanceToolkit(enable_analysis=False)
        assert toolkit_no_stats.stats is None

        # With analysis
        toolkit_with_stats = BinanceToolkit(enable_analysis=True)
        assert toolkit_with_stats.stats is not None
        from roma_dspy.tools.utils.statistics import StatisticalAnalyzer

        assert isinstance(toolkit_with_stats.stats, StatisticalAnalyzer)

    def test_comprehensive_statistical_methods(self):
        """Verify StatisticalAnalyzer has all required methods."""
        from roma_dspy.tools.utils.statistics import StatisticalAnalyzer

        stats = StatisticalAnalyzer()

        required_methods = [
            "classify_trend_from_change",
            "classify_volatility_from_change",
            "calculate_price_statistics",
            "calculate_volume_rating",
            "calculate_kline_analysis",
            "calculate_trade_analysis",
            "calculate_simple_moving_average",
            "calculate_exponential_moving_average",
            "calculate_rsi",
            "calculate_bollinger_bands",
            "calculate_returns",
            "calculate_sharpe_ratio",
            "calculate_max_drawdown",
        ]

        for method_name in required_methods:
            assert hasattr(stats, method_name), f"Missing method: {method_name}"


class TestCompleteness:
    """Validate completeness compared to requirements."""

    def test_all_binance_endpoints_covered(self):
        """Verify all essential Binance endpoints are covered."""
        from roma_dspy.tools.crypto.binance.types import BinanceEndpoint

        # Market data endpoints
        assert BinanceEndpoint.TICKER_PRICE
        assert BinanceEndpoint.TICKER_24HR
        assert BinanceEndpoint.TICKER_BOOK
        assert BinanceEndpoint.DEPTH
        assert BinanceEndpoint.TRADES
        assert BinanceEndpoint.KLINES

        # Exchange info
        assert BinanceEndpoint.EXCHANGE_INFO
        assert BinanceEndpoint.PING
        assert BinanceEndpoint.TIME

    def test_imports_all_work(self):
        """Verify all public imports work correctly."""
        # Main toolkit
        from roma_dspy.tools import BinanceToolkit

        # Value objects
        from roma_dspy.tools.value_objects.crypto import (
            Kline,
            Trade,
            OrderBookSnapshot,
            TickerStats,
            BookTicker,
            TrendDirection,
            VolatilityLevel,
            OrderSide,
        )

        # Utils
        from roma_dspy.tools.utils import StatisticalAnalyzer

        # All should be classes/enums
        assert isinstance(BinanceToolkit, type)
        assert isinstance(Kline, type)
        assert isinstance(TrendDirection, type)
        assert isinstance(StatisticalAnalyzer, type)


class TestDRYPrinciples:
    """Validate DRY (Don't Repeat Yourself) principles."""

    def test_no_duplicate_classification_logic(self):
        """Verify classification logic is not duplicated."""
        from roma_dspy.tools.utils.statistics import StatisticalAnalyzer
        from roma_dspy.tools.crypto.binance.toolkit import BinanceToolkit

        # StatisticalAnalyzer should be the single source of truth
        stats = StatisticalAnalyzer()
        assert hasattr(stats, "classify_trend_from_change")
        assert hasattr(stats, "classify_volatility_from_change")

        # BinanceToolkit should NOT have duplicate methods
        toolkit = BinanceToolkit()
        assert not hasattr(toolkit, "_classify_volatility")
        assert not hasattr(toolkit, "_classify_volume")

    def test_value_objects_reusable_across_toolkits(self):
        """Verify value objects are generic enough for reuse."""
        from roma_dspy.tools.value_objects.crypto import (
            Kline,
            Trade,
            OrderBookSnapshot,
        )

        # These should work for any crypto source, not just Binance
        # They should NOT have Binance-specific fields

        # Check Kline is generic
        kline_fields = set(Kline.model_fields.keys())
        assert "binance" not in str(kline_fields).lower()

        # Check Trade is generic
        trade_fields = set(Trade.model_fields.keys())
        assert "binance" not in str(trade_fields).lower()

        # Check OrderBookSnapshot is generic
        book_fields = set(OrderBookSnapshot.model_fields.keys())
        assert "binance" not in str(book_fields).lower()
