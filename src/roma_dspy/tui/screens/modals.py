"""Modal screens for TUI.

Provides detail modals, help modal, and export modal with full parsing system.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger
from rich.markup import escape
from rich.syntax import Syntax
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Checkbox, Collapsible, Input, Label, RadioButton, RadioSet, Static, Tree
from textual.widgets.tree import TreeNode

from roma_dspy.tui.models import TraceViewModel
from roma_dspy.tui.utils.helpers import ErrorCollector, ToolExtractor
from roma_dspy.tui.rendering.formatters import Formatters


# =============================================================================
# DATA TYPES AND ENUMS
# =============================================================================


class DataType(Enum):
    """Type of data in a section."""

    NESTED = "nested"  # Dicts, lists - use tree view
    TEXT = "text"  # Plain text - use text area
    CODE = "code"  # Code snippets - use syntax highlighting
    MARKDOWN = "markdown"  # Rich text - use markdown renderer
    UNKNOWN = "unknown"  # Auto-detect


class ViewMode(Enum):
    """How to render the data."""

    AUTO = "auto"  # Auto-detect best view
    TREE = "tree"  # Interactive tree
    RAW = "raw"  # Raw text/JSON
    FORMATTED = "formatted"  # Pretty-printed
    CUSTOM = "custom"  # Custom renderer


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class DetailSection:
    """A collapsible section in the detail view."""

    id: str  # "input", "output", "reasoning"
    title: str  # "Input", "Output", "Reasoning"
    icon: str  # "📥", "📤", "🧠"
    data: Any  # The actual data
    data_type: DataType  # Type of data
    collapsed: bool = False  # Initial collapsed state
    view_mode: ViewMode = ViewMode.AUTO  # How to display
    renderer_hint: Optional[str] = None  # "json", "python", "markdown"


@dataclass
class DetailViewData:
    """Normalized container for any detail view."""

    title: str  # "Span: ChainOfThought.forward"
    metadata: Dict[str, Any]  # Simple key-value pairs (always visible)
    sections: List[Optional[DetailSection]]  # Collapsible sections (None = skip)
    source_object: Any  # Original object for reference


# =============================================================================
# PARSERS - Convert domain objects to DetailViewData
# =============================================================================


class DetailViewParser(ABC):
    """Base parser - converts objects to DetailViewData."""

    def __init__(self) -> None:
        """Initialize parser."""
        self.formatters = Formatters()

    @abstractmethod
    def parse(self, obj: Any, context: str = "unknown", show_io: bool = True) -> DetailViewData:
        """Parse any object into normalized detail view data.

        Args:
            obj: Source object to parse
            context: Context string for logging/debugging
            show_io: Whether to include I/O sections (default: True)
        """
        pass

    def _detect_type(self, data: Any) -> DataType:
        """Auto-detect data type."""
        if data is None:
            return DataType.TEXT

        if isinstance(data, (dict, list)):
            return DataType.NESTED

        if isinstance(data, str):
            # Check if it's JSON, code, markdown, etc.
            stripped = data.strip()

            # JSON-like
            if stripped.startswith(("{", "[")):
                return DataType.CODE

            # Multi-line text
            if "\n" in data and len(data) > 200:
                return DataType.TEXT

            # Short text
            return DataType.TEXT

        # Numbers, booleans, etc.
        return DataType.TEXT

    def _extract_exception_type(self, error_text: str) -> str:
        """Extract exception type from error message.

        DRY: Delegates to ErrorCollector.extract_exception_type for centralized logic.

        Args:
            error_text: Error message string

        Returns:
            Exception type name or "Unknown"
        """
        return ErrorCollector.extract_exception_type(error_text)


class SpanDetailParser(DetailViewParser):
    """Parser for TraceViewModel objects (spans/LM calls)."""

    def __init__(self) -> None:
        """Initialize parser with formatters and tool extractor."""
        super().__init__()
        self.extractor = ToolExtractor()

    def parse(self, obj: Any, context: str = "span", show_io: bool = True) -> DetailViewData:
        """Parse a TraceViewModel into detail view data."""
        if not isinstance(obj, TraceViewModel):
            raise TypeError(f"Expected TraceViewModel, got {type(obj)}")

        trace = obj

        # Build title with module, name, and context
        module_name = trace.module or "Unknown Module"
        span_name = trace.name or "Unknown"

        # Create comprehensive title
        if trace.module and trace.name and trace.module != trace.name:
            title = f"{escape(module_name)} → {escape(span_name)}"
        else:
            title = f"{escape(module_name)}"

        # Build metadata (always visible at top)
        metadata = {}

        # Task context (show first if available)
        if trace.task_id:
            task_id_short = trace.task_id[:16] if len(trace.task_id) > 16 else trace.task_id
            metadata["Task ID"] = escape(task_id_short)

        # Agent type (module name represents the agent)
        if trace.module:
            metadata["Agent"] = escape(trace.module)

        if trace.duration > 0:
            metadata["Duration"] = self.formatters.format_duration(trace.duration)
        if trace.tokens > 0:
            metadata["Tokens"] = self.formatters.format_tokens(trace.tokens)
        if trace.cost > 0:
            metadata["Cost"] = self.formatters.format_cost(trace.cost)
        if trace.model:
            metadata["Model"] = escape(trace.model)
        if trace.temperature is not None:
            metadata["Temperature"] = str(trace.temperature)
        if trace.start_time:
            metadata["Start Time"] = escape(trace.start_time)
        if trace.trace_id:
            metadata["Trace ID"] = escape(trace.trace_id)

        # Check for span-level errors first (DRY: centralized error detection)
        has_span_error = (hasattr(trace, 'error') and trace.error) or (hasattr(trace, 'exception') and trace.exception)

        # Check for errors in tool calls (DRY: use self.extractor)
        error_count = 0
        failed_tools = []
        if trace.tool_calls:
            for tool_call in trace.tool_calls:
                if not self.extractor.is_successful(tool_call):
                    error_count += 1
                    tool_name = self.extractor.extract_name(tool_call)
                    failed_tools.append(tool_name)

        # Add error indicator to metadata if errors exist
        if has_span_error or error_count > 0:
            if has_span_error:
                exception_type = trace.exception or "Error"
                metadata["Errors"] = f"❌ Span Error: {escape(exception_type)}"
            elif error_count > 0:
                error_summary = f"⚠️ {error_count} tool error{'s' if error_count > 1 else ''}"
                if failed_tools:
                    tools_preview = ", ".join(failed_tools[:2])
                    if len(failed_tools) > 2:
                        tools_preview += f", +{len(failed_tools) - 2} more"
                    error_summary += f" ({tools_preview})"
                metadata["Errors"] = error_summary

        # Add I/O summary to metadata
        available_sections = []
        if trace.inputs:
            available_sections.append("Input")
        if trace.outputs:
            available_sections.append("Output")
        if trace.reasoning:
            available_sections.append("Reasoning")

        if available_sections:
            sections_list = ", ".join(available_sections)
            if show_io:
                metadata["I/O"] = f"✓ Showing: {sections_list}"
            else:
                metadata["I/O"] = f"✗ Hidden: {sections_list} (press 'l' to show)"
        else:
            metadata["I/O"] = "No data available"

        # Ensure metadata is never empty
        if not metadata:
            metadata["Status"] = "Active"

        # Build sections
        sections = []

        # Add error sections ONLY if show_io is True
        # When I/O Display is OFF, only show error summary in metadata (not detailed sections)
        if show_io:
            # Add span error section if span-level error exists
            if has_span_error:
                error_text = trace.error or "Unknown error"
                exception_type = trace.exception or "Error"

                # Split error message from stacktrace if present
                error_message = error_text
                stacktrace = None
                if "Traceback (most recent call last):" in str(error_text):
                    parts = str(error_text).split("Traceback (most recent call last):", 1)
                    error_message = parts[0].strip() or "Error occurred (see stacktrace)"
                    stacktrace = "Traceback (most recent call last):" + parts[1]

                # Add error message section
                sections.append(
                    DetailSection(
                        id="span_error",
                        title=f"Span Error: {exception_type}",
                        icon="❌",
                        data=error_message,
                        data_type=DataType.TEXT,
                        collapsed=False,
                        view_mode=ViewMode.AUTO,
                    )
                )

                # Add stacktrace section if available
                if stacktrace:
                    sections.append(
                        DetailSection(
                            id="stacktrace",
                            title="Stack Trace",
                            icon="📜",
                            data=stacktrace,
                            data_type=DataType.CODE,
                            collapsed=False,
                            view_mode=ViewMode.AUTO,
                            renderer_hint="python",
                        )
                    )

            # Add tool error summary section if tool errors exist
            if error_count > 0 and trace.tool_calls:
                error_details = self._extract_error_details(trace.tool_calls)

                sections.append(
                    DetailSection(
                        id="tool_errors",
                        title=f"Tool Errors ({error_count})",
                        icon="⚠️",
                        data=error_details,
                        data_type=DataType.NESTED,
                        collapsed=False,
                        view_mode=ViewMode.TREE,
                    )
                )

        # Add I/O sections ONLY if show_io is True
        # When I/O Display is OFF, user wants minimal view (metadata only)
        if show_io:
            # Section 1: Input
            if trace.inputs:
                sections.append(
                    DetailSection(
                        id="input",
                        title="Input",
                        icon="📥",
                        data=trace.inputs,
                        data_type=self._detect_type(trace.inputs),
                        collapsed=False,
                        view_mode=ViewMode.AUTO,
                    )
                )

            # Section 2: Output
            if trace.outputs:
                sections.append(
                    DetailSection(
                        id="output",
                        title="Output",
                        icon="📤",
                        data=trace.outputs,
                        data_type=self._detect_type(trace.outputs),
                        collapsed=False,
                        view_mode=ViewMode.AUTO,
                    )
                )

            # Section 3: Reasoning (if present)
            if trace.reasoning:
                sections.append(
                    DetailSection(
                        id="reasoning",
                        title="Reasoning",
                        icon="🧠",
                        data=trace.reasoning,
                        data_type=DataType.TEXT,
                        collapsed=True,
                        view_mode=ViewMode.AUTO,
                    )
                )

        # Section 4: Tool Calls (always visible - metadata, not I/O)
        if trace.tool_calls:
            sections.append(
                DetailSection(
                    id="tool_calls",
                    title="Tool Calls",
                    icon="🔧",
                    data=trace.tool_calls,
                    data_type=DataType.NESTED,
                    collapsed=True,
                    view_mode=ViewMode.TREE,
                )
            )

        return DetailViewData(
            title=title, metadata=metadata, sections=sections, source_object=trace
        )

    def _extract_error_details(self, tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract error details from failed tool calls.

        Single Responsibility: Error extraction logic centralized here.

        Args:
            tool_calls: List of tool call dictionaries

        Returns:
            List of error detail dictionaries with 'tool' and 'error' keys
        """
        error_details = []
        for tool_call in tool_calls:
            if not self.extractor.is_successful(tool_call):
                tool_name = self.extractor.extract_name(tool_call)
                error_text = tool_call.get("error") or tool_call.get("exception") or "Unknown error"
                error_details.append({
                    "tool": tool_name,
                    "error": error_text
                })
        return error_details


