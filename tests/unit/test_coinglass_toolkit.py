"""Tests for Coinglass toolkit."""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from roma_dspy.tools.crypto.coinglass import (
    CoinglassToolkit,
    CoinglassAPIClient,
    CoinglassAPIError,
    CoinglassInterval,
    CoinglassTimeRange,
)


@pytest.fixture
def mock_api_client():
    """Create mock API client."""
    client = AsyncMock(spec=CoinglassAPIClient)
    client.api_key = "test_api_key"
    return client


@pytest.fixture
def coinglass_toolkit(mock_api_client):
    """Create Coinglass toolkit with mocked client."""
    with patch(
        "roma_dspy.tools.crypto.coinglass.toolkit.CoinglassAPIClient",
        return_value=mock_api_client,
    ):
        toolkit = CoinglassToolkit(
            symbols=["BTC", "ETH"],
            default_symbol="BTC",
            api_key="test_api_key",
        )
        toolkit.client = mock_api_client
        return toolkit


class TestCoinglassToolkitInitialization:
    """Test toolkit initialization."""

    def test_initialization_with_symbols(self):
        """Test initialization with symbol restrictions."""
        with patch("roma_dspy.tools.crypto.coinglass.toolkit.CoinglassAPIClient"):
            toolkit = CoinglassToolkit(symbols=["BTC", "ETH", "sol"], default_symbol="ETH")

            assert toolkit.symbols == ["BTC", "ETH", "SOL"]  # Uppercase conversion
            assert toolkit.default_symbol == "ETH"
            assert toolkit.enabled is True

    def test_initialization_without_symbols(self):
        """Test initialization without symbol restrictions."""
        with patch("roma_dspy.tools.crypto.coinglass.toolkit.CoinglassAPIClient"):
            toolkit = CoinglassToolkit()

            assert toolkit.symbols is None
            assert toolkit.default_symbol == "BTC"

    def test_get_enabled_tools(self, coinglass_toolkit):
        """Test getting enabled tools."""
        tools = coinglass_toolkit.get_enabled_tools()

        expected_tools = [
            "get_funding_rates_weighted_by_oi",
            "get_funding_rates_per_exchange",
            "get_arbitrage_opportunities",
            "get_open_interest_by_exchange",
            "get_open_interest_history",
            "get_taker_buy_sell_volume",
            "get_liquidations_by_exchange",
        ]

        for tool_name in expected_tools:
            assert tool_name in tools
            assert callable(tools[tool_name])

    def test_tool_inclusion(self):
        """Test tool inclusion filtering."""
        with patch("roma_dspy.tools.crypto.coinglass.toolkit.CoinglassAPIClient"):
            toolkit = CoinglassToolkit(
                include_tools=["get_arbitrage_opportunities", "get_liquidations_by_exchange"]
            )

            tools = toolkit.get_enabled_tools()
            assert len(tools) == 2
            assert "get_arbitrage_opportunities" in tools
            assert "get_liquidations_by_exchange" in tools

    def test_tool_exclusion(self):
        """Test tool exclusion filtering."""
        with patch("roma_dspy.tools.crypto.coinglass.toolkit.CoinglassAPIClient"):
            toolkit = CoinglassToolkit(
                exclude_tools=["get_funding_rates_per_exchange", "get_open_interest_history"]
            )

            tools = toolkit.get_enabled_tools()
            assert "get_funding_rates_per_exchange" not in tools
            assert "get_open_interest_history" not in tools
            assert "get_arbitrage_opportunities" in tools


class TestSymbolValidation:
    """Test symbol validation."""

    def test_validate_symbol_allowed(self, coinglass_toolkit):
        """Test validation of allowed symbol."""
        result = coinglass_toolkit._validate_symbol("btc")
        assert result == "BTC"

        result = coinglass_toolkit._validate_symbol("ETH")
        assert result == "ETH"

    def test_validate_symbol_not_allowed(self, coinglass_toolkit):
        """Test validation of disallowed symbol."""
        with pytest.raises(ValueError, match="not in allowed symbols"):
            coinglass_toolkit._validate_symbol("SOL")

    def test_validate_symbol_no_restrictions(self):
        """Test validation with no symbol restrictions."""
        with patch("roma_dspy.tools.crypto.coinglass.toolkit.CoinglassAPIClient"):
            toolkit = CoinglassToolkit()  # No symbol restrictions

            result = toolkit._validate_symbol("DOGE")
            assert result == "DOGE"


