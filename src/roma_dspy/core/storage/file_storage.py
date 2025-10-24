"""File storage with execution ID isolation and goofys compatibility."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union
from uuid import uuid4

from loguru import logger

from roma_dspy.config.schemas.storage import StorageConfig


class FileStorage:
    """
    File storage scoped to execution ID with goofys S3 mounting compatibility.

    All paths are scoped to: {base_path}/executions/{execution_id}/

    Provides goofys-compatible file operations:
    - Buffered writes (avoids small writes that goofys handles poorly)
    - Atomic operations via temp files + rename (single S3 PUT)
    - Sequential write patterns (no append/seek)

    Folder structure:
        {base_path}/
        └── executions/
            └── {execution_id}/
                ├── artifacts/              # General artifacts & toolkit storage
                │   ├── {toolkit_name}/     # Toolkit-organized storage (e.g., coingecko, binance)
                │   │   └── {data_type}/    # Data type folders (e.g., klines, coin_prices)
                │   │       └── *.parquet   # Timestamped parquet files
                ├── temp/                   # Temporary files
                ├── results/                # Execution results
                │   ├── plots/              # Plot outputs
                │   └── reports/            # Report outputs
                ├── outputs/                # Agent outputs
                └── logs/                   # Execution logs

    Example:
        ```python
        from roma_dspy.config.manager import ConfigManager

        config = ConfigManager.load()
        storage = FileStorage(
            config=config.storage,
            execution_id="20250930_143022_abc12345"
        )

        # Get paths
        artifacts_path = storage.get_artifacts_path("coingecko/coin_prices/btc_usd.parquet")
        temp_path = storage.get_temp_path("processing.tmp")
        plot_path = storage.get_plots_path("chart.png")

        # Write with buffering (goofys-optimized)
        await storage.put("coingecko/coin_prices/btc_usd.parquet", data_bytes)

        # Key-based operations with metadata
        await storage.put("my_file.json", json_data, metadata={"version": "1.0"})
        data = await storage.get("my_file.json")

        # Toolkit storage follows: {toolkit_name}/{data_type}/{filename}
        # Example: artifacts/binance/klines/BTCUSDT_1h_20250122_143022_a1b2c3d4.parquet
        ```
    """

    # Standard subdirectories
    ARTIFACTS_SUBDIR = "artifacts"
    TEMP_SUBDIR = "temp"
    RESULTS_SUBDIR = "results"
    PLOTS_SUBDIR = "results/plots"
    REPORTS_SUBDIR = "results/reports"
    OUTPUTS_SUBDIR = "outputs"
    LOGS_SUBDIR = "logs"

    def __init__(
        self,
        config: StorageConfig,
        execution_id: str,
    ):
        """Initialize file storage.

        Args:
            config: StorageConfig with base_path, max_file_size, buffer_size
            execution_id: Execution ID for isolation
        """
        self.config = config
        self.execution_id = execution_id
        self.buffer_size = config.buffer_size
        self.max_file_size = config.max_file_size

        # Base path from config (e.g., /opt/sentient from STORAGE_BASE_PATH env var)
        self.base_path = Path(config.base_path)

        # Execution-scoped root: {base_path}/executions/{execution_id}/
        self.root = self.base_path / "executions" / execution_id

        # Create all directories immediately (sync, works in all contexts)
        self.root.mkdir(parents=True, exist_ok=True)
        for subdir in [
            self.ARTIFACTS_SUBDIR,
            self.TEMP_SUBDIR,
            self.RESULTS_SUBDIR,
            self.PLOTS_SUBDIR,
            self.REPORTS_SUBDIR,
            self.OUTPUTS_SUBDIR,
            self.LOGS_SUBDIR,
        ]:
            (self.root / subdir).mkdir(parents=True, exist_ok=True)

        logger.info(f"Initialized FileStorage for execution: {execution_id} at {self.root}")

    # ==================== DRY Path Helpers ====================

    def _get_subdir_path(self, subdir: str, key: str = "") -> Path:
        """DRY helper for subdirectory paths.

        Args:
            subdir: Subdirectory name
            key: Optional key/filename within subdirectory

        Returns:
            Full path in subdirectory
        """
        if key:
            return self.root / subdir / self.normalize_key(key)
        return self.root / subdir

    def get_artifacts_path(self, key: str = "") -> Path:
        """Get path in artifacts subdirectory."""
        return self._get_subdir_path(self.ARTIFACTS_SUBDIR, key)

    def get_temp_path(self, key: str = "") -> Path:
        """Get path in temp subdirectory."""
        return self._get_subdir_path(self.TEMP_SUBDIR, key)

    def get_results_path(self, key: str = "") -> Path:
        """Get path in results subdirectory."""
        return self._get_subdir_path(self.RESULTS_SUBDIR, key)

    def get_plots_path(self, key: str = "") -> Path:
        """Get path in plots subdirectory."""
        return self._get_subdir_path(self.PLOTS_SUBDIR, key)

    def get_reports_path(self, key: str = "") -> Path:
        """Get path in reports subdirectory."""
        return self._get_subdir_path(self.REPORTS_SUBDIR, key)

    def get_outputs_path(self, key: str = "") -> Path:
        """Get path in outputs subdirectory."""
        return self._get_subdir_path(self.OUTPUTS_SUBDIR, key)

    def get_logs_path(self, key: str = "") -> Path:
        """Get path in logs subdirectory."""
        return self._get_subdir_path(self.LOGS_SUBDIR, key)

    def get_full_path(self, key: str) -> Path:
        """Get full path for key relative to execution root.

        Args:
            key: Storage key (can include subdirectory, e.g., "artifacts/data.json")

        Returns:
            Full filesystem path
        """
        normalized_key = self.normalize_key(key)
        return self.root / normalized_key

    # ==================== Key Normalization & Generation ====================

    def normalize_key(self, key: str) -> str:
        """Normalize storage key to consistent format.

        Args:
            key: Raw key

        Returns:
            Normalized key (no leading slashes, forward slashes only)
        """
        # Remove leading/trailing slashes, normalize path separators
        normalized = key.strip("/").replace("\\", "/")

        # Remove double slashes
        while "//" in normalized:
            normalized = normalized.replace("//", "/")

        return normalized

    def generate_key(self, prefix: str = "", suffix: str = "") -> str:
        """Generate unique storage key.

        Args:
            prefix: Key prefix
            suffix: Key suffix (e.g., file extension)

        Returns:
            Unique storage key
        """
        unique_id = str(uuid4())
        return f"{prefix}{unique_id}{suffix}"

    # ==================== Key-Based Storage Operations ====================

    async def put(
        self,
        key: str,
        data: bytes,
        metadata: Optional[dict[str, str]] = None
    ) -> str:
        """Store data at key path with optional metadata.

        Args:
            key: Storage key (relative to execution root)
            data: Raw data to store
            metadata: Optional metadata (stored as .metadata file)

        Returns:
            Full path to stored file

        Raises:
            ValueError: If data exceeds max_file_size
        """
        if len(data) > self.max_file_size:
            raise ValueError(
                f"File size {len(data)} bytes exceeds maximum {self.max_file_size} bytes"
            )

        full_path = self.get_full_path(key)
        full_path.parent.mkdir(parents=True, exist_ok=True)

        # Atomic write via temp file + rename
        temp_path = full_path.with_suffix(full_path.suffix + ".tmp")

        try:
            with open(temp_path, "wb", buffering=self.buffer_size) as f:
                f.write(data)

            # Atomic rename (overwrites destination)
            temp_path.replace(full_path)

            # Store metadata if provided
            if metadata:
                await self._store_metadata(full_path, metadata)

            logger.debug(f"Stored {len(data)} bytes at {key}")
            return str(full_path)

        except Exception as e:
            # Clean up temp file on error
            if temp_path.exists():
                temp_path.unlink()
            logger.error(f"Failed to store data at {key}: {e}")
            raise

    async def get(self, key: str) -> Optional[bytes]:
        """Retrieve data by key.

        Args:
            key: Storage key

        Returns:
            Raw data or None if not found
        """
        full_path = self.get_full_path(key)

        if not full_path.exists():
            return None

        try:
            with open(full_path, "rb", buffering=self.buffer_size) as f:
                data = f.read()

            logger.debug(f"Retrieved {len(data)} bytes from {key}")
            return data

        except Exception as e:
            logger.error(f"Failed to retrieve data from {key}: {e}")
            return None

    async def put_text(
        self,
        key: str,
        text: str,
        encoding: str = "utf-8",
        metadata: Optional[dict[str, str]] = None
    ) -> str:
        """Store text content.

        Args:
            key: Storage key
            text: Text content
            encoding: Text encoding
            metadata: Optional metadata

        Returns:
            Full path to stored file
        """
        data = text.encode(encoding)
        return await self.put(key, data, metadata)

    async def get_text(self, key: str, encoding: str = "utf-8") -> Optional[str]:
        """Retrieve text content.

        Args:
            key: Storage key
            encoding: Text encoding

        Returns:
            Text content or None if not found
        """
        data = await self.get(key)
        if data is None:
            return None

        try:
            return data.decode(encoding)
        except UnicodeDecodeError as e:
            logger.error(f"Failed to decode text from {key}: {e}")
            return None

    async def put_json(self, key: str, obj: Any, metadata: Optional[dict[str, str]] = None) -> str:
        """Store JSON-serializable object.

        Args:
            key: Storage key
            obj: JSON-serializable object
            metadata: Optional metadata

        Returns:
            Full path to stored file
        """
        json_text = json.dumps(obj, indent=2, default=str)
        return await self.put_text(key, json_text, metadata=metadata)

    async def get_json(self, key: str) -> Optional[Any]:
        """Retrieve JSON object.

        Args:
            key: Storage key

        Returns:
            Parsed JSON object or None if not found
        """
        text = await self.get_text(key)
        if text is None:
            return None

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON from {key}: {e}")
            return None

    async def exists(self, key: str) -> bool:
        """Check if file exists at key path.

        Args:
            key: Storage key

        Returns:
            True if file exists
        """
        full_path = self.get_full_path(key)
        return full_path.exists() and full_path.is_file()

    async def get_size(self, key: str) -> Optional[int]:
        """Get file size in bytes.

        Args:
            key: Storage key

        Returns:
            Size in bytes or None if not found
        """
        full_path = self.get_full_path(key)
        if not full_path.exists():
            return None
        return full_path.stat().st_size

    async def delete(self, key: str) -> bool:
        """Delete file at key path.

        Args:
            key: Storage key

        Returns:
            True if deleted, False if not found
        """
        full_path = self.get_full_path(key)

        if not full_path.exists():
            return False

        try:
            full_path.unlink()
            logger.debug(f"Deleted file at {key}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete file at {key}: {e}")
            return False

    async def list_keys(self, prefix: str = "") -> list[str]:
        """List all keys with optional prefix filter.

        Args:
            prefix: Key prefix to filter by

        Returns:
            List of matching keys (relative to execution root)
        """
        if prefix:
            search_path = self.get_full_path(prefix)
            # If prefix is a directory, search inside it
            if search_path.is_dir():
                pattern = "**/*"
                search_root = search_path
            else:
                # Search for files matching prefix pattern
                pattern = f"{search_path.name}*"
                search_root = search_path.parent
        else:
            pattern = "**/*"
            search_root = self.root

        try:
            if "**" in pattern:
                files = search_root.rglob(pattern.replace("**/*", "*"))
            else:
                files = search_root.glob(pattern)

            # Convert to relative keys and filter files only
            keys = []
            for file_path in files:
                if file_path.is_file():
                    relative_path = file_path.relative_to(self.root)
                    keys.append(str(relative_path))

            return sorted(keys)

        except Exception as e:
            logger.error(f"Failed to list keys with prefix '{prefix}': {e}")
            return []

    # ==================== File Operations ====================

    async def copy_local(self, source_path: Union[str, Path], key: str) -> str:
        """Copy local file to storage.

        Args:
            source_path: Path to local file
            key: Storage key for destination

        Returns:
            Full path to stored file

        Raises:
            FileNotFoundError: If source file not found
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        dest_path = self.get_full_path(key)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.copy2(source, dest_path)
            logger.debug(f"Copied {source_path} to {key}")
            return str(dest_path)

        except Exception as e:
            logger.error(f"Failed to copy {source_path} to {key}: {e}")
            raise

    async def move_local(self, source_path: Union[str, Path], key: str) -> str:
        """Move local file to storage.

        Args:
            source_path: Path to local file
            key: Storage key for destination

        Returns:
            Full path to stored file

        Raises:
            FileNotFoundError: If source file not found
        """
        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        dest_path = self.get_full_path(key)
        dest_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            shutil.move(str(source), str(dest_path))
            logger.debug(f"Moved {source_path} to {key}")
            return str(dest_path)

        except Exception as e:
            logger.error(f"Failed to move {source_path} to {key}: {e}")
            raise

    # ==================== Cleanup Operations ====================

    async def cleanup_temp_files(self, older_than_hours: int = 24) -> int:
        """Clean up temporary files older than specified hours.

        Args:
            older_than_hours: Remove files older than this many hours

        Returns:
            Number of files cleaned up
        """
        temp_path = self.root / self.TEMP_SUBDIR

        if not temp_path.exists():
            return 0

        try:
            from datetime import timedelta
            cutoff_time = datetime.now().timestamp() - (older_than_hours * 3600)

            cleaned_count = 0
            for file_path in temp_path.rglob("*"):
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    file_path.unlink()
                    cleaned_count += 1

            logger.info(f"Cleaned up {cleaned_count} temporary files")
            return cleaned_count

        except Exception as e:
            logger.error(f"Failed to clean up temp files: {e}")
            return 0

    async def cleanup_execution_temp_files(self) -> int:
        """Clean up all temporary files for this execution.

        Returns:
            Number of files cleaned
        """
        temp_path = self.root / self.TEMP_SUBDIR

        if not temp_path.exists():
            return 0

        cleaned_count = 0
        try:
            for file_path in temp_path.rglob("*"):
                if file_path.is_file():
                    file_path.unlink()
                    cleaned_count += 1

            logger.info(
                f"Cleaned {cleaned_count} temp files for execution {self.execution_id}"
            )
            return cleaned_count

        except Exception as e:
            logger.error(f"Failed to clean temp files for {self.execution_id}: {e}")
            return cleaned_count

    # ==================== Metadata & Info ====================

    async def _store_metadata(self, file_path: Path, metadata: dict[str, str]) -> None:
        """Store metadata as .metadata file.

        Args:
            file_path: Path to file
            metadata: Metadata dictionary
        """
        try:
            metadata_path = file_path.with_suffix(file_path.suffix + ".metadata")
            metadata_content = json.dumps(metadata, indent=2)

            with open(metadata_path, "w") as f:
                f.write(metadata_content)

        except Exception as e:
            # Metadata storage is optional - don't fail the main operation
            logger.warning(f"Failed to store metadata for {file_path}: {e}")

    async def get_storage_info(self) -> dict[str, Any]:
        """Get storage usage information for this execution.

        Returns:
            Dictionary with storage statistics
        """
        try:
            total_size = 0
            file_count = 0

            for file_path in self.root.rglob("*"):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
                    file_count += 1

            return {
                "execution_id": self.execution_id,
                "root_path": str(self.root),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "file_count": file_count,
                "artifacts_path": str(self.get_artifacts_path()),
                "temp_path": str(self.get_temp_path()),
                "results_path": str(self.get_results_path()),
                "plots_path": str(self.get_plots_path()),
                "reports_path": str(self.get_reports_path()),
                "outputs_path": str(self.get_outputs_path()),
                "logs_path": str(self.get_logs_path()),
            }

        except Exception as e:
            logger.error(f"Failed to get storage info: {e}")
            return {"error": str(e)}
