"""JSON schema validation for export files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

from loguru import logger

try:
    import jsonschema
    from jsonschema import Draft7Validator
except ImportError:
    raise ImportError(
        "jsonschema is required for import/export. "
        "Install with: pip install jsonschema"
    )

from roma_dspy.tui.types.export import ValidationResult


class SchemaValidator:
    """Validates export files against JSON schemas.

    Performs structural validation, type checking, and reference integrity validation.
    Supports multiple schema versions with automatic detection.
    """

    # Max nesting depth for task hierarchy (prevent stack overflow)
    MAX_DEPTH = 100

    # Supported schema versions
    SUPPORTED_VERSIONS = ["1.0.0", "1.1.0"]

    def __init__(self, schema_version: str = "1.1.0") -> None:
        """Initialize validator with specified schema version.

        Args:
            schema_version: Schema version to use (default: 1.1.0, latest)
        """
        if schema_version not in self.SUPPORTED_VERSIONS:
            raise ValueError(
                f"Unsupported schema version: {schema_version}. "
                f"Supported: {', '.join(self.SUPPORTED_VERSIONS)}"
            )

        self.schema_version = schema_version
        self.schema = self._load_schema(schema_version)
        self.validator = Draft7Validator(self.schema)

    def _load_schema(self, version: str) -> Dict[str, Any]:
        """Load JSON schema from file for specified version.

        Args:
            version: Schema version (e.g., "1.0.0", "1.1.0")

        Returns:
            Schema dictionary

        Raises:
            FileNotFoundError: If schema file not found
            json.JSONDecodeError: If schema is invalid JSON
        """
        # Convert version to filename format (e.g., "1.0.0" -> "export_v1_0_0.json")
        version_str = version.replace(".", "_")
        schema_filename = f"export_v{version_str}.json"
        schema_path = Path(__file__).parent.parent / "schemas" / schema_filename

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        with schema_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def detect_schema_version(data: Dict[str, Any]) -> str:
        """Detect schema version from export data.

        Args:
            data: Export data dictionary

        Returns:
            Schema version string (e.g., "1.0.0", "1.1.0")

        Raises:
            ValueError: If schema_version field is missing or invalid
        """
        schema_version = data.get("schema_version")

        if not schema_version:
            raise ValueError("Missing schema_version field in export data")

        if not isinstance(schema_version, str):
            raise ValueError(f"Invalid schema_version type: {type(schema_version)}")

        if schema_version not in SchemaValidator.SUPPORTED_VERSIONS:
            raise ValueError(
                f"Unsupported schema version: {schema_version}. "
                f"Supported: {', '.join(SchemaValidator.SUPPORTED_VERSIONS)}"
            )

        return schema_version

    def validate(self, data: Dict[str, Any]) -> ValidationResult:
        """Validate export data against schema.

        Automatically detects schema version from data and validates against
        the appropriate schema. Falls back to current validator version if
        detection fails.

        Args:
            data: Parsed export JSON

        Returns:
            ValidationResult with errors and warnings
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Extract basic info for result
        execution_id = ""
        task_count = 0
        trace_count = 0
        export_level = ""
        schema_version = data.get("schema_version", "")

        # Detect schema version and switch validator if needed
        try:
            detected_version = self.detect_schema_version(data)

            # If detected version differs from current validator, reload schema
            if detected_version != self.schema_version:
                logger.info(
                    f"Schema version mismatch: validator={self.schema_version}, "
                    f"data={detected_version}. Reloading schema..."
                )
                self.schema_version = detected_version
                self.schema = self._load_schema(detected_version)
                self.validator = Draft7Validator(self.schema)

        except ValueError as exc:
            # Schema version detection failed - use current validator
            logger.warning(f"Schema version detection failed: {exc}")
            errors.append(f"Schema version issue: {exc}")

        try:
            execution = data.get("execution", {})
            execution_id = execution.get("execution_id", "")
            task_count = len(execution.get("tasks", {}))
            export_level = data.get("export_level", "")

            # Count traces
            for task in execution.get("tasks", {}).values():
                trace_count += len(task.get("traces", []))

        except Exception as exc:
            logger.warning(f"Failed to extract export info: {exc}")

        # Schema validation
        schema_errors = list(self.validator.iter_errors(data))
        if schema_errors:
            for error in schema_errors[:10]:  # Limit to first 10 errors
                # Format error path
                path = ".".join(str(p) for p in error.path) if error.path else "root"
                errors.append(f"{path}: {error.message}")

            if len(schema_errors) > 10:
                errors.append(f"... and {len(schema_errors) - 10} more errors")

            return ValidationResult(
                valid=False,
                filepath=None,  # Validator doesn't know the filepath
                errors=errors,
                warnings=warnings,
                schema_version=schema_version,
                execution_id=execution_id,
                task_count=task_count,
                trace_count=trace_count,
                export_level=export_level,
            )

        # Additional validations beyond schema
        try:
            # Reference integrity
            ref_errors, ref_warnings = self._validate_references(data)
            errors.extend(ref_errors)
            warnings.extend(ref_warnings)

            # Depth validation
            depth_errors = self._validate_depth(data)
            errors.extend(depth_errors)

            # Metric consistency
            metric_warnings = self._validate_metrics(data)
            warnings.extend(metric_warnings)

        except Exception as exc:
            logger.error(f"Validation error: {exc}", exc_info=True)
            errors.append(f"Validation failed: {str(exc)[:100]}")

        return ValidationResult(
            valid=len(errors) == 0,
            filepath=None,  # Validator doesn't know the filepath
            errors=errors,
            warnings=warnings,
            schema_version=schema_version,
            execution_id=execution_id,
            task_count=task_count,
            trace_count=trace_count,
            export_level=export_level,
        )

    def _validate_references(self, data: Dict[str, Any]) -> Tuple[List[str], List[str]]:
        """Validate reference integrity (task IDs, parent/child relationships).

        Args:
            data: Export data

        Returns:
            Tuple of (errors, warnings)
        """
        errors: List[str] = []
        warnings: List[str] = []

        execution = data.get("execution", {})
        tasks = execution.get("tasks", {})
        root_task_ids = execution.get("root_task_ids", [])

        # Collect all task IDs
        all_task_ids: Set[str] = set(tasks.keys())

        # Validate root task IDs exist
        for root_id in root_task_ids:
            if root_id not in all_task_ids:
                errors.append(f"Root task ID not found: {root_id}")

        # Validate task references
        for task_id, task in tasks.items():
            # Parent task ID
            parent_id = task.get("parent_task_id")
            if parent_id and parent_id not in all_task_ids:
                errors.append(f"Task {task_id}: parent_task_id not found: {parent_id}")

            # Subtask IDs
            for subtask_id in task.get("subtask_ids", []):
                if subtask_id not in all_task_ids:
                    errors.append(f"Task {task_id}: subtask_id not found: {subtask_id}")

            # Trace task_id references
            for trace in task.get("traces", []):
                trace_task_id = trace.get("task_id")
                if trace_task_id != task_id:
                    warnings.append(
                        f"Trace {trace.get('trace_id')}: task_id mismatch "
                        f"(expected {task_id}, got {trace_task_id})"
                    )

        # Detect circular references
        circular = self._detect_circular_refs(tasks)
        if circular:
            errors.append(f"Circular task references detected: {', '.join(circular[:5])}")

        return errors, warnings

    def _detect_circular_refs(self, tasks: Dict[str, Any]) -> List[str]:
        """Detect circular references in task hierarchy.

        Args:
            tasks: Tasks dictionary

        Returns:
            List of task IDs involved in cycles
        """
        circular: List[str] = []

        def has_cycle(task_id: str, visited: Set[str], path: Set[str]) -> bool:
            """DFS cycle detection."""
            if task_id in path:
                circular.append(task_id)
                return True

            if task_id in visited:
                return False

            if task_id not in tasks:
                return False

            visited.add(task_id)
            path.add(task_id)

            # Check subtasks
            for subtask_id in tasks[task_id].get("subtask_ids", []):
                if has_cycle(subtask_id, visited, path):
                    return True

            path.remove(task_id)
            return False

        visited: Set[str] = set()
        for task_id in tasks:
            if task_id not in visited:
                has_cycle(task_id, visited, set())

        return circular

    def _validate_depth(self, data: Dict[str, Any]) -> List[str]:
        """Validate task hierarchy depth.

        Args:
            data: Export data

        Returns:
            List of errors
        """
        errors: List[str] = []

        tasks = data.get("execution", {}).get("tasks", {})

        def check_depth(task_id: str, current_depth: int) -> None:
            """Recursively check depth."""
            if current_depth > self.MAX_DEPTH:
                errors.append(
                    f"Task hierarchy exceeds max depth ({self.MAX_DEPTH}): {task_id}"
                )
                return

            if task_id not in tasks:
                return

            for subtask_id in tasks[task_id].get("subtask_ids", []):
                check_depth(subtask_id, current_depth + 1)

        # Check from root tasks
        for root_id in data.get("execution", {}).get("root_task_ids", []):
            check_depth(root_id, 0)

        return errors

    def _validate_metrics(self, data: Dict[str, Any]) -> List[str]:
        """Validate metric consistency.

        Args:
            data: Export data

        Returns:
            List of warnings
        """
        warnings: List[str] = []

        execution = data.get("execution", {})
        tasks = execution.get("tasks", {})
        metrics = execution.get("metrics", {})

        # Calculate actual totals from tasks
        actual_tokens = sum(task.get("total_tokens", 0) for task in tasks.values())
        actual_cost = sum(task.get("total_cost", 0) for task in tasks.values())

        # Compare with metrics (allow 1% tolerance for rounding)
        expected_tokens = metrics.get("total_tokens", 0)
        if expected_tokens > 0:
            diff_pct = abs(actual_tokens - expected_tokens) / expected_tokens
            if diff_pct > 0.01:
                warnings.append(
                    f"Metric mismatch: total_tokens "
                    f"(expected {expected_tokens}, calculated {actual_tokens})"
                )

        expected_cost = metrics.get("total_cost", 0)
        if expected_cost > 0:
            diff_pct = abs(actual_cost - expected_cost) / expected_cost
            if diff_pct > 0.01:
                warnings.append(
                    f"Metric mismatch: total_cost "
                    f"(expected ${expected_cost:.4f}, calculated ${actual_cost:.4f})"
                )

        return warnings
