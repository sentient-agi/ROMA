"""Storage configuration schema."""

from typing import Optional
from pydantic.dataclasses import dataclass
from pydantic import Field, field_validator


@dataclass
class PostgresConfig:
    """PostgreSQL persistence configuration for execution traces and checkpoints."""

    enabled: bool = Field(
        default=False,
        description="Enable PostgreSQL persistence for traces and checkpoints",
    )

    connection_url: str = Field(
        default="postgresql+asyncpg://localhost/roma_dspy",
        description="PostgreSQL connection URL using asyncpg driver",
    )

    pool_size: int = Field(default=5, description="Connection pool size", ge=1, le=50)

    max_overflow: int = Field(
        default=10,
        description="Maximum overflow connections beyond pool_size",
        ge=0,
        le=100,
    )

    pool_timeout: float = Field(
        default=30.0, description="Connection pool timeout in seconds", ge=1.0
    )

    echo_sql: bool = Field(
        default=False, description="Echo SQL statements to logs (debug mode)"
    )

    @field_validator("connection_url")
    @classmethod
    def validate_connection_url(cls, v: str) -> str:
        """Validate connection URL uses asyncpg driver."""
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "connection_url must use asyncpg driver (postgresql+asyncpg://)"
            )
        return v


@dataclass
class FilesystemScannerConfig:
    """Filesystem scanner configuration for fallback artifact detection."""

    enabled: bool = Field(
        default=True,
        description=(
            "Whether to run the filesystem scanner (4th fallback layer for artifact detection). "
            "When disabled, only relies on tool output detection, text parsing, and priority registration."
        ),
    )

    filter_by_mtime: bool = Field(
        default=True,
        description=(
            "Whether to filter files by modification time. "
            "When enabled, only includes files modified after task execution started. "
            "When disabled, includes all files in artifact directories regardless of mtime."
        ),
    )

    mtime_buffer_seconds: int = Field(
        default=0,
        description=(
            "Additional buffer (in seconds) to subtract from start_time for mtime filtering. "
            "Example: 60 = include files from the last minute before execution started. "
            "Useful for catching files created by setup scripts."
        ),
        ge=0,
    )


@dataclass
class StorageConfig:
    """
    Storage configuration for execution-scoped file storage.

    The base_path is where S3 is mounted via goofys in production,
    or a local directory in development. It should be the same across
    all environments (host, Docker, E2B) for path consistency.
    """

    base_path: str = Field(
        description=(
            "Base storage path (mount point for S3 via goofys). "
            "This path must be identical across host and E2B for file sharing. "
            "Set via STORAGE_BASE_PATH environment variable."
        ),
        examples=["~/.tmp/sentient", "${HOME}/roma_storage"],
    )

    max_file_size: int = Field(
        default=100 * 1024 * 1024,
        description="Maximum file size in bytes (default: 100MB)",
        ge=0,
    )

    buffer_size: int = Field(
        default=1024 * 1024,
        description=(
            "I/O buffer size in bytes for goofys optimization (default: 1MB). "
            "Larger buffers reduce small writes that goofys handles poorly."
        ),
        ge=1024,
    )

    flat_structure: bool = Field(
        default=False,
        description=(
            "Use flat storage structure without execution_id isolation. "
            "When enabled, files are stored directly in base_path instead of "
            "base_path/executions/{execution_id}/. "
            "Useful for Terminal-Bench integration where base_path=/app."
        ),
    )

    filesystem_scanner: FilesystemScannerConfig = Field(
        default_factory=FilesystemScannerConfig,
        description="Filesystem scanner configuration for fallback artifact detection",
    )

    postgres: Optional[PostgresConfig] = Field(
        default=None, description="PostgreSQL persistence configuration"
    )
