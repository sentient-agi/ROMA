"""Test data handling fixes for crypto toolkits."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from datetime import datetime, timezone

from roma_dspy.tools.crypto.binance.toolkit import BinanceToolkit
from roma_dspy.tools.value_objects.crypto import (
    Kline,
    OrderBookSnapshot,
    OrderBookLevel,
    OrderSide,
    Trade,
)


class TestBinanceDataHandling:
    """Test that Binance toolkit properly returns full data arrays."""

    @pytest.mark.asyncio
    async def test_get_klines_returns_full_data(self):
        """Test that get_klines returns ALL klines, not just summary."""
        toolkit = BinanceToolkit()

        # Mock client to return sample klines
        mock_klines = [
            Kline(
                open_time=datetime(2025, 10, 15, i, 0, tzinfo=timezone.utc),
                open=Decimal("50000"),
                high=Decimal("51000"),
                low=Decimal("49000"),
                close=Decimal("50500"),
                volume=Decimal("100"),
                close_time=datetime(2025, 10, 15, i, 59, tzinfo=timezone.utc),
                quote_volume=Decimal("5000000"),
                trades_count=1000,
                taker_buy_base_volume=Decimal("50"),
                taker_buy_quote_volume=Decimal("2500000"),
            )
            for i in range(24)
        ]

        with patch.object(toolkit, "_validate_symbol", return_value="BTCUSDT"):
            with patch.object(toolkit.client, "get_klines", return_value=mock_klines):
                result = await toolkit.get_klines("BTCUSDT", interval="1h", limit=24)

        # Verify success
        assert result["success"] is True

        # Should have inline data (below threshold)
        assert "data" in result
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 24

        # Verify each kline has all fields
        kline = result["data"][0]
        assert "open_time" in kline
        assert "open" in kline
        assert "high" in kline
        assert "low" in kline
        assert "close" in kline
        assert "volume" in kline
        assert "close_time" in kline
        assert "quote_volume" in kline
        assert "trades_count" in kline

        # Summary should still be in metadata
        assert "count" in result
        assert result["count"] == 24
        assert "latest_close" in result
        assert "interval" in result

    @pytest.mark.asyncio
    async def test_get_order_book_returns_full_levels(self):
        """Test that get_order_book returns all bids/asks."""
        toolkit = BinanceToolkit()

        # Mock order book
        mock_bids = [
            OrderBookLevel(
                price=Decimal(f"5000{i}"), quantity=Decimal("1.0"), side=OrderSide.BID
            )
            for i in range(20)
        ]
        mock_asks = [
            OrderBookLevel(
                price=Decimal(f"5100{i}"), quantity=Decimal("1.0"), side=OrderSide.ASK
            )
            for i in range(20)
        ]
        mock_book = OrderBookSnapshot(
            symbol="BTCUSDT",
            bids=mock_bids,
            asks=mock_asks,
            timestamp=datetime.now(timezone.utc),
            last_update_id=12345,
        )

        with patch.object(toolkit, "_validate_symbol", return_value="BTCUSDT"):
            with patch.object(toolkit.client, "get_order_book", return_value=mock_book):
                result = await toolkit.get_order_book("BTCUSDT", limit=20)

        # Verify success
        assert result["success"] is True

        # Should have inline data
        assert "data" in result
        book = result["data"]

        # Verify structure
        assert "bids" in book
        assert "asks" in book
        assert isinstance(book["bids"], list)
        assert isinstance(book["asks"], list)
        assert len(book["bids"]) == 20
        assert len(book["asks"]) == 20

        # Verify bid structure
        bid = book["bids"][0]
        assert "price" in bid
        assert "quantity" in bid

        # Summary in metadata
        assert "bids_count" in result
        assert result["bids_count"] == 20
        assert "best_bid" in result
        assert "best_ask" in result

    @pytest.mark.asyncio
    async def test_get_recent_trades_returns_full_trades(self):
        """Test that get_recent_trades returns all trades."""
        toolkit = BinanceToolkit()

        # Mock trades
        mock_trades = [
            Trade(
                id=i,
                symbol="BTCUSDT",
                price=Decimal(f"5000{i}"),
                quantity=Decimal("0.1"),
                quote_quantity=Decimal(f"500{i}"),
                timestamp=datetime.now(timezone.utc),
                is_buyer_maker=i % 2 == 0,
                is_best_match=True,
            )
            for i in range(50)
        ]

        with patch.object(toolkit, "_validate_symbol", return_value="BTCUSDT"):
            with patch.object(
                toolkit.client, "get_recent_trades", return_value=mock_trades
            ):
                result = await toolkit.get_recent_trades("BTCUSDT", limit=50)

        # Verify success
        assert result["success"] is True

        # Should have inline data
        assert "data" in result
        assert isinstance(result["data"], list)
        assert len(result["data"]) == 50

        # Verify trade structure
        trade = result["data"][0]
        assert "id" in trade
        assert "price" in trade
        assert "quantity" in trade
        assert "timestamp" in trade
        assert "is_buyer_maker" in trade

        # Summary in metadata
        assert "trades_count" in result
        assert result["trades_count"] == 50
        assert "latest_price" in result
        assert "avg_price" in result


class TestDataStorageIntegration:
    """Test storage integration with fixed tuple return."""

    @pytest.mark.asyncio
    async def test_storage_tuple_return(self):
        """Test that DataStorage.store_parquet returns (key, size_kb) tuple."""
        from roma_dspy.tools.utils.storage import DataStorage

        # Mock file storage
        class MockFileStorage:
            def __init__(self):
                self.execution_id = "test_exec"
                self.data = {}
                self.root = "/fake/root"

            async def put(self, key, data):
                self.data[key] = data
                # Return full path like real FileStorage
                return f"{self.root}/{key}"

            async def get(self, key):
                return self.data.get(key)

        file_storage = MockFileStorage()
        data_storage = DataStorage(
            file_storage=file_storage,
            toolkit_name="test",
            threshold_kb=1,
        )

        test_data = [{"price": i, "volume": i * 100} for i in range(100)]

        result = await data_storage.store_parquet(
            data=test_data,
            data_type="test_data",
            prefix="test",
        )

        # Verify tuple return
        assert isinstance(result, tuple)
        assert len(result) == 2
        full_path, size_kb = result
        assert isinstance(full_path, str)
        assert isinstance(size_kb, (int, float))
        assert size_kb > 0
        # Full path should be returned (not just key)
        assert full_path.startswith("/fake/root/")

    @pytest.mark.asyncio
    async def test_build_success_response_with_storage(self):
        """Test that _build_success_response properly handles storage."""
        from roma_dspy.tools.utils.storage import DataStorage

        # Mock file storage
        class MockFileStorage:
            def __init__(self):
                self.execution_id = "test_exec"
                self.data = {}
                self.root = "/fake/root"

            async def put(self, key, data):
                self.data[key] = data
                # Return full path like real FileStorage
                return f"{self.root}/{key}"

        toolkit = BinanceToolkit()

        # Add storage to toolkit
        file_storage = MockFileStorage()
        toolkit._data_storage = DataStorage(
            file_storage=file_storage,
            toolkit_name="binance",
            threshold_kb=1,  # Force storage
        )

        # Large data that should be stored
        large_data = [{"price": i} for i in range(1000)]

        response = await toolkit._build_success_response(
            data=large_data,
            storage_data_type="test",
            storage_prefix="test_prefix",
            tool_name="test_tool",
            extra_field="extra_value",
        )

        # Should be stored
        assert response["success"] is True
        assert "file_path" in response
        assert "stored" in response
        assert response["stored"] is True
        assert "size_kb" in response
        assert "message" in response

        # Data should NOT be inline
        assert "data" not in response

        # Metadata should be present
        assert "extra_field" in response
        assert response["extra_field"] == "extra_value"


class TestEdgeCases:
    """Test edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_empty_klines_array(self):
        """Test handling of empty klines response."""
        toolkit = BinanceToolkit()

        with patch.object(toolkit, "_validate_symbol", return_value="BTCUSDT"):
            with patch.object(toolkit.client, "get_klines", return_value=[]):
                result = await toolkit.get_klines("BTCUSDT", interval="1h", limit=24)

        # Should succeed with empty data
        assert result["success"] is True
        assert "data" in result
        assert result["data"] == []
        assert result["count"] == 0

    @pytest.mark.asyncio
    async def test_empty_trades_array(self):
        """Test handling of empty trades response."""
        toolkit = BinanceToolkit()

        with patch.object(toolkit, "_validate_symbol", return_value="BTCUSDT"):
            with patch.object(toolkit.client, "get_recent_trades", return_value=[]):
                result = await toolkit.get_recent_trades("BTCUSDT", limit=50)

        # Should succeed with empty data
        assert result["success"] is True
        assert "data" in result
        assert result["data"] == []
        assert result["trades_count"] == 0

    @pytest.mark.asyncio
    async def test_data_validation_invalid_type(self):
        """Test that DataStorage validates data types."""
        from roma_dspy.tools.utils.storage import DataStorage

        class MockFileStorage:
            def __init__(self):
                self.execution_id = "test"
                self.data = {}
                self.root = "/fake/root"

            async def put(self, key, data):
                self.data[key] = data
                # Return full path like real FileStorage
                return f"{self.root}/{key}"

        storage = DataStorage(
            file_storage=MockFileStorage(),
            toolkit_name="test",
            threshold_kb=1,
        )

        # Try to store invalid type (string)
        with pytest.raises(ValueError, match="Cannot store str as Parquet"):
            await storage.store_parquet(
                data="invalid_string_data",
                data_type="test",
                prefix="test",
            )

    @pytest.mark.asyncio
    async def test_metadata_preserved_with_storage(self):
        """Test that metadata is preserved when data is stored."""
        from roma_dspy.tools.utils.storage import DataStorage

        toolkit = BinanceToolkit()

        # Mock storage
        class MockFileStorage:
            def __init__(self):
                self.execution_id = "test_exec"
                self.data = {}
                self.root = "/fake/root"

            async def put(self, key, data):
                self.data[key] = data
                # Return full path like real FileStorage
                return f"{self.root}/{key}"

        file_storage = MockFileStorage()
        toolkit._data_storage = DataStorage(
            file_storage=file_storage,
            toolkit_name="binance",
            threshold_kb=1,
        )

        # Create response with metadata
        large_data = [{"value": i} for i in range(1000)]

        response = await toolkit._build_success_response(
            data=large_data,
            storage_data_type="test",
            storage_prefix="test",
            tool_name="test_tool",
            count=1000,
            symbol="BTCUSDT",
            interval="1h",
        )

        # Metadata should be preserved
        assert response["count"] == 1000
        assert response["symbol"] == "BTCUSDT"
        assert response["interval"] == "1h"

        # But data should be in file
        assert "file_path" in response
        assert "data" not in response
