"""Export service for TUI data - supports JSON, CSV, and Markdown formats."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from roma_dspy.tui.models import (
    CheckpointViewModel,
    ExecutionViewModel,
    MetricsSummary,
    TaskViewModel,
    TraceViewModel,
)
from roma_dspy.tui.types.export import ExportLevel, ExportResult
from roma_dspy.tui.utils.checksum import compute_checksum
from roma_dspy.tui.utils.file_loader import FileLoader

# Get ROMA version from package metadata
try:
    from importlib.metadata import version
    _ROMA_VERSION = version("roma-dspy")
except Exception:
    _ROMA_VERSION = "unknown"


class ExportService:
    """Service for exporting TUI data in various formats.

    Follows Single Responsibility Principle - one class for all export operations.
    """

    SCHEMA_VERSION = "1.1.0"
    ROMA_VERSION = _ROMA_VERSION

    @staticmethod
    def export_execution_full(
        execution: ExecutionViewModel,
        filepath: Path,
        level: ExportLevel = ExportLevel.FULL,
        exclude_io: bool = False,
        redact_sensitive: bool = False,
        api_url: str = "",
    ) -> ExportResult:
        """Export complete execution with schema, checksum, and privacy options.

        This is the primary export method for sharable execution files.
        Tracks export duration for performance monitoring.

        Args:
            execution: Execution to export
            filepath: Output file path
            level: Export detail level (full/compact/minimal)
            exclude_io: Whether to exclude trace I/O data
            redact_sensitive: Whether to redact sensitive strings

        Returns:
            ExportResult with metadata

        Raises:
            PermissionError: If lacking write permissions
            OSError: If disk full or other OS-level error
            ValueError: If data cannot be serialized
        """
        import time
        start_time = time.time()

        logger.info(
            f"Exporting execution {execution.execution_id[:8]} "
            f"(level={level.value}, exclude_io={exclude_io}, redact={redact_sensitive})"
        )

        # Prepare execution data based on level
        execution_data = ExportService._prepare_execution_data(
            execution, level, exclude_io
        )

        # Redact sensitive data if requested
        if redact_sensitive:
            # Import here to avoid circular dependency
            from roma_dspy.tui.utils.sensitive_redactor import SensitiveDataRedactor

            redactor = SensitiveDataRedactor()
            execution_data = redactor.redact(execution_data)

        # Compute checksum of execution data using shared utility
        checksum = compute_checksum(execution_data)

        # Build export document
        export_doc = {
            "schema_version": ExportService.SCHEMA_VERSION,
            "roma_version": ExportService.ROMA_VERSION,
            "exported_at": datetime.now().isoformat(),
            "export_level": level.value,
            "checksum": checksum,
            "compressed": False,  # Will be updated if compressed
            "privacy": {
                "io_excluded": exclude_io,
                "redacted": redact_sensitive,
            },
            "execution": execution_data,
            "metadata": {
                "export_source": "tui",
                "original_api_url": api_url,
                "task_count": len(execution.tasks),
                "trace_count": sum(len(t.traces) for t in execution.tasks.values()),
                "uncompressed_size_bytes": 0,  # Will be computed
            },
        }

        # Estimate size before writing
        json_str = json.dumps(export_doc, default=str)
        export_doc["metadata"]["uncompressed_size_bytes"] = len(json_str.encode("utf-8"))

        # Write to file with auto-compression if > 10MB
        # Track created file for cleanup on error
        created_file: Optional[Path] = None

        try:
            final_path, was_compressed = FileLoader.auto_compress_if_large(
                export_doc,
                filepath,
                threshold_bytes=10 * 1024 * 1024,  # 10 MB threshold
            )
            created_file = final_path  # Track for cleanup

            # Update compressed flag in document if compressed
            if was_compressed:
                export_doc["compressed"] = True

            file_size = final_path.stat().st_size
            duration = time.time() - start_time

            logger.info(
                f"Exported to {final_path} "
                f"({file_size / 1024 / 1024:.1f} MB, {len(execution.tasks)} tasks, "
                f"compressed={was_compressed}, {duration:.2f}s)"
            )

            return ExportResult(
                filepath=final_path,
                size_bytes=file_size,
                compressed=was_compressed,
                checksum=checksum,
                level=level,
                task_count=len(execution.tasks),
                trace_count=sum(len(t.traces) for t in execution.tasks.values()),
                io_excluded=exclude_io,
                redacted=redact_sensitive,
                duration_seconds=duration,
            )

        except PermissionError as exc:
            logger.error(f"Permission denied writing to {filepath}: {exc}")
            # Clean up partial file
            ExportService._cleanup_partial_file(created_file)
            raise PermissionError(
                f"Cannot write to {filepath}: Permission denied"
            ) from exc
        except OSError as exc:
            if exc.errno == 28:  # ENOSPC
                logger.error(f"Disk full while writing to {filepath}")
                # Clean up partial file
                ExportService._cleanup_partial_file(created_file)
                raise OSError("Disk full - cannot write export file") from exc
            else:
                logger.error(f"OS error writing to {filepath}: {exc}")
                # Clean up partial file
                ExportService._cleanup_partial_file(created_file)
                raise OSError(f"Cannot write to {filepath}: {exc}") from exc
        except (TypeError, ValueError) as exc:
            logger.error(f"Data serialization error: {exc}")
            # Clean up partial file
            ExportService._cleanup_partial_file(created_file)
            raise ValueError(f"Cannot serialize data to JSON: {exc}") from exc
        except Exception as exc:
            # Catch any unexpected errors and clean up
            logger.error(f"Unexpected error during export: {exc}", exc_info=True)
            ExportService._cleanup_partial_file(created_file)
            raise

    @staticmethod
    def _prepare_execution_data(
        execution: ExecutionViewModel,
        level: ExportLevel,
        exclude_io: bool,
    ) -> Dict[str, Any]:
        """Prepare execution data based on export level.

        Args:
            execution: Execution to export
            level: Export level
            exclude_io: Whether to exclude I/O data

        Returns:
            Prepared execution dictionary
        """
        # Convert execution to dict (handles dataclasses)
        if hasattr(execution, "__dict__"):
            exec_dict = execution.__dict__.copy()
        else:
            exec_dict = dict(execution)

        # Process tasks based on level
        if "tasks" in exec_dict:
            processed_tasks = {}
            for task_id, task in exec_dict["tasks"].items():
                processed_tasks[task_id] = ExportService._prepare_task_data(
                    task, level, exclude_io
                )
            exec_dict["tasks"] = processed_tasks

        # Normalize metrics dataclass
        metrics = exec_dict.get("metrics")
        if isinstance(metrics, MetricsSummary):
            exec_dict["metrics"] = metrics.__dict__.copy()
        elif hasattr(metrics, "__dict__"):
            exec_dict["metrics"] = metrics.__dict__.copy()

        # Normalize checkpoints
        checkpoints = exec_dict.get("checkpoints")
        if isinstance(checkpoints, list):
            exec_dict["checkpoints"] = [
                cp.__dict__.copy() if hasattr(cp, "__dict__") else dict(cp)
                for cp in checkpoints
            ]

        return exec_dict

    @staticmethod
    def _prepare_task_data(
        task: TaskViewModel,
        level: ExportLevel,
        exclude_io: bool,
    ) -> Dict[str, Any]:
        """Prepare task data based on export level.

        Args:
            task: Task to prepare
            level: Export level
            exclude_io: Whether to exclude I/O data

        Returns:
            Prepared task dictionary
        """
        # Convert task to dict
        if hasattr(task, "__dict__"):
            task_dict = task.__dict__.copy()
        else:
            task_dict = dict(task)

        if task_dict.get("parent_task_id") == "root":
            task_dict["parent_task_id"] = None

        # Process traces based on level
        traces = task_dict.get("traces")
        if isinstance(traces, list):
            strip_io = level == ExportLevel.COMPACT or exclude_io
            if level == ExportLevel.MINIMAL:
                task_dict["traces"] = []
            else:
                task_dict["traces"] = [
                    ExportService._trace_to_dict(trace, strip_io=strip_io)
                    for trace in traces
                ]

        return task_dict

    @staticmethod
    def _trace_to_dict(trace: Any, strip_io: bool = False) -> Dict[str, Any]:
        """Convert trace to JSON-friendly dictionary."""
        if hasattr(trace, "__dict__"):
            trace_dict = trace.__dict__.copy()
        else:
            trace_dict = dict(trace)

        # Normalize enumerations and complex objects
        source = trace_dict.get("source")
        if hasattr(source, "value"):
            trace_dict["source"] = source.value

        # Ensure tool calls are serializable (they should already be dict/list)
        # Apply I/O stripping if requested
        if strip_io:
            trace_dict["inputs"] = None
            trace_dict["outputs"] = None
            trace_dict["reasoning"] = None

        return trace_dict

    @staticmethod
    def estimate_export_size(
        execution: ExecutionViewModel,
        level: ExportLevel,
    ) -> int:
        """Estimate export size in bytes.

        Args:
            execution: Execution to estimate
            level: Export level

        Returns:
            Estimated size in bytes
        """
        # Prepare data without I/O (worst case)
        exec_data = ExportService._prepare_execution_data(execution, level, False)

        # Serialize to estimate size
        json_str = json.dumps(exec_data, default=str)
        return len(json_str.encode("utf-8"))

    @staticmethod
    def export_to_json(
        data: Any,
        filepath: Path,
        pretty: bool = True,
        include_metadata: bool = True,
    ) -> None:
        """Export data as JSON.

        Args:
            data: Data to export (dict, list, or Pydantic model)
            filepath: Output file path
            pretty: Use pretty-printing (default: True)
            include_metadata: Add export metadata (default: True)

        Raises:
            PermissionError: If lacking write permissions
            OSError: If disk full or other OS-level error
            ValueError: If data cannot be serialized
        """
        # Convert Pydantic models to dict
        if hasattr(data, 'model_dump'):
            export_data = data.model_dump()
        elif hasattr(data, '__dict__'):
            export_data = data.__dict__
        else:
            export_data = data

        # Add metadata
        if include_metadata:
            export_wrapper = {
                "exported_at": datetime.now().isoformat(),
                "format": "json",
                "data": export_data,
            }
        else:
            export_wrapper = export_data

        # Write to file with comprehensive error handling
        try:
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)

            with filepath.open('w', encoding='utf-8') as f:
                if pretty:
                    json.dump(export_wrapper, f, indent=2, default=str)
                else:
                    json.dump(export_wrapper, f, default=str)

            logger.info(f"Exported JSON to {filepath}")

        except PermissionError as exc:
            logger.error(f"Permission denied writing to {filepath}: {exc}")
            raise PermissionError(f"Cannot write to {filepath}: Permission denied") from exc
        except OSError as exc:
            # Covers disk full, read-only filesystem, etc.
            if exc.errno == 28:  # ENOSPC - No space left on device
                logger.error(f"Disk full while writing to {filepath}")
                raise OSError("Disk full - cannot write export file") from exc
            else:
                logger.error(f"OS error writing to {filepath}: {exc}")
                raise OSError(f"Cannot write to {filepath}: {exc}") from exc
        except (TypeError, ValueError) as exc:
            logger.error(f"Data serialization error: {exc}")
            raise ValueError(f"Cannot serialize data to JSON: {exc}") from exc

    @staticmethod
    def export_spans_to_csv(
        traces: List[TraceViewModel],
        filepath: Path,
    ) -> None:
        """Export span traces as CSV.

        Args:
            traces: List of trace view models
            filepath: Output file path

        Raises:
            PermissionError: If lacking write permissions
            OSError: If disk full or other OS-level error
        """
        try:
            # Ensure parent directory exists
            filepath.parent.mkdir(parents=True, exist_ok=True)

            with filepath.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'trace_id', 'task_id', 'parent_trace_id', 'name', 'module',
                    'duration', 'tokens', 'cost', 'model', 'start_time'
                ])
                writer.writeheader()

                for trace in traces:
                    writer.writerow({
                        'trace_id': trace.trace_id,
                        'task_id': trace.task_id,
                        'parent_trace_id': trace.parent_trace_id or '',
                        'name': trace.name,
                        'module': trace.module or '',
                        'duration': trace.duration,
                        'tokens': trace.tokens,
                        'cost': trace.cost,
                        'model': trace.model or '',
                        'start_time': trace.start_time or '',
                    })

            logger.info(f"Exported {len(traces)} spans to CSV: {filepath}")

        except PermissionError as exc:
            logger.error(f"Permission denied writing to {filepath}: {exc}")
            raise PermissionError(f"Cannot write to {filepath}: Permission denied") from exc
        except OSError as exc:
            if exc.errno == 28:
                logger.error(f"Disk full while writing to {filepath}")
                raise OSError("Disk full - cannot write export file") from exc
            else:
                logger.error(f"OS error writing to {filepath}: {exc}")
                raise OSError(f"Cannot write to {filepath}: {exc}") from exc

    @staticmethod
    def export_lm_calls_to_csv(
        traces: List[TraceViewModel],
        filepath: Path,
    ) -> None:
        """Export LM call traces as CSV.

        Args:
            traces: List of trace view models (filtered to LM calls)
            filepath: Output file path

        Raises:
            PermissionError: If lacking write permissions
            OSError: If disk full or other OS-level error
        """
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with filepath.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'trace_id', 'module', 'model', 'duration', 'tokens', 'cost',
                    'temperature', 'start_time'
                ])
                writer.writeheader()

                for trace in traces:
                    writer.writerow({
                        'trace_id': trace.trace_id,
                        'module': trace.module or '',
                        'model': trace.model or '',
                        'duration': trace.duration,
                        'tokens': trace.tokens,
                        'cost': trace.cost,
                        'temperature': trace.temperature if trace.temperature else '',
                        'start_time': trace.start_time or '',
                    })

            logger.info(f"Exported {len(traces)} LM calls to CSV: {filepath}")

        except PermissionError as exc:
            logger.error(f"Permission denied writing to {filepath}: {exc}")
            raise PermissionError(f"Cannot write to {filepath}: Permission denied") from exc
        except OSError as exc:
            if exc.errno == 28:
                logger.error(f"Disk full while writing to {filepath}")
                raise OSError("Disk full - cannot write export file") from exc
            else:
                logger.error(f"OS error writing to {filepath}: {exc}")
                raise OSError(f"Cannot write to {filepath}: {exc}") from exc

    @staticmethod
    def export_tool_calls_to_csv(
        tool_calls: List[Dict[str, Any]],
        filepath: Path,
    ) -> None:
        """Export tool calls as CSV.

        Args:
            tool_calls: List of tool call dictionaries
            filepath: Output file path

        Raises:
            PermissionError: If lacking write permissions
            OSError: If disk full or other OS-level error
        """
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with filepath.open('w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'id', 'name', 'toolkit', 'duration', 'status'
                ])
                writer.writeheader()

                for call in tool_calls:
                    writer.writerow({
                        'id': call.get('id', ''),
                        'name': call.get('name', ''),
                        'toolkit': call.get('toolkit', ''),
                        'duration': call.get('duration', 0),
                        'status': call.get('status', ''),
                    })

            logger.info(f"Exported {len(tool_calls)} tool calls to CSV: {filepath}")

        except PermissionError as exc:
            logger.error(f"Permission denied writing to {filepath}: {exc}")
            raise PermissionError(f"Cannot write to {filepath}: Permission denied") from exc
        except OSError as exc:
            if exc.errno == 28:
                logger.error(f"Disk full while writing to {filepath}")
                raise OSError("Disk full - cannot write export file") from exc
            else:
                logger.error(f"OS error writing to {filepath}: {exc}")
                raise OSError(f"Cannot write to {filepath}: {exc}") from exc

    @staticmethod
    def export_to_markdown(
        execution: ExecutionViewModel,
        filepath: Path,
    ) -> None:
        """Export execution summary as Markdown report.

        Args:
            execution: Execution view model
            filepath: Output file path

        Raises:
            PermissionError: If lacking write permissions
            OSError: If disk full or other OS-level error
        """
        lines = []

        # Header
        lines.append(f"# ROMA-DSPy Execution Report")
        lines.append(f"\n**Execution ID**: `{execution.execution_id}`")
        lines.append(f"**Status**: {execution.status}")
        lines.append(f"**Goal**: {execution.root_goal}")
        lines.append(f"**Exported**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Summary metrics
        lines.append("## Summary Metrics")
        lines.append("")
        lines.append(f"- **Total Tasks**: {len(execution.tasks)}")
        lines.append(f"- **Total Calls**: {execution.metrics.total_calls}")
        lines.append(f"- **Total Tokens**: {execution.metrics.total_tokens:,}")
        lines.append(f"- **Total Cost**: ${execution.metrics.total_cost:.4f}")
        lines.append(f"- **Total Duration**: {execution.metrics.total_duration:.2f}s")
        if execution.metrics.total_calls > 0:
            lines.append(f"- **Avg Latency**: {execution.metrics.avg_latency_ms:.1f}ms")
        lines.append("")

        # Module breakdown
        if execution.metrics.by_module:
            lines.append("## Module Breakdown")
            lines.append("")
            lines.append("| Module | Calls | Tokens | Cost | Duration |")
            lines.append("|--------|-------|--------|------|----------|")
            for module, stats in execution.metrics.by_module.items():
                calls = stats.get('calls', 0)
                tokens = stats.get('tokens', 0)
                cost = stats.get('cost', 0.0)
                duration = stats.get('duration', 0.0)
                lines.append(f"| {module} | {calls} | {tokens:,} | ${cost:.4f} | {duration:.2f}s |")
            lines.append("")

        # Task hierarchy
        lines.append("## Task Hierarchy")
        lines.append("")
        for task_id in execution.root_task_ids:
            task = execution.tasks.get(task_id)
            if task:
                lines.extend(ExportService._format_task_tree(task, execution.tasks, depth=0))
        lines.append("")

        # Top operations
        all_traces = []
        for task in execution.tasks.values():
            all_traces.extend(task.traces)

        if all_traces:
            lines.append("## Top 10 Operations")
            lines.append("")

            # By duration
            lines.append("### Longest Operations")
            lines.append("")
            sorted_by_duration = sorted(all_traces, key=lambda t: t.duration, reverse=True)[:10]
            for i, trace in enumerate(sorted_by_duration, 1):
                lines.append(f"{i}. **{trace.name}** ({trace.module or 'Unknown'}): {trace.duration:.2f}s")
            lines.append("")

            # By cost
            traces_with_cost = [t for t in all_traces if t.cost > 0]
            if traces_with_cost:
                lines.append("### Most Expensive Operations")
                lines.append("")
                sorted_by_cost = sorted(traces_with_cost, key=lambda t: t.cost, reverse=True)[:10]
                for i, trace in enumerate(sorted_by_cost, 1):
                    lines.append(f"{i}. **{trace.name}** ({trace.module or 'Unknown'}): ${trace.cost:.4f}")
                lines.append("")

        # Write to file with error handling
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            with filepath.open('w', encoding='utf-8') as f:
                f.write('\n'.join(lines))

            logger.info(f"Exported Markdown report to {filepath}")

        except PermissionError as exc:
            logger.error(f"Permission denied writing to {filepath}: {exc}")
            raise PermissionError(f"Cannot write to {filepath}: Permission denied") from exc
        except OSError as exc:
            if exc.errno == 28:
                logger.error(f"Disk full while writing to {filepath}")
                raise OSError("Disk full - cannot write export file") from exc
            else:
                logger.error(f"OS error writing to {filepath}: {exc}")
                raise OSError(f"Cannot write to {filepath}: {exc}") from exc

    @staticmethod
    def _format_task_tree(
        task: TaskViewModel,
        all_tasks: Dict[str, TaskViewModel],
        depth: int = 0,
    ) -> List[str]:
        """Format task hierarchy as markdown tree (DRY helper).

        Args:
            task: Task to format
            all_tasks: All tasks dict for looking up children
            depth: Current nesting depth

        Returns:
            List of markdown lines
        """
        indent = "  " * depth
        lines = []

        # Task summary
        status_emoji = "✓" if task.status == "completed" else "⏳" if task.status == "running" else "•"
        lines.append(
            f"{indent}- {status_emoji} **{task.goal[:80]}** "
            f"({task.total_duration:.2f}s, {task.total_tokens} tokens, ${task.total_cost:.4f})"
        )

        # Recursively add children
        for child_id in task.subtask_ids:
            child = all_tasks.get(child_id)
            if child:
                lines.extend(ExportService._format_task_tree(child, all_tasks, depth + 1))

        return lines

    @staticmethod
    def _cleanup_partial_file(filepath: Optional[Path]) -> None:
        """Clean up partial file created during failed export.

        Args:
            filepath: Path to partial file (may be None if never created)
        """
        if filepath is None:
            return

        if not filepath.exists():
            return

        try:
            filepath.unlink()
            logger.info(f"Cleaned up partial export file: {filepath}")
        except Exception as exc:
            # Log but don't raise - cleanup is best-effort
            logger.warning(f"Failed to clean up partial file {filepath}: {exc}")

    @staticmethod
    def _sanitize_execution_id(execution_id: str) -> str:
        """Sanitize execution ID for safe filename usage.

        Removes path separators and dangerous characters, keeping only
        alphanumeric characters, dashes, and underscores.

        Args:
            execution_id: Raw execution ID

        Returns:
            Sanitized execution ID (max 8 chars)

        Raises:
            ValueError: If execution_id contains no valid characters
        """
        safe_id = "".join(
            c for c in execution_id if c.isalnum() or c in "-_"
        )[:8]

        if not safe_id:
            raise ValueError(
                "Invalid execution_id: must contain at least one alphanumeric character"
            )

        return safe_id

    @staticmethod
    def _validate_export_path(filepath: Path, base_dir: Path) -> None:
        """Validate export path is within base directory and safe.

        Performs multiple security checks:
        1. Lexical check for ".." in path (before resolution)
        2. Check that base_dir itself is not a symlink to sensitive location
        3. Filesystem check that resolved path is within base directory

        Args:
            filepath: Path to validate
            base_dir: Base directory that must contain filepath

        Raises:
            ValueError: If path is unsafe or escapes base directory
        """
        # Check 1: Lexical check for path traversal attempts (before resolution)
        if ".." in str(filepath):
            raise ValueError(
                f"Path traversal detected (..): {filepath}"
            )

        # Check 2: Warn if base_dir is a symlink (potential security issue)
        if base_dir.is_symlink():
            logger.warning(
                f"Export directory is a symlink: {base_dir} -> {base_dir.resolve()}"
            )
            # Don't fail, just warn - user may have legitimate reason

        # Check 3: Filesystem check - resolved path must be within resolved base_dir
        try:
            resolved_filepath = filepath.resolve()
            resolved_base_dir = base_dir.resolve()

            # Use relative_to to check containment
            resolved_filepath.relative_to(resolved_base_dir)

            # Additional string prefix check for extra safety
            if not str(resolved_filepath).startswith(str(resolved_base_dir)):
                raise ValueError(
                    f"Resolved path escapes base directory: {resolved_filepath} "
                    f"not in {resolved_base_dir}"
                )

        except ValueError as exc:
            raise ValueError(
                f"Generated filepath is outside export directory: {filepath}"
            ) from exc

    @staticmethod
    def get_default_export_path(
        execution_id: str,
        format: str,
        scope: str,
        base_dir: Optional[Path] = None,
    ) -> Path:
        """Generate default export filepath with timestamp and security validation.

        Uses multiple layers of security checks to prevent path traversal attacks:
        - Sanitizes execution_id (removes dangerous characters)
        - Validates format and scope parameters
        - Checks for path traversal patterns before resolution
        - Validates resolved paths are within base directory
        - Checks base directory is not a symlink to sensitive location

        Args:
            execution_id: Execution ID
            format: Export format (json, csv, markdown)
            scope: Export scope (execution, task, tab)
            base_dir: Base directory (default: ~/.roma_tui/exports/)

        Returns:
            Suggested filepath

        Raises:
            ValueError: If execution_id contains invalid characters or path is unsafe
            PermissionError: If base directory is not writable
        """
        # Sanitize execution_id using helper method
        safe_execution_id = ExportService._sanitize_execution_id(execution_id)

        # Validate format and scope (prevent extension manipulation)
        if format not in ["json", "csv", "markdown", "md"]:
            raise ValueError(f"Invalid format: {format}")
        if scope not in ["execution", "task", "tab", "spans", "lm_calls", "tool_calls"]:
            raise ValueError(f"Invalid scope: {scope}")

        # Set and validate base directory
        if base_dir is None:
            base_dir = Path.home() / ".roma_tui" / "exports"

        # Ensure base_dir exists and is writable
        try:
            base_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError as exc:
            raise PermissionError(f"Cannot create export directory {base_dir}") from exc

        # Check write permissions
        if not base_dir.exists() or not base_dir.is_dir():
            raise ValueError(f"Export directory does not exist or is not a directory: {base_dir}")

        # Test write access by checking if current process can write (Bug #2 fix)
        if not os.access(base_dir, os.W_OK):
            raise PermissionError(f"Export directory is not writable: {base_dir}")

        # Generate filename with sanitized execution_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{safe_execution_id}_{scope}_{timestamp}.{format}"

        # Construct full path
        filepath = base_dir / filename

        # Comprehensive security validation using helper method
        ExportService._validate_export_path(filepath, base_dir)

        return filepath
