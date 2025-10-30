"""File loading utilities with format detection and compression support."""

from __future__ import annotations

import gzip
import json
import os
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

# Platform-specific imports for file locking
try:
    import fcntl  # Unix/Linux/macOS
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

try:
    import msvcrt  # Windows
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


@contextmanager
def file_lock(file_handle, exclusive: bool = True):
    """Cross-platform file locking context manager.

    Args:
        file_handle: Open file handle to lock
        exclusive: Whether to acquire exclusive lock (True) or shared lock (False)

    Yields:
        File handle (for use in with statement)

    Note:
        - On Unix/Linux/macOS: Uses fcntl for advisory locking
        - On Windows: Uses msvcrt for mandatory locking
        - Releases lock automatically on context exit
        - If locking is not available, logs warning and proceeds without lock
    """
    lock_acquired = False

    try:
        if HAS_FCNTL:
            # Unix/Linux/macOS - advisory locking
            lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            try:
                fcntl.flock(file_handle.fileno(), lock_type)
                lock_acquired = True
                logger.debug(f"Acquired {'exclusive' if exclusive else 'shared'} file lock (fcntl)")
            except (OSError, IOError) as e:
                logger.warning(f"Failed to acquire file lock: {e}")

        elif HAS_MSVCRT:
            # Windows - mandatory locking
            try:
                # Lock first byte of file (msvcrt locks specific byte ranges)
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK if exclusive else msvcrt.LK_NBRLCK, 1)
                lock_acquired = True
                logger.debug(f"Acquired {'exclusive' if exclusive else 'shared'} file lock (msvcrt)")
            except (OSError, IOError) as e:
                logger.warning(f"Failed to acquire file lock: {e}")
        else:
            # No locking available
            logger.warning("File locking not available on this platform - proceeding without lock")

        yield file_handle

    finally:
        # Release lock
        if lock_acquired:
            try:
                if HAS_FCNTL:
                    fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
                    logger.debug("Released file lock (fcntl)")
                elif HAS_MSVCRT:
                    msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
                    logger.debug("Released file lock (msvcrt)")
            except (OSError, IOError) as e:
                logger.warning(f"Failed to release file lock: {e}")