class ToolCallDetailParser(DetailViewParser):
    """Parser for tool call dictionaries."""

    def __init__(self) -> None:
        super().__init__()
        self.extractor = ToolExtractor()

    def parse(self, obj: Any, context: str = "tool", show_io: bool = True) -> DetailViewData:
        """Parse a tool call dict into detail view data.

        Args:
            obj: Tool item dict with keys: 'call', 'trace', 'module'
            context: Additional context string
            show_io: Whether to include I/O sections (default: True)
        """
        if not isinstance(obj, dict):
            raise TypeError(f"Expected dict, got {type(obj)}")

        call = obj.get("call", {})
        trace = obj.get("trace")
        module_name = obj.get("module", "unknown")

        # Extract tool name
        tool_name = self._extract_tool_name(call)

        # Build title
        title = f"Tool Call: {escape(tool_name)}"

        # Build metadata
        metadata = {}

        # Tool info
        toolkit = self.extractor.extract_toolkit(call) or "unknown"
        tool_type = self.extractor.extract_type(call)
        metadata["Tool"] = escape(tool_name)
        metadata["Toolkit"] = escape(toolkit)
        metadata["Type"] = escape(tool_type)

        tool_id = call.get("id") or call.get("tool_call_id") or call.get("call_id")
        if tool_id:
            metadata["Call ID"] = escape(str(tool_id))

        execution_id = call.get("roma.execution_id") or call.get("execution_id")
        if execution_id:
            metadata["Execution"] = escape(str(execution_id))[:16]

        enhanced_flag = call.get("roma.enhanced") or call.get("enhanced")
        if enhanced_flag is not None:
            enhanced_text = "Yes" if str(enhanced_flag).lower() in {"true", "1", "yes"} else "No"
            metadata["Span Enhanced"] = enhanced_text

        # Duration (if available)
        duration_ms = call.get("duration_ms") or call.get("duration")
        if duration_ms:
            # Convert milliseconds to seconds
            duration_s = duration_ms / 1000.0
            metadata["Duration"] = f"{duration_s:.3f}s"
        elif trace and trace.duration:
            metadata["Duration"] = self.formatters.format_duration(trace.duration)

        # Status
        success = self._tool_call_successful(call)
        metadata["Status"] = "✓ Success" if success else "✗ Failed"

        # Add exception type to metadata if tool failed (DRY: use base parser method)
        if not success:
            error_text = call.get("error") or call.get("exception")
            if error_text:
                exception_type = self._extract_exception_type(str(error_text))
                if exception_type != "Unknown":
                    metadata["Exception"] = escape(exception_type)

        # Module
        if module_name and module_name != "unknown":
            metadata["Module"] = escape(module_name)

        # Extract arguments and output
        # IMPORTANT: Extract from call dict FIRST, not from parent trace
        # The trace.inputs/outputs are the parent span's data (e.g., executor module),
        # not the individual tool call's arguments/output
        args = self.extractor.extract_arguments(call)
        if args is None:
            args = self._extract_tool_arguments(call)

        output = self.extractor.extract_output(call)
        if output is None:
            output = self._extract_tool_output(call)
            # If output is a JSON string, parse it
            if isinstance(output, str):
                try:
                    import json
                    output = json.loads(output)
                except (json.JSONDecodeError, ValueError):
                    pass

        available_sections = []
        if args is not None:
            available_sections.append("Arguments")
        if output is not None:
            available_sections.append("Output")

        # Add I/O summary to metadata
        if available_sections:
            sections_list = ", ".join(available_sections)
            if show_io:
                metadata["I/O"] = f"✓ Showing: {sections_list}"
            else:
                metadata["I/O"] = f"✗ Hidden: {sections_list}"
        else:
            metadata["I/O"] = "No data available"

        # Check for span-level error and add to metadata
        if trace and ((hasattr(trace, 'error') and trace.error) or (hasattr(trace, 'exception') and trace.exception)):
            span_exception = trace.exception or "Error"
            metadata["Parent Span"] = f"🔴 Error: {escape(span_exception)}"

        # Ensure metadata is never empty
        if not metadata:
            metadata["Status"] = "Active"

        # Build sections
        sections = []

        # Check for span-level error (parent span that contains this tool call)
        has_span_error = trace and ((hasattr(trace, 'error') and trace.error) or (hasattr(trace, 'exception') and trace.exception))

        # Only add error and I/O sections if show_io is True
        if show_io:
            # Add span error section if parent span has an error (shown first)
            if has_span_error:
                span_error_text = trace.error or "Unknown error"
                span_exception_type = trace.exception or "Error"

                # Split error message from stacktrace if present
                span_error_message = span_error_text
                span_stacktrace = None
                if "Traceback (most recent call last):" in str(span_error_text):
                    parts = str(span_error_text).split("Traceback (most recent call last):", 1)
                    span_error_message = parts[0].strip() or "Error occurred in parent span (see stacktrace)"
                    span_stacktrace = "Traceback (most recent call last):" + parts[1]

                sections.append(
                    DetailSection(
                        id="span_error",
                        title=f"Parent Span Error: {span_exception_type}",
                        icon="🔴",
                        data=span_error_message,
                        data_type=DataType.TEXT,
                        collapsed=False,
                        view_mode=ViewMode.AUTO,
                    )
                )

                # Add stacktrace if available
                if span_stacktrace:
                    sections.append(
                        DetailSection(
                            id="span_stacktrace",
                            title="Span Stack Trace",
                            icon="📜",
                            data=span_stacktrace,
                            data_type=DataType.CODE,
                            collapsed=True,
                            view_mode=ViewMode.AUTO,
                            renderer_hint="python",
                        )
                    )

            # Section 1: Arguments
            if args is not None:
                sections.append(
                    DetailSection(
                        id="arguments",
                        title="Arguments",
                        icon="📝",
                        data=args,
                        data_type=self._detect_type(args),
                        collapsed=False,
                        view_mode=ViewMode.AUTO,
                    )
                )

            # Section 2: Output
            if output is not None:
                output_to_display = output

                # Check if this is a code execution output with stdout
                if isinstance(output, dict) and "stdout" in output:
                    stdout = output.get("stdout", [])

                    # If stdout is a list, join it
                    if isinstance(stdout, list):
                        stdout_text = "".join(stdout)
                    else:
                        stdout_text = str(stdout)

                    # Create restructured output that shows stdout first
                    if stdout_text:
                        output_to_display = {
                            "stdout": stdout_text,
                            "success": output.get("success"),
                            "results": output.get("results"),
                            "stderr": output.get("stderr"),
                            "error": output.get("error"),
                            "sandbox_id": output.get("sandbox_id"),
                        }
                        # Remove None/empty values
                        output_to_display = {
                            k: v for k, v in output_to_display.items()
                            if v is not None and v != [] and v != ""
                        }

                sections.append(
                    DetailSection(
                        id="output",
                        title="Output",
                        icon="📤",
                        data=output_to_display,
                        data_type=self._detect_type(output_to_display),
                        collapsed=False,
                        view_mode=ViewMode.AUTO,
                    )
                )

            # Section 3: Error (only visible when show_io is enabled)
            error = call.get("error") or call.get("exception")
            if error:
                sections.append(
                    DetailSection(
                        id="error",
                        title="Error",
                        icon="❌",
                        data=error,
                        data_type=self._detect_type(error),
                        collapsed=False,
                        view_mode=ViewMode.AUTO,
                    )
                )

        events = call.get("events") or call.get("event")
        if events:
            sections.append(
                DetailSection(
                    id="events",
                    title="Events",
                    icon="📌",
                    data=events,
                    data_type=self._detect_type(events),
                    collapsed=True,
                    view_mode=ViewMode.AUTO,
                )
            )

        return DetailViewData(
            title=title, metadata=metadata, sections=sections, source_object=obj
        )

    def _extract_tool_name(self, call: Dict[str, Any]) -> str:
        """Extract tool name from call dict."""
        # Try function object first (OpenAI format)
        func = call.get("function")
        if isinstance(func, dict):
            func_name = func.get("name")
            if func_name:
                return func_name

        # Try various field names
        name = (
            call.get("roma.tool_name") or
            call.get("tool")
            or call.get("tool_name")
            or call.get("name")
            or call.get("type")
            or call.get("id")
        )
        return name or "unknown"

    def _extract_tool_arguments(self, call: Dict[str, Any]) -> Any:
        """Extract arguments from call dict."""
        # Try various argument field names
        args = (
            call.get("arguments")
            or call.get("args")
            or call.get("input")
            or call.get("params")
            or call.get("parameters")
        )

        # Check function.arguments (OpenAI format)
        if args is None:
            func = call.get("function")
            if isinstance(func, dict):
                args = func.get("arguments") or func.get("args")

        # Handle special case: code stored as dict key (MLflow artifact format)
        if isinstance(args, dict):
            # Check if this is just type metadata without actual content
            if set(args.keys()) == {"type"} or (
                set(args.keys()) == {"code", "type"}
                and isinstance(args.get("code"), dict)
                and not args.get("code")
            ):
                return None

            # For code execution tools, check if code is stored as a dict key
            if "code" in args:
                code_val = args["code"]
                if isinstance(code_val, dict):
                    if len(code_val) == 1:
                        # Code is stored as: {"code": {"<actual_code_string>": None}}
                        actual_code = list(code_val.keys())[0]
                        args = dict(args)
                        args["code"] = actual_code
                        args.pop("type", None)
                elif isinstance(code_val, str):
                    # Code is already a string, remove redundant type field
                    if "type" in args:
                        args = dict(args)
                        args.pop("type", None)

        return args

    def _extract_tool_output(self, call: Dict[str, Any]) -> Any:
        """Extract output from call dict."""
        # Try various output field names
        output = (
            call.get("output")
            or call.get("result")
            or call.get("return")
            or call.get("response")
        )

        if output is not None:
            return output

        # Check function.output (OpenAI format)
        func = call.get("function")
        if isinstance(func, dict):
            func_output = func.get("output") or func.get("result")
            if func_output is not None:
                return func_output

        # Check for content field
        content = call.get("content")
        if content is not None:
            return content

        return None

    def _tool_call_successful(self, call: Dict[str, Any]) -> bool:
        """Check if tool call was successful."""
        # Check for error field
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

        # If no error and no explicit failure, assume success
        return True


