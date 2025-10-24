"""Parquet data storage for toolkit responses."""

from __future__ import annotations

import asyncio
import io
import json
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from roma_dspy.core.storage import FileStorage


class DataStorage:
    """
    Parquet storage for large toolkit responses.

    Uses FileStorage for execution-isolated I/O operations.
    Handles threshold checking, DataFrame conversion, and compression.

    Features:
    - Automatic threshold-based storage
    - Parquet serialization with Snappy compression (fallback to gzip)
    - Flattened 2-level folder structure for LLM browsability
    - Execution-isolated via FileStorage
    - True async I/O (non-blocking)

    Storage Path Structure:
        artifacts/{toolkit_name}/{data_type}/{filename}

        Examples:
        - artifacts/coingecko/coin_prices/btc_usd_20250122_143022_123456_a1b2c3d4.parquet
        - artifacts/binance/klines/BTCUSDT_1h_20250122_144000_111111_m3n4o5p6.parquet
        - artifacts/mcp_exa/search_results/exa_crypto_news_20250122_145500_222222_x9y8z7w6.parquet

    Example:
        ```python
        from roma_dspy.core.storage import FileStorage
        from roma_dspy.tools.utils.storage import DataStorage
        from roma_dspy.config.manager import ConfigManager

        config = ConfigManager.load()
        file_storage = FileStorage(
            config=config.storage,
            execution_id="20250930_143022_abc"
        )
        await file_storage.initialize()

        data_storage = DataStorage(
            file_storage=file_storage,
            toolkit_name="coingecko",
            threshold_kb=1000,
        )

        # Check if data should be stored
        large_data = {"prices": [...]}  # Large dataset
        if data_storage.should_store(large_data):
            full_path, size_kb = await data_storage.store_parquet(
                data=large_data,
                data_type="market_charts",
                prefix="btc_usd_30d",
            )
            print(f"Stored {size_kb:.1f}KB to {full_path}")

        # Load data back
        records = await data_storage.load_parquet(key)
        ```
    """

    def __init__(
        self,
        file_storage: FileStorage,
        toolkit_name: str,
        threshold_kb: int = 1000,
    ):
        """Initialize data storage.

        Args:
            file_storage: FileStorage instance (with execution_id)
            toolkit_name: Toolkit name for path organization
            threshold_kb: Size threshold for storage in KB (default: 1000KB = 1MB)
        """
        self.file_storage = file_storage
        self.toolkit_name = toolkit_name
        self.threshold_kb = threshold_kb

        logger.debug(
            f"Initialized DataStorage for {toolkit_name} "
            f"(threshold: {threshold_kb}KB, execution: {file_storage.execution_id})"
        )

    def estimate_size_kb(self, data: Any) -> float:
        """Estimate data size in KB.

        Uses JSON serialization size as proxy for memory footprint.

        Args:
            data: Data to estimate

        Returns:
            Estimated size in KB
        """
        if isinstance(data, (dict, list)):
            json_str = json.dumps(data, default=str)
            return len(json_str.encode('utf-8')) / 1024
        return len(str(data).encode('utf-8')) / 1024

    def should_store(self, data: Any) -> bool:
        """Check if data exceeds storage threshold.

        Args:
            data: Data to check

        Returns:
            True if data size > threshold_kb
        """
        size_kb = self.estimate_size_kb(data)
        should = size_kb > self.threshold_kb

        if should:
            logger.debug(
                f"Data size {size_kb:.1f}KB exceeds threshold "
                f"{self.threshold_kb}KB - will store to file"
            )

        return should

    async def _to_dataframe(self, data: Any) -> "pd.DataFrame":
        """Convert data to pandas DataFrame (async for large data).

        Args:
            data: Data to convert (dict, list, or DataFrame)

        Returns:
            pandas DataFrame

        Raises:
            ImportError: If pandas not installed
            ValueError: If data cannot be converted
        """
        import pandas as pd

        def _convert():
            if isinstance(data, pd.DataFrame):
                return data

            if isinstance(data, dict):
                if any(isinstance(v, (list, dict)) for v in data.values()):
                    return pd.json_normalize(data)
                return pd.DataFrame([data])

            if isinstance(data, list):
                return pd.DataFrame(data)

            return pd.DataFrame([{"value": data}])

        # Run potentially slow DataFrame construction in thread
        return await asyncio.to_thread(_convert)

    async def store_parquet(
        self,
        data: Any,
        data_type: str,
        prefix: str,
    ) -> tuple[str, float]:
        """Store data as Parquet file in execution-isolated location.

        Args:
            data: Data to store (dict, list, or DataFrame-compatible)
            data_type: Data type for path organization (e.g., "market_charts", "klines")
            prefix: Filename prefix (e.g., "btc_usd_30d")

        Returns:
            Tuple of (full_file_path, size_kb)

        Raises:
            ImportError: If pandas/pyarrow not installed
            ValueError: If data type not supported
            IOError: If write fails
        """
        # Validate data type
        import pandas as pd

        if not isinstance(data, (dict, list, pd.DataFrame)):
            raise ValueError(
                f"Cannot store {type(data).__name__} as Parquet. "
                f"Supported types: dict, list, DataFrame. "
                f"Got: {type(data)}"
            )

        # Validate empty data
        if isinstance(data, (list, dict)) and not data:
            logger.warning(f"Storing empty {type(data).__name__} to Parquet")
        # Convert to DataFrame (async)
        df = await self._to_dataframe(data)

        # Serialize to parquet bytes (async, can be slow for large data)
        def _serialize():
            # Check for snappy availability upfront
            try:
                import snappy
                compression = "snappy"
            except ImportError:
                logger.debug("Snappy compression not available, using gzip")
                compression = "gzip"

            buffer = io.BytesIO()
            df.to_parquet(
                buffer,
                engine="pyarrow",
                compression=compression,
                index=False,
            )
            return buffer.getvalue()

        parquet_bytes = await asyncio.to_thread(_serialize)

        # Generate unique filename with timestamp and UUID suffix
        # Prevents race conditions when multiple tools execute concurrently
        import uuid
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")  # Include microseconds
        hex_suffix = uuid.uuid4().hex[:8]  # 8-char random hex for uniqueness
        filename = f"{prefix}_{timestamp}_{hex_suffix}.parquet"

        # Build flattened 2-level storage key: artifacts/{toolkit_name}/{data_type}/{filename}
        # No date folders - execution scoped by execution_id, timestamp in filename
        # Keeps data_type for LLM browsability (e.g., list_files("artifacts/binance/klines/"))
        key = f"artifacts/{self.toolkit_name}/{data_type}/{filename}"

        # Store via FileStorage (returns full filesystem path)
        full_path = await self.file_storage.put(key, parquet_bytes)

        size_kb = len(parquet_bytes) / 1024
        logger.info(f"Stored Parquet: {full_path} ({size_kb:.1f}KB)")

        return full_path, size_kb

    async def load_parquet(self, key: str) -> list[dict]:
        """Load data from Parquet file.

        Args:
            key: Storage key for Parquet file

        Returns:
            Data as list of dictionaries (records)

        Raises:
            ImportError: If pandas/pyarrow not installed
            FileNotFoundError: If file doesn't exist
        """
        import pandas as pd

        # Get data via FileStorage
        parquet_bytes = await self.file_storage.get(key)
        if parquet_bytes is None:
            raise FileNotFoundError(f"Parquet file not found: {key}")

        # Deserialize parquet (async, can be slow)
        def _deserialize():
            buffer = io.BytesIO(parquet_bytes)
            df = pd.read_parquet(buffer, engine="pyarrow")
            return df.to_dict(orient="records")

        return await asyncio.to_thread(_deserialize)
