"""
PTC Result Processor

Processes PTCArtifactResult and writes artifacts to filesystem.
"""

import os
from pathlib import Path
from typing import Optional, List, Dict
from loguru import logger

from .schemas import PTCArtifactResult, CodeArtifact, ArtifactType, ExecutionStatus


class ArtifactProcessorError(Exception):
    """Base exception for artifact processor errors."""
    pass


class ArtifactProcessor:
    """
    Processes PTC results and writes artifacts to filesystem.

    Handles:
    - Writing code artifacts to appropriate locations
    - Creating directory structure
    - File permissions and validation
    - Conflict resolution (overwrite vs. skip)
    """

    def __init__(
        self,
        base_path: Optional[Path] = None,
        overwrite: bool = True,
        create_dirs: bool = True,
        dry_run: bool = False,
    ):
        """
        Initialize artifact processor.

        Args:
            base_path: Base directory for writing artifacts (default: current directory)
            overwrite: Whether to overwrite existing files (default: True)
            create_dirs: Whether to create missing directories (default: True)
            dry_run: If True, don't actually write files (for testing)
        """
        self.base_path = Path(base_path or Path.cwd())
        self.overwrite = overwrite
        self.create_dirs = create_dirs
        self.dry_run = dry_run

    def process_result(self, result: PTCArtifactResult) -> Dict[str, any]:
        """
        Process PTC result and write all artifacts.

        Args:
            result: Artifact result from PTC

        Returns:
            Dictionary with processing statistics

        Raises:
            ArtifactProcessorError: If processing fails
        """
        logger.info(
            f"Processing result {result.execution_id}: "
            f"{len(result.artifacts)} artifacts, status={result.status}"
        )

        if not result.success:
            logger.warning(
                f"Result status is {result.status}, but proceeding with artifact processing"
            )

        # Process statistics
        stats = {
            "execution_id": result.execution_id,
            "status": result.status.value,
            "total_artifacts": len(result.artifacts),
            "written": 0,
            "skipped": 0,
            "errors": 0,
            "files_by_type": {},
        }

        # Write each artifact
        for artifact in result.artifacts:
            try:
                written = self.write_artifact(artifact)
                if written:
                    stats["written"] += 1
                else:
                    stats["skipped"] += 1

                # Count by type
                type_key = artifact.artifact_type.value
                stats["files_by_type"][type_key] = stats["files_by_type"].get(type_key, 0) + 1

            except Exception as e:
                stats["errors"] += 1
                logger.error(
                    f"Failed to write artifact {artifact.file_path}: {e}"
                )

        logger.info(
            f"Processing complete: written={stats['written']}, "
            f"skipped={stats['skipped']}, errors={stats['errors']}"
        )

        return stats

    def write_artifact(self, artifact: CodeArtifact) -> bool:
        """
        Write a single artifact to filesystem.

        Args:
            artifact: Code artifact to write

        Returns:
            True if file was written, False if skipped

        Raises:
            ArtifactProcessorError: If write fails
        """
        # Construct full path
        file_path = self.base_path / artifact.file_path

        # Check if file exists
        if file_path.exists() and not self.overwrite:
            logger.debug(f"Skipping existing file: {file_path}")
            return False

        # Create parent directories
        if self.create_dirs:
            file_path.parent.mkdir(parents=True, exist_ok=True)

        # Dry run mode
        if self.dry_run:
            logger.info(f"[DRY RUN] Would write: {file_path}")
            return True

        try:
            # Write file
            file_path.write_text(artifact.content, encoding="utf-8")
            logger.debug(
                f"Wrote {len(artifact.content)} bytes to {file_path} "
                f"(type: {artifact.artifact_type.value})"
            )
            return True

        except Exception as e:
            raise ArtifactProcessorError(
                f"Failed to write {file_path}: {e}"
            ) from e

    def get_artifact_summary(self, result: PTCArtifactResult) -> str:
        """
        Get human-readable summary of artifacts.

        Args:
            result: Artifact result

        Returns:
            Formatted summary string
        """
        lines = [
            f"Execution: {result.execution_id}",
            f"Status: {result.status.value}",
            f"Duration: {result.duration_seconds:.2f}s",
            f"Artifacts: {len(result.artifacts)}",
        ]

        # Group by type
        by_type: Dict[ArtifactType, List[CodeArtifact]] = {}
        for artifact in result.artifacts:
            if artifact.artifact_type not in by_type:
                by_type[artifact.artifact_type] = []
            by_type[artifact.artifact_type].append(artifact)

        # Add type breakdown
        for artifact_type, artifacts in sorted(by_type.items()):
            lines.append(f"  {artifact_type.value}: {len(artifacts)} files")
            for artifact in artifacts[:5]:  # Show first 5
                lines.append(f"    - {artifact.file_path}")
            if len(artifacts) > 5:
                lines.append(f"    ... and {len(artifacts) - 5} more")

        # Add test results
        if result.test_results:
            lines.append("\nTest Results:")
            lines.append(f"  Command: {result.test_results.test_command}")
            lines.append(f"  Passed: {result.test_results.tests_passed}")
            lines.append(f"  Failed: {result.test_results.tests_failed}")
            lines.append(f"  Duration: {result.test_results.duration_seconds:.2f}s")

        # Add LLM usage
        if result.llm_usage:
            lines.append("\nLLM Usage:")
            lines.append(f"  Total tokens: {result.total_tokens_used:,}")
            if result.total_cost_usd > 0:
                lines.append(f"  Total cost: ${result.total_cost_usd:.4f}")

        return "\n".join(lines)

    def validate_result(self, result: PTCArtifactResult) -> List[str]:
        """
        Validate result before processing.

        Args:
            result: Artifact result to validate

        Returns:
            List of validation warnings (empty if no issues)
        """
        warnings = []

        # Check status
        if result.status == ExecutionStatus.FAILURE:
            warnings.append(f"Result status is FAILURE: {result.error_message}")

        if result.status == ExecutionStatus.TIMEOUT:
            warnings.append("Result status is TIMEOUT - code may be incomplete")

        # Check artifacts
        if not result.artifacts:
            warnings.append("No artifacts in result")

        # Check for duplicate file paths
        file_paths = [a.file_path for a in result.artifacts]
        duplicates = [p for p in file_paths if file_paths.count(p) > 1]
        if duplicates:
            warnings.append(f"Duplicate file paths: {set(duplicates)}")

        # Check test results (if testing was expected)
        if result.test_results is None:
            warnings.append("No test results - tests may not have run")
        elif result.test_results.tests_failed > 0:
            warnings.append(
                f"{result.test_results.tests_failed} test(s) failed"
            )

        # Check for errors/warnings from PTC
        if result.error_message:
            warnings.append(f"PTC error: {result.error_message}")

        if result.warnings:
            warnings.extend([f"PTC warning: {w}" for w in result.warnings])

        return warnings

    def process_with_validation(
        self,
        result: PTCArtifactResult,
        fail_on_warnings: bool = False,
    ) -> Dict[str, any]:
        """
        Process result with validation.

        Args:
            result: Artifact result to process
            fail_on_warnings: If True, raise exception on validation warnings

        Returns:
            Processing statistics

        Raises:
            ArtifactProcessorError: If validation fails and fail_on_warnings=True
        """
        # Validate first
        warnings = self.validate_result(result)

        if warnings:
            warning_msg = "\n".join(f"  - {w}" for w in warnings)
            logger.warning(f"Validation warnings:\n{warning_msg}")

            if fail_on_warnings:
                raise ArtifactProcessorError(
                    f"Validation failed with {len(warnings)} warnings:\n{warning_msg}"
                )

        # Process artifacts
        stats = self.process_result(result)
        stats["validation_warnings"] = warnings

        return stats