class TestFundingRateTools:
    """Test funding rate related tools."""

    @pytest.mark.asyncio
    async def test_get_funding_rates_weighted_by_oi_success(self, coinglass_toolkit):
        """Test successful funding rates weighted by OI retrieval."""
        mock_data = {
            "code": "0",
            "data": [
                {"time": 1640000000000, "open": 0.0001, "high": 0.0002, "low": 0.0001, "close": 0.00015}
            ],
        }
        coinglass_toolkit.client.get_funding_rates_weighted_by_oi.return_value = mock_data

        result = await coinglass_toolkit.get_funding_rates_weighted_by_oi(
            symbol="BTC", interval="8h", limit=100
        )

        assert result["success"] is True
        assert result["symbol"] == "BTC"
        assert result["interval"] == "8h"
        assert result["limit"] == 100
        assert result["data_points"] == 1
        coinglass_toolkit.client.get_funding_rates_weighted_by_oi.assert_called_once_with(
            symbol="BTC",
            start_time=None,
            end_time=None,
            interval=CoinglassInterval.EIGHT_HOURS,
            limit=100,
        )

    @pytest.mark.asyncio
    async def test_get_funding_rates_weighted_by_oi_invalid_interval(self, coinglass_toolkit):
        """Test funding rates with invalid interval."""
        result = await coinglass_toolkit.get_funding_rates_weighted_by_oi(
            symbol="BTC", interval="invalid"
        )

        assert result["success"] is False
        assert "Invalid interval" in result["error"]

    @pytest.mark.asyncio
    async def test_get_funding_rates_weighted_by_oi_invalid_symbol(self, coinglass_toolkit):
        """Test funding rates with invalid symbol."""
        result = await coinglass_toolkit.get_funding_rates_weighted_by_oi(symbol="SOL")

        assert result["success"] is False
        assert "not in allowed symbols" in result["error"]

    @pytest.mark.asyncio
    async def test_get_funding_rates_per_exchange_success(self, coinglass_toolkit):
        """Test successful funding rates per exchange retrieval."""
        mock_data = {
            "code": "0",
            "data": [
                {
                    "symbol": "BTC",
                    "stablecoin_margin_list": [
                        {
                            "exchange": "Binance",
                            "funding_rate": 0.0001,
                            "funding_rate_interval": 8,
                            "next_funding_time": 1640000000000,
                        }
                    ],
                    "token_margin_list": [],
                }
            ],
        }
        coinglass_toolkit.client.get_funding_rates_per_exchange.return_value = mock_data

        result = await coinglass_toolkit.get_funding_rates_per_exchange()

        assert result["success"] is True
        assert result["symbols_count"] == 1
        coinglass_toolkit.client.get_funding_rates_per_exchange.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_arbitrage_opportunities_success(self, coinglass_toolkit):
        """Test successful arbitrage opportunities retrieval."""
        mock_data = {
            "code": "0",
            "data": [
                {
                    "symbol": "BTC",
                    "buy": {
                        "exchange": "Binance",
                        "open_interest_usd": 1000000,
                        "funding_rate": 0.0001,
                        "funding_rate_interval": 8,
                    },
                    "sell": {
                        "exchange": "Bybit",
                        "open_interest_usd": 900000,
                        "funding_rate": -0.0001,
                        "funding_rate_interval": 8,
                    },
                    "apr": 2.19,
                    "funding": 0.0002,
                    "fee": 0.0004,
                    "spread": 0.5,
                    "next_funding_time": 1640000000000,
                }
            ],
        }
        coinglass_toolkit.client.get_arbitrage_opportunities.return_value = mock_data

        result = await coinglass_toolkit.get_arbitrage_opportunities()

        assert result["success"] is True
        assert result["opportunities_count"] == 1
        coinglass_toolkit.client.get_arbitrage_opportunities.assert_called_once()


class TestOpenInterestTools:
    """Test open interest related tools."""

    @pytest.mark.asyncio
    async def test_get_open_interest_by_exchange_success(self, coinglass_toolkit):
        """Test successful open interest by exchange retrieval."""
        mock_data = {
            "code": "0",
            "data": [
                {"exchange": "Binance", "open_interest_usd": 5000000, "percentage": 25.5},
                {"exchange": "Bybit", "open_interest_usd": 3000000, "percentage": 15.3},
            ],
        }
        coinglass_toolkit.client.get_open_interest_exchange_list.return_value = mock_data

        result = await coinglass_toolkit.get_open_interest_by_exchange(symbol="ETH")

        assert result["success"] is True
        assert result["symbol"] == "ETH"
        assert result["exchanges_count"] == 2
        coinglass_toolkit.client.get_open_interest_exchange_list.assert_called_once_with(
            symbol="ETH"
        )

    @pytest.mark.asyncio
    async def test_get_open_interest_history_success(self, coinglass_toolkit):
        """Test successful open interest history retrieval."""
        mock_data = {"code": "0", "data": [{"time": 1640000000000, "value": 5000000}]}
        coinglass_toolkit.client.get_open_interest_history_chart.return_value = mock_data

        result = await coinglass_toolkit.get_open_interest_history(symbol="BTC", time_range="1h")

        assert result["success"] is True
        assert result["symbol"] == "BTC"
        assert result["time_range"] == "1h"
        assert result["data_points"] == 1
        coinglass_toolkit.client.get_open_interest_history_chart.assert_called_once_with(
            symbol="BTC", time_range=CoinglassTimeRange.ONE_HOUR
        )

    @pytest.mark.asyncio
    async def test_get_open_interest_history_invalid_range(self, coinglass_toolkit):
        """Test open interest history with invalid time range."""
        result = await coinglass_toolkit.get_open_interest_history(
            symbol="BTC", time_range="invalid"
        )

        assert result["success"] is False
        assert "Invalid time_range" in result["error"]