class LMCallDetailParser(SpanDetailParser):
    """Parser for LM calls - just an alias for SpanDetailParser."""

    def parse(self, obj: Any, context: str = "lm_call", show_io: bool = True) -> DetailViewData:
        """Parse an LM call (which is just a TraceViewModel)."""
        return super().parse(obj, context, show_io=show_io)


class ErrorDetailParser(DetailViewParser):
    """Parser for error dictionaries from ErrorCollector.

    Follows SOLID principles:
    - Single Responsibility: Only parses error dicts into DetailViewData
    - DRY: Reuses base parser methods for common operations
    """

    def parse(self, obj: Any, context: str = "error", show_io: bool = True) -> DetailViewData:
        """Parse an error dict into detail view data.

        Args:
            obj: Error dict from ErrorCollector with keys:
                 type, source, message, timestamp, trace_id, span_id,
                 exception_type, full_error
            context: Additional context string
            show_io: Whether to include I/O sections (default: True)
        """
        if not isinstance(obj, dict):
            raise TypeError(f"Expected dict, got {type(obj)}")

        # Extract error fields (DRY: centralized field extraction)
        error_type = obj.get("type", "Unknown Error")
        source = obj.get("source", "Unknown")
        exception_type = obj.get("exception_type", "Unknown")
        full_error = obj.get("full_error", obj.get("message", "No error message"))
        timestamp = obj.get("timestamp", "")
        trace_id = obj.get("trace_id", "")
        span_id = obj.get("span_id", "")

        # Build title (clear and descriptive)
        title = f"Error Details: {escape(exception_type)}"

        # Build metadata (always visible at top)
        metadata = {}

        # Core error info
        metadata["Type"] = escape(error_type)
        metadata["Source"] = escape(source)
        metadata["Exception"] = escape(exception_type)

        # Severity icon (DRY: reuse from table renderer logic)
        severity_icon = self._get_severity_icon(exception_type, error_type)
        metadata["Severity"] = severity_icon

        # Timestamps
        if timestamp:
            metadata["Timestamp"] = escape(self.formatters.format_timestamp(timestamp))

        # Trace identifiers
        if trace_id:
            metadata["Trace ID"] = escape(str(trace_id)[:16] + "...")

        if span_id and span_id != trace_id:
            metadata["Span ID"] = escape(str(span_id)[:16] + "...")

        # Build sections (collapsible areas)
        sections = self._build_error_sections(full_error, exception_type)

        return DetailViewData(
            title=title,
            metadata=metadata,
            sections=sections,
            source_object=obj,
        )

    def _get_severity_icon(self, exception_type: str, error_type: str) -> str:
        """Get severity icon based on error type.

        DRY: Centralized severity logic matching table renderer.

        Args:
            exception_type: Exception class name
            error_type: Error category (Span Error, Tool Error, etc.)

        Returns:
            Severity icon emoji
        """
        if "Authentication" in exception_type or "Critical" in error_type:
            return "🔴 Critical"
        elif "Parse" in exception_type or "Tool" in error_type:
            return "🟡 Warning"
        else:
            return "🟠 Error"

    def _build_error_sections(self, full_error: str, exception_type: str) -> List[Optional[DetailSection]]:
        """Build collapsible sections for error details.

        SOLID: Single responsibility - only build sections, don't parse data.

        Args:
            full_error: Full error message with potential stacktrace
            exception_type: Exception class name

        Returns:
            List of DetailSection objects
        """
        sections = []

        # Parse error message and stacktrace (if present)
        error_message, stacktrace = self._split_error_and_trace(full_error)

        # Section 1: Error Message (always shown, always expanded)
        sections.append(
            DetailSection(
                id="error_message",
                title="Error Message",
                icon="❌",
                data=error_message,
                data_type=DataType.TEXT,
                collapsed=False,  # Always visible
                view_mode=ViewMode.RAW,
            )
        )

        # Section 2: Stack Trace (if available, expanded by default)
        if stacktrace:
            sections.append(
                DetailSection(
                    id="stacktrace",
                    title="Stack Trace",
                    icon="📜",
                    data=stacktrace,
                    data_type=DataType.CODE,
                    collapsed=False,  # Expanded by default for visibility
                    view_mode=ViewMode.RAW,
                    renderer_hint="python",  # Syntax highlighting
                )
            )

        return sections

    def _split_error_and_trace(self, full_error: str) -> tuple[str, Optional[str]]:
        """Split error message from stacktrace.

        DRY: Centralized logic for parsing error format.

        Args:
            full_error: Full error text (may contain stacktrace)

        Returns:
            Tuple of (error_message, stacktrace_or_none)
        """
        if not isinstance(full_error, str):
            return str(full_error), None

        # Check if there's a Python traceback
        if "Traceback (most recent call last):" in full_error:
            # Split at traceback marker
            parts = full_error.split("Traceback (most recent call last):", 1)
            error_message = parts[0].strip()
            stacktrace = "Traceback (most recent call last):" + parts[1]
            return error_message or "Error occurred (see stacktrace)", stacktrace

        # Check for other stacktrace formats
        if "\n  File " in full_error or "\n    at " in full_error:
            # Try to find where stacktrace starts
            lines = full_error.split("\n")
            for i, line in enumerate(lines):
                if line.strip().startswith("File ") or line.strip().startswith("at "):
                    error_message = "\n".join(lines[:i]).strip()
                    stacktrace = "\n".join(lines[i:])
                    return error_message or "Error occurred (see stacktrace)", stacktrace

        # No stacktrace found - return full error as message
        return full_error, None


