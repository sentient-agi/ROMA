"""DSPy callback to enhance MLflow autolog Tool.* spans with ROMA attributes.

This callback integrates with MLflow's DSPy autolog to add ROMA-specific metadata
to Tool.* spans created by MLflow's MlflowCallback. It does NOT create spans itself,
only enhances existing spans created by MLflow autolog.

Architecture:
- MLflow's MlflowCallback creates Tool.* spans when autolog is enabled
- ROMAToolSpanCallback runs on_tool_start and gets the MLflow-created span
- Adds ROMA attributes (execution_id, tool_name, tool_type, toolkit_name)
- Tracks tool calls in ExecutionContext for checkpoint/recovery

Key Features:
- Distinguishes builtin tools from MCP tools
- Uses actual MCP server names (e.g., "mcp_exa" not "MCPToolkit")
- Records tool call history for checkpointing
- Thread-safe via contextvars
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from dspy.utils.callback import BaseCallback
from loguru import logger

from roma_dspy.core.context.execution_context import ExecutionContext
from roma_dspy.tools.metrics.models import ToolInvocationEvent

try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False


class ROMAToolSpanCallback(BaseCallback):
    """Enhances MLflow autolog-created Tool.* spans with ROMA attributes.

    This callback must be registered AFTER mlflow.dspy.autolog() to work correctly.
    It retrieves spans created by MLflow's callback and adds ROMA metadata.

    Usage:
        # In MLflowManager.initialize()
        mlflow.dspy.autolog(log_traces=True)

        roma_callback = ROMAToolSpanCallback()
        callbacks = dspy.settings.get("callbacks", [])  # Get MLflow's callback
        callbacks.append(roma_callback)  # Add ROMA callback
        dspy.settings.configure(callbacks=callbacks)

    Attributes Added to Spans:
        - roma.execution_id: Execution ID from ExecutionContext
        - roma.tool_name: Tool function name
        - roma.tool_type: "builtin" or "mcp"
        - roma.toolkit_name: Toolkit class name (e.g., "mcp_exa")
        - roma.enhanced: "true" marker
    """

    # Memory leak protection configuration
    MAX_PENDING_CALLS = 100  # Maximum concurrent pending calls before cleanup
    STALE_CALL_TTL_SECONDS = 300  # 5 minutes - calls older than this are considered stale

    # DSPy internal tools to exclude from observability
    INTERNAL_DSPY_TOOLS = frozenset(['finish', 'Finish'])

    def __init__(self):
        """Initialize callback with empty pending calls tracking."""
        # Track tool calls between start/end for history recording
        self._pending_calls: Dict[str, Dict[str, Any]] = {}
        self.enhanced_count = 0
        self.cleanup_count = 0  # Track number of stale calls cleaned up

    def _cleanup_stale_calls(self) -> None:
        """Remove stale pending calls to prevent memory leaks.

        This method is called when pending_calls approaches the size limit.
        It removes calls in two phases:
        1. Remove calls older than STALE_CALL_TTL_SECONDS
        2. If still over limit, remove oldest calls

        This prevents memory leaks when on_tool_end is never called due to:
        - Agent crashes
        - DSPy exceptions
        - Tool timeouts
        - Ctrl+C interrupts
        """
        current_time = time.time()

        # Phase 1: Remove stale calls (older than TTL)
        stale_calls = [
            call_id for call_id, info in self._pending_calls.items()
            if current_time - info.get('timestamp', 0) > self.STALE_CALL_TTL_SECONDS
        ]

        for call_id in stale_calls:
            call_info = self._pending_calls.pop(call_id)
            self.cleanup_count += 1
            logger.warning(
                f"Cleaned up stale call (on_tool_end never called)",
                call_id=call_id,
                tool_name=call_info.get('tool_name', 'unknown'),
                age_seconds=int(current_time - call_info.get('timestamp', 0))
            )

        # Phase 2: If still over limit, remove oldest calls (emergency)
        if len(self._pending_calls) > self.MAX_PENDING_CALLS:
            excess = len(self._pending_calls) - self.MAX_PENDING_CALLS
            # Sort by timestamp (oldest first)
            oldest_calls = sorted(
                self._pending_calls.items(),
                key=lambda x: x[1].get('timestamp', 0)
            )[:excess]

            for call_id, call_info in oldest_calls:
                self._pending_calls.pop(call_id)
                self.cleanup_count += 1

            logger.error(
                f"Emergency cleanup: removed {excess} oldest calls",
                total_pending=len(self._pending_calls),
                total_cleaned=self.cleanup_count,
                reason="Exceeded MAX_PENDING_CALLS limit"
            )

    def on_tool_start(self, call_id: str, instance: Any, inputs: Dict[str, Any]):
        """Enhance MLflow's Tool.* span with ROMA attributes.

        Args:
            call_id: Unique identifier for this tool call
            instance: DSPy Tool instance
            inputs: Tool input arguments (kwargs dict)
        """
        if not MLFLOW_AVAILABLE:
            return

        # Memory leak protection: cleanup if approaching limit
        if len(self._pending_calls) > int(self.MAX_PENDING_CALLS * 0.8):
            self._cleanup_stale_calls()

        tool_name = getattr(instance, 'name', 'unknown')

        # Filter out DSPy internal tools (e.g., ReAct's "finish" tool)
        if tool_name in self.INTERNAL_DSPY_TOOLS:
            logger.debug(f"Skipping internal DSPy tool: {tool_name}")
            return

        # Detect duplicate call_id (defensive programming)
        if call_id in self._pending_calls:
            prev_tool = self._pending_calls[call_id].get('tool_name', 'unknown')
            logger.error(
                f"Duplicate call_id detected: {call_id}",
                previous_tool=prev_tool,
                current_tool=tool_name
            )
            # Continue anyway (overwrite) but log for debugging

        try:
            # Get the span that MLflow's callback created
            span = mlflow.get_current_active_span()

            if not span:
                logger.debug(f"No active span found for tool {tool_name} (MLflow autolog may not be enabled)")
                return

            # Get execution context
            ctx = ExecutionContext.get()
            execution_id = ctx.execution_id if ctx else "unknown"

            # Identify toolkit and tool type
            toolkit_name, tool_type = self._identify_toolkit(instance)

            # Build ROMA attributes
            roma_attrs = {
                "roma.execution_id": execution_id,
                "roma.tool_name": tool_name,
                "roma.tool_type": tool_type,
                "roma.toolkit_name": toolkit_name,
                "roma.enhanced": "true",
            }

            # Add attributes to MLflow's span
            span.set_attributes(roma_attrs)
            self.enhanced_count += 1

            # Store call info for on_tool_end (includes timestamp for cleanup and duration tracking)
            self._pending_calls[call_id] = {
                "tool_name": tool_name,
                "toolkit_name": toolkit_name,
                "tool_type": tool_type,
                "inputs": inputs,
                "timestamp": time.time(),  # For cleanup detection and duration calculation
            }

            logger.debug(
                f"Enhanced MLflow span for tool {tool_name}",
                tool_type=tool_type,
                toolkit_name=toolkit_name,
                execution_id=execution_id,
            )

        except Exception as e:
            logger.warning(f"Failed to enhance MLflow span for tool {tool_name}: {e}")

    def _calculate_size(self, obj: Any) -> int:
        """Safely calculate approximate size of object in bytes.

        Uses multiple fallback strategies to handle edge cases:
        1. JSON serialization (most accurate for dict/list)
        2. repr() for objects (safer than str())
        3. Return 0 on any failure

        Args:
            obj: Object to measure

        Returns:
            Approximate size in bytes, capped at limits for safety
        """
        try:
            # Try JSON serialization (most common case for tool inputs/outputs)
            import json
            serialized = json.dumps(obj, default=str, ensure_ascii=False)
            # Cap at 10MB to prevent memory issues from huge objects
            return min(len(serialized), 10_000_000)
        except (TypeError, ValueError, RecursionError):
            try:
                # Fallback to repr (safer than str for objects)
                repr_str = repr(obj)
                # Cap at 1MB for repr
                return min(len(repr_str), 1_000_000)
            except Exception:
                # Last resort: return 0
                return 0

    def on_tool_end(self, call_id: str, outputs: Any, exception: Exception | None = None):
        """Record tool call in ExecutionContext and enhance MLflow span with success/error status.

        Args:
            call_id: Unique identifier for this tool call
            outputs: Tool output/result
            exception: Exception if tool call failed
        """
        if call_id not in self._pending_calls:
            logger.debug(f"on_tool_end called for unknown call_id: {call_id}")
            return

        call_info = self._pending_calls.pop(call_id)

        try:
            # Add success/error status to MLflow span (for TUI visualization)
            if MLFLOW_AVAILABLE:
                span = mlflow.get_current_active_span()
                if span:
                    success = exception is None
                    span.set_attributes({
                        "roma.success": str(success).lower(),  # "true" or "false"
                        "roma.error": str(exception) if exception else None,
                        "roma.status": "success" if success else "error",
                    })
                    logger.debug(
                        f"Updated MLflow span status for {call_info['tool_name']}",
                        success=success,
                        has_error=exception is not None,
                    )

            # Record in ExecutionContext for checkpointing
            ctx = ExecutionContext.get()

            if ctx:
                # Calculate duration from our tracked timestamp
                # Note: This is separate from MLflow span duration (which is for trace UI)
                # This duration is for PostgreSQL analytics and checkpoint recovery
                duration_ms = (time.time() - call_info['timestamp']) * 1000.0

                # Calculate input/output sizes safely
                input_size_bytes = self._calculate_size(call_info['inputs'])
                output_size_bytes = self._calculate_size(outputs) if outputs is not None else 0

                # Create ToolInvocationEvent for checkpoint storage
                event = ToolInvocationEvent(
                    execution_id=ctx.execution_id,
                    toolkit_class=call_info['toolkit_name'],
                    tool_name=call_info['tool_name'],
                    invoked_at=datetime.now(timezone.utc),
                    duration_ms=duration_ms,
                    input_size_bytes=input_size_bytes,
                    output_size_bytes=output_size_bytes,
                    success=exception is None,
                    error=str(exception) if exception else None,
                    metadata={
                        'tool_type': call_info['tool_type'],
                    }
                )

                # Append to ExecutionContext for checkpoint/PostgreSQL storage
                ctx.tool_invocations.append(event)

                logger.debug(
                    f"Recorded tool invocation for {call_info['tool_name']}",
                    duration_ms=duration_ms,
                    success=exception is None,
                )

        except Exception as e:
            logger.warning(f"Failed to record tool call in ExecutionContext: {e}")

    def _identify_toolkit(self, instance: Any) -> Tuple[str, str]:
        """Identify toolkit name and tool type from DSPy Tool instance.

        Strategy:
        1. Check if tool has _mcp_server_name metadata -> MCP tool
        2. Check if tool has _roma_toolkit_type metadata -> use it
        3. Check tool function's module path for "mcp" -> MCP tool
        4. Otherwise -> builtin tool with generic name

        Args:
            instance: DSPy Tool instance

        Returns:
            Tuple of (toolkit_name, tool_type)
            - toolkit_name: e.g., "mcp_exa", "BinanceToolkit", "SerperToolkit"
            - tool_type: "builtin" or "mcp"
        """
        func = getattr(instance, 'func', None)
        if not func:
            return ("UnknownToolkit", "builtin")

        # Check for explicit MCP metadata (set by MCPToolkit)
        if hasattr(func, '_mcp_server_name'):
            server_name = func._mcp_server_name
            return (f"mcp_{server_name}", "mcp")

        # Check for explicit toolkit type metadata
        if hasattr(func, '_roma_toolkit_type'):
            tool_type = func._roma_toolkit_type
            toolkit_name = getattr(func, '_roma_toolkit_name', "UnknownToolkit")
            return (toolkit_name, tool_type)

        # Infer from module path
        try:
            module = getattr(func, '__module__', '')
            if 'mcp' in module.lower():
                return ("MCPToolkit", "mcp")

            # Try to extract toolkit name from module
            # e.g., roma_dspy.tools.crypto.binance.toolkit -> BinanceToolkit
            parts = module.split('.')
            if 'tools' in parts and len(parts) > parts.index('tools') + 1:
                toolkit_category = parts[parts.index('tools') + 1]
                return (f"{toolkit_category.capitalize()}Toolkit", "builtin")
        except Exception:
            pass

        # Fallback
        return ("BuiltinToolkit", "builtin")
