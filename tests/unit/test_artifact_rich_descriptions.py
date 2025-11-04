"""
Tests for rich artifact descriptions with tool arguments and metadata.

Tests the enhancement where artifact descriptions include:
- Tool invocation signature with full arguments
- Parquet file metadata (rows, columns, date ranges)
- Clear guidance for downstream agents to reuse artifacts
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd
import pytest

from roma_dspy.core.artifacts import ArtifactBuilder, ArtifactRegistry
from roma_dspy.core.context import ExecutionContext
from roma_dspy.core.storage import FileStorage
from roma_dspy.tools.metrics.artifact_detector import (
    _build_rich_description,
    auto_register_artifacts,
)
from roma_dspy.types import ArtifactType


class TestRichDescriptionBasic:
    """Test basic rich description generation."""

    @pytest.mark.asyncio
    async def test_description_without_kwargs(self, tmp_path):
        """Test description generation without tool arguments."""
        # Create a simple text file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="TestToolkit",
            tool_name="test_tool",
            tool_kwargs=None
        )

        # Should contain tool signature without args
        assert "TestToolkit.test_tool()" in description
        # Should contain timestamp
        assert "Fetched:" in description
        # Should contain file type
        assert "File type: .txt" in description
        # Should contain reuse guidance
        assert "⚠️ Use this artifact directly" in description

    @pytest.mark.asyncio
    async def test_description_with_kwargs(self, tmp_path):
        """Test description generation with tool arguments."""
        # Create a simple text file
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")

        tool_kwargs = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 100
        }

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="CoinGeckoToolkit",
            tool_name="get_coins",
            tool_kwargs=tool_kwargs
        )

        # Should contain tool signature with full args
        assert "CoinGeckoToolkit.get_coins(" in description
        assert "vs_currency='usd'" in description
        assert "order='market_cap_desc'" in description
        assert "per_page=100" in description
        # Should contain reuse guidance with tool name
        assert "⚠️ Use this artifact directly instead of calling get_coins()" in description


class TestRichDescriptionParquet:
    """Test rich description generation for Parquet files."""

    @pytest.mark.asyncio
    async def test_parquet_description_basic(self, tmp_path):
        """Test Parquet description with basic metadata."""
        # Create a Parquet file with test data
        test_file = tmp_path / "test_data.parquet"
        df = pd.DataFrame({
            "id": [1, 2, 3, 4, 5],
            "name": ["Bitcoin", "Ethereum", "Cardano", "Polkadot", "Solana"],
            "symbol": ["BTC", "ETH", "ADA", "DOT", "SOL"],
            "price": [45000.0, 3000.0, 1.2, 25.0, 100.0],
            "market_cap": [850e9, 350e9, 40e9, 30e9, 40e9]
        })
        df.to_parquet(test_file)

        tool_kwargs = {"vs_currency": "usd", "per_page": 5}

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="CoinGeckoToolkit",
            tool_name="get_coins",
            tool_kwargs=tool_kwargs
        )

        # Should contain tool signature
        assert "CoinGeckoToolkit.get_coins(vs_currency='usd', per_page=5)" in description
        # Should contain row and column counts
        assert "5 rows × 5 columns" in description
        # Should contain column names
        assert "id, name, symbol, price, market_cap" in description
        # Should contain reuse guidance
        assert "⚠️ Use this artifact directly instead of calling get_coins() again" in description

    @pytest.mark.asyncio
    async def test_parquet_description_with_timestamps(self, tmp_path):
        """Test Parquet description with timestamp columns and date range."""
        # Create Parquet file with timestamp data
        test_file = tmp_path / "timeseries.parquet"
        df = pd.DataFrame({
            "timestamp": pd.date_range("2025-01-01", periods=100, freq="D"),
            "price": [50000 + i * 100 for i in range(100)],
            "volume": [1000000 + i * 10000 for i in range(100)]
        })
        df.to_parquet(test_file)

        tool_kwargs = {"symbol": "BTC", "days": 100}

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="CoinGeckoToolkit",
            tool_name="get_price_history",
            tool_kwargs=tool_kwargs
        )

        # Should contain row count
        assert "100 rows" in description
        # Should contain column names
        assert "timestamp" in description
        assert "price" in description
        assert "volume" in description
        # Should contain date range
        assert "Date range (timestamp):" in description
        assert "2025-01-01" in description
        assert "2025-04-10" in description  # 100 days from Jan 1

    @pytest.mark.asyncio
    async def test_parquet_description_many_columns(self, tmp_path):
        """Test Parquet description with >15 columns (should truncate)."""
        # Create Parquet with many columns
        test_file = tmp_path / "wide_data.parquet"
        columns = {f"col_{i}": list(range(10)) for i in range(20)}
        df = pd.DataFrame(columns)
        df.to_parquet(test_file)

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="TestToolkit",
            tool_name="get_wide_data",
            tool_kwargs={"format": "parquet"}
        )

        # Should show first 15 columns + ...
        assert "col_0" in description
        assert "col_14" in description
        assert "..." in description
        # Should not show all 20 columns
        column_section = description.split("Columns:")[1].split("\n")[0]
        assert "col_19" not in column_section

    @pytest.mark.asyncio
    async def test_parquet_read_failure_fallback(self, tmp_path):
        """Test fallback to basic description if Parquet read fails."""
        # Create a non-Parquet file with .parquet extension
        test_file = tmp_path / "corrupt.parquet"
        test_file.write_text("not a parquet file")

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="TestToolkit",
            tool_name="test_tool",
            tool_kwargs={"test": "value"}
        )

        # Should fall back to basic description
        assert "TestToolkit.test_tool(test='value')" in description
        assert "File type: .parquet" in description
        assert "⚠️ Use this artifact directly" in description
        # Should NOT contain dataset info
        assert "rows" not in description.lower()
        assert "columns" not in description.lower()


class TestAutoRegisterWithRichDescription:
    """Test auto_register_artifacts with rich descriptions."""

    @pytest.mark.asyncio
    async def test_auto_register_passes_kwargs(self, tmp_path):
        """Test that auto_register_artifacts passes tool_kwargs to description builder."""
        # Setup
        execution_id = "test_exec_123"
        test_file = tmp_path / "data.parquet"

        # Create simple Parquet file
        df = pd.DataFrame({"id": [1, 2, 3], "value": [10, 20, 30]})
        df.to_parquet(test_file)

        # Mock context
        mock_registry = MagicMock(spec=ArtifactRegistry)
        mock_registry.get_by_path = AsyncMock(return_value=None)  # Not already registered
        mock_registry.register = AsyncMock()

        mock_storage = MagicMock(spec=FileStorage)
        mock_storage.root = str(tmp_path)

        mock_ctx = MagicMock()
        mock_ctx.execution_id = execution_id
        mock_ctx.artifact_registry = mock_registry
        mock_ctx.file_storage = mock_storage

        tool_kwargs = {"chain": "ethereum", "protocol": "uniswap"}

        with patch("roma_dspy.tools.metrics.artifact_detector.ExecutionContext.get", return_value=mock_ctx):
            count = await auto_register_artifacts(
                file_paths=[str(test_file)],
                toolkit_class="DefiLlamaToolkit",
                tool_name="get_tvl",
                execution_id=execution_id,
                tool_kwargs=tool_kwargs
            )

        # Should register 1 artifact
        assert count == 1
        assert mock_registry.register.call_count == 1

        # Get the registered artifact
        registered_artifact = mock_registry.register.call_args[0][0]

        # Description should include tool kwargs
        assert "DefiLlamaToolkit.get_tvl(" in registered_artifact.metadata.description
        assert "chain='ethereum'" in registered_artifact.metadata.description
        assert "protocol='uniswap'" in registered_artifact.metadata.description
        # Should include Parquet metadata
        assert "3 rows × 2 columns" in registered_artifact.metadata.description
        assert "id, value" in registered_artifact.metadata.description

    @pytest.mark.asyncio
    async def test_auto_register_without_kwargs(self, tmp_path):
        """Test auto_register_artifacts works without tool_kwargs."""
        # Setup
        execution_id = "test_exec_456"
        test_file = tmp_path / "simple.txt"
        test_file.write_text("test content")

        # Mock context
        mock_registry = MagicMock(spec=ArtifactRegistry)
        mock_registry.get_by_path = AsyncMock(return_value=None)
        mock_registry.register = AsyncMock()

        mock_storage = MagicMock(spec=FileStorage)
        mock_storage.root = str(tmp_path)

        mock_ctx = MagicMock()
        mock_ctx.execution_id = execution_id
        mock_ctx.artifact_registry = mock_registry
        mock_ctx.file_storage = mock_storage

        with patch("roma_dspy.tools.metrics.artifact_detector.ExecutionContext.get", return_value=mock_ctx):
            count = await auto_register_artifacts(
                file_paths=[str(test_file)],
                toolkit_class="TestToolkit",
                tool_name="test_tool",
                execution_id=execution_id,
                tool_kwargs=None  # No kwargs
            )

        assert count == 1
        registered_artifact = mock_registry.register.call_args[0][0]

        # Description should have tool signature without args
        assert "TestToolkit.test_tool()" in registered_artifact.metadata.description
        # Should still have reuse guidance
        assert "⚠️ Use this artifact directly" in registered_artifact.metadata.description


class TestDescriptionFormattingEdgeCases:
    """Test edge cases in description formatting."""

    @pytest.mark.asyncio
    async def test_kwargs_with_special_characters(self, tmp_path):
        """Test tool kwargs with special characters are properly escaped."""
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")

        tool_kwargs = {
            "query": "bitcoin OR ethereum",
            "filter": "price > 1000",
            "tags": ["defi", "nft"]
        }

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="SearchToolkit",
            tool_name="search",
            tool_kwargs=tool_kwargs
        )

        # Should properly repr the values
        assert "query='bitcoin OR ethereum'" in description
        assert "filter='price > 1000'" in description
        assert "tags=['defi', 'nft']" in description

    @pytest.mark.asyncio
    async def test_kwargs_with_none_values(self, tmp_path):
        """Test tool kwargs with None values."""
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")

        tool_kwargs = {
            "limit": 100,
            "offset": None,
            "filter": None
        }

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="APIToolkit",
            tool_name="fetch",
            tool_kwargs=tool_kwargs
        )

        assert "limit=100" in description
        assert "offset=None" in description
        assert "filter=None" in description

    @pytest.mark.asyncio
    async def test_empty_kwargs_dict(self, tmp_path):
        """Test with empty kwargs dict (not None)."""
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="TestToolkit",
            tool_name="test_tool",
            tool_kwargs={}  # Empty dict
        )

        # Should treat empty dict as "no args"
        assert "TestToolkit.test_tool()" in description

    @pytest.mark.asyncio
    async def test_parquet_with_no_data(self, tmp_path):
        """Test Parquet file with no rows."""
        test_file = tmp_path / "empty.parquet"
        df = pd.DataFrame(columns=["id", "name", "value"])
        df.to_parquet(test_file)

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="TestToolkit",
            tool_name="get_empty_data",
            tool_kwargs=None
        )

        # Should show 0 rows
        assert "0 rows" in description
        assert "3 columns" in description
        assert "id, name, value" in description


class TestDescriptionGuidanceMessages:
    """Test the guidance messages in descriptions."""

    @pytest.mark.asyncio
    async def test_guidance_includes_tool_name(self, tmp_path):
        """Test that reuse guidance mentions specific tool name."""
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")

        description = await _build_rich_description(
            path=test_file,
            toolkit_class="CoinGeckoToolkit",
            tool_name="get_price",
            tool_kwargs={"id": "bitcoin"}
        )

        # Should mention the specific tool name
        assert "instead of calling get_price()" in description
        # Basic files don't mention "same parameters"
        assert "⚠️ Use this artifact directly" in description

    @pytest.mark.asyncio
    async def test_parquet_guidance_vs_basic_guidance(self, tmp_path):
        """Test that Parquet files get enhanced guidance."""
        # Basic file
        basic_file = tmp_path / "basic.txt"
        basic_file.write_text("test")
        basic_desc = await _build_rich_description(
            path=basic_file,
            toolkit_class="Test",
            tool_name="test",
            tool_kwargs=None
        )

        # Parquet file
        parquet_file = tmp_path / "data.parquet"
        df = pd.DataFrame({"a": [1]})
        df.to_parquet(parquet_file)
        parquet_desc = await _build_rich_description(
            path=parquet_file,
            toolkit_class="Test",
            tool_name="test",
            tool_kwargs=None
        )

        # Both should have warning emoji
        assert "⚠️" in basic_desc
        assert "⚠️" in parquet_desc

        # Parquet should have dataset info
        assert "Dataset:" in parquet_desc
        assert "Dataset:" not in basic_desc