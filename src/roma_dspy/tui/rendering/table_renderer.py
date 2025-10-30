"""Unified table rendering for TUI v2.

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
from roma_dspy.tui.utils.helpers import Filters, ToolExtractor


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
            table.add_row("(none)", "", "", "")
            return

        # Display each LM call trace
        for trace in lm_traces:
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

            row_key = table.add_row(
                module_or_name,
                model,
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
            table.add_row("(none)", "", "", "", "", "")
            return

        # Display each tool call
        for item in tool_calls:
            call = item["call"]
            trace = item["trace"]

            # Extract tool info
            tool_name = self.extractor.extract_name(call)
            toolkit = self.extractor.extract_toolkit(call)
            tool_type = self.extractor.extract_type(call)

            # Calculate duration from trace
            duration = self.formatters.format_duration(trace.duration)

            # Determine status
            status = "✓" if self.extractor.is_successful(call) else "✗"

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
                if not self.extractor.is_successful(call):
                    error_text = call.get("error") or call.get("exception")
                    if error_text:
                        preview = self.formatters.short_snippet(error_text, width=80)
            else:
                # Show arguments if toggle is OFF (default)
                args = self.extractor.extract_arguments(call)
                if args is not None:
                    preview = self.formatters.short_snippet(args, width=80)

            if not preview and not self.extractor.is_successful(call):
                error_text = call.get("error") or call.get("exception")
                if error_text:
                    preview = self.formatters.short_snippet(error_text, width=80)

            row_key = table.add_row(
                tool_name,
                tool_type,
                toolkit,
                duration,
                status,
                preview,
            )

            # Map row key to tool call dict
            row_map[row_key] = item

        logger.debug(f"Rendered tool table: mode={mode}, rows={len(tool_calls)}")

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

        Args:
            source: Data source
            mode: Rendering mode

        Returns:
            List of tool call dicts with trace context
        """
        traces = self._get_traces_for_mode(source, mode)

        tool_calls = []
        for trace in traces:
            if trace.tool_calls:
                for call in trace.tool_calls:
                    # Add trace context to tool call
                    tool_calls.append({
                        "call": call,
                        "trace": trace,
                        "module": trace.module or trace.name,
                    })

        return tool_calls
