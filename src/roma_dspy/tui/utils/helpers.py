"""Helper utilities for TUI v2.

This module contains:
- ToolExtractor: Extract tool call data (ELIMINATES DUPLICATION from v1)
- Filters: Filter traces and tasks
"""

from __future__ import annotations

from typing import Any, Dict, List

from roma_dspy.tui.models import TaskViewModel, TraceViewModel


class ToolExtractor:
    """Extract tool call information.

    This class consolidates tool extraction logic that was duplicated
    in both app.py and detail_view.py in v1 (~150 lines of duplication).
    """

    @staticmethod
    def extract_name(call: Dict[str, Any]) -> str:
        """Extract tool name from tool call dict.

        Args:
            call: Tool call dictionary

        Returns:
            Tool name or "unknown"
        """
        if not isinstance(call, dict):
            return str(call)

        # Try function object first (OpenAI format)
        func = call.get("function")
        if isinstance(func, dict):
            func_name = func.get("name")
            if func_name:
                return func_name

        # Try various field names
        name = (
            call.get("roma.tool_name") or
            call.get("tool") or
            call.get("tool_name") or
            call.get("name") or
            call.get("type") or
            call.get("id")
        )

        return name or "unknown"

    @staticmethod
    def extract_toolkit(call: Dict[str, Any]) -> str:
        """Extract toolkit name from tool call dict.

        Args:
            call: Tool call dictionary

        Returns:
            Toolkit name or "-"
        """
        if not isinstance(call, dict):
            return "-"

        raw_attrs = call.get("attributes")
        attrs = raw_attrs if isinstance(raw_attrs, dict) else None

        toolkit = (
            call.get("roma.toolkit_name")
            or call.get("toolkit")
            or call.get("toolkit_class")
            or call.get("source")
            or (attrs.get("roma.toolkit_name") if attrs else None)
        )
        return toolkit or "-"

    @staticmethod
    def extract_type(call: Dict[str, Any]) -> str:
        """Extract tool type (builtin, mcp, etc.)."""
        if not isinstance(call, dict):
            return "-"

        raw_attrs = call.get("attributes")
        attrs = raw_attrs if isinstance(raw_attrs, dict) else None

        tool_type = (
            call.get("roma.tool_type")
            or call.get("tool_type")
            or (attrs.get("roma.tool_type") if attrs else None)
            or call.get("type")
        )

        if isinstance(tool_type, str):
            return tool_type

        if isinstance(tool_type, dict):
            return tool_type.get("name", "-")

        return str(tool_type) if tool_type is not None else "-"

    @staticmethod
    def extract_arguments(call: Dict[str, Any]) -> Any:
        """Extract arguments from tool call dict.

        Args:
            call: Tool call dictionary

        Returns:
            Arguments or None
        """
        if not isinstance(call, dict):
            return None

        # Try function.arguments first (OpenAI format)
        func = call.get("function")
        if isinstance(func, dict):
            args = func.get("arguments")
            if args is not None:
                return args

        # Try direct arguments
        args = (
            call.get("arguments") or
            call.get("args") or
            call.get("input") or
            call.get("params") or
            call.get("parameters")
        )
        if args is not None:
            return args

        # Fallback: return whole call dict minus known metadata fields
        excluded_keys = {
            "tool", "tool_name", "name", "type", "id",
            "function", "output", "result", "return",
            "error", "status", "toolkit", "toolkit_class", "source"
        }
        filtered = {k: v for k, v in call.items() if k not in excluded_keys}
        return filtered if filtered else None

    @staticmethod
    def extract_output(call: Dict[str, Any]) -> Any:
        """Extract output/result from tool call dict.

        Args:
            call: Tool call dictionary

        Returns:
            Output or None
        """
        if not isinstance(call, dict):
            return None

        # Try various output field names in the call itself
        output = (
            call.get("output") or
            call.get("result") or
            call.get("return") or
            call.get("response")
        )
        if output is not None:
            return output

        # Check function.output (OpenAI format)
        func = call.get("function")
        if isinstance(func, dict):
            func_output = func.get("output") or func.get("result")
            if func_output is not None:
                return func_output

        # Check for content field (some frameworks use this)
        content = call.get("content")
        if content is not None:
            return content

        return None

    @staticmethod
    def is_successful(call: Dict[str, Any]) -> bool:
        """Check if tool call was successful.

        Args:
            call: Tool call dictionary

        Returns:
            True if successful, False otherwise
        """
        if not isinstance(call, dict):
            return True

        # Check for error field - if present, call failed
        if call.get("error") or call.get("exception"):
            return False

        # Check for explicit status field
        status = call.get("status")
        if status:
            status_str = str(status).lower()
            if status_str in ("failed", "error", "failure"):
                return False
            if status_str in ("success", "ok", "completed"):
                return True

        # If no error and no explicit failure status, assume success
        return True