class FileLoader:
    """Handles file loading with format detection and compression.

    Supports:
    - Auto-detection of .json vs .json.gz
    - Transparent gzip decompression
    - Size limit enforcement
    - Streaming for large files
    """

    # Max uncompressed size (500 MB)
    MAX_SIZE_BYTES = 500 * 1024 * 1024

    # Threshold for streaming (50 MB)
    STREAMING_THRESHOLD = 50 * 1024 * 1024

    # Magic bytes for format detection
    GZIP_MAGIC = b"\x1f\x8b"  # gzip magic bytes
    JSON_MAGIC = b"{"  # JSON starts with '{'

    @staticmethod
    def load_json(filepath: Path, max_size: Optional[int] = None) -> Dict[str, Any]:
        """Load JSON file with auto-detection and decompression.

        Args:
            filepath: Path to .json or .json.gz file
            max_size: Max size in bytes (default: 500MB)

        Returns:
            Parsed JSON data

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file exceeds size limit or is invalid format
            json.JSONDecodeError: If JSON is malformed
        """
        if not filepath.exists():
            raise FileNotFoundError(f"File not found: {filepath}")

        if max_size is None:
            max_size = FileLoader.MAX_SIZE_BYTES

        # Check file size
        file_size = filepath.stat().st_size
        if file_size > max_size:
            raise ValueError(
                f"File too large: {file_size / 1024 / 1024:.1f} MB "
                f"(max: {max_size / 1024 / 1024:.1f} MB)"
            )

        # Detect format
        is_compressed = FileLoader.is_compressed(filepath)

        logger.debug(
            f"Loading {'compressed' if is_compressed else 'plain'} JSON: {filepath} "
            f"({file_size / 1024:.1f} KB)"
        )

        # Load based on compression
        if is_compressed:
            return FileLoader._load_gzip_json(filepath, max_size)
        else:
            return FileLoader._load_plain_json(filepath)

    @staticmethod
    def is_compressed(filepath: Path) -> bool:
        """Detect if file is gzip compressed.

        Uses magic bytes (first 2 bytes) for reliable detection.

        Args:
            filepath: Path to file

        Returns:
            True if file is gzip compressed
        """
        # First check extension (fast path)
        if filepath.suffix in [".gz", ".gzip"]:
            return True

        # Check magic bytes (reliable)
        try:
            with filepath.open("rb") as f:
                magic = f.read(2)
                return magic == FileLoader.GZIP_MAGIC
        except Exception:
            return False

    @staticmethod
    def _load_plain_json(filepath: Path) -> Dict[str, Any]:
        """Load plain JSON file with shared file locking.

        Args:
            filepath: Path to .json file

        Returns:
            Parsed JSON

        Raises:
            json.JSONDecodeError: If JSON is malformed
        """
        with filepath.open("r", encoding="utf-8") as f:
            with file_lock(f, exclusive=False):  # Shared lock for reading
                return json.load(f)

    @staticmethod
    def _load_gzip_json(filepath: Path, max_uncompressed_size: int) -> Dict[str, Any]:
        """Load gzip-compressed JSON file with shared file locking.

        Uses BytesIO buffer to avoid memory spike from string concatenation.
        More memory-efficient than accumulating in string.

        Args:
            filepath: Path to .json.gz file
            max_uncompressed_size: Max uncompressed size

        Returns:
            Parsed JSON

        Raises:
            ValueError: If uncompressed size exceeds limit
            json.JSONDecodeError: If JSON is malformed
        """
        # Read compressed data with shared lock, accumulate in BytesIO buffer
        buffer = BytesIO()

        with gzip.open(filepath, "rb") as f:
            with file_lock(f, exclusive=False):  # Shared lock for reading
                chunk_size = 1024 * 1024  # 1 MB chunks

                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                    # Write to buffer instead of string concatenation (more efficient)
                    buffer.write(chunk)

                    # Check if we've exceeded limit
                    current_size = buffer.tell()
                    if current_size > max_uncompressed_size:
                        raise ValueError(
                            f"Uncompressed size exceeds limit "
                            f"({max_uncompressed_size / 1024 / 1024:.1f} MB)"
                        )

        # Parse JSON from buffer (more efficient than json.loads(string))
        buffer.seek(0)
        return json.load(buffer)

    @staticmethod
    def save_json(
        data: Dict[str, Any],
        filepath: Path,
        compress: bool = False,
        pretty: bool = True,
    ) -> int:
        """Save JSON data with optional compression and file locking.

        Uses cross-platform file locking to prevent concurrent write corruption.
        On Unix/Linux/macOS uses fcntl, on Windows uses msvcrt.

        Args:
            data: Data to save
            filepath: Output path
            compress: Whether to compress with gzip
            pretty: Whether to pretty-print JSON

        Returns:
            Size of written file in bytes

        Raises:
            OSError: If write fails
        """
        # Ensure parent directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)

        if compress:
            # Write compressed with file locking
            with gzip.open(filepath, "wt", encoding="utf-8") as f:
                with file_lock(f, exclusive=True):
                    if pretty:
                        json.dump(data, f, indent=2, default=str)
                    else:
                        json.dump(data, f, default=str)
        else:
            # Write plain with file locking
            with filepath.open("w", encoding="utf-8") as f:
                with file_lock(f, exclusive=True):
                    if pretty:
                        json.dump(data, f, indent=2, default=str)
                    else:
                        json.dump(data, f, default=str)

        return filepath.stat().st_size

    @staticmethod
    def auto_compress_if_large(
        data: Dict[str, Any],
        filepath: Path,
        threshold_bytes: int = 10 * 1024 * 1024,  # 10 MB
    ) -> tuple[Path, bool]:
        """Save JSON with auto-compression if size exceeds threshold.

        Args:
            data: Data to save
            filepath: Base output path (may add .gz)
            threshold_bytes: Size threshold for compression (default: 10MB)

        Returns:
            Tuple of (final_filepath, was_compressed)

        Raises:
            OSError: If write fails
        """
        # Estimate size
        json_str = json.dumps(data, default=str)
        estimated_size = len(json_str.encode("utf-8"))

        logger.debug(f"Estimated export size: {estimated_size / 1024 / 1024:.1f} MB")

        # Decide whether to compress
        should_compress = estimated_size > threshold_bytes

        if should_compress:
            # Ensure .gz extension
            if not str(filepath).endswith(".gz"):
                final_path = Path(str(filepath) + ".gz")
            else:
                final_path = filepath

            logger.info(f"Compressing export (size > {threshold_bytes / 1024 / 1024:.1f} MB)")
            FileLoader.save_json(data, final_path, compress=True)

            return final_path, True
        else:
            # Save uncompressed
            # Remove .gz extension if present
            if str(filepath).endswith(".gz"):
                final_path = Path(str(filepath)[:-3])
            else:
                final_path = filepath

            FileLoader.save_json(data, final_path, compress=False)

            return final_path, False
