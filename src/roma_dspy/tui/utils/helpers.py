"""Helper utilities for TUI.

This module contains:
- ToolExtractor: Extract tool call data (ELIMINATES DUPLICATION from v1)
- Filters: Filter traces and tasks
- SearchEngine: Unified search with regex and advanced filtering
- ErrorCollector: Collect and categorize errors from tasks, spans, and tools
- wrap_tool_calls_with_trace: DRY helper to wrap tool calls with trace context
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from roma_dspy.tui.models import TaskViewModel, TraceViewModel


def wrap_tool_calls_with_trace(traces: List[TraceViewModel]) -> List[Dict[str, Any]]:
    """Wrap raw tool calls with trace context for SearchEngine and rendering.

    DRY helper: Extracts tool calls from traces and wraps each with its parent trace.
    This structure is required by SearchEngine.search_tool_calls() and used by
    TableRenderer for consistent tool call representation.

    Args:
        traces: List of trace view models

    Returns:
        List of tool call items with structure:
            {"call": {...}, "trace": trace, "module": "..."}

    Example:
        >>> traces = [trace1, trace2]
        >>> items = wrap_tool_calls_with_trace(traces)
        >>> items[0]
        {
            "call": {"tool": "web_search", "toolkit": "mcp_exa", ...},
            "trace": <TraceViewModel>,
            "module": "executor"
        }
    """
    tool_items = []
    for trace in traces:
        if trace.tool_calls:
            for call in trace.tool_calls:
                tool_items.append({
                    "call": call,
                    "trace": trace,
                    "module": trace.module or trace.name,
                })
    return tool_items


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


class SearchEngine:
    """Unified search engine with advanced filtering capabilities.

    Follows Single Responsibility Principle: handles only search/filter logic.
    Leverages existing Filters class (DRY principle).
    """

    @staticmethod
    def compile_pattern(term: str, case_sensitive: bool, use_regex: bool) -> Optional[re.Pattern]:
        """Compile search term into regex pattern.

        Args:
            term: Search term
            case_sensitive: Whether to use case-sensitive matching
            use_regex: Whether to treat term as regex pattern

        Returns:
            Compiled regex pattern or None if invalid

        Raises:
            ValueError: If regex pattern is invalid
        """
        if not term:
            return None

        if use_regex:
            flags = 0 if case_sensitive else re.IGNORECASE
            try:
                return re.compile(term, flags)
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")
        else:
            # Escape regex special chars for literal search
            escaped_term = re.escape(term)
            flags = 0 if case_sensitive else re.IGNORECASE
            return re.compile(escaped_term, flags)

    @staticmethod
    def match_pattern(pattern: re.Pattern, text: str) -> bool:
        """Check if pattern matches text.

        Args:
            pattern: Compiled regex pattern
            text: Text to search

        Returns:
            True if pattern found in text
        """
        return pattern.search(text) is not None

    @staticmethod
    def get_searchable_fields_trace(trace: TraceViewModel, include_io: bool = False) -> List[str]:
        """Get searchable text fields from a trace.

        Args:
            trace: Trace view model
            include_io: Whether to include inputs/outputs in search

        Returns:
            List of searchable text values
        """
        fields = [
            trace.name or "",
            trace.module or "",
            trace.model or "",
            str(trace.trace_id),
        ]

        if include_io:
            # Include inputs and outputs if requested
            if trace.inputs:
                fields.append(str(trace.inputs))
            if trace.outputs:
                fields.append(str(trace.outputs))
            if trace.reasoning:
                fields.append(str(trace.reasoning))

        return fields

    @staticmethod
    def get_searchable_fields_task(task: TaskViewModel) -> List[str]:
        """Get searchable text fields from a task.

        Args:
            task: Task view model

        Returns:
            List of searchable text values
        """
        return [
            task.goal or "",
            task.module or "",
            task.status or "",
            str(task.task_id),
            task.result or "",
            task.error or "",
        ]

    @staticmethod
    def get_searchable_fields_tool(tool_call: Dict[str, Any]) -> List[str]:
        """Get searchable text fields from a tool call.

        Args:
            tool_call: Tool call dictionary with "call", "trace", "module" keys

        Returns:
            List of searchable text values
        """
        # Extract the actual tool call from the structure
        call = tool_call.get("call", {})
        module = tool_call.get("module", "")

        return [
            ToolExtractor.extract_name(call),
            ToolExtractor.extract_toolkit(call),
            ToolExtractor.extract_type(call),
            str(module),
            str(call.get("status", "")),
        ]

    @classmethod
    def search_items(
        cls,
        items: List[Any],
        term: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
        field_extractor: Optional[Callable[[Any], List[str]]] = None,
    ) -> List[Any]:
        """Generic search function that works with any item type.

        Follows Open/Closed Principle: extensible via field_extractor function.

        Args:
            items: List of items to search
            term: Search term or regex pattern
            case_sensitive: Whether to use case-sensitive matching
            use_regex: Whether to treat term as regex pattern
            field_extractor: Function to extract searchable fields from each item

        Returns:
            Filtered list of matching items

        Raises:
            ValueError: If regex pattern is invalid
        """
        if not term or not items:
            return items

        try:
            pattern = cls.compile_pattern(term, case_sensitive, use_regex)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")

        if not pattern:
            return items

        def matches_item(item: Any) -> bool:
            """Check if item matches search pattern."""
            if field_extractor:
                fields = field_extractor(item)
            else:
                # Default: convert item to string
                fields = [str(item)]

            return any(cls.match_pattern(pattern, field) for field in fields)

        return [item for item in items if matches_item(item)]

    @classmethod
    def search_traces_advanced(
        cls,
        traces: List[TraceViewModel],
        term: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
        search_in_io: bool = False,
    ) -> List[TraceViewModel]:
        """Advanced trace search with regex and I/O support.

        Leverages existing search_items for DRY.

        Args:
            traces: List of traces
            term: Search term or regex pattern
            case_sensitive: Whether to use case-sensitive matching
            use_regex: Whether to treat term as regex pattern
            search_in_io: Whether to search in inputs/outputs

        Returns:
            Filtered list of matching traces

        Raises:
            ValueError: If regex pattern is invalid
        """
        return cls.search_items(
            items=traces,
            term=term,
            case_sensitive=case_sensitive,
            use_regex=use_regex,
            field_extractor=lambda t: cls.get_searchable_fields_trace(t, search_in_io),
        )

    @classmethod
    def search_tasks_advanced(
        cls,
        tasks: List[TaskViewModel],
        term: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> List[TaskViewModel]:
        """Advanced task search with regex support.

        Args:
            tasks: List of tasks
            term: Search term or regex pattern
            case_sensitive: Whether to use case-sensitive matching
            use_regex: Whether to treat term as regex pattern

        Returns:
            Filtered list of matching tasks

        Raises:
            ValueError: If regex pattern is invalid
        """
        return cls.search_items(
            items=tasks,
            term=term,
            case_sensitive=case_sensitive,
            use_regex=use_regex,
            field_extractor=cls.get_searchable_fields_task,
        )

    @classmethod
    def search_tool_calls(
        cls,
        tool_calls: List[Dict[str, Any]],
        term: str,
        case_sensitive: bool = False,
        use_regex: bool = False,
    ) -> List[Dict[str, Any]]:
        """Search tool calls.

        Args:
            tool_calls: List of tool call dictionaries
            term: Search term or regex pattern
            case_sensitive: Whether to use case-sensitive matching
            use_regex: Whether to treat term as regex pattern

        Returns:
            Filtered list of matching tool calls

        Raises:
            ValueError: If regex pattern is invalid
        """
        return cls.search_items(
            items=tool_calls,
            term=term,
            case_sensitive=case_sensitive,
            use_regex=use_regex,
            field_extractor=cls.get_searchable_fields_tool,
        )

    @staticmethod
    def filter_by_module(traces: List[TraceViewModel], module: str) -> List[TraceViewModel]:
        """Filter traces by module name.

        Args:
            traces: List of traces
            module: Module name to filter by

        Returns:
            Filtered list
        """
        if not module:
            return traces
        module_lower = module.lower()
        return [t for t in traces if (t.module or "").lower() == module_lower]

    @staticmethod
    def filter_by_model(traces: List[TraceViewModel], model: str) -> List[TraceViewModel]:
        """Filter traces by model name.

        Args:
            traces: List of traces
            model: Model name to filter by

        Returns:
            Filtered list
        """
        if not model:
            return traces
        model_lower = model.lower()
        return [t for t in traces if (t.model or "").lower() == model_lower]

    @staticmethod
    def filter_by_duration_range(
        traces: List[TraceViewModel],
        min_ms: Optional[float] = None,
        max_ms: Optional[float] = None,
    ) -> List[TraceViewModel]:
        """Filter traces by duration range.

        Args:
            traces: List of traces
            min_ms: Minimum duration in milliseconds
            max_ms: Maximum duration in milliseconds

        Returns:
            Filtered list
        """
        result = traces

        if min_ms is not None:
            result = [t for t in result if (t.duration or 0) * 1000 >= min_ms]

        if max_ms is not None:
            result = [t for t in result if (t.duration or 0) * 1000 <= max_ms]

        return result

    @staticmethod
    def filter_by_status(
        tasks: List[TaskViewModel],
        status: str,
    ) -> List[TaskViewModel]:
        """Filter tasks by status.

        Args:
            tasks: List of tasks
            status: Status to filter by (e.g., "completed", "failed")

        Returns:
            Filtered list
        """
        if not status:
            return tasks
        status_lower = status.lower()
        return [t for t in tasks if (t.status or "").lower() == status_lower]


class ErrorCollector:
    """Collect and categorize errors from tasks, spans, and tool calls."""

    def __init__(self) -> None:
        """Initialize error collector."""
        self.tool_extractor = ToolExtractor()

    @staticmethod
    def extract_exception_type(error_text: str) -> str:
        """Extract exception type from error message.

        DRY: Centralized exception type extraction utility.

        Args:
            error_text: Error message string

        Returns:
            Exception type name or "Unknown"
        """
        if not isinstance(error_text, str):
            return "Unknown"

        # Try to extract exception type from error message
        # Format: "ExceptionType: message" or just "message"
        if ":" in error_text:
            first_part = error_text.split(":", 1)[0].strip()
            # Check if it looks like an exception name (CamelCase or contains Error/Exception)
            if "Error" in first_part or "Exception" in first_part or (first_part and first_part[0].isupper()):
                return first_part

        return "Unknown"

    def collect_span_errors(self, traces: List[TraceViewModel]) -> List[Dict[str, Any]]:
        """Collect errors from traces (both span-level errors and tool call errors).

        Args:
            traces: List of trace view models

        Returns:
            List of error dictionaries with fields:
                - type: Error category (e.g., "Span Error", "Tool Error")
                - source: Span/tool name
                - message: Error message
                - timestamp: When it occurred
                - trace_id: Parent trace ID
                - span_id: Span ID (trace_id)
                - exception_type: Exception class name
                - full_error: Complete error details
        """
        errors = []

        for trace in traces:
            # First, check if the trace itself has an error (from span exception events)
            if trace.error or trace.exception:
                # Skip Tool.* spans - they'll be collected as tool errors below
                # (Tool.* child spans are now added to parent's tool_calls array)
                trace_name = trace.name or ""
                if trace_name.startswith("Tool."):
                    continue

                error_text = trace.error or "Unknown error"
                exception_type = trace.exception or self.extract_exception_type(str(error_text))

                # Truncate message for preview (keep full in full_error)
                message_preview = error_text if isinstance(error_text, str) else str(error_text)
                if len(message_preview) > 150:
                    message_preview = message_preview[:147] + "..."

                error_dict = {
                    "type": "Span Error",
                    "source": trace.name or "Unknown",
                    "message": message_preview,
                    "timestamp": trace.start_time or "",
                    "trace_id": trace.trace_id,
                    "span_id": trace.trace_id,
                    "exception_type": exception_type,
                    "full_error": error_text,
                    "trace": trace,  # Include full trace object for detail modal
                }

                errors.append(error_dict)

            # Then check tool calls within the trace
            if trace.tool_calls:
                for tool_call in trace.tool_calls:
                    if self.tool_extractor.is_successful(tool_call):
                        continue

                    # Extract error details
                    error_text = tool_call.get("error") or tool_call.get("exception") or "Unknown error"
                    tool_name = self.tool_extractor.extract_name(tool_call)

                    # Extract exception type - prefer explicit exception field if available
                    # (execution_data_service.py stores exception type in 'exception' field)
                    exception_type = tool_call.get("exception") or self.extract_exception_type(str(error_text))

                    # Truncate message for preview (keep full in full_error)
                    message_preview = error_text if isinstance(error_text, str) else str(error_text)
                    if len(message_preview) > 150:
                        message_preview = message_preview[:147] + "..."

                    error_dict = {
                        "type": "Tool Error",
                        "source": tool_name,
                        "message": message_preview,
                        "timestamp": trace.start_time or "",
                        "trace_id": trace.trace_id,
                        "span_id": trace.trace_id,  # For tools, span_id is same as trace_id
                        "exception_type": exception_type,
                        "full_error": error_text,
                        "trace": trace,  # Include full trace object for detail modal
                        "tool_call": tool_call,  # Include tool call for tool-specific detail view
                    }

                    errors.append(error_dict)

        return errors

    def collect_task_errors(self, task: TaskViewModel) -> List[Dict[str, Any]]:
        """Collect errors from task's error field.

        Args:
            task: Task view model

        Returns:
            List of error dictionaries (single item if task has error, empty list otherwise)
        """
        errors = []

        if task.error:
            error_dict = {
                "type": "Task Error",
                "source": task.goal or task.task_id,
                "message": task.error[:150] + ("..." if len(task.error) > 150 else ""),
                "timestamp": "",  # Tasks don't have timestamps in current model
                "trace_id": "",
                "span_id": "",
                "exception_type": "TaskError",
                "full_error": task.error,
            }
            errors.append(error_dict)

        return errors

    def collect_all_errors(self, task: TaskViewModel) -> List[Dict[str, Any]]:
        """Collect all errors from task and its traces.

        Args:
            task: Task view model with traces

        Returns:
            Combined list of all errors from task and spans
        """
        errors = []

        # Collect task-level errors
        errors.extend(self.collect_task_errors(task))

        # Collect span/tool errors
        if task.traces:
            errors.extend(self.collect_span_errors(task.traces))

        # Sort by timestamp (most recent first)
        errors.sort(key=lambda e: e["timestamp"], reverse=True)

        return errors