# =============================================================================
# RENDERERS - Render data as Textual widgets
# =============================================================================


class DataRenderer(ABC):
    """Base class for data renderers."""

    @abstractmethod
    def render(self, data: Any, **kwargs) -> Widget:
        """Render data as a Textual widget."""
        pass


class TreeDataRenderer(DataRenderer):
    """Renders nested data as interactive tree."""

    def render(self, data: Any, **kwargs) -> Widget:
        """Render data as tree widget."""
        tree = Tree("Data", id=kwargs.get("section_id", "tree"))
        tree.show_root = False
        self._build_tree(tree.root, data)
        return tree

    def _build_tree(self, parent: TreeNode, data: Any, key: str = "root") -> None:
        """Recursively build tree nodes."""
        if isinstance(data, dict):
            if not data:
                parent.add_leaf("[dim]{empty}[/dim]")
                return

            for k, v in data.items():
                if isinstance(v, (dict, list)) and v:
                    # Nested structure - create expandable node
                    preview = self._get_preview(v)
                    label = f"{self._format_key(k)} [dim]{preview}[/dim]"
                    child_node = parent.add(label, expand=False)
                    self._build_tree(child_node, v, k)
                elif self._is_long_value(v):
                    # Long string or multiline - make it expandable
                    preview = self._format_value(v)
                    label = f"{self._format_key(k)}: {preview}"
                    child_node = parent.add(label, expand=False)
                    self._add_full_text(child_node, v)
                else:
                    # Short leaf node - show inline
                    label = f"{self._format_key(k)}: {self._format_value(v)}"
                    parent.add_leaf(label)

        elif isinstance(data, list):
            if not data:
                parent.add_leaf("[dim][] empty[/dim]")
                return

            for i, item in enumerate(data):
                if isinstance(item, (dict, list)) and item:
                    preview = self._get_preview(item)
                    label = f"[{i}] [dim]{preview}[/dim]"
                    child_node = parent.add(label, expand=False)
                    self._build_tree(child_node, item, f"[{i}]")
                elif self._is_long_value(item):
                    preview = self._format_value(item)
                    label = f"[{i}]: {preview}"
                    child_node = parent.add(label, expand=False)
                    self._add_full_text(child_node, item)
                else:
                    label = f"[{i}]: {self._format_value(item)}"
                    parent.add_leaf(label)
        else:
            # Scalar value
            parent.add_leaf(self._format_value(data))

    def _get_preview(self, data: Any) -> str:
        """Generate preview for collapsed nodes."""
        if isinstance(data, dict):
            return f"{{{len(data)} keys}}"
        elif isinstance(data, list):
            return f"[{len(data)} items]"
        else:
            return ""

    def _is_long_value(self, value: Any) -> bool:
        """Check if value should be expandable."""
        if isinstance(value, str):
            return len(value) > 100 or "\n" in value
        return False

    def _add_full_text(self, parent: TreeNode, text: str) -> None:
        """Add full text content as child nodes."""
        if "\n" in text:
            # Multi-line: add each line as a child
            lines = text.split("\n")
            for i, line in enumerate(lines, 1):
                if line:
                    escaped_line = escape(line)
                    parent.add_leaf(f"[dim]L{i}:[/dim] [green]{escaped_line}[/green]")
                else:
                    parent.add_leaf(f"[dim]L{i}:[/dim] [dim](empty line)[/dim]")
        else:
            # Long single line: chunk into 200-char segments
            chunk_size = 200
            for i in range(0, len(text), chunk_size):
                chunk = text[i:i + chunk_size]
                escaped_chunk = escape(chunk)
                chunk_label = f"[dim][{i}:{i+len(chunk)}][/dim] [green]{escaped_chunk}[/green]"
                parent.add_leaf(chunk_label)

    def _format_key(self, key: Any) -> str:
        """Format dict key."""
        return f"[bold cyan]{escape(str(key))}[/bold cyan]"

    def _format_value(self, value: Any) -> str:
        """Format value with syntax highlighting."""
        if isinstance(value, str):
            if len(value) > 100:
                return f'[green]"{escape(value[:100])}..."[/green]'
            elif "\n" in value:
                lines = value.split("\n")
                return f'[green]"{escape(lines[0])}..." ({len(lines)} lines)[/green]'
            else:
                return f'[green]"{escape(value)}"[/green]'
        elif isinstance(value, bool):
            return f"[blue]{value}[/blue]"
        elif isinstance(value, (int, float)):
            return f"[yellow]{value}[/yellow]"
        elif value is None:
            return "[dim]null[/dim]"
        else:
            return escape(str(value))


class RawRenderer(DataRenderer):
    """Renders data as formatted JSON/text."""

    def render(self, data: Any, **kwargs) -> Widget:
        """Render as formatted JSON or string."""
        import json

        if isinstance(data, (dict, list)):
            try:
                formatted = json.dumps(data, indent=2)
                return Static(escape(formatted), id=kwargs.get("section_id", "raw"))
            except Exception:
                return Static(escape(str(data)), id=kwargs.get("section_id", "raw"))
        else:
            text = str(data) if data is not None else ""
            return Static(escape(text), id=kwargs.get("section_id", "raw"))


class TextRenderer(DataRenderer):
    """Renders plain text with wrapping."""

    def render(self, data: Any, **kwargs) -> Widget:
        """Render as plain text."""
        text = str(data) if data is not None else ""
        return Static(escape(text), id=kwargs.get("section_id", "text"))


class CodeRenderer(DataRenderer):
    """Renders code with syntax highlighting."""

    def render(self, data: Any, language: str = "json", **kwargs) -> Widget:
        """Render with syntax highlighting."""
        code = str(data) if data is not None else ""

        try:
            syntax = Syntax(code, language, theme="monokai", line_numbers=False)
            return Static(syntax, id=kwargs.get("section_id", "code"))
        except Exception:
            return Static(code, id=kwargs.get("section_id", "code"))


# =============================================================================
# WIDGETS - UI components
# =============================================================================


