"""Unit tests for DefiLlama toolkit."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from roma_dspy.tools.crypto.defillama import DefiLlamaToolkit, DefiLlamaAPIError


class TestDefiLlamaToolkit:
    """Unit tests for DefiLlama toolkit."""

    def test_initialization_defaults(self):
        """Test toolkit initialization with default parameters."""
        toolkit = DefiLlamaToolkit()

        assert toolkit.enabled is True
        assert toolkit.default_chain == "ethereum"
        assert toolkit.enable_analysis is True
        assert toolkit.enable_pro_features is False
        assert toolkit.stats is not None

    def test_initialization_custom_params(self):
        """Test toolkit initialization with custom parameters."""
        toolkit = DefiLlamaToolkit(
            default_chain="polygon",
            enable_analysis=False,
            api_key="test_key",
            enable_pro_features=True,
        )

        assert toolkit.default_chain == "polygon"
        assert toolkit.enable_analysis is False
        assert toolkit.enable_pro_features is True
        assert toolkit.stats is None  # Should be None when analysis disabled

    def test_tool_availability_free_api(self):
        """Test tool availability without Pro API key."""
        toolkit = DefiLlamaToolkit()

        # Free API tools should be available
        assert toolkit._is_tool_available("get_protocols")
        assert toolkit._is_tool_available("get_protocol_tvl")
        assert toolkit._is_tool_available("get_chains")

        # Pro API tools should not be available
        assert not toolkit._is_tool_available("get_yield_pools")
        assert not toolkit._is_tool_available("get_active_users")

    def test_tool_availability_pro_api(self):
        """Test tool availability with Pro API key."""
        toolkit = DefiLlamaToolkit(api_key="test_key", enable_pro_features=True)

        # All tools should be available
        assert toolkit._is_tool_available("get_protocols")
        assert toolkit._is_tool_available("get_yield_pools")
        assert toolkit._is_tool_available("get_active_users")

    def test_validate_chain_success(self):
        """Test successful chain validation."""
        toolkit = DefiLlamaToolkit()

        assert toolkit._validate_chain("ethereum") == "ethereum"
        assert toolkit._validate_chain("ETHEREUM") == "ethereum"
        assert toolkit._validate_chain("  polygon  ") == "polygon"

    def test_validate_chain_failure(self):
        """Test chain validation with invalid inputs."""
        toolkit = DefiLlamaToolkit()

        with pytest.raises(ValueError, match="Chain cannot be empty"):
            toolkit._validate_chain("")

        with pytest.raises(ValueError, match="Invalid chain format"):
            toolkit._validate_chain("eth/ereum")

        with pytest.raises(ValueError, match="Invalid chain format"):
            toolkit._validate_chain("eth ereum")

    def test_validate_protocol_success(self):
        """Test successful protocol validation."""
        toolkit = DefiLlamaToolkit()

        assert toolkit._validate_protocol("aave") == "aave"
        assert toolkit._validate_protocol("AAVE") == "aave"
        assert toolkit._validate_protocol("  uniswap-v3  ") == "uniswap-v3"

    def test_validate_protocol_failure(self):
        """Test protocol validation with invalid inputs."""
        toolkit = DefiLlamaToolkit()

        with pytest.raises(ValueError, match="Protocol cannot be empty"):
            toolkit._validate_protocol("")

        with pytest.raises(ValueError, match="Invalid protocol format"):
            toolkit._validate_protocol("aave/v2")

        with pytest.raises(ValueError, match="Invalid protocol format"):
            toolkit._validate_protocol("aave v2")

    def test_get_enabled_tools(self):
        """Test getting enabled tools."""
        toolkit = DefiLlamaToolkit()
        enabled_tools = toolkit.get_enabled_tools()

        assert isinstance(enabled_tools, dict)
        assert len(enabled_tools) > 0
        assert "get_protocols" in enabled_tools
        assert callable(enabled_tools["get_protocols"])

    def test_get_tool_metadata(self):
        """Test getting tool metadata."""
        toolkit = DefiLlamaToolkit()
        metadata = toolkit.get_tool_metadata("get_protocols")

        assert metadata is not None
        assert metadata["name"] == "get_protocols"
        assert "description" in metadata
        assert len(metadata["description"]) > 0

    def test_toolkit_disabled(self):
        """Test toolkit when disabled."""
        toolkit = DefiLlamaToolkit(enabled=False)
        enabled_tools = toolkit.get_enabled_tools()

        assert len(enabled_tools) == 0

    def test_include_tools(self):
        """Test selective tool inclusion."""
        toolkit = DefiLlamaToolkit(include_tools=["get_protocols", "get_protocol_tvl"])
        enabled_tools = toolkit.get_enabled_tools()

        assert "get_protocols" in enabled_tools
        assert "get_protocol_tvl" in enabled_tools
        assert "get_chains" not in enabled_tools

    def test_exclude_tools(self):
        """Test selective tool exclusion."""
        toolkit = DefiLlamaToolkit(exclude_tools=["get_chains", "get_protocol_detail"])
        enabled_tools = toolkit.get_enabled_tools()

        assert "get_protocols" in enabled_tools
        assert "get_chains" not in enabled_tools
        assert "get_protocol_detail" not in enabled_tools

    @pytest.mark.asyncio
    async def test_error_response_format(self):
        """Test error response format."""
        with patch(
            "src.roma_dspy.tools.crypto.defillama.toolkit.DefiLlamaAPIClient"
        ) as mock_client:
            mock_instance = MagicMock()
            mock_instance.get_protocols = AsyncMock(
                side_effect=DefiLlamaAPIError("API Error")
            )
            mock_client.return_value = mock_instance

            toolkit = DefiLlamaToolkit()
            result = await toolkit.get_protocols()

            assert result["success"] is False
            assert "error" in result
            assert "error_type" in result
            assert result["error_type"] == "DefiLlamaAPIError"
            assert "toolkit" in result
            assert result["toolkit"] == "DefiLlamaToolkit"
            assert "tool" in result
            assert result["tool"] == "get_protocols"
            assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_success_response_format(self):
        """Test success response format."""
        with patch(
            "src.roma_dspy.tools.crypto.defillama.toolkit.DefiLlamaAPIClient"
        ) as mock_client:
            mock_instance = MagicMock()
            mock_instance.get_protocols = AsyncMock(
                return_value=[{"id": "aave", "name": "Aave", "tvl": 5000000000}]
            )
            mock_client.return_value = mock_instance

            toolkit = DefiLlamaToolkit()
            result = await toolkit.get_protocols()

            assert result["success"] is True
            assert "toolkit" in result
            assert result["toolkit"] == "DefiLlamaToolkit"
            assert "tool" in result
            assert result["tool"] == "get_protocols"
            assert "timestamp" in result
            assert "count" in result

    def test_toolkit_repr(self):
        """Test toolkit string representation."""
        toolkit = DefiLlamaToolkit()
        repr_str = repr(toolkit)

        assert "DefiLlamaToolkit" in repr_str
        assert "enabled=True" in repr_str

    @pytest.mark.asyncio
    async def test_aclose(self):
        """Test toolkit cleanup."""
        with patch(
            "src.roma_dspy.tools.crypto.defillama.toolkit.DefiLlamaAPIClient"
        ) as mock_client:
            mock_instance = MagicMock()
            mock_instance.close = AsyncMock()
            mock_client.return_value = mock_instance

            toolkit = DefiLlamaToolkit()
            await toolkit.aclose()

            mock_instance.close.assert_called_once()

    def test_storage_config(self):
        """Test storage threshold configuration."""
        toolkit = DefiLlamaToolkit(storage_threshold_kb=500)

        # Storage threshold should be passed to config
        assert "storage_threshold_kb" in toolkit.config
        assert toolkit.config["storage_threshold_kb"] == 500

    @pytest.mark.asyncio
    async def test_protocol_tvl_formatting_billions(self):
        """Test TVL formatting for billions."""
        with patch(
            "src.roma_dspy.tools.crypto.defillama.toolkit.DefiLlamaAPIClient"
        ) as mock_client:
            mock_instance = MagicMock()
            mock_instance.get_protocol_tvl = AsyncMock(return_value=5234567890)
            mock_client.return_value = mock_instance

            toolkit = DefiLlamaToolkit()
            result = await toolkit.get_protocol_tvl("aave")

            assert result["success"] is True
            assert "$5.23B" in result["data"]["tvl_formatted"]

    @pytest.mark.asyncio
    async def test_protocol_tvl_formatting_millions(self):
        """Test TVL formatting for millions."""
        with patch(
            "src.roma_dspy.tools.crypto.defillama.toolkit.DefiLlamaAPIClient"
        ) as mock_client:
            mock_instance = MagicMock()
            mock_instance.get_protocol_tvl = AsyncMock(return_value=123456789)
            mock_client.return_value = mock_instance

            toolkit = DefiLlamaToolkit()
            result = await toolkit.get_protocol_tvl("aave")

            assert result["success"] is True
            assert "$123.46M" in result["data"]["tvl_formatted"]

    @pytest.mark.asyncio
    async def test_analysis_generation_with_empty_data(self):
        """Test analysis generation with empty data."""
        with patch(
            "src.roma_dspy.tools.crypto.defillama.toolkit.DefiLlamaAPIClient"
        ) as mock_client:
            mock_instance = MagicMock()
            mock_instance.get_protocols = AsyncMock(return_value=[])
            mock_client.return_value = mock_instance

            toolkit = DefiLlamaToolkit(enable_analysis=True)
            result = await toolkit.get_protocols()

            assert result["success"] is True
            # Should not have analysis with empty data
            assert "analysis" not in result or not result.get("analysis")

    @pytest.mark.asyncio
    async def test_invalid_response_type(self):
        """Test handling of invalid API response types."""
        with patch(
            "src.roma_dspy.tools.crypto.defillama.toolkit.DefiLlamaAPIClient"
        ) as mock_client:
            mock_instance = MagicMock()
            mock_instance.get_protocols = AsyncMock(
                return_value="invalid"
            )  # Should be list
            mock_client.return_value = mock_instance

            toolkit = DefiLlamaToolkit()
            result = await toolkit.get_protocols()

            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_yield_pool_id_validation(self):
        """Test yield chart pool ID validation."""
        with patch(
            "src.roma_dspy.tools.crypto.defillama.toolkit.DefiLlamaAPIClient"
        ) as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance

            toolkit = DefiLlamaToolkit(api_key="test_key", enable_pro_features=True)

            # Empty pool_id should fail
            result = await toolkit.get_yield_chart("")
            assert result["success"] is False
            assert "error" in result

    @pytest.mark.asyncio
    async def test_historical_liquidity_token_validation(self):
        """Test historical liquidity token validation."""
        with patch(
            "src.roma_dspy.tools.crypto.defillama.toolkit.DefiLlamaAPIClient"
        ) as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value = mock_instance

            toolkit = DefiLlamaToolkit(api_key="test_key", enable_pro_features=True)

            # Token too short should fail
            result = await toolkit.get_historical_liquidity("u")
            assert result["success"] is False
            assert "error" in result


def test_client_initialization():
    """Test that client is properly initialized."""
    toolkit = DefiLlamaToolkit()
    assert toolkit.client is not None
    assert hasattr(toolkit.client, "get_protocols")
    assert hasattr(toolkit.client, "get_protocol_tvl")


def test_stats_analyzer_initialization():
    """Test that stats analyzer is properly initialized."""
    toolkit_with_analysis = DefiLlamaToolkit(enable_analysis=True)
    assert toolkit_with_analysis.stats is not None

    toolkit_without_analysis = DefiLlamaToolkit(enable_analysis=False)
    assert toolkit_without_analysis.stats is None