class Filters:
    """Filter traces and tasks."""

    @staticmethod
    def is_lm_call(trace: TraceViewModel) -> bool:
        """Check if trace is an LM call.

        Args:
            trace: Trace view model

        Returns:
            True if LM call
        """
        # LM calls typically have tokens or model, and name contains "lm" or "call"
        has_tokens_or_model = trace.tokens > 0 or trace.model is not None
        name_lower = (trace.name or "").lower()
        has_lm_name = "lm" in name_lower or "call" in name_lower

        return has_tokens_or_model and has_lm_name

    @staticmethod
    def is_wrapper_span(trace: TraceViewModel) -> bool:
        """Check if trace is a wrapper span (should be hidden from timeline).

        Args:
            trace: Trace view model

        Returns:
            True if wrapper span
        """
        name = (trace.name or "").lower()
        wrapper_names = {
            "atomizer", "planner", "executor", "aggregator", "verifier",
            "agent executor", "agent_wrapper", "module_wrapper"
        }
        return name in wrapper_names

    @staticmethod
    def is_wrapper_for_table(trace: TraceViewModel) -> bool:
        """Check if trace is a generic wrapper (should be hidden from table).

        Different from is_wrapper_span - this only hides generic wrappers,
        not agent-type wrappers which should be visible in the table.

        Args:
            trace: Trace view model

        Returns:
            True if generic wrapper
        """
        name = (trace.name or "").lower()
        # Don't hide agent-type wrappers - they should be visible!
        agent_types = {"atomizer", "planner", "executor", "aggregator", "verifier"}
        if name in agent_types:
            return False

        # Only hide generic wrapper names
        return name in {"agent executor", "agent_wrapper", "module_wrapper"}

    @staticmethod
    def filter_lm_traces(traces: List[TraceViewModel]) -> List[TraceViewModel]:
        """Filter to only LM call traces.

        Args:
            traces: List of traces

        Returns:
            Filtered list of LM call traces
        """
        return [t for t in traces if Filters.is_lm_call(t)]

    @staticmethod
    def filter_non_wrapper_traces(traces: List[TraceViewModel]) -> List[TraceViewModel]:
        """Filter out wrapper spans.

        Args:
            traces: List of traces

        Returns:
            Filtered list without wrappers
        """
        return [t for t in traces if not Filters.is_wrapper_span(t)]

    @staticmethod
    def search_traces(
        traces: List[TraceViewModel],
        search_term: str,
        case_sensitive: bool = False
    ) -> List[TraceViewModel]:
        """Search traces by term.

        Args:
            traces: List of traces
            search_term: Search term
            case_sensitive: Whether search is case-sensitive

        Returns:
            Filtered list of matching traces
        """
        if not search_term:
            return traces

        term = search_term if case_sensitive else search_term.lower()

        def matches(trace: TraceViewModel) -> bool:
            """Check if trace matches search term."""
            fields = [
                trace.name or "",
                trace.module or "",
                trace.model or "",
                str(trace.trace_id) or ""
            ]

            for field in fields:
                value = field if case_sensitive else field.lower()
                if term in value:
                    return True
            return False

        return [t for t in traces if matches(t)]

    @staticmethod
    def search_tasks(
        tasks: List[TaskViewModel],
        search_term: str,
        case_sensitive: bool = False
    ) -> List[TaskViewModel]:
        """Search tasks by term.

        Args:
            tasks: List of tasks
            search_term: Search term
            case_sensitive: Whether search is case-sensitive

        Returns:
            Filtered list of matching tasks
        """
        if not search_term:
            return tasks

        term = search_term if case_sensitive else search_term.lower()

        def matches(task: TaskViewModel) -> bool:
            """Check if task matches search term."""
            fields = [
                task.goal or "",
                task.module or "",
                str(task.task_id) or "",
                task.status or ""
            ]

            for field in fields:
                value = field if case_sensitive else field.lower()
                if term in value:
                    return True
            return False

        return [t for t in tasks if matches(t)]