class GenericDetailView(VerticalScroll):
    """Generic detail view widget that displays normalized DetailViewData."""

    DEFAULT_CSS = """
    GenericDetailView {
        background: $panel;
        border: solid $primary;
        padding: 1;
    }

    GenericDetailView .detail-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    GenericDetailView .detail-metadata {
        background: $boost;
        padding: 1;
        margin-bottom: 1;
        border: round $primary-lighten-1;
        height: auto;
        min-height: 3;
    }

    GenericDetailView .metadata-row {
        margin-bottom: 0;
        height: auto;
    }

    GenericDetailView Collapsible {
        margin-bottom: 1;
        border: round $primary-darken-1;
    }

    GenericDetailView Tree {
        height: auto;
        scrollbar-size: 1 1;
    }

    GenericDetailView Static {
        height: auto;
    }
    """

    def __init__(
        self,
        data: DetailViewData,
        renderer_registry: Optional[Dict[DataType, DataRenderer]] = None,
        **kwargs,
    ):
        """Initialize the detail view.

        Args:
            data: The normalized detail view data
            renderer_registry: Optional custom renderers for data types
            **kwargs: Additional widget arguments
        """
        super().__init__(**kwargs)
        self.data = data

        # Set up default renderers
        if renderer_registry is None:
            self.renderers = {
                DataType.NESTED: TreeDataRenderer(),
                DataType.TEXT: TextRenderer(),
                DataType.CODE: CodeRenderer(),
                DataType.MARKDOWN: TextRenderer(),
                DataType.UNKNOWN: RawRenderer(),
            }
        else:
            self.renderers = renderer_registry

    def compose(self) -> ComposeResult:
        """Compose the detail view layout."""
        # Title
        yield Label(self.data.title, classes="detail-title")

        # Metadata section
        if self.data.metadata is not None and len(self.data.metadata) > 0:
            with Container(classes="detail-metadata"):
                for key, value in self.data.metadata.items():
                    yield Label(f"[bold]{key}:[/bold] {value}", classes="metadata-row")
        elif self.data.metadata is not None:
            with Container(classes="detail-metadata"):
                yield Label("[dim]No metadata available[/dim]", classes="metadata-row")

        # Collapsible sections
        for section in self.data.sections:
            if section is None:
                continue

            with Collapsible(
                title=f"{section.icon} {section.title}",
                collapsed=section.collapsed,
                id=f"section-{section.id}",
            ):
                renderer = self._select_renderer(section)
                if renderer:
                    render_kwargs = {"section_id": f"data-{section.id}"}

                    if isinstance(renderer, CodeRenderer) and section.renderer_hint:
                        render_kwargs["language"] = section.renderer_hint

                    widget = renderer.render(section.data, **render_kwargs)
                    yield widget

    def _select_renderer(self, section: DetailSection) -> Optional[DataRenderer]:
        """Select the appropriate renderer for a section."""
        # Map view mode to renderer
        if section.view_mode == ViewMode.TREE:
            return self.renderers.get(DataType.NESTED)
        elif section.view_mode == ViewMode.RAW:
            return RawRenderer()
        elif section.view_mode == ViewMode.FORMATTED:
            return CodeRenderer()

        # Auto mode - use data type
        return self.renderers.get(section.data_type, RawRenderer())


# =============================================================================
# MODALS - Modal screens
# =============================================================================


class DetailModal(ModalScreen):
    """Modal dialog that displays a GenericDetailView.

    Supports:
    - ESC / q to close
    - 't' to toggle I/O display
    - Automatic sizing
    """

    DEFAULT_CSS = """
    DetailModal {
        align: center middle;
    }

    DetailModal > Container {
        width: 90%;
        height: 90%;
        background: $panel;
        border: thick $primary;
    }

    DetailModal .modal-title {
        dock: top;
        height: 3;
        background: $primary;
        color: $text;
        content-align: center middle;
        text-style: bold;
    }

    DetailModal .toggle-hint {
        dock: bottom;
        height: 1;
        background: $panel-darken-1;
        color: $text-muted;
        content-align: center middle;
        text-style: italic;
    }

    DetailModal GenericDetailView {
        height: 1fr;
        border: none;
    }
    """

    BINDINGS = [
        Binding("escape,q", "dismiss", "Close", show=True),
    ]

    def __init__(
        self,
        source_obj: Any,
        parser: DetailViewParser,
        show_io: bool = True,
        renderer_registry: Optional[Dict[DataType, DataRenderer]] = None,
        **kwargs,
    ):
        """Initialize the modal.

        Args:
            source_obj: The original object to parse
            parser: Parser instance to use for rendering
            show_io: Initial I/O display state (default: True)
            renderer_registry: Optional custom renderers
            **kwargs: Additional screen arguments
        """
        super().__init__(**kwargs)
        self.source_obj = source_obj
        self.parser = parser
        self.show_io = show_io
        self.renderer_registry = renderer_registry
        self._current_data = parser.parse(source_obj, show_io=show_io)
        self._view_counter = 0

    def compose(self) -> ComposeResult:
        """Compose the modal layout."""
        with Container(id="modal-container"):
            yield Label(self._current_data.title, classes="modal-title")
            yield GenericDetailView(
                self._current_data,
                renderer_registry=self.renderer_registry,
                id=f"detail-view-{self._view_counter}",
            )
            hint_text = self._get_toggle_hint_text()
            yield Label(hint_text, classes="toggle-hint")

    def _get_toggle_hint_text(self) -> str:
        """Get the toggle hint text based on current state."""
        if self.show_io:
            return "I/O Display: ON • Press 'd' to toggle detailed view (hide I/O sections) • Press 't' to scroll to top"
        else:
            return "I/O Display: OFF • Press 'd' to toggle detailed view (show I/O sections) • Press 't' to scroll to top"

    def on_key(self, event: events.Key) -> None:
        """Handle key events - intercept 'd' and 't' before they bubble to app."""
        if event.key == "d":
            event.stop()
            self._toggle_io()
        elif event.key == "t":
            event.stop()
            self._scroll_to_top()

    def _toggle_io(self) -> None:
        """Toggle I/O display and refresh view."""
        old_show_io = self.show_io
        old_counter = self._view_counter

        self.show_io = not self.show_io
        self._view_counter += 1

        try:
            self._current_data = self.parser.parse(self.source_obj, show_io=self.show_io)

            container = self.query_one("#modal-container", Container)
            container.remove_children()

            container.mount(Label(self._current_data.title, classes="modal-title"))
            container.mount(
                GenericDetailView(
                    self._current_data,
                    renderer_registry=self.renderer_registry,
                    id=f"detail-view-{self._view_counter}",
                )
            )
            hint_text = self._get_toggle_hint_text()
            container.mount(Label(hint_text, classes="toggle-hint"))

            status = "ON" if self.show_io else "OFF"
            self.notify(f"I/O Display: {status}", severity="information", timeout=1)

        except Exception as e:
            self.show_io = old_show_io
            self._view_counter = old_counter
            self.notify(f"Failed to toggle I/O: {str(e)[:100]}", severity="error", timeout=3)
            logger.error(f"Failed to toggle I/O in detail modal: {e}", exc_info=True)

    def _scroll_to_top(self) -> None:
        """Scroll detail view to top."""
        detail_view = self.query_one(GenericDetailView)
        detail_view.scroll_home(animate=True)

    def action_dismiss(self) -> None:
        """Close the modal."""
        self.dismiss()


