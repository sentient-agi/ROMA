"""Integration tests for CoinGecko toolkit."""

import pytest

from roma_dspy.tools.crypto.coingecko import CoinGeckoToolkit
from roma_dspy.tools.utils.statistics import StatisticalAnalyzer
from roma_dspy.tools.value_objects.crypto import (
    TrendDirection,
    VolatilityLevel,
)


class TestCoinGeckoToolkitIntegration:
    """Test CoinGecko toolkit integration."""

    def test_toolkit_initialization_with_analysis(self):
        """Test toolkit initialization with analysis enabled."""
        toolkit = CoinGeckoToolkit(
            coins=["bitcoin", "ethereum"],
            default_vs_currency="usd",
            enable_analysis=True,
        )

        assert toolkit.enable_analysis is True
        assert toolkit.stats is not None
        assert isinstance(toolkit.stats, StatisticalAnalyzer)
        assert toolkit.default_vs_currency == "usd"
        assert toolkit.coins == ["bitcoin", "ethereum"]

    def test_toolkit_initialization_without_analysis(self):
        """Test toolkit initialization without analysis."""
        toolkit = CoinGeckoToolkit(
            coins=["bitcoin"],
            default_vs_currency="usd",
            enable_analysis=False,
        )

        assert toolkit.enable_analysis is False
        assert toolkit.stats is None

    def test_toolkit_has_all_required_methods(self):
        """Verify all 8 required tools are present."""
        toolkit = CoinGeckoToolkit()

        required_methods = [
            "get_coin_price",
            "get_coin_info",
            "get_coin_market_chart",
            "get_coins_markets",
            "get_coin_ohlc",
            "search_coins_exchanges_categories",
            "get_global_crypto_data",
            "get_token_price_by_contract",
        ]

        for method_name in required_methods:
            assert hasattr(toolkit, method_name), f"Missing method: {method_name}"
            method = getattr(toolkit, method_name)
            assert callable(method), f"Method not callable: {method_name}"

    def test_context_manager_support(self):
        """Verify async context manager support."""
        toolkit = CoinGeckoToolkit()

        assert hasattr(toolkit, "__aenter__")
        assert hasattr(toolkit, "__aexit__")
        assert hasattr(toolkit, "aclose")

    def test_stats_integration(self):
        """Test StatisticalAnalyzer integration."""
        toolkit = CoinGeckoToolkit(enable_analysis=True)

        assert toolkit.stats is not None
        assert hasattr(toolkit.stats, "classify_trend_from_change")
        assert hasattr(toolkit.stats, "classify_volatility_from_change")

    def test_coin_filtering(self):
        """Test coin allowlist filtering."""
        toolkit = CoinGeckoToolkit(coins=["bitcoin", "ethereum"])

        assert toolkit.coins == ["bitcoin", "ethereum"]

    def test_default_vs_currency(self):
        """Test default vs_currency configuration."""
        toolkit_usd = CoinGeckoToolkit(default_vs_currency="usd")
        assert toolkit_usd.default_vs_currency == "usd"

        toolkit_btc = CoinGeckoToolkit(default_vs_currency="BTC")
        assert toolkit_btc.default_vs_currency == "btc"  # Normalized to lowercase

    def test_api_client_initialization(self):
        """Test API client is properly initialized."""
        toolkit = CoinGeckoToolkit()

        assert toolkit.client is not None
        assert hasattr(toolkit.client, "get_simple_price")
        assert hasattr(toolkit.client, "get_coin_info")
        assert hasattr(toolkit.client, "get_market_chart")

    def test_pro_api_configuration(self):
        """Test Pro API configuration."""
        toolkit = CoinGeckoToolkit(api_key="test_key", use_pro=True)

        assert toolkit.client.api_key == "test_key"
        assert toolkit.client.use_pro is True

    def test_public_api_configuration(self):
        """Test public API configuration."""
        toolkit = CoinGeckoToolkit()

        assert toolkit.client.api_key is None
        assert toolkit.client.use_pro is False

    def test_generic_value_objects_usage(self):
        """Verify toolkit uses generic crypto value objects."""
        # CoinGecko should use the same value objects as Binance
        from roma_dspy.tools.value_objects.crypto import (
            PricePoint,
            AssetIdentifier,
            TrendDirection,
            VolatilityLevel,
        )

        # These should be generic types, not CoinGecko-specific
        assert TrendDirection.BULLISH
        assert VolatilityLevel.HIGH
        assert PricePoint
        assert AssetIdentifier

    def test_statistical_analyzer_returns_base_enums(self):
        """Verify StatisticalAnalyzer returns base crypto enums."""
        toolkit = CoinGeckoToolkit(enable_analysis=True)

        trend = toolkit.stats.classify_trend_from_change(2.5)
        volatility = toolkit.stats.classify_volatility_from_change(3.0)

        assert isinstance(trend, TrendDirection)
        assert isinstance(volatility, VolatilityLevel)

        # Should be base enum types
        assert (
            type(trend).__module__ == "src.roma_dspy.tools.value_objects.crypto.trading"
        )
        assert (
            type(volatility).__module__
            == "src.roma_dspy.tools.value_objects.crypto.trading"
        )

    def test_no_duplicate_classification_logic(self):
        """Verify classification logic is not duplicated."""
        toolkit = CoinGeckoToolkit(enable_analysis=True)

        # CoinGeckoToolkit should NOT have duplicate methods
        assert not hasattr(toolkit, "_classify_trend")
        assert not hasattr(toolkit, "_classify_volatility")

        # Should use StatisticalAnalyzer
        assert hasattr(toolkit.stats, "classify_trend_from_change")
        assert hasattr(toolkit.stats, "classify_volatility_from_change")

    def test_imports_work(self):
        """Test all imports work correctly."""
        from roma_dspy.tools import CoinGeckoToolkit
        from roma_dspy.tools.crypto import CoinGeckoToolkit as CoinGeckoToolkit2
        from roma_dspy.tools.crypto.coingecko import (
            CoinGeckoToolkit as CoinGeckoToolkit3,
        )

        # All should be the same class
        assert CoinGeckoToolkit is CoinGeckoToolkit2
        assert CoinGeckoToolkit2 is CoinGeckoToolkit3

    def test_coingecko_endpoints_defined(self):
        """Test CoinGecko endpoints are properly defined."""
        from roma_dspy.tools.crypto.coingecko.types import CoinGeckoEndpoint

        # Market data endpoints
        assert CoinGeckoEndpoint.SIMPLE_PRICE
        assert CoinGeckoEndpoint.TOKEN_PRICE
        assert CoinGeckoEndpoint.COIN_INFO
        assert CoinGeckoEndpoint.MARKET_CHART
        assert CoinGeckoEndpoint.MARKET_CHART_RANGE
        assert CoinGeckoEndpoint.COIN_OHLC
        assert CoinGeckoEndpoint.COINS_MARKETS
        assert CoinGeckoEndpoint.COINS_LIST
        assert CoinGeckoEndpoint.SEARCH
        assert CoinGeckoEndpoint.GLOBAL_DATA
