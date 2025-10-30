"""Import service for loading exported execution files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any

from loguru import logger

from roma_dspy.tui.models import ExecutionViewModel, TaskViewModel, TraceViewModel, CheckpointViewModel, MetricsSummary, DataSource
from roma_dspy.tui.types.export import ValidationResult
from roma_dspy.tui.utils.checksum import compute_checksum
from roma_dspy.tui.utils.file_loader import FileLoader
from roma_dspy.tui.utils.schema_validator import SchemaValidator


class ImportService:
    """Service for importing exported execution files.

    Handles validation, checksum verification, and reconstruction of ExecutionViewModel.
    """

    def __init__(self) -> None:
        """Initialize import service with validator."""
        self.validator = SchemaValidator()

    def load_from_file(
        self,
        filepath: Path,
        validate_checksum: bool = True,
    ) -> ExecutionViewModel:
        """Load execution from exported file.

        Args:
            filepath: Path to exported .json file
            validate_checksum: Whether to verify checksum (default: True).
                Set to False to skip checksum validation for faster imports
                or when loading from trusted sources. Note: Skipping validation
                means file corruption or tampering won't be detected.

        Returns:
            ExecutionViewModel reconstructed from file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file is invalid or corrupted
            json.JSONDecodeError: If file is not valid JSON
        """
        if not filepath.exists():
            raise FileNotFoundError(f"Export file not found: {filepath}")

        logger.info(f"Loading execution from {filepath}")

        # Read file with auto-decompression
        try:
            data = FileLoader.load_json(filepath)
        except json.JSONDecodeError as exc:
            logger.error(f"Invalid JSON in {filepath}: {exc}")
            raise json.JSONDecodeError(
                f"File is not valid JSON: {exc.msg}",
                exc.doc,
                exc.pos
            ) from exc
        except ValueError as exc:
            # File too large or invalid format
            logger.error(f"Invalid file: {exc}")
            raise ValueError(f"Cannot load file: {exc}") from exc

        # Validate schema
        validation = self.validator.validate(data)
        if not validation.valid:
            error_msg = "; ".join(validation.errors[:5])
            logger.error(f"Validation failed: {error_msg}")
            raise ValueError(f"Invalid export file: {error_msg}")

        # Validate checksum using shared utility
        if validate_checksum:
            stored_checksum = data.get("checksum", "")
            if stored_checksum:
                logger.debug("Verifying export file checksum...")
                computed_checksum = compute_checksum(data["execution"])
                if stored_checksum != computed_checksum:
                    logger.warning(
                        f"Checksum mismatch: stored={stored_checksum[:16]}..., "
                        f"computed={computed_checksum[:16]}..."
                    )
                    raise ValueError(
                        "Checksum validation failed - file may be corrupted or tampered"
                    )
                logger.debug("Checksum validation passed")
            else:
                logger.warning("No checksum found in export file - skipping validation")
        else:
            logger.info("Checksum validation skipped (validate_checksum=False)")

        # Reconstruct ExecutionViewModel
        try:
            execution = self._reconstruct_execution(data["execution"])
            logger.info(
                f"Loaded execution {execution.execution_id[:8]} "
                f"({len(execution.tasks)} tasks)"
            )
            return execution
        except Exception as exc:
            logger.error(f"Failed to reconstruct execution: {exc}", exc_info=True)
            raise ValueError(f"Failed to load execution: {exc}") from exc

    def validate_export_file(
        self,
        filepath: Path,
        validate_checksum: bool = True,
    ) -> ValidationResult:
        """Validate export file without loading.

        Args:
            filepath: Path to exported file
            validate_checksum: Whether to verify checksum (default: True).
                Set to False for faster validation without data integrity check.

        Returns:
            ValidationResult with details
        """
        if not filepath.exists():
            return ValidationResult(
                valid=False,
                filepath=filepath,
                errors=[f"File not found: {filepath}"],
            )

        # Read and parse with auto-decompression
        try:
            data = FileLoader.load_json(filepath)
        except json.JSONDecodeError as exc:
            return ValidationResult(
                valid=False,
                filepath=filepath,
                errors=[f"Invalid JSON: {exc.msg}"],
            )
        except ValueError as exc:
            return ValidationResult(
                valid=False,
                filepath=filepath,
                errors=[f"Invalid file: {str(exc)}"],
            )
        except Exception as exc:
            return ValidationResult(
                valid=False,
                filepath=filepath,
                errors=[f"Failed to read file: {exc}"],
            )

        # Schema validation
        validation = self.validator.validate(data)

        # Checksum validation using shared utility (optional)
        if validation.valid and validate_checksum:
            stored_checksum = data.get("checksum", "")
            if stored_checksum:
                logger.debug("Verifying checksum during validation...")
                computed_checksum = compute_checksum(data["execution"])
                if stored_checksum != computed_checksum:
                    validation.checksum_valid = False
                    validation.warnings.append(
                        "Checksum mismatch - file may be corrupted"
                    )
            else:
                validation.warnings.append(
                    "No checksum found - cannot verify integrity"
                )
        elif validation.valid and not validate_checksum:
            logger.debug("Checksum validation skipped")
            validation.warnings.append(
                "Checksum validation skipped - file integrity not verified"
            )

        return validation

    def _reconstruct_execution(self, data: Dict[str, Any]) -> ExecutionViewModel:
        """Reconstruct ExecutionViewModel from dict.

        Args:
            data: Execution data dictionary

        Returns:
            ExecutionViewModel
        """
        # Reconstruct tasks
        tasks = {}
        for task_id, task_data in data.get("tasks", {}).items():
            tasks[task_id] = self._reconstruct_task(task_data)

        # Reconstruct checkpoints
        checkpoints = []
        for cp_data in data.get("checkpoints", []):
            checkpoints.append(CheckpointViewModel(**cp_data))

        # Reconstruct metrics
        metrics_data = data.get("metrics", {})
        metrics = MetricsSummary(
            total_calls=metrics_data.get("total_calls", 0),
            total_tokens=metrics_data.get("total_tokens", 0),
            total_cost=metrics_data.get("total_cost", 0.0),
            total_duration=metrics_data.get("total_duration", 0.0),
            avg_latency_ms=metrics_data.get("avg_latency_ms", 0.0),
            by_module=metrics_data.get("by_module", {}),
        )

        # Create ExecutionViewModel
        return ExecutionViewModel(
            execution_id=data["execution_id"],
            root_goal=data.get("root_goal", ""),
            status=data.get("status", "unknown"),
            tasks=tasks,
            root_task_ids=data.get("root_task_ids", []),
            checkpoints=checkpoints,
            metrics=metrics,
            data_sources=data.get("data_sources", {}),
            warnings=data.get("warnings", []),
        )

    def _reconstruct_task(self, data: Dict[str, Any]) -> TaskViewModel:
        """Reconstruct TaskViewModel from dict.

        Args:
            data: Task data dictionary

        Returns:
            TaskViewModel
        """
        # Reconstruct traces
        traces = []
        for trace_data in data.get("traces", []):
            traces.append(self._reconstruct_trace(trace_data))

        return TaskViewModel(
            task_id=data["task_id"],
            parent_task_id=data.get("parent_task_id"),
            goal=data.get("goal", ""),
            status=data.get("status", "unknown"),
            module=data.get("module"),
            task_type=data.get("task_type"),
            node_type=data.get("node_type"),
            depth=data.get("depth", 0),
            result=data.get("result"),
            error=data.get("error"),
            traces=traces,
            total_duration=data.get("total_duration", 0.0),
            total_tokens=data.get("total_tokens", 0),
            total_cost=data.get("total_cost", 0.0),
            subtask_ids=data.get("subtask_ids", []),
        )

    def _reconstruct_trace(self, data: Dict[str, Any]) -> TraceViewModel:
        """Reconstruct TraceViewModel from dict.

        Args:
            data: Trace data dictionary

        Returns:
            TraceViewModel
        """
        # Parse source enum
        source_str = data.get("source", "merged")
        try:
            source = DataSource(source_str)
        except ValueError:
            source = DataSource.MERGED

        return TraceViewModel(
            trace_id=data["trace_id"],
            task_id=data["task_id"],
            parent_trace_id=data.get("parent_trace_id"),
            name=data.get("name", "Unknown"),
            module=data.get("module"),
            duration=data.get("duration", 0.0),
            tokens=data.get("tokens", 0),
            cost=data.get("cost", 0.0),
            inputs=data.get("inputs"),
            outputs=data.get("outputs"),
            reasoning=data.get("reasoning"),
            tool_calls=data.get("tool_calls", []),
            start_time=data.get("start_time"),
            start_ts=data.get("start_ts"),
            model=data.get("model"),
            temperature=data.get("temperature"),
            source=source,
            has_full_io=data.get("has_full_io", False),
        )
