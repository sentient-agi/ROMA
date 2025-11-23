"""Integration tests for DefiLlama toolkit."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from roma_dspy.tools.crypto.defillama import DefiLlamaToolkit
from roma_dspy.core.storage import FileStorage


class TestDefiLlamaIntegration:
    """Test DefiLlama toolkit integration."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def execution_id(self):
        """Test execution ID."""
        return "test_defillama_20251001"

    @pytest.fixture
    def mock_client(self):
        """Mock DefiLlama API client."""
        with patch(
            "src.roma_dspy.tools.crypto.defillama.toolkit.DefiLlamaAPIClient"
        ) as mock:
            client_instance = MagicMock()
            mock.return_value = client_instance
            yield client_instance

    def test_toolkit_initialization(self):
        """Test DefiLlama toolkit initialization."""
        toolkit = DefiLlamaToolkit(
            default_chain="ethereum",
            enable_analysis=True,
        )

        assert toolkit.default_chain == "ethereum"
        assert toolkit.enable_analysis is True
        assert toolkit.stats is not None
        assert toolkit.client is not None

    def test_toolkit_with_storage(self, temp_dir, execution_id):
        """Test toolkit with storage integration."""
        storage = FileStorage(execution_id=execution_id, base_dir=temp_dir)
        toolkit = DefiLlamaToolkit(
            file_storage=storage,
            enable_analysis=True,
        )

        assert toolkit._data_storage is not None
        assert toolkit._data_storage.toolkit_name == "defillama"

    @pytest.mark.asyncio
    async def test_get_protocols_with_analysis(self, mock_client):
        """Test get_protocols with analysis generation."""
        # Mock API response
        mock_protocols = [
            {
                "id": "aave",
                "name": "Aave",
                "tvl": 5000000000,
                "category": "Lending",
                "chains": ["ethereum"],
            },
            {
                "id": "uniswap",
                "name": "Uniswap",
                "tvl": 3000000000,
                "category": "DEX",
                "chains": ["ethereum", "polygon"],
            },
            {
                "id": "compound",
                "name": "Compound",
                "tvl": 2000000000,
                "category": "Lending",
                "chains": ["ethereum"],
            },
        ]
        mock_client.get_protocols = AsyncMock(return_value=mock_protocols)

        toolkit = DefiLlamaToolkit(enable_analysis=True)
        toolkit.client = mock_client

        result = await toolkit.get_protocols()

        assert result["success"] is True
        assert result["count"] == 3
        assert "analysis" in result
        assert "ecosystem_overview" in result["analysis"]
        assert result["analysis"]["ecosystem_overview"]["total_protocols"] == 3
        assert result["analysis"]["ecosystem_overview"]["total_tvl"] == 10000000000
        assert "category_breakdown" in result["analysis"]
        assert result["analysis"]["category_breakdown"]["Lending"] == 2
        assert "chain_adoption" in result["analysis"]
        assert "market_insights" in result["analysis"]

    @pytest.mark.asyncio
    async def test_get_protocol_fees_with_analysis(self, mock_client):
        """Test get_protocol_fees with analysis generation."""
        # Mock API response with historical data
        mock_fees = {
            "id": "uniswap",
            "name": "Uniswap",
            "total24h": 5000000,
            "total7d": 35000000,
            "totalAllTime": 2000000000,
            "change_1d": 5.5,
            "totalDataChart": [
                [1696118400, 4500000],
                [1696204800, 4700000],
                [1696291200, 5000000],
            ],
        }
        mock_client.get_protocol_fees = AsyncMock(return_value=mock_fees)

        toolkit = DefiLlamaToolkit(enable_analysis=True)
        toolkit.client = mock_client

        result = await toolkit.get_protocol_fees("uniswap")

        assert result["success"] is True
        assert "analysis" in result
        assert "financial_metrics" in result["analysis"]
        assert result["analysis"]["financial_metrics"]["daily_fees_24h"] == 5000000
        assert (
            result["analysis"]["financial_metrics"]["fee_sustainability_score"]
            == "high"
        )
        assert "trend_analysis" in result["analysis"]
        assert "revenue_insights" in result["analysis"]

    @pytest.mark.asyncio
    async def test_get_yield_pools_with_analysis(self, mock_client):
        """Test get_yield_pools with analysis generation."""
        # Mock API response
        mock_pools = {
            "data": [
                {"pool": "pool1", "chain": "ethereum", "project": "aave", "apy": 8.5},
                {"pool": "pool2", "chain": "polygon", "project": "aave", "apy": 25.3},
                {
                    "pool": "pool3",
                    "chain": "arbitrum",
                    "project": "compound",
                    "apy": 4.2,
                },
                {
                    "pool": "pool4",
                    "chain": "ethereum",
                    "project": "uniswap",
                    "apy": 12.7,
                },
            ]
        }
        mock_client.get_yield_pools = AsyncMock(return_value=mock_pools)

        toolkit = DefiLlamaToolkit(
            api_key="test_key", enable_pro_features=True, enable_analysis=True
        )
        toolkit.client = mock_client

        result = await toolkit.get_yield_pools()

        assert result["success"] is True
        assert "analysis" in result
        assert "yield_landscape" in result["analysis"]
        assert result["analysis"]["yield_landscape"]["total_pools"] == 4
        assert "opportunity_segments" in result["analysis"]
        assert "ecosystem_diversity" in result["analysis"]
        assert result["analysis"]["ecosystem_diversity"]["active_chains"] == 3
        assert result["analysis"]["ecosystem_diversity"]["active_protocols"] == 3

    @pytest.mark.asyncio
    async def test_get_chain_historical_tvl_with_analysis(self, mock_client):
        """Test get_chain_historical_tvl with analysis generation."""
        # Mock API response with 100 data points
        mock_historical = []
        base_tvl = 50000000000
        for i in range(100):
            # Simulate growth trend
            tvl = base_tvl * (1 + i * 0.01)
            mock_historical.append([1696118400 + i * 86400, tvl])

        mock_client.get_chain_historical_tvl = AsyncMock(return_value=mock_historical)

        toolkit = DefiLlamaToolkit(enable_analysis=True)
        toolkit.client = mock_client

        result = await toolkit.get_chain_historical_tvl("ethereum")

        assert result["success"] is True
        assert "analysis" in result
        assert "tvl_metrics" in result["analysis"]
        assert "growth_metrics" in result["analysis"]
        assert "health_indicators" in result["analysis"]
        assert result["analysis"]["health_indicators"]["health_status"] in [
            "growing",
            "declining",
            "stable",
        ]

    @pytest.mark.asyncio
    async def test_storage_integration(self, temp_dir, execution_id, mock_client):
        """Test automatic Parquet storage for large responses."""
        # Create large mock data that exceeds threshold
        large_protocols = [
            {
                "id": f"protocol{i}",
                "name": f"Protocol {i}",
                "tvl": 1000000000 + i * 1000000,
                "category": "Lending",
                "chains": ["ethereum"],
            }
            for i in range(1000)  # Large dataset
        ]
        mock_client.get_protocols = AsyncMock(return_value=large_protocols)

        storage = FileStorage(execution_id=execution_id, base_dir=temp_dir)
        toolkit = DefiLlamaToolkit(
            file_storage=storage,
            enable_analysis=True,
            storage_threshold_kb=1,  # Low threshold to trigger storage
        )
        toolkit.client = mock_client

        result = await toolkit.get_protocols()

        assert result["success"] is True
        # Data should be stored due to size
        if "stored" in result:
            assert result["stored"] is True
            assert "file_path" in result
            assert "message" in result
            # Verify file exists
            file_path = Path(result["file_path"])
            assert file_path.exists()

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_client):
        """Test error handling in toolkit methods."""
        mock_client.get_protocols = AsyncMock(side_effect=Exception("API Error"))

        toolkit = DefiLlamaToolkit(enable_analysis=True)
        toolkit.client = mock_client

        result = await toolkit.get_protocols()

        assert result["success"] is False
        assert "error" in result
        assert "toolkit" in result
        assert result["toolkit"] == "DefiLlamaToolkit"

    @pytest.mark.asyncio
    async def test_protocol_validation(self, mock_client):
        """Test protocol validation."""
        toolkit = DefiLlamaToolkit()
        toolkit.client = mock_client

        # Test invalid protocol format
        result = await toolkit.get_protocol_tvl("invalid protocol name")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_chain_validation(self, mock_client):
        """Test chain validation."""
        toolkit = DefiLlamaToolkit()
        toolkit.client = mock_client

        # Test invalid chain format
        result = await toolkit.get_chain_fees("invalid/chain")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.asyncio
    async def test_pro_api_availability(self):
        """Test Pro API tool availability based on configuration."""
        # Without API key - Pro tools should not be available
        toolkit_free = DefiLlamaToolkit(enable_analysis=True)
        assert not toolkit_free._is_tool_available("get_yield_pools")
        assert not toolkit_free._is_tool_available("get_active_users")

        # With API key - Pro tools should be available
        toolkit_pro = DefiLlamaToolkit(
            api_key="test_key", enable_pro_features=True, enable_analysis=True
        )
        assert toolkit_pro._is_tool_available("get_yield_pools")
        assert toolkit_pro._is_tool_available("get_active_users")

        # Free tools should always be available
        assert toolkit_free._is_tool_available("get_protocols")
        assert toolkit_pro._is_tool_available("get_protocols")

    @pytest.mark.asyncio
    async def test_analysis_disabled(self, mock_client):
        """Test toolkit with analysis disabled."""
        mock_protocols = [
            {
                "id": "aave",
                "name": "Aave",
                "tvl": 5000000000,
                "category": "Lending",
                "chains": ["ethereum"],
            },
        ]
        mock_client.get_protocols = AsyncMock(return_value=mock_protocols)

        toolkit = DefiLlamaToolkit(enable_analysis=False)
        toolkit.client = mock_client

        result = await toolkit.get_protocols()

        assert result["success"] is True
        assert "analysis" not in result  # No analysis when disabled

    @pytest.mark.asyncio
    async def test_get_protocol_tvl_formatting(self, mock_client):
        """Test TVL formatting in get_protocol_tvl."""
        mock_client.get_protocol_tvl = AsyncMock(return_value=5234567890)  # 5.23B

        toolkit = DefiLlamaToolkit()
        toolkit.client = mock_client

        result = await toolkit.get_protocol_tvl("aave")

        assert result["success"] is True
        assert result["data"]["tvl"] == 5234567890
        assert "$5.23B" in result["data"]["tvl_formatted"]

    def test_toolkit_representation(self):
        """Test toolkit string representation."""
        toolkit = DefiLlamaToolkit(enable_analysis=True)
        repr_str = repr(toolkit)
        assert "DefiLlamaToolkit" in repr_str
        assert "enabled=True" in repr_str

    @pytest.mark.asyncio
    async def test_context_manager(self, mock_client):
        """Test async context manager."""
        mock_client.close = AsyncMock()

        async with DefiLlamaToolkit(enable_analysis=True) as toolkit:
            toolkit.client = mock_client
            assert toolkit is not None

        # Verify cleanup was called
        mock_client.close.assert_called_once()


def test_toolkit_imports():
    """Test that all toolkit components can be imported."""
    from roma_dspy.tools.crypto.defillama import (
        DefiLlamaToolkit,
        DefiLlamaAPIClient,
        DefiLlamaAPIError,
        DataType,
    )

    assert DefiLlamaToolkit is not None
    assert DefiLlamaAPIClient is not None
    assert DefiLlamaAPIError is not None
    assert DataType is not None


def test_toolkit_in_main_exports():
    """Test that DefiLlamaToolkit is exported from main tools module."""
    from roma_dspy.tools import DefiLlamaToolkit

    assert DefiLlamaToolkit is not None
