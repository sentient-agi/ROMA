"""
Artifact type definitions for the artifact context management system.

This module defines the ArtifactType enum for semantic artifact classification.
All enums follow the (str, Enum) pattern for DSPy compatibility.

MediaType (TEXT, FILE, IMAGE, etc.) is reused from existing media_type.py.
File format/MIME type detection is handled by python-magic.

All artifacts are execution-scoped (live for duration of execution).
"""

from enum import Enum
from typing import Literal


class ArtifactType(str, Enum):
    """
    MECE taxonomy of artifact types.

    Artifacts are classified by their semantic purpose and content:
    - Data artifacts: Raw, processed, or analyzed data
    - Document artifacts: Reports, code, images, etc.
    """

    # Data artifacts
    DATA_FETCH = "data_fetch"  # Raw data from APIs/tools (e.g., CoinGecko response)
    DATA_PROCESSED = "data_processed"  # Cleaned/transformed data
    DATA_ANALYSIS = "data_analysis"  # Analysis results with insights

    # Document artifacts
    REPORT = "report"  # Written reports (Markdown, PDF, HTML)
    PLOT = "plot"  # Visualizations (charts, graphs)
    CODE = "code"  # Generated code
    IMAGE = "image"  # Images (PNG, JPG, etc.)
    DOCUMENT = "document"  # General documents

    @classmethod
    def from_string(cls, value: str) -> "ArtifactType":
        """
        Create ArtifactType from string value.

        Args:
            value: String value (case-insensitive)

        Returns:
            ArtifactType enum value

        Raises:
            ValueError: If value is not a valid artifact type
        """
        try:
            return cls(value.lower())
        except ValueError:
            valid = ", ".join([t.value for t in cls])
            raise ValueError(
                f"Invalid artifact type: {value}. Valid types: {valid}"
            )

    @property
    def is_data(self) -> bool:
        """Check if artifact is a data type."""
        return self in (
            ArtifactType.DATA_FETCH,
            ArtifactType.DATA_PROCESSED,
            ArtifactType.DATA_ANALYSIS,
        )

    @property
    def is_document(self) -> bool:
        """Check if artifact is a document type."""
        return self in (
            ArtifactType.REPORT,
            ArtifactType.PLOT,
            ArtifactType.CODE,
            ArtifactType.IMAGE,
            ArtifactType.DOCUMENT,
        )

    @classmethod
    def from_file_extension(cls, extension: str) -> "ArtifactType":
        """
        Infer artifact type from file extension.

        Args:
            extension: File extension (with or without leading dot)

        Returns:
            ArtifactType enum value based on extension

        Example:
            >>> ArtifactType.from_file_extension(".csv")
            <ArtifactType.DATA_PROCESSED: 'data_processed'>
            >>> ArtifactType.from_file_extension("png")
            <ArtifactType.PLOT: 'plot'>
        """
        # Normalize extension (remove leading dot, lowercase)
        ext = extension.lower().lstrip(".")

        # Extension to type mapping
        EXTENSION_MAP = {
            # Data files
            "csv": cls.DATA_PROCESSED,
            "json": cls.DATA_PROCESSED,
            "parquet": cls.DATA_PROCESSED,
            "xlsx": cls.DATA_PROCESSED,
            "xls": cls.DATA_PROCESSED,
            "tsv": cls.DATA_PROCESSED,
            "jsonl": cls.DATA_PROCESSED,
            # Plots/visualizations
            "png": cls.PLOT,
            "jpg": cls.PLOT,
            "jpeg": cls.PLOT,
            "svg": cls.PLOT,
            "pdf": cls.PLOT,  # Could be report or plot, default to plot
            # Reports
            "md": cls.REPORT,
            "markdown": cls.REPORT,
            "txt": cls.REPORT,
            "html": cls.REPORT,
            "htm": cls.REPORT,
            # Code
            "py": cls.CODE,
            "js": cls.CODE,
            "ts": cls.CODE,
            "java": cls.CODE,
            "cpp": cls.CODE,
            "c": cls.CODE,
            "go": cls.CODE,
            "rs": cls.CODE,
            "sh": cls.CODE,
            # Images (non-plot)
            "gif": cls.IMAGE,
            "bmp": cls.IMAGE,
            "tiff": cls.IMAGE,
            "webp": cls.IMAGE,
            # General documents
            "docx": cls.DOCUMENT,
            "doc": cls.DOCUMENT,
            "pptx": cls.DOCUMENT,
            "ppt": cls.DOCUMENT,
        }

        return EXTENSION_MAP.get(ext, cls.DOCUMENT)  # Default to DOCUMENT


# Type literal for type hints
ArtifactTypeLiteral = Literal[
    "data_fetch",
    "data_processed",
    "data_analysis",
    "report",
    "plot",
    "code",
    "image",
    "document",
]
