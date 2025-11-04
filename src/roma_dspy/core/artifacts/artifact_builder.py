"""
Artifact builder for metadata enrichment and file inspection.

This module provides the ArtifactBuilder class that:
- Creates Artifact instances with enriched metadata
- Uses python-magic for MIME type detection
- Extracts schema from structured data (CSV, Parquet)
- Generates content previews
- Validates file paths for security

All file operations are async to prevent blocking the event loop.
"""

import csv
import mimetypes
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional, Dict, List, Any
from uuid import UUID, uuid4

from loguru import logger

try:
    import aiofiles
    AIOFILES_AVAILABLE = True
except ImportError:
    AIOFILES_AVAILABLE = False
    aiofiles = None  # type: ignore

try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False

try:
    import pyarrow.parquet as pq
    PYARROW_AVAILABLE = True
except ImportError:
    PYARROW_AVAILABLE = False

from roma_dspy.types import (
    Artifact,
    ArtifactMetadata,
    ArtifactType,
    MediaType,
)


class ArtifactBuilder:
    """
    Builder for creating enriched Artifact instances.

    Responsibilities:
    - File type detection via python-magic
    - Metadata enrichment (size, schema, preview)
    - Path validation and normalization
    - Content preview generation
    - Schema extraction for tabular data

    Security:
    - Validates paths to prevent traversal attacks
    - Enforces file size limits to prevent DoS
    - Uses async I/O to prevent event loop blocking
    """

    # Security limits
    MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB
    MAX_PREVIEW_BYTES = 1000  # 1 KB preview

    def __init__(self):
        """Initialize artifact builder with python-magic."""
        if MAGIC_AVAILABLE:
            self.magic_mime = magic.Magic(mime=True)
        else:
            self.magic_mime = None
            logger.warning("python-magic not available, MIME detection will use fallback")

    async def build(
        self,
        name: str,
        artifact_type: ArtifactType,
        storage_path: str,
        created_by_task: str,
        created_by_module: str,
        description: str,
        derived_from: Optional[List[UUID]] = None,
        usage_hints: Optional[List[str]] = None,
        custom_metadata: Optional[Dict[str, Any]] = None,
    ) -> Artifact:
        """
        Build enriched artifact with automatic metadata detection.

        Args:
            name: Human-readable name
            artifact_type: Semantic type (DATA_FETCH, REPORT, etc.)
            storage_path: Path to artifact file
            created_by_task: Task ID that created this
            created_by_module: Module name that created this
            description: Human-readable description
            derived_from: Optional list of parent artifact IDs
            usage_hints: Optional suggestions for downstream use
            custom_metadata: Optional custom metadata fields

        Returns:
            Artifact with enriched metadata

        Raises:
            ValueError: If storage_path is invalid or unsafe
            FileNotFoundError: If storage_path doesn't exist
            PermissionError: If file is not readable
        """
        # Validate and normalize path
        normalized_path = self._validate_path(storage_path)

        # Detect MIME type
        mime_type = self._detect_mime_type(normalized_path)

        # Determine media type from MIME
        media_type = self._mime_to_media_type(mime_type)

        # Get file size
        size_bytes = os.path.getsize(normalized_path)

        # Security check: enforce size limit
        if size_bytes > self.MAX_FILE_SIZE_BYTES:
            logger.warning(
                f"File exceeds size limit: {size_bytes} > {self.MAX_FILE_SIZE_BYTES} bytes",
                path=normalized_path,
            )
            # Still create artifact but skip preview extraction
            preview = None
        else:
            # Generate content preview
            preview = await self._generate_preview(normalized_path, mime_type)

        # Extract schema for structured data
        schema_info = await self._extract_schema(normalized_path, mime_type)

        # Build metadata
        metadata = ArtifactMetadata(
            description=description,
            mime_type=mime_type,
            size_bytes=size_bytes,
            row_count=schema_info.get("row_count"),
            column_count=schema_info.get("column_count"),
            data_schema=schema_info.get("schema"),
            preview=preview,
            usage_hints=usage_hints or [],
            custom=custom_metadata or {},
        )

        # Create artifact
        artifact = Artifact(
            artifact_id=uuid4(),
            name=name,
            artifact_type=artifact_type,
            media_type=media_type,
            storage_path=normalized_path,
            created_by_task=created_by_task,
            created_by_module=created_by_module,
            created_at=datetime.now(UTC),
            metadata=metadata,
            derived_from=derived_from or [],
        )

        logger.debug(
            "Built artifact",
            artifact_id=str(artifact.artifact_id),
            name=name,
            artifact_type=artifact_type,
            path=normalized_path,
        )

        return artifact

    def _validate_path(self, storage_path: str) -> str:
        """
        Validate and normalize storage path.

        Args:
            storage_path: Path to validate

        Returns:
            Normalized absolute path

        Raises:
            ValueError: If path is invalid or unsafe
            FileNotFoundError: If path doesn't exist
        """
        # Convert to Path object
        path = Path(storage_path)

        # Must be absolute
        if not path.is_absolute():
            raise ValueError(f"Storage path must be absolute: {storage_path}")

        # Must exist
        if not path.exists():
            raise FileNotFoundError(f"Storage path does not exist: {storage_path}")

        # Must be a file (not directory)
        if not path.is_file():
            raise ValueError(f"Storage path must be a file: {storage_path}")

        # Resolve to prevent symlink attacks
        resolved = path.resolve()

        # Check for path traversal
        normalized = os.path.normpath(str(resolved))
        if ".." in normalized.split(os.sep):
            raise ValueError(f"Path traversal detected: {storage_path}")

        return normalized

    def _detect_mime_type(self, file_path: str) -> str:
        """
        Detect MIME type using python-magic.

        Args:
            file_path: Path to file

        Returns:
            MIME type string (e.g., "application/json")
        """
        if not MAGIC_AVAILABLE or self.magic_mime is None:
            # Fallback: use file extension
            return self._detect_mime_from_extension(file_path)

        try:
            mime_type = self.magic_mime.from_file(file_path)
            logger.debug(f"Detected MIME type: {mime_type}", path=file_path)
            return mime_type
        except Exception as e:
            logger.warning(f"Failed to detect MIME type: {e}", path=file_path)
            return self._detect_mime_from_extension(file_path)

    def _detect_mime_from_extension(self, file_path: str) -> str:
        """
        Fallback MIME type detection using file extension.

        Args:
            file_path: Path to file

        Returns:
            MIME type string
        """
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "application/octet-stream"

    def _mime_to_media_type(self, mime_type: str) -> MediaType:
        """
        Map MIME type to MediaType enum.

        Args:
            mime_type: MIME type string

        Returns:
            MediaType enum value
        """
        # Extract main type
        main_type = mime_type.split("/")[0]

        if main_type == "text":
            return MediaType.TEXT
        elif main_type == "image":
            return MediaType.IMAGE
        elif main_type == "audio":
            return MediaType.AUDIO
        elif main_type == "video":
            return MediaType.VIDEO
        else:
            # Default to FILE for application/*, etc.
            return MediaType.FILE

    async def _generate_preview(self, file_path: str, mime_type: str) -> Optional[str]:
        """
        Generate content preview for text-based files.

        Args:
            file_path: Path to file
            mime_type: MIME type

        Returns:
            Preview string (first N bytes) or None for binary files
        """
        # Check if aiofiles is available
        if not AIOFILES_AVAILABLE or aiofiles is None:
            logger.debug("Cannot generate preview: aiofiles not available")
            return None

        # Validate inputs
        if not file_path:
            logger.debug("Cannot generate preview: file_path is None or empty")
            return None

        if not mime_type:
            logger.debug("Cannot generate preview: mime_type is None or empty")
            return None

        # Only generate preview for text-based files
        if not mime_type.startswith("text/") and mime_type not in [
            "application/json",
            "application/xml",
            "application/csv",
        ]:
            return None

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = await f.read(self.MAX_PREVIEW_BYTES)
                if len(content) == self.MAX_PREVIEW_BYTES:
                    content += "..."
                return content
        except Exception as e:
            logger.warning(f"Failed to generate preview: {e}", path=file_path)
            return None

    async def _extract_schema(self, file_path: str, mime_type: str) -> Dict[str, Any]:
        """
        Extract schema information from structured data files.

        Args:
            file_path: Path to file
            mime_type: MIME type

        Returns:
            Dictionary with schema info (row_count, column_count, schema)
        """
        # Validate inputs
        if not file_path or not mime_type:
            logger.debug("Cannot extract schema: file_path or mime_type is None")
            return {}

        schema_info: Dict[str, Any] = {}

        # CSV files
        if mime_type == "text/csv" or file_path.endswith(".csv"):
            schema_info = await self._extract_csv_schema(file_path)

        # Parquet files
        elif mime_type == "application/vnd.apache.parquet" or file_path.endswith(".parquet"):
            schema_info = await self._extract_parquet_schema(file_path)

        return schema_info

    async def _extract_csv_schema(self, file_path: str) -> Dict[str, Any]:
        """
        Extract schema from CSV file.

        Args:
            file_path: Path to CSV file

        Returns:
            Dictionary with row_count, column_count, schema
        """
        if not AIOFILES_AVAILABLE or aiofiles is None:
            logger.debug("aiofiles not available, skipping CSV schema extraction", path=file_path)
            return {}

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = await f.read()

                # Handle empty files
                if not content.strip():
                    logger.debug("CSV file is empty", path=file_path)
                    return {}

                reader = csv.DictReader(content.splitlines())

                # Get column names from first row
                fieldnames = reader.fieldnames or []
                column_count = len(fieldnames)

                # Count rows (approximate, since we're reading in memory)
                row_count = sum(1 for _ in reader)

                # Build schema (column_name -> "string" type hint)
                schema = {col: "string" for col in fieldnames}

                return {
                    "row_count": row_count,
                    "column_count": column_count,
                    "schema": schema,
                }
        except Exception as e:
            logger.warning(f"Failed to extract CSV schema: {e}", path=file_path)
            return {}

    async def _extract_parquet_schema(self, file_path: str) -> Dict[str, Any]:
        """
        Extract schema from Parquet file using PyArrow.

        Args:
            file_path: Path to Parquet file

        Returns:
            Dictionary with row_count, column_count, schema
        """
        if not PYARROW_AVAILABLE:
            logger.debug("PyArrow not installed, skipping Parquet schema extraction", path=file_path)
            return {}

        try:
            # Check if file is empty before attempting to read
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                logger.debug("Parquet file is empty (0 bytes)", path=file_path)
                return {}

            # Read Parquet metadata without loading data
            parquet_file = pq.ParquetFile(file_path)
            schema = parquet_file.schema_arrow

            # Extract column info
            column_count = len(schema.names)
            row_count = parquet_file.metadata.num_rows

            # Build schema (column_name -> PyArrow type string)
            schema_dict = {name: str(schema.field(name).type) for name in schema.names}

            return {
                "row_count": row_count,
                "column_count": column_count,
                "schema": schema_dict,
            }
        except Exception as e:
            logger.warning(f"Failed to extract Parquet schema: {e}", path=file_path)
            return {}
