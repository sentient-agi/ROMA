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
        "report, plot, code, image, document"
    )
    description: str = Field(..., description="Description of artifact contents")
    derived_from: Optional[str] = Field(
        None,
        description="Comma-separated artifact IDs this was derived from"
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
    data_schema: Optional[Dict[str, str]] = Field(None, description="Schema (column_name -> type)")

    # Content preview
    preview: Optional[str] = Field(None, description="Content preview (truncated)")

    # Usage guidance
    usage_hints: Optional[List[str]] = Field(None, description="Suggestions for downstream use")

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
    created_by_module: str = Field(..., description="Module name (Executor, Planner, etc.)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp")

    # Content metadata
    metadata: ArtifactMetadata = Field(..., description="Rich metadata")

    # Lineage
    derived_from: List[UUID] = Field(default_factory=list, description="Parent artifact IDs")

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
    Lightweight artifact reference for XML serialization in context.

    Used in ExecutionContext to provide available artifacts to downstream tasks
    without sending full metadata (keeps context size manageable).

    Attributes:
        artifact_id: Unique identifier
        name: Human-readable name
        artifact_type: Semantic type
        storage_path: Path to artifact
        description: Brief description from metadata
        created_by_task: Task ID that created this
        relevance_score: Optional relevance score for context ranking
    """

    artifact_id: UUID = Field(..., description="Unique identifier")
    name: str = Field(..., description="Human-readable name")
    artifact_type: ArtifactType = Field(..., description="Semantic type")
    storage_path: str = Field(..., description="Path to artifact")
    description: str = Field(..., description="Brief description")
    created_by_task: str = Field(..., description="Task ID that created this")
    relevance_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Relevance score")

    @classmethod
    def from_artifact(cls, artifact: Artifact, relevance_score: Optional[float] = None) -> "ArtifactReference":
        """
        Create reference from full artifact.

        Args:
            artifact: Full artifact to create reference from
            relevance_score: Optional relevance score for context ranking

        Returns:
            Lightweight artifact reference
        """
        return cls(
            artifact_id=artifact.artifact_id,
            name=artifact.name,
            artifact_type=artifact.artifact_type,
            storage_path=artifact.storage_path,
            description=artifact.metadata.description,
            created_by_task=artifact.created_by_task,
            relevance_score=relevance_score,
        )

    def to_xml_element(self) -> str:
        """
        Serialize to XML element string for context.

        Returns:
            XML string like: <artifact id="..." name="..." type="..." path="..." task="...">description</artifact>
        """
        relevance = f' relevance="{self.relevance_score}"' if self.relevance_score is not None else ""
        return (
            f'<artifact id="{self.artifact_id}" '
            f'name="{self.name}" '
            f'type="{self.artifact_type.value}" '
            f'path="{self.storage_path}" '
            f'task="{self.created_by_task}"'
            f'{relevance}>'
            f'{self.description}'
            f'</artifact>'
        )
