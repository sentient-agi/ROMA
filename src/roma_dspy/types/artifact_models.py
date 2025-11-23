"""
Pydantic models for the artifact context management system.

This module defines the core data models for artifact tracking:
- ArtifactMetadata: Rich metadata about artifact content
- Artifact: Complete artifact record with lineage and metadata
- ArtifactReference: Lightweight reference for XML serialization
- ArtifactRegistrationRequest: Input model for artifact registration tool

All artifacts are execution-scoped (live for duration of execution).
MIME type detection handled by python-magic.
Media type classification uses existing MediaType enum.
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator

from roma_dspy.types.artifact_types import ArtifactType
from roma_dspy.types.media_type import MediaType


def _escape_xml(text: str) -> str:
    """
    Escape XML special characters to prevent parsing errors.

    Shared utility for all artifact XML serialization.
    """
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


class ArtifactRegistrationRequest(BaseModel):
    """
    Input model for artifact registration.

    Used by register_artifact tool to accept structured input.
    Supports both single and batch registration.

    Attributes:
        file_path: Absolute path to the file to register
        name: Human-readable name for the artifact
        artifact_type: Type of artifact (data_fetch, data_processed, etc.)
        description: Description of what this artifact contains
        derived_from: Optional comma-separated artifact IDs this was derived from
    """

    file_path: str = Field(..., description="Absolute path to the file")
    name: str = Field(..., description="Human-readable artifact name")
    artifact_type: str = Field(
        ...,
        description="Artifact type: data_fetch, data_processed, data_analysis, "
        "report, plot, code, image, document",
    )
    description: str = Field(..., description="Description of artifact contents")
    derived_from: Optional[str] = Field(
        None, description="Comma-separated artifact IDs this was derived from"
    )


class ArtifactMetadata(BaseModel):
    """
    Rich metadata about artifact content.

    Attributes:
        description: Human-readable description of what this artifact contains
        mime_type: MIME type detected by python-magic (e.g., "application/json")
        size_bytes: File size in bytes (for file-based artifacts)
        row_count: Number of rows (for tabular data like CSV/Parquet)
        column_count: Number of columns (for tabular data)
        data_schema: Schema information (for structured data)
        preview: Short preview of content (first few lines/rows)
        usage_hints: Suggestions for how downstream tasks might use this artifact
        custom: Additional custom metadata fields
    """

    description: str = Field(..., description="Human-readable description")
    mime_type: Optional[str] = Field(None, description="MIME type from python-magic")
    size_bytes: Optional[int] = Field(None, ge=0, description="File size in bytes")

    # Tabular data metadata
    row_count: Optional[int] = Field(None, ge=0, description="Number of rows")
    column_count: Optional[int] = Field(None, ge=0, description="Number of columns")
    data_schema: Optional[Dict[str, str]] = Field(
        None, description="Schema (column_name -> type)"
    )

    # Content preview
    preview: Optional[str] = Field(None, description="Content preview (truncated)")

    # Usage guidance
    usage_hints: Optional[List[str]] = Field(
        None, description="Suggestions for downstream use"
    )

    # Extensibility
    custom: Dict[str, Any] = Field(default_factory=dict, description="Custom metadata")

    @field_validator("preview")
    @classmethod
    def validate_preview_length(cls, v: Optional[str]) -> Optional[str]:
        """Ensure preview is reasonably sized (max 1000 chars)."""
        if v and len(v) > 1000:
            return v[:997] + "..."
        return v


class Artifact(BaseModel):
    """
    Complete artifact record with lineage and metadata.

    Attributes:
        artifact_id: Unique identifier (UUID)
        name: Human-readable name
        artifact_type: Semantic type (DATA_FETCH, REPORT, etc.)
        media_type: Media classification (TEXT, FILE, IMAGE, etc.)
        storage_path: Absolute path to artifact file/data
        created_by_task: Task ID that created this artifact
        created_by_module: Module name that created this artifact
        created_at: Creation timestamp
        metadata: Rich metadata about content
        derived_from: List of parent artifact IDs (lineage tracking)
    """

    artifact_id: UUID = Field(default_factory=uuid4, description="Unique identifier")
    name: str = Field(..., description="Human-readable name")
    artifact_type: ArtifactType = Field(..., description="Semantic type")
    media_type: MediaType = Field(..., description="Media classification")
    storage_path: str = Field(..., description="Absolute path to artifact")

    # Provenance
    created_by_task: str = Field(..., description="Task ID that created this")
    created_by_module: str = Field(
        ..., description="Module name (Executor, Planner, etc.)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="Creation timestamp"
    )

    # Content metadata
    metadata: ArtifactMetadata = Field(..., description="Rich metadata")

    # Lineage
    derived_from: List[UUID] = Field(
        default_factory=list, description="Parent artifact IDs"
    )

    @field_validator("storage_path")
    @classmethod
    def validate_storage_path(cls, v: str) -> str:
        """Ensure storage path is absolute and safe."""
        import os

        # Must be absolute path
        if not os.path.isabs(v):
            raise ValueError(f"Storage path must be absolute: {v}")

        # Path traversal check: resolve and check if it escapes original prefix
        try:
            normalized = os.path.normpath(v)
            # Check for .. in path components
            if ".." in v:
                raise ValueError(f"Path traversal detected in storage_path: {v}")
        except Exception:
            raise ValueError(f"Invalid storage path: {v}")

        return normalized

    def model_dump_summary(self) -> Dict[str, Any]:
        """
        Serialize artifact to summary dict (for logging/display).

        Returns:
            Dictionary with key artifact info (excludes full metadata)
        """
        return {
            "artifact_id": str(self.artifact_id),
            "name": self.name,
            "type": self.artifact_type.value,
            "media": self.media_type.value,
            "path": self.storage_path,
            "created_by": f"{self.created_by_module}/{self.created_by_task}",
            "created_at": self.created_at.isoformat(),
            "description": self.metadata.description,
        }


class ArtifactReference(BaseModel):
    """
    Artifact reference for XML serialization in context with full metadata.

    Used in ExecutionContext to provide available artifacts to downstream tasks
    with complete metadata for effective reuse (structure info, schema, preview).

    Attributes:
        artifact_id: Unique identifier
        name: Human-readable name
        artifact_type: Semantic type
        storage_path: Path to artifact
        description: Brief description from metadata (convenience field)
        created_by_task: Task ID that created this
        relevance_score: Optional relevance score for context ranking
        metadata: Full artifact metadata (schema, preview, size, etc.)
    """

    artifact_id: UUID = Field(..., description="Unique identifier")
    name: str = Field(..., description="Human-readable name")
    artifact_type: ArtifactType = Field(..., description="Semantic type")
    storage_path: str = Field(..., description="Path to artifact")
    description: str = Field(
        ..., description="Brief description (from metadata.description)"
    )
    created_by_task: str = Field(..., description="Task ID that created this")
    relevance_score: Optional[float] = Field(
        None, ge=0.0, le=1.0, description="Relevance score"
    )
    metadata: ArtifactMetadata = Field(..., description="Full artifact metadata")

    @classmethod
    def from_artifact(
        cls, artifact: Artifact, relevance_score: Optional[float] = None
    ) -> "ArtifactReference":
        """
        Create reference from full artifact.

        Args:
            artifact: Full artifact to create reference from
            relevance_score: Optional relevance score for context ranking

        Returns:
            Artifact reference with full metadata
        """
        return cls(
            artifact_id=artifact.artifact_id,
            name=artifact.name,
            artifact_type=artifact.artifact_type,
            storage_path=artifact.storage_path,
            description=artifact.metadata.description,
            created_by_task=artifact.created_by_task,
            relevance_score=relevance_score,
            metadata=artifact.metadata,
        )

    def to_xml_element(self) -> str:
        """
        Serialize to XML element string for context with full metadata.

        This is the SINGLE SOURCE OF TRUTH for artifact XML serialization.
        Called from ExecutorSpecificContext, PlannerSpecificContext, and AggregatorSpecificContext.

        Returns:
            XML string with artifact info and nested metadata (schema, structure, preview)
        """
        relevance = (
            f' relevance="{self.relevance_score}"'
            if self.relevance_score is not None
            else ""
        )

        xml_parts = [
            f'<artifact id="{self.artifact_id}" '
            f'name="{self.name}" '
            f'type="{self.artifact_type.value}" '
            f'path="{self.storage_path}" '
            f'task="{self.created_by_task}"'
            f"{relevance}>"
        ]

        # Description
        xml_parts.append(
            f"  <description>{_escape_xml(self.description)}</description>"
        )

        # Metadata section (only if we have meaningful metadata)
        metadata_parts = []

        # Basic file info
        if self.metadata.mime_type:
            metadata_parts.append(
                f"    <mime_type>{_escape_xml(self.metadata.mime_type)}</mime_type>"
            )
        if self.metadata.size_bytes is not None:
            size_kb = self.metadata.size_bytes / 1024
            metadata_parts.append(
                f"    <size_bytes>{self.metadata.size_bytes}</size_bytes>"
            )
            metadata_parts.append(f"    <size_kb>{size_kb:.2f}</size_kb>")

        # Structure info (for tabular data)
        if self.metadata.row_count is not None:
            metadata_parts.append(
                f"    <row_count>{self.metadata.row_count}</row_count>"
            )
        if self.metadata.column_count is not None:
            metadata_parts.append(
                f"    <column_count>{self.metadata.column_count}</column_count>"
            )

        # Schema (for structured data)
        if self.metadata.data_schema:
            metadata_parts.append("    <schema>")
            for col_name, col_type in self.metadata.data_schema.items():
                metadata_parts.append(
                    f'      <column name="{_escape_xml(col_name)}" type="{_escape_xml(col_type)}" />'
                )
            metadata_parts.append("    </schema>")

        # Preview
        if self.metadata.preview:
            metadata_parts.append(
                f"    <preview>{_escape_xml(self.metadata.preview)}</preview>"
            )

        # Usage hints
        if self.metadata.usage_hints:
            metadata_parts.append("    <usage_hints>")
            for hint in self.metadata.usage_hints:
                metadata_parts.append(f"      <hint>{_escape_xml(hint)}</hint>")
            metadata_parts.append("    </usage_hints>")

        if metadata_parts:
            xml_parts.append("  <metadata>")
            xml_parts.extend(metadata_parts)
            xml_parts.append("  </metadata>")

        xml_parts.append("</artifact>")

        return "\n".join(xml_parts)
