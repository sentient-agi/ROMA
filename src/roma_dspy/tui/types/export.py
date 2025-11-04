"""Export and import type definitions for TUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List


class ExportLevel(Enum):
    """Export detail level.

    Controls what data is included in exports to manage file size:
    - FULL: All data including trace I/O, reasoning, tool calls (~100%)
    - COMPACT: Excludes trace inputs/outputs/reasoning (~20-30% of full)
    - MINIMAL: Task tree + metrics only, no trace details (~5% of full)
    """

    FULL = "full"
    COMPACT = "compact"
    MINIMAL = "minimal"

    def __str__(self) -> str:
        return self.value


@dataclass
class ExportResult:
    """Result of an export operation.

    Contains metadata about the exported file for user feedback.
    """

    filepath: Path
    """Path to the exported file"""

    size_bytes: int
    """Final file size in bytes"""

    compressed: bool
    """Whether file was compressed with gzip"""

    checksum: str
    """SHA256 checksum (format: 'sha256:hex')"""

    level: ExportLevel
    """Export level used"""

    task_count: int
    """Number of tasks exported"""

    trace_count: int
    """Number of traces exported"""

    io_excluded: bool = False
    """Whether trace I/O was excluded"""

    redacted: bool = False
    """Whether sensitive data was redacted"""

    duration_seconds: float = 0.0
    """Export operation duration in seconds"""

    def size_mb(self) -> float:
        """Get size in megabytes."""
        return self.size_bytes / (1024 * 1024)

    def summary(self) -> str:
        """Get human-readable summary."""
        size_str = f"{self.size_mb():.1f} MB"
        if self.compressed:
            size_str += " (compressed)"

        parts = [
            f"Level: {self.level.value}",
            f"Tasks: {self.task_count}",
            f"Traces: {self.trace_count}",
            f"Size: {size_str}",
        ]

        if self.io_excluded:
            parts.append("I/O excluded")
        if self.redacted:
            parts.append("Sensitive data redacted")
        if self.duration_seconds > 0:
            parts.append(f"{self.duration_seconds:.2f}s")

        return " | ".join(parts)


@dataclass
class ValidationResult:
    """Result of export file validation.

    Used by ImportService to report validation status before loading.
    """

    valid: bool
    """Whether file passed validation"""

    filepath: Optional[Path] = None
    """Path to the validated file (for tracking/logging)"""

    errors: List[str] = field(default_factory=list)
    """Validation errors (empty if valid)"""

    warnings: List[str] = field(default_factory=list)
    """Non-fatal warnings"""

    schema_version: str = ""
    """Detected schema version"""

    execution_id: str = ""
    """Execution ID from export"""

    task_count: int = 0
    """Number of tasks in export"""

    trace_count: int = 0
    """Number of traces in export"""

    export_level: str = ""
    """Export level (full/compact/minimal)"""

    checksum_valid: bool = True
    """Whether checksum verification passed"""

    def summary(self) -> str:
        """Get human-readable summary."""
        if not self.valid:
            return f"❌ Invalid: {'; '.join(self.errors[:3])}"

        parts = [
            f"✓ Valid export",
            f"schema v{self.schema_version}",
            f"{self.task_count} tasks",
        ]

        if not self.checksum_valid:
            parts.append("⚠️ checksum mismatch")
        elif self.warnings:
            parts.append(f"{len(self.warnings)} warnings")

        return " | ".join(parts)
