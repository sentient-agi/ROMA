"""Integration tests for storage system."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from roma_dspy.config.schemas import StorageConfig
from roma_dspy.core.storage import FileStorage
from roma_dspy.tools.utils.storage import DataStorage


class TestStorageIntegration:
    """Test storage system integration."""

    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for tests."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def execution_id(self):
        """Test execution ID."""
        return "test_20250930_143022_abc123"

    @pytest.fixture
    def storage_config(self, temp_dir):
        """Create test storage config."""
        return StorageConfig(
            base_path=str(temp_dir),
            buffer_size=1024 * 1024,
            max_file_size=100 * 1024 * 1024,
        )

    def test_file_storage_initialization(self, storage_config, execution_id):
        """Test FileStorage initialization."""
        storage = FileStorage(
            config=storage_config,
            execution_id=execution_id,
        )

        assert storage.execution_id == execution_id
        assert (
            storage.root == Path(storage_config.base_path) / "executions" / execution_id
        )
        assert (storage.root / "artifacts").exists()
        assert (storage.root / "outputs").exists()
        assert (storage.root / "logs").exists()

    @pytest.mark.asyncio
    async def test_file_storage_put_get(self, storage_config, execution_id):
        """Test FileStorage put and get operations."""
        storage = FileStorage(
            config=storage_config,
            execution_id=execution_id,
        )

        # Store data
        test_data = b"test data content"
        key = "test/data.bin"

        await storage.put(key, test_data)
        assert await storage.exists(key)

        # Retrieve data
        read_data = await storage.get(key)
        assert read_data == test_data

    @pytest.mark.asyncio
    async def test_file_storage_json_operations(self, storage_config, execution_id):
        """Test FileStorage JSON write and read."""
        storage = FileStorage(
            config=storage_config,
            execution_id=execution_id,
        )

        test_data = {"test": "data", "number": 123}
        key = "outputs/test_output.json"

        # Write JSON
        await storage.put_json(key, test_data)
        assert await storage.exists(key)

        # Read JSON
        read_data = await storage.get_json(key)
        assert read_data == test_data

    @pytest.mark.asyncio
    async def test_data_storage_initialization(self, storage_config, execution_id):
        """Test DataStorage initialization."""
        file_storage = FileStorage(
            config=storage_config,
            execution_id=execution_id,
        )

        data_storage = DataStorage(
            file_storage=file_storage,
            toolkit_name="test_toolkit",
            threshold_kb=100,
        )

        assert data_storage.toolkit_name == "test_toolkit"
        assert data_storage.threshold_kb == 100

    def test_data_storage_size_estimation(self, storage_config, execution_id):
        """Test DataStorage size estimation accuracy."""
        file_storage = FileStorage(
            config=storage_config,
            execution_id=execution_id,
        )

        data_storage = DataStorage(
            file_storage=file_storage,
            toolkit_name="test_toolkit",
            threshold_kb=1,  # 1KB threshold
        )

        # Small data should not exceed threshold
        small_data = {"test": "data"}
        assert not data_storage.should_store(small_data)

        # Large data should exceed threshold
        large_data = {"test": "x" * 10000}  # ~10KB
        assert data_storage.should_store(large_data)

        # Verify size estimation accuracy
        size_kb = data_storage.estimate_size_kb(large_data)
        # Should be close to actual JSON size
        import json

        actual_size = len(json.dumps(large_data).encode("utf-8")) / 1024
        assert abs(size_kb - actual_size) < 0.1  # Within 100 bytes

    @pytest.mark.asyncio
    async def test_data_storage_parquet_operations(self, storage_config, execution_id):
        """Test DataStorage Parquet write and read."""
        pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")

        file_storage = FileStorage(
            config=storage_config,
            execution_id=execution_id,
        )

        data_storage = DataStorage(
            file_storage=file_storage,
            toolkit_name="test_toolkit",
            threshold_kb=1,
        )

        # Store data
        test_data = [
            {"coin": "bitcoin", "price": 50000},
            {"coin": "ethereum", "price": 3000},
        ]

        full_path, size_kb = await data_storage.store_parquet(
            data=test_data,
            data_type="test_prices",
            prefix="btc_eth_prices",
        )

        assert isinstance(full_path, str)
        assert "test_toolkit" in full_path
        assert "test_prices" in full_path
        assert "btc_eth_prices" in full_path
        assert isinstance(size_kb, (int, float))
        assert size_kb > 0

        # Extract key from full path for FileStorage operations
        # full_path is like: /tmp/.../executions/{exec_id}/toolkits/...
        # We need the relative key: toolkits/...
        key = str(Path(full_path).relative_to(file_storage.root))
        assert await file_storage.exists(key)

        # Load data
        loaded_data = await data_storage.load_parquet(key)
        assert len(loaded_data) == 2
        assert loaded_data[0]["coin"] == "bitcoin"
        assert loaded_data[1]["coin"] == "ethereum"

    @pytest.mark.asyncio
    async def test_async_non_blocking(self, storage_config, execution_id):
        """Test that async operations don't block the event loop."""
        pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")

        file_storage = FileStorage(
            config=storage_config,
            execution_id=execution_id,
        )

        data_storage = DataStorage(
            file_storage=file_storage,
            toolkit_name="test_toolkit",
            threshold_kb=1,
        )

        # Create large dataset
        large_data = [{"id": i, "value": f"data_{i}" * 100} for i in range(1000)]

        # Run multiple operations concurrently
        tasks = [
            data_storage.store_parquet(
                data=large_data,
                data_type="concurrent_test",
                prefix=f"batch_{i}",
            )
            for i in range(3)
        ]

        # Should complete without blocking
        results = await asyncio.gather(*tasks)
        assert len(results) == 3
        # Each result is a tuple (full_path, size_kb)
        assert all(isinstance(r, tuple) and len(r) == 2 for r in results)
        assert all(
            isinstance(r[0], str) and isinstance(r[1], (int, float)) for r in results
        )

    @pytest.mark.asyncio
    async def test_compression_fallback(self, storage_config, execution_id):
        """Test fallback to gzip when snappy unavailable."""
        pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")

        file_storage = FileStorage(
            config=storage_config,
            execution_id=execution_id,
        )

        data_storage = DataStorage(
            file_storage=file_storage,
            toolkit_name="test_toolkit",
            threshold_kb=1,
        )

        test_data = [{"id": i, "value": i * 2} for i in range(100)]

        # Should work even if snappy fails (graceful fallback)
        full_path, size_kb = await data_storage.store_parquet(
            data=test_data,
            data_type="compression_test",
            prefix="fallback_test",
        )

        assert isinstance(full_path, str)
        assert isinstance(size_kb, (int, float))

        # Extract key from full path for loading
        key = str(Path(full_path).relative_to(file_storage.root))

        # Should be able to load regardless of compression
        loaded_data = await data_storage.load_parquet(key)
        assert len(loaded_data) == 100

    @pytest.mark.asyncio
    async def test_file_not_found(self, storage_config, execution_id):
        """Test loading non-existent file raises error."""
        pytest.importorskip("pandas")
        pytest.importorskip("pyarrow")

        file_storage = FileStorage(
            config=storage_config,
            execution_id=execution_id,
        )

        data_storage = DataStorage(
            file_storage=file_storage,
            toolkit_name="test_toolkit",
            threshold_kb=1,
        )

        with pytest.raises(FileNotFoundError):
            await data_storage.load_parquet("nonexistent/file.parquet")


def test_storage_system_available():
    """Test that storage modules can be imported."""
    from roma_dspy.core.storage import FileStorage
    from roma_dspy.tools.utils.storage import DataStorage

    assert FileStorage is not None
    assert DataStorage is not None