class HelpModal(ModalScreen):
    """Help modal showing keyboard shortcuts."""

    DEFAULT_CSS = """
    HelpModal {
        align: center middle;
    }

    HelpModal > Container {
        width: 60%;
        height: 70%;
        background: $panel;
        border: thick $primary;
    }

    HelpModal .modal-title {
        dock: top;
        height: 3;
        background: $primary;
        color: $text;
        content-align: center middle;
        text-style: bold;
    }

    HelpModal .help-content {
        padding: 2;
    }
    """

    BINDINGS = [
        Binding("escape,q", "dismiss", "Close", show=True),
    ]

    def compose(self) -> ComposeResult:
        """Compose help modal."""
        with Container():
            yield Label("Keyboard Shortcuts", classes="modal-title")
            with VerticalScroll(classes="help-content"):
                yield Static(self._get_help_text())

    def _get_help_text(self) -> str:
        """Get help text content."""
        return """[bold cyan]Navigation[/bold cyan]
↑/↓ or k/j - Move cursor in tables/trees
Tab - Switch between panels
←/→ - Collapse/expand tree nodes
t - Scroll to top of current tab
1/2/3/4 - Switch to Spans/LM/Tools/Summary tab

[bold cyan]Search & Filter[/bold cyan]
/ - Open search modal (search across all data)
Esc - Clear active search filter
f - Toggle error-only filter (show only failed items)
  • Regex support: Use patterns like "error.*timeout"
  • Case sensitive: Optional checkbox in modal
  • Search in I/O: Include trace inputs/outputs (slower)
  • Scope options:
    - Current tab: Filter active tab only
    - All tabs: Search across Spans, LM, and Tools
    - Specific: Filter only Spans, LM Calls, or Tools
  • Error filter: Shows only traces/tools with failures
  • Filters combine: Both search + error filter can be active
  • Results show: 🔍 12/50 ('error') + ❌ Errors Only in subtitle

[bold cyan]Data Operations[/bold cyan]
e - Export (opens modal to configure export)
i - Import execution from file
r - Reload data from server
l - Toggle live mode (auto-refresh every 2s)

[bold cyan]Copy Commands[/bold cyan]
c - Copy simple text (e.g., "Full execution (5 tasks)")
Shift+C - Copy as complete JSON export
  • If tree focused: Copies full execution or task subtree
  • If span/LM/tool selected: Copies that specific item
  • Execution copy includes schema, checksum, metadata
  • Can be pasted to file and re-imported

[bold cyan]Sorting[/bold cyan]
s - Cycle sort column (Duration → Start Time → Model)
Shift+S - Reverse sort order

[bold cyan]Selection Behavior[/bold cyan]
• Click root in tree → Copy gets full execution
• Click task in tree → Copy gets task + all descendants
• Click span in table → Copy gets just that span
• Tree focus = priority (use tree selection)
• Table focus = use table selection

[bold cyan]View Controls[/bold cyan]
Enter - Open detail modal for selected item
d - Toggle I/O display in detail modal

[bold cyan]General[/bold cyan]
? - Show this help
q - Quit application
Esc - Close modal/dialog

[bold yellow]Export Format Guide:[/bold yellow]
• JSON Full: Complete data with traces (~100% size)
• JSON Compact: No trace I/O (~20-30% size)
• JSON Minimal: Metrics only (~5% size)
• CSV: Tabular data (spans, LM calls, tools)
• Markdown: Summary report

[bold yellow]Copy JSON Export Structure:[/bold yellow]
When copying ExecutionViewModel, you get:
{
  "schema_version": "1.1.0",
  "checksum": "sha256:...",
  "execution": { ... },
  "metadata": { ... }
}
This can be saved and re-imported!"""

    def action_dismiss(self) -> None:
        """Close the modal."""
        self.dismiss()


class ExportModal(ModalScreen[tuple[str, str, str, str, str, bool, bool] | None]):
    """Export modal for selecting export format, scope, and privacy options.

    Allows user to configure:
    - Format: JSON, CSV, Markdown
    - Scope: Full Execution, Current Tab, Selected Item
    - Export Level: Full, Compact, Minimal (JSON only)
    - Privacy: Exclude I/O data, Redact sensitive strings
    - Preview of export path

    Returns:
        Tuple of (format, scope, execution_id, filepath) if Export clicked, None if Cancel
    """

    DEFAULT_CSS = """
    ExportModal {
        align: center middle;
    }

    ExportModal > Container {
        width: 60%;
        height: auto;
        max-height: 90%;
        background: $panel;
        border: thick $primary;
    }

    ExportModal .modal-title {
        dock: top;
        height: 3;
        background: $primary;
        color: $text;
        content-align: center middle;
        text-style: bold;
    }

    ExportModal .export-content {
        padding: 2;
        height: auto;
    }

    ExportModal .export-section {
        margin-bottom: 2;
        border: round $primary-darken-1;
        padding: 1;
        background: $boost;
        height: auto;
    }

    ExportModal .section-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    ExportModal RadioSet {
        height: auto;
        border: none;
        background: transparent;
    }

    ExportModal RadioButton {
        height: auto;
        margin-bottom: 0;
    }

    ExportModal .preview-section {
        margin-top: 2;
        padding: 1;
        background: $panel-darken-1;
        border: round $primary-lighten-1;
        height: auto;
    }

    ExportModal .button-bar {
        dock: bottom;
        height: 3;
        align: center middle;
        background: $panel-darken-1;
    }

    ExportModal Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape,q", "cancel", "Cancel", show=True),
        Binding("enter", "export", "Export", show=True),
    ]

    def __init__(
        self,
        execution_id: str,
        active_tab: str = "spans",
        has_selection: bool = False,
        **kwargs,
    ):
        """Initialize export modal.

        Args:
            execution_id: Current execution ID
            active_tab: Currently active tab ID
            has_selection: Whether an item is currently selected
            **kwargs: Additional screen arguments
        """
        super().__init__(**kwargs)
        self.execution_id = execution_id
        self.active_tab = active_tab
        self.has_selection = has_selection
        self._generated_filepath: str = ""  # Store generated path to avoid race condition

    def compose(self) -> ComposeResult:
        """Compose export modal layout."""
        with Container():
            yield Label("Export Data", classes="modal-title")

            with VerticalScroll(classes="export-content"):
                # Format selection section
                with Container(classes="export-section"):
                    yield Label("Export Format", classes="section-title")
                    with RadioSet(id="format-radio"):
                        yield RadioButton("JSON - Complete structured data", value=True, id="format-json")
                        yield RadioButton("CSV - Table data (tables only)", id="format-csv")
                        yield RadioButton("Markdown - Summary report", id="format-md")

                # Scope selection section
                with Container(classes="export-section"):
                    yield Label("Export Scope", classes="section-title")
                    with RadioSet(id="scope-radio"):
                        yield RadioButton("Full Execution - All data", value=True, id="scope-execution")
                        yield RadioButton("Current Tab - Active tab only", id="scope-tab")
                        if self.has_selection:
                            yield RadioButton("Selected Item - Current selection", id="scope-selected")

                # Export Level section (JSON only)
                with Container(classes="export-section", id="level-section"):
                    yield Label("Export Level (JSON only)", classes="section-title")
                    with RadioSet(id="level-radio"):
                        yield RadioButton("Full - All data including trace I/O (~100%)", value=True, id="level-full")
                        yield RadioButton("Compact - No trace I/O (~20-30%)", id="level-compact")
                        yield RadioButton("Minimal - Metrics only (~5%)", id="level-minimal")

                # Privacy options section
                with Container(classes="export-section"):
                    yield Label("Privacy Options", classes="section-title")
                    yield Checkbox("Exclude trace I/O data", id="exclude-io-check")
                    yield Checkbox("Redact sensitive strings (API keys, tokens)", id="redact-check")

                # Preview section
                with Container(classes="preview-section"):
                    yield Label("[bold]Export Path Preview:[/bold]", classes="section-title")
                    yield Static("Generating preview...", id="export-preview")

            # Button bar
            with Container(classes="button-bar"):
                yield Button("Export", variant="primary", id="export-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self) -> None:
        """Update preview on mount."""
        self._update_level_visibility()
        self._update_preview()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio button changes."""
        # Update level section visibility based on format selection
        if event.radio_set.id == "format-radio":
            self._update_level_visibility()
        self._update_preview()

    def _update_level_visibility(self) -> None:
        """Show/hide the Export Level section based on selected format."""
        try:
            format_radio = self.query_one("#format-radio", RadioSet)
            level_section = self.query_one("#level-section", Container)

            format_btn = format_radio.pressed_button
            # Only show level section for JSON format
            is_json = format_btn and format_btn.id == "format-json"
            level_section.display = is_json
        except Exception:
            # Widget not ready yet, will be called again on mount
            pass

    def _update_preview(self) -> None:
        """Update the export path preview and store generated path."""
        preview_static = self.query_one("#export-preview", Static)
        preview_text, filepath = self._get_preview_text()
        # Store filepath if valid, or empty string if error occurred
        self._generated_filepath = str(filepath) if filepath else ""
        preview_static.update(preview_text)

    def _get_preview_text(self) -> tuple[str, Path | None]:
        """Generate preview text for export path.

        Returns:
            Tuple of (preview_text, filepath)
        """
        # Get selected format (handle case where widgets don't exist yet during compose)
        try:
            format_radio = self.query_one("#format-radio", RadioSet)
        except Exception:
            return ("Generating preview...", None)

        format_btn = format_radio.pressed_button
        if format_btn:
            if format_btn.id == "format-json":
                format_ext = "json"
            elif format_btn.id == "format-csv":
                format_ext = "csv"
            else:
                format_ext = "md"
        else:
            format_ext = "json"

        # Get selected scope
        try:
            scope_radio = self.query_one("#scope-radio", RadioSet)
        except Exception:
            return ("Generating preview...", None)

        scope_btn = scope_radio.pressed_button
        if scope_btn:
            if scope_btn.id == "scope-execution":
                scope_name = "execution"
            elif scope_btn.id == "scope-tab":
                # Map tab IDs to export scope names (Bug #1 fix)
                tab_to_scope = {
                    "tab-spans": "spans",
                    "tab-lm": "lm_calls",
                    "tab-tools": "tool_calls",
                    "tab-info": "task",
                    "tab-summary": "execution",
                    "tab-errors": "execution",  # Errors tab exports as execution
                }
                scope_name = tab_to_scope.get(self.active_tab, "tab")
            else:
                scope_name = "selected"
        else:
            scope_name = "execution"

        # Generate path (only once to avoid race condition)
        # Use ExportService for safe path generation with validation
        from roma_dspy.tui.utils.export import ExportService

        try:
            filepath = ExportService.get_default_export_path(
                execution_id=self.execution_id,
                format=format_ext,
                scope=scope_name,
            )
            return f"[dim]{filepath}[/dim]", filepath
        except (ValueError, PermissionError) as exc:
            # If path generation fails, show error in preview
            logger.error(f"Export path generation failed: {exc}")
            return f"[red]Error: {str(exc)[:60]}[/red]", None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "export-btn":
            self.action_export()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_export(self) -> None:
        """Export with selected options."""
        # Validate that filepath was generated successfully
        if not self._generated_filepath:
            logger.warning("Cannot export: filepath generation failed")
            # Error is already shown in preview, don't dismiss modal
            return

        # Get selected format
        format_radio = self.query_one("#format-radio", RadioSet)
        format_btn = format_radio.pressed_button
        if format_btn:
            if format_btn.id == "format-json":
                export_format = "json"
            elif format_btn.id == "format-csv":
                export_format = "csv"
            else:
                export_format = "markdown"
        else:
            export_format = "json"

        # Get selected scope
        scope_radio = self.query_one("#scope-radio", RadioSet)
        scope_btn = scope_radio.pressed_button
        if scope_btn:
            if scope_btn.id == "scope-execution":
                export_scope = "execution"
            elif scope_btn.id == "scope-tab":
                export_scope = "tab"
            else:
                export_scope = "selected"
        else:
            export_scope = "execution"

        # Get selected export level (only applies to JSON)
        level_radio = self.query_one("#level-radio", RadioSet)
        level_btn = level_radio.pressed_button
        if level_btn:
            if level_btn.id == "level-compact":
                export_level = "compact"
            elif level_btn.id == "level-minimal":
                export_level = "minimal"
            else:
                export_level = "full"
        else:
            export_level = "full"

        # Get privacy options
        exclude_io = self.query_one("#exclude-io-check", Checkbox).value
        redact_sensitive = self.query_one("#redact-check", Checkbox).value

        # Dismiss with result (format, scope, execution_id, filepath, level, exclude_io, redact)
        self.dismiss((
            export_format,
            export_scope,
            self.execution_id,
            self._generated_filepath,
            export_level,
            exclude_io,
            redact_sensitive
        ))

    def action_cancel(self) -> None:
        """Cancel export."""
        self.dismiss(None)