class TestLongShortTools:
    """Test long/short ratio and liquidation tools."""

    @pytest.mark.asyncio
    async def test_get_taker_buy_sell_volume_success(self, coinglass_toolkit):
        """Test successful taker buy/sell volume retrieval."""
        mock_data = {
            "code": "0",
            "data": {
                "symbol": "BTC",
                "buy_ratio": 55.3,
                "sell_ratio": 44.7,
                "buy_vol_usd": 100000000,
                "sell_vol_usd": 80000000,
                "exchange_list": [
                    {
                        "exchange": "Binance",
                        "buy_ratio": 60.0,
                        "sell_ratio": 40.0,
                        "buy_vol_usd": 50000000,
                        "sell_vol_usd": 30000000,
                    }
                ],
            },
        }
        coinglass_toolkit.client.get_taker_buy_sell_volume.return_value = mock_data

        result = await coinglass_toolkit.get_taker_buy_sell_volume(symbol="BTC", time_range="1h")

        assert result["success"] is True
        assert result["symbol"] == "BTC"
        assert result["time_range"] == "1h"
        coinglass_toolkit.client.get_taker_buy_sell_volume.assert_called_once_with(
            symbol="BTC", range_param=CoinglassTimeRange.ONE_HOUR
        )

    @pytest.mark.asyncio
    async def test_get_liquidations_by_exchange_success(self, coinglass_toolkit):
        """Test successful liquidations by exchange retrieval."""
        mock_data = {
            "code": "0",
            "data": [
                {
                    "exchange": "All",
                    "liquidation_usd": 10000000,
                    "longLiquidation_usd": 6000000,
                    "shortLiquidation_usd": 4000000,
                },
                {
                    "exchange": "Binance",
                    "liquidation_usd": 5000000,
                    "longLiquidation_usd": 3000000,
                    "shortLiquidation_usd": 2000000,
                },
            ],
        }
        coinglass_toolkit.client.get_liquidations_by_exchange.return_value = mock_data

        result = await coinglass_toolkit.get_liquidations_by_exchange(
            symbol="ETH", time_range="4h"
        )

        assert result["success"] is True
        assert result["symbol"] == "ETH"
        assert result["time_range"] == "4h"
        assert result["exchanges_count"] == 2
        coinglass_toolkit.client.get_liquidations_by_exchange.assert_called_once_with(
            symbol="ETH", range_param=CoinglassTimeRange.FOUR_HOURS
        )

    @pytest.mark.asyncio
    async def test_get_liquidations_by_exchange_invalid_range(self, coinglass_toolkit):
        """Test liquidations with invalid time range."""
        result = await coinglass_toolkit.get_liquidations_by_exchange(
            symbol="BTC", time_range="99h"
        )

        assert result["success"] is False
        assert "Invalid time_range" in result["error"]


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_api_error_handling(self, coinglass_toolkit):
        """Test handling of API errors."""
        coinglass_toolkit.client.get_arbitrage_opportunities.side_effect = CoinglassAPIError(
            "API Error", status_code=500
        )

        result = await coinglass_toolkit.get_arbitrage_opportunities()

        assert result["success"] is False
        assert "API Error" in result["error"]
        assert result["error_type"] == "CoinglassAPIError"

    @pytest.mark.asyncio
    async def test_value_error_handling(self, coinglass_toolkit):
        """Test handling of value errors."""
        result = await coinglass_toolkit.get_open_interest_by_exchange(symbol="INVALID")

        assert result["success"] is False
        assert "not in allowed symbols" in result["error"]


class TestAsyncContextManager:
    """Test async context manager."""

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_api_client):
        """Test toolkit as async context manager."""
        with patch(
            "roma_dspy.tools.crypto.coinglass.toolkit.CoinglassAPIClient",
            return_value=mock_api_client,
        ):
            async with CoinglassToolkit() as toolkit:
                assert toolkit is not None
                assert isinstance(toolkit, CoinglassToolkit)

            mock_api_client.close.assert_called_once()