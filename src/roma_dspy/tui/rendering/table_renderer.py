"""Unified table rendering for TUI.

This module consolidates table rendering that was duplicated 3x in v1:
- _render_lm_table() / _render_lm_table_for_agent() / _render_lm_table_all()
- _render_tool_calls_table() / _render_tool_calls_table_for_agent() / _render_tool_calls_table_all()

ELIMINATES ~220 lines of duplication!
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from loguru import logger
from textual.widgets import DataTable

from roma_dspy.tui.models import AgentGroupViewModel, ExecutionViewModel, TaskViewModel, TraceViewModel
from roma_dspy.tui.rendering.formatters import Formatters
from roma_dspy.tui.utils.helpers import ErrorCollector, Filters, ToolExtractor


class TableRenderer:
    """Unified table rendering."""

    def __init__(self, show_io: bool = False) -> None:
        """Initialize renderer.

        Args:
            show_io: Whether to show I/O in previews
        """
        self.show_io = show_io
        self.formatters = Formatters()
        self.filters = Filters()
        self.extractor = ToolExtractor()
        self.error_collector = ErrorCollector()

    def render_lm_table(
        self,
        table: DataTable,
        source: TaskViewModel | AgentGroupViewModel | ExecutionViewModel | None,
        mode: Literal["task", "agent", "all"],
        row_map: Dict[Any, TraceViewModel]
    ) -> None:
        """Unified LM table rendering.

        This ONE method replaces 3 methods from v1 (saves ~110 lines).

        Args:
            table: DataTable widget to render into
            source: Data source (task, agent group, or execution)
            mode: Rendering mode
            row_map: Dictionary to store row key -> trace mapping
        """
        # Clear table and row map
        table.clear()
        row_map.clear()

        # Get traces based on mode
        traces = self._get_traces_for_mode(source, mode)

        # Filter to only LM call spans
        lm_traces = self.filters.filter_lm_traces(traces)

        if not lm_traces:
            table.add_row("(none)", "", "", "", "")
            return

        # Display each LM call trace
        for trace in lm_traces:
            # Check if trace has errors (DRY: centralized error detection)
            has_errors = self._trace_has_errors(trace)

            # Build preview from inputs/outputs
            preview = ""
            if trace.inputs:
                preview = self.formatters.short_snippet(trace.inputs, width=80)
            if self.show_io and trace.outputs:
                preview = self.formatters.short_snippet(trace.outputs, width=80)

            # Format values
            module_or_name = trace.module or trace.name or ""
            model = trace.model or ""
            latency = self.formatters.format_duration(trace.duration)
            start_time = self.formatters.format_timestamp(trace.start_time) if trace.start_time else ""

            # Add error icon if trace has errors (span-level or tool-level)
            if has_errors:
                module_or_name = f"❌ {module_or_name}"

            row_key = table.add_row(
                module_or_name,
                model,
                start_time,
                latency,
                preview,
            )

            # Map row key to trace object for click event handling
            row_map[row_key] = trace

        logger.debug(f"Rendered LM table: mode={mode}, rows={len(lm_traces)}")

    def render_tool_table(
        self,
        table: DataTable,
        source: TaskViewModel | AgentGroupViewModel | ExecutionViewModel | None,
        mode: Literal["task", "agent", "all"],
        row_map: Dict[Any, Dict[str, Any]]
    ) -> None:
        """Unified tool table rendering.

        This ONE method replaces 3 methods from v1 (saves ~110 lines).

        Args:
            table: DataTable widget to render into
            source: Data source (task, agent group, or execution)
            mode: Rendering mode
            row_map: Dictionary to store row key -> tool call mapping
        """
        # Clear table and row map
        table.clear()
        row_map.clear()

        # Get tool calls based on mode
        tool_calls = self._get_tool_calls_for_mode(source, mode)

        if not tool_calls:
            table.add_row("(none)", "", "", "", "", "", "")
            return

        # Display each tool call
        for item in tool_calls:
            call = item["call"]
            trace = item["trace"]

            # Extract tool info
            tool_name = self.extractor.extract_name(call)
            toolkit = self.extractor.extract_toolkit(call)
            tool_type = self.extractor.extract_type(call)

            # Calculate duration and start time from trace
            duration = self.formatters.format_duration(trace.duration)
            start_time = self.formatters.format_timestamp(trace.start_time) if trace.start_time else ""

            # Determine status and if tool failed
            is_successful = self.extractor.is_successful(call)
            status = "✓" if is_successful else "✗"

            # Build preview from arguments/output based on toggle
            preview = ""
            if self.show_io:
                # Show output if toggle is ON
                output = self.extractor.extract_output(call)

                # If no output in call, try trace outputs as fallback
                if output is None and trace and trace.outputs:
                    output = trace.outputs

                if output is not None:
                    preview = self.formatters.short_snippet(output, width=80)
                else:
                    # Fallback to arguments if still no output
                    args = self.extractor.extract_arguments(call)
                    if args is not None:
                        preview = f"[dim]{self.formatters.short_snippet(args, width=80)}[/dim]"
                if not is_successful:
                    error_text = call.get("error") or call.get("exception")
                    if error_text:
                        preview = self.formatters.short_snippet(error_text, width=80)
            else:
                # Show arguments if toggle is OFF (default)
                args = self.extractor.extract_arguments(call)
                if args is not None:
                    preview = self.formatters.short_snippet(args, width=80)

            if not preview and not is_successful:
                error_text = call.get("error") or call.get("exception")
                if error_text:
                    preview = self.formatters.short_snippet(error_text, width=80)

            # Apply red styling to failed tools
            if not is_successful:
                tool_name = f"[red]{tool_name}[/red]"
                status = f"[red]{status}[/red]"
                preview = f"[red]{preview}[/red]"

            row_key = table.add_row(
                tool_name,
                tool_type,
                toolkit,
                start_time,
                duration,
                status,
                preview,
            )

            # Map row key to tool call dict
            row_map[row_key] = item

        logger.debug(f"Rendered tool table: mode={mode}, rows={len(tool_calls)}")

    def _trace_has_errors(self, trace: Any) -> bool:
        """Check if a trace has any errors (span-level or tool-level).

        DRY: Centralized error detection logic for consistent error indicators.

        Args:
            trace: TraceViewModel to check

        Returns:
            True if trace has errors, False otherwise
        """
        # Check span-level errors (from trace.error or trace.exception)
        if hasattr(trace, 'error') and trace.error:
            return True
        if hasattr(trace, 'exception') and trace.exception:
            return True

        # Check tool call errors
        if hasattr(trace, 'tool_calls') and trace.tool_calls:
            return any(
                not self.extractor.is_successful(tool_call)
                for tool_call in trace.tool_calls
            )

        return False

    def _get_traces_for_mode(
        self,
        source: TaskViewModel | AgentGroupViewModel | ExecutionViewModel | None,
        mode: Literal["task", "agent", "all"]
    ) -> List[TraceViewModel]:
        """Get traces based on mode.

        Args:
            source: Data source
            mode: Rendering mode

        Returns:
            List of traces
        """
        if mode == "task" and isinstance(source, TaskViewModel):
            return source.traces
        elif mode == "agent" and isinstance(source, AgentGroupViewModel):
            return source.traces
        elif mode == "all" and isinstance(source, ExecutionViewModel):
            # Collect all traces from all tasks
            all_traces: List[TraceViewModel] = []
            for task in source.tasks.values():
                all_traces.extend(task.traces)
            return all_traces
        else:
            logger.warning(f"Invalid mode/source combination: mode={mode}, source={type(source)}")
            return []

    def _get_tool_calls_for_mode(
        self,
        source: TaskViewModel | AgentGroupViewModel | ExecutionViewModel | None,
        mode: Literal["task", "agent", "all"]
    ) -> List[Dict[str, Any]]:
        """Get tool calls based on mode.

        DRY: Uses shared utility function to wrap tool calls with trace context.

        Args:
            source: Data source
            mode: Rendering mode

        Returns:
            List of tool call dicts with trace context
        """
        from roma_dspy.tui.utils.helpers import wrap_tool_calls_with_trace

        traces = self._get_traces_for_mode(source, mode)
        return wrap_tool_calls_with_trace(traces)

    def render_error_table(
        self,
        table: DataTable,
        source: Any,  # TaskViewModel | AgentGroupViewModel | ExecutionViewModel | None
        row_map: Dict[Any, Dict[str, Any]]
    ) -> None:
        """Render error analysis table.

        Args:
            table: DataTable widget to render into
            source: Task, AgentGroup, or Execution to extract errors from
            row_map: Dictionary to store row key -> error mapping
        """
        from roma_dspy.tui.models import ExecutionViewModel, TaskViewModel

        # Clear table and row map
        table.clear()
        row_map.clear()

        # Collect errors based on source type
        errors = []

        if isinstance(source, TaskViewModel):
            # Single task: collect its errors
            errors = self.error_collector.collect_all_errors(source)
        elif isinstance(source, ExecutionViewModel):
            # Execution: collect errors from all tasks
            for task in source.tasks.values():
                errors.extend(self.error_collector.collect_all_errors(task))
        elif source is None:
            # No source provided
            table.add_row("(no data loaded)", "", "", "")
            return
        else:
            # Unknown source type - try to treat as task
            if hasattr(source, 'traces'):
                errors = self.error_collector.collect_all_errors(source)

        if not errors:
            table.add_row("(no errors found)", "", "", "")
            return

        # Display each error
        for error in errors:
            # Severity icon based on error type
            severity_icon = ""
            if "Authentication" in error["exception_type"] or "Critical" in error["type"]:
                severity_icon = "🔴"
            elif "Parse" in error["exception_type"] or "Tool" in error["type"]:
                severity_icon = "🟡"
            else:
                severity_icon = "🟠"

            # Format error type with icon
            error_type = f"{severity_icon} {error['exception_type']}"

            # Format timestamp
            timestamp = ""
            if error["timestamp"]:
                timestamp = self.formatters.format_timestamp(error["timestamp"])

            # Truncate error message for table view (keep full message in row_map for detail modal)
            error_message = error["message"]
            if len(error_message) > 60:
                error_message = error_message[:57] + "..."

            row_key = table.add_row(
                error_type,
                error["source"],
                error_message,  # Shortened for table view
                timestamp,
            )

            # Map row key to error dict for detail modal
            row_map[row_key] = error

        logger.debug(f"Rendered error table: {len(errors)} errors")
