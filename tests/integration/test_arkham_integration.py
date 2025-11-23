"""Integration tests for Arkham Intelligence toolkit."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from roma_dspy.tools.crypto.arkham import ArkhamToolkit
from roma_dspy.core.storage import FileStorage
from roma_dspy.tools.utils.storage import DataStorage


@pytest.fixture
def mock_client():
    """Create mock Arkham API client."""
    client = MagicMock()
    client.aclose = AsyncMock()
    return client


@pytest.fixture
def temp_storage(tmp_path):
    """Create temporary storage for tests."""
    execution_id = "test_arkham_execution"
    file_storage = FileStorage(execution_id=execution_id, base_dir=tmp_path)
    return file_storage


class TestArkhamIntegration:
    """Integration tests for Arkham toolkit."""

    def test_toolkit_initialization(self):
        """Test Arkham toolkit initialization."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit(
            default_chain="ethereum",
            enable_analysis=True,
        )

        assert toolkit.default_chain == "ethereum"
        assert toolkit.enable_analysis is True
        assert toolkit.api_key == "test_key"
        assert toolkit.stats is not None

    def test_toolkit_with_storage(self, temp_storage):
        """Test toolkit with FileStorage integration."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit(
            file_storage=temp_storage,
            enable_analysis=True,
        )

        # Toolkit has data_storage which wraps file_storage
        assert toolkit._data_storage is not None
        assert toolkit._data_storage.file_storage is not None

    @pytest.mark.asyncio
    async def test_get_top_tokens_with_analysis(self, mock_client):
        """Test get_top_tokens with analysis generation."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        mock_tokens = {
            "tokens": [
                {
                    "token": {"marketCap": 1000000000, "symbol": "ETH"},
                    "current": {"price": 2000, "inflowDexVolume": 5000000},
                },
                {
                    "token": {"marketCap": 500000000, "symbol": "BTC"},
                    "current": {"price": 40000, "inflowDexVolume": 3000000},
                },
            ],
            "total": 2,
        }
        mock_client.get_top_tokens = AsyncMock(return_value=mock_tokens)

        toolkit = ArkhamToolkit(enable_analysis=True)
        toolkit.client = mock_client

        result = await toolkit.get_top_tokens(timeframe="24h", size=2)

        assert result["success"] is True
        assert result["count"] == 2
        assert "analysis" in result
        assert "market_cap_analysis" in result["analysis"]

    @pytest.mark.asyncio
    async def test_get_token_holders_with_analysis(self, mock_client):
        """Test get_token_holders with concentration analysis."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        mock_holders = {
            "addressTopHolders": [
                {"balance": "1000000", "pctOfCap": 10.5},
                {"balance": "500000", "pctOfCap": 5.2},
                {"balance": "250000", "pctOfCap": 2.6},
            ]
        }
        mock_client.get_token_holders = AsyncMock(return_value=mock_holders)

        toolkit = ArkhamToolkit(enable_analysis=True)
        toolkit.client = mock_client

        result = await toolkit.get_token_holders("ethereum")

        assert result["success"] is True
        assert "analysis" in result
        assert "concentration_metrics" in result["analysis"]
        assert result["analysis"]["concentration_metrics"]["whale_holders"] >= 0

    @pytest.mark.asyncio
    async def test_get_token_top_flow_with_analysis(self, mock_client):
        """Test get_token_top_flow with flow analysis."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        mock_flows = [
            {"inUSD": 1000000, "outUSD": 500000},
            {"inUSD": 750000, "outUSD": 250000},
        ]
        mock_client.get_token_top_flow = AsyncMock(return_value=mock_flows)

        toolkit = ArkhamToolkit(enable_analysis=True)
        toolkit.client = mock_client

        result = await toolkit.get_token_top_flow("bitcoin", time_last="24h")

        assert result["success"] is True
        assert "analysis" in result
        assert "flow_summary" in result["analysis"]
        assert result["analysis"]["flow_summary"]["net_flow_usd"] > 0

    @pytest.mark.asyncio
    async def test_get_supported_chains(self, mock_client):
        """Test get_supported_chains."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        mock_chains = {"chains": [{"id": "ethereum"}, {"id": "bitcoin"}]}
        mock_client.get_supported_chains = AsyncMock(return_value=mock_chains)

        toolkit = ArkhamToolkit()
        toolkit.client = mock_client

        result = await toolkit.get_supported_chains()

        assert result["success"] is True
        assert result["count"] == 2

    @pytest.mark.asyncio
    async def test_get_transfers_with_analysis(self, mock_client):
        """Test get_transfers with analysis."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        mock_transfers = {
            "transfers": [
                {"historicalUSD": 100000},
                {"historicalUSD": 50000},
                {"historicalUSD": 25000},
            ],
            "count": 3,
        }
        mock_client.get_transfers = AsyncMock(return_value=mock_transfers)

        toolkit = ArkhamToolkit(enable_analysis=True)
        toolkit.client = mock_client

        result = await toolkit.get_transfers(limit=3)

        assert result["success"] is True
        assert "analysis" in result
        assert "transfer_summary" in result["analysis"]

    @pytest.mark.asyncio
    async def test_get_token_balances_with_analysis(self, mock_client):
        """Test get_token_balances with portfolio analysis."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        mock_balances = {
            "balances": {
                "ethereum": [
                    {"usd": 10000, "symbol": "ETH"},
                    {"usd": 5000, "symbol": "USDC"},
                ]
            }
        }
        mock_client.get_token_balances = AsyncMock(return_value=mock_balances)

        toolkit = ArkhamToolkit(enable_analysis=True)
        toolkit.client = mock_client

        result = await toolkit.get_token_balances("0x123")

        assert result["success"] is True
        assert "analysis" in result
        assert "portfolio_summary" in result["analysis"]

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_client):
        """Test error handling."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        from roma_dspy.tools.crypto.arkham import ArkhamAPIError

        mock_client.get_top_tokens = AsyncMock(side_effect=ArkhamAPIError("API Error"))

        toolkit = ArkhamToolkit()
        toolkit.client = mock_client

        result = await toolkit.get_top_tokens()

        assert result["success"] is False
        assert "error" in result  # BaseToolkit uses "error" not "message"
        assert result["error_type"] == "ArkhamAPIError"

    @pytest.mark.asyncio
    async def test_chain_validation(self):
        """Test chain validation."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit()

        # Valid chain
        result = toolkit._validate_chain("ethereum")
        assert result == "ethereum"

        # Invalid chain
        with pytest.raises(ValueError):
            toolkit._validate_chain("invalid_chain")

    @pytest.mark.asyncio
    async def test_address_validation(self):
        """Test address validation."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit()

        # Valid Ethereum address
        result = toolkit._validate_address("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
        assert result.startswith("0x")

        # Invalid address
        with pytest.raises(ValueError):
            toolkit._validate_address("")

    @pytest.mark.asyncio
    async def test_cleanup(self):
        """Test toolkit cleanup via aclose."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit()
        # Toolkit has aclose method for cleanup
        await toolkit.aclose()
        assert toolkit.client is not None  # Client still exists after close

    def test_toolkit_representation(self):
        """Test toolkit string representation."""
        import os

        os.environ["ARKHAM_API_KEY"] = "test_key"

        toolkit = ArkhamToolkit()
        repr_str = repr(toolkit)

        assert "ArkhamToolkit" in repr_str


def test_toolkit_imports():
    """Test that toolkit can be imported."""
    from roma_dspy.tools.crypto.arkham import ArkhamToolkit

    assert ArkhamToolkit is not None


def test_toolkit_in_main_exports():
    """Test toolkit is exported from main tools module."""
    from roma_dspy.tools import ArkhamToolkit

    assert ArkhamToolkit is not None