# =============================================================================
# IMPORT MODAL
# =============================================================================


class ImportModal(ModalScreen[Path | None]):
    """Import modal for loading execution from exported file.

    Allows user to:
    - Enter/paste file path
    - Validate file in real-time
    - See validation results (schema, checksum, etc.)
    - Import or cancel

    Returns:
        Path object if Import clicked, None if Cancel
    """

    DEFAULT_CSS = """
    ImportModal {
        align: center middle;
    }

    ImportModal > Container {
        width: 70%;
        height: auto;
        max-height: 90%;
        background: $panel;
        border: thick $primary;
    }

    ImportModal .modal-title {
        dock: top;
        height: 3;
        background: $primary;
        color: $text;
        content-align: center middle;
        text-style: bold;
    }

    ImportModal .import-content {
        padding: 2;
        height: auto;
    }

    ImportModal .import-section {
        margin-bottom: 2;
        border: round $primary-darken-1;
        padding: 1;
        background: $boost;
        height: auto;
    }

    ImportModal .section-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    ImportModal Input {
        margin-top: 1;
        margin-bottom: 1;
    }

    ImportModal .validation-section {
        margin-top: 2;
        padding: 1;
        background: $panel-darken-1;
        border: round $primary-lighten-1;
        height: auto;
        min-height: 8;
    }

    ImportModal .validation-status {
        padding: 1;
    }

    ImportModal .button-bar {
        dock: bottom;
        height: 3;
        align: center middle;
        background: $panel-darken-1;
    }

    ImportModal Button {
        margin: 0 1;
    }
    """

    BINDINGS = [
        Binding("escape,q", "cancel", "Cancel", show=True),
        Binding("ctrl+i", "import", "Import", show=True),
    ]

    def __init__(self, **kwargs):
        """Initialize import modal."""
        super().__init__(**kwargs)
        self._validation_result = None
        self._is_validating = False

    def compose(self) -> ComposeResult:
        """Compose import modal layout."""
        with Container():
            yield Label("Import Execution", classes="modal-title")

            with VerticalScroll(classes="import-content"):
                # File path input section
                with Container(classes="import-section"):
                    yield Label("File Path", classes="section-title")
                    yield Static(
                        "[dim]Enter path to exported .json or .json.gz file[/dim]\n"
                        "[dim]Tip: Drag and drop file or paste absolute path[/dim]",
                        classes="import-hint"
                    )
                    yield Input(
                        placeholder="e.g., /path/to/roma_export_abc123_20250127.json.gz",
                        id="filepath-input"
                    )

                # Validation results section
                with Container(classes="validation-section"):
                    yield Label("[bold]Validation Status:[/bold]", classes="section-title")
                    yield Static(
                        "[dim]Enter a file path to validate...[/dim]",
                        id="validation-status",
                        classes="validation-status"
                    )

            # Button bar
            with Container(classes="button-bar"):
                yield Button("Import", variant="primary", id="import-btn", disabled=True)
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_mount(self) -> None:
        """Focus input on mount."""
        self.query_one("#filepath-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle file path input changes - validate in real-time."""
        filepath_str = event.value.strip()

        if not filepath_str:
            # Reset validation status
            self._validation_result = None
            self._update_validation_display("[dim]Enter a file path to validate...[/dim]")
            self._set_import_enabled(False)
            return

        # Validate the file path
        self._validate_file(filepath_str)

    def _validate_file(self, filepath_str: str) -> None:
        """Validate the file asynchronously."""
        if self._is_validating:
            return

        self._is_validating = True
        self._update_validation_display("[dim]⏳ Validating...[/dim]")

        # Parse path
        try:
            filepath = Path(filepath_str).expanduser().resolve()
        except Exception as e:
            self._update_validation_display(f"[red]✗ Invalid path: {str(e)[:60]}[/red]")
            self._set_import_enabled(False)
            self._is_validating = False
            return

        # Check if file exists
        if not filepath.exists():
            self._update_validation_display(f"[red]✗ File not found: {filepath}[/red]")
            self._set_import_enabled(False)
            self._is_validating = False
            return

        # Validate export file
        try:
            from roma_dspy.tui.utils.import_service import ImportService

            import_service = ImportService()
            validation = import_service.validate_export_file(filepath)

            self._validation_result = validation

            if validation.valid:
                # Build success message
                status_lines = [
                    "[green]✓ Validation PASSED[/green]",
                    "",
                    f"[bold]Execution ID:[/bold] {validation.execution_id[:16]}...",
                    f"[bold]Schema Version:[/bold] {validation.schema_version}",
                ]

                if validation.checksum_valid:
                    status_lines.append("[bold]Checksum:[/bold] ✓ Valid")
                else:
                    status_lines.append("[bold]Checksum:[/bold] ⚠️  Mismatch")

                if validation.warnings:
                    status_lines.append("")
                    status_lines.append(f"[yellow]Warnings ({len(validation.warnings)}):[/yellow]")
                    for warning in validation.warnings[:3]:
                        status_lines.append(f"  ⚠️  {warning[:60]}")
                    if len(validation.warnings) > 3:
                        status_lines.append(f"  [dim]... and {len(validation.warnings) - 3} more[/dim]")

                self._update_validation_display("\n".join(status_lines))
                self._set_import_enabled(True)

            else:
                # Build error message
                status_lines = [
                    "[red]✗ Validation FAILED[/red]",
                    "",
                    f"[bold red]Errors ({len(validation.errors)}):[/bold red]"
                ]

                for error in validation.errors[:5]:
                    status_lines.append(f"  ✗ {error[:60]}")

                if len(validation.errors) > 5:
                    status_lines.append(f"  [dim]... and {len(validation.errors) - 5} more[/dim]")

                self._update_validation_display("\n".join(status_lines))
                self._set_import_enabled(False)

        except Exception as e:
            logger.error(f"Validation error: {e}", exc_info=True)
            self._update_validation_display(f"[red]✗ Validation error: {str(e)[:80]}[/red]")
            self._set_import_enabled(False)

        finally:
            self._is_validating = False

    def _update_validation_display(self, content: str) -> None:
        """Update validation status display."""
        try:
            status_widget = self.query_one("#validation-status", Static)
            status_widget.update(content)
        except Exception:
            pass  # Widget not mounted yet

    def _set_import_enabled(self, enabled: bool) -> None:
        """Enable or disable the import button."""
        try:
            import_btn = self.query_one("#import-btn", Button)
            import_btn.disabled = not enabled
        except Exception:
            pass  # Widget not mounted yet

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "import-btn":
            self.action_import()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_import(self) -> None:
        """Import execution from file."""
        if not self._validation_result or not self._validation_result.valid:
            logger.warning("Cannot import: validation failed or not completed")
            return

        # Get filepath
        filepath_str = self.query_one("#filepath-input", Input).value.strip()

        try:
            filepath = Path(filepath_str).expanduser().resolve()
            logger.info(f"Importing execution from: {filepath}")
            self.dismiss(filepath)
        except Exception as e:
            logger.error(f"Import failed: {e}", exc_info=True)
            self._update_validation_display(f"[red]✗ Import failed: {str(e)[:60]}[/red]")

    def action_cancel(self) -> None:
        """Cancel import."""
        self.dismiss(None)


# =============================================================================
# SEARCH MODAL
# =============================================================================


class SearchModal(ModalScreen[Optional[Dict[str, Any]]]):
    """Search and filter modal.

    Follows Single Responsibility Principle: only handles search UI.
    Returns search options to caller, doesn't perform actual filtering.
    """

    DEFAULT_CSS = """
    SearchModal {
        align: center middle;
    }

    SearchModal > VerticalScroll {
        width: 70;
        height: auto;
        max-height: 90%;
        background: $panel;
        border: heavy $primary;
        padding: 1 2;
    }

    SearchModal .modal-title {
        text-align: center;
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }

    SearchModal .section-title {
        text-style: bold;
        margin-top: 1;
        margin-bottom: 0;
    }

    SearchModal #search-input {
        width: 100%;
        margin-bottom: 1;
    }

    SearchModal .options-container {
        height: auto;
        margin-bottom: 1;
    }

    SearchModal .checkbox-row {
        height: auto;
        margin: 0 0 0 1;
    }

    SearchModal RadioSet {
        height: auto;
        margin: 0 0 1 1;
    }

    SearchModal #results-preview {
        text-align: center;
        color: $text-muted;
        margin: 1 0;
        padding: 1;
        background: $boost;
    }

    SearchModal .button-bar {
        align: center middle;
        height: 3;
        margin-top: 1;
    }

    SearchModal Button {
        margin: 0 1;
        min-width: 12;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("ctrl+c", "cancel", "Cancel", show=False),
    ]

    def __init__(self, initial_term: str = "") -> None:
        """Initialize search modal.

        Args:
            initial_term: Initial search term to populate
        """
        super().__init__()
        self._initial_term = initial_term

    def compose(self) -> ComposeResult:
        """Compose modal widgets with scrollable container."""
        with VerticalScroll():
            yield Label("🔍 Search & Filter", classes="modal-title")

            # Search input
            yield Label("Search Term:", classes="section-title")
            yield Input(
                placeholder="Enter search term or regex pattern...",
                id="search-input",
                value=self._initial_term,
            )

            # Search options
            yield Label("Options:", classes="section-title")
            with Container(classes="options-container"):
                with Container(classes="checkbox-row"):
                    yield Checkbox("Case sensitive", id="case-sensitive")
                with Container(classes="checkbox-row"):
                    yield Checkbox("Use regex", id="use-regex")
                with Container(classes="checkbox-row"):
                    yield Checkbox("Search in I/O (slower)", id="search-in-io")

            # Scope selection
            yield Label("Scope:", classes="section-title")
            with RadioSet(id="scope-radio"):
                yield RadioButton("Current tab", id="scope-current", value=True)
                yield RadioButton("All tabs", id="scope-all")
                yield RadioButton("Spans only", id="scope-spans")
                yield RadioButton("LM calls only", id="scope-lm")
                yield RadioButton("Tool calls only", id="scope-tools")

            # Results preview (updated live)
            yield Static("Ready to search...", id="results-preview")

            # Buttons
            with Container(classes="button-bar"):
                yield Button("Search", id="search-btn", variant="primary")
                yield Button("Clear", id="clear-btn")
                yield Button("Cancel", id="cancel-btn")

    def on_mount(self) -> None:
        """Focus search input when modal opens."""
        self.query_one("#search-input", Input).focus()

    def on_key(self, event: events.Key) -> None:
        """Handle key press events.

        Enter key triggers search from anywhere in the modal.
        """
        if event.key == "enter":
            logger.info("Enter key detected - triggering search")
            self.action_search()
            event.prevent_default()
            event.stop()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Update preview as user types.

        Follows Interface Segregation Principle: only handles input events.
        """
        if event.input.id == "search-input":
            term = event.value.strip()
            if term:
                preview = f"Will search for: '{term[:30]}{'...' if len(term) > 30 else ''}'"
            else:
                preview = "Enter a search term to begin..."

            try:
                self.query_one("#results-preview", Static).update(preview)
            except Exception:
                pass  # Widget not mounted yet

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses.

        Follows Single Responsibility: routes button events only.
        """
        if event.button.id == "search-btn":
            self.action_search()
        elif event.button.id == "clear-btn":
            self.action_clear()
        elif event.button.id == "cancel-btn":
            self.action_cancel()

    def action_search(self) -> None:
        """Apply search and close modal.

        Returns search options dict to caller.
        Follows Dependency Inversion: returns data, doesn't perform search.
        """
        # Get search term
        term = self.query_one("#search-input", Input).value.strip()

        if not term:
            # Show message and don't dismiss
            self.query_one("#results-preview", Static).update(
                "[yellow]Please enter a search term[/yellow]"
            )
            return

        # Get options
        case_sensitive = self.query_one("#case-sensitive", Checkbox).value
        use_regex = self.query_one("#use-regex", Checkbox).value
        search_in_io = self.query_one("#search-in-io", Checkbox).value

        # Get scope
        scope = "current"  # default
        radio_set = self.query_one("#scope-radio", RadioSet)
        pressed_button = radio_set.pressed_button
        if pressed_button:
            scope_id = pressed_button.id or "scope-current"
            scope = scope_id.replace("scope-", "")

        # Validate regex if needed
        if use_regex:
            try:
                import re
                re.compile(term)
            except re.error as e:
                self.query_one("#results-preview", Static).update(
                    f"[red]Invalid regex: {str(e)[:40]}[/red]"
                )
                return

        # Return search options
        result = {
            "term": term,
            "case_sensitive": case_sensitive,
            "use_regex": use_regex,
            "search_in_io": search_in_io,
            "scope": scope,
        }

        logger.info(f"Search submitted: {result}")
        self.dismiss(result)

    def action_clear(self) -> None:
        """Clear search inputs."""
        self.query_one("#search-input", Input).value = ""
        self.query_one("#case-sensitive", Checkbox).value = False
        self.query_one("#use-regex", Checkbox).value = False
        self.query_one("#search-in-io", Checkbox).value = False

        # Reset scope to current tab
        radio_set = self.query_one("#scope-radio", RadioSet)
        current_btn = self.query_one("#scope-current", RadioButton)
        radio_set.action_toggle_button(current_btn)

        # Update preview
        self.query_one("#results-preview", Static).update("Search cleared. Ready...")

        # Focus input
        self.query_one("#search-input", Input).focus()

    def action_cancel(self) -> None:
        """Cancel search and close modal."""
        logger.debug("Search cancelled")
        self.dismiss(None)
