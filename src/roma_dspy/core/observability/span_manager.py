"""MLflow span management for ROMA module execution tracing.

This module provides a clean, composable interface for creating and managing
MLflow spans with ROMA-specific attributes for TUI visualization and hierarchy
reconstruction.
"""

from __future__ import annotations

import os
import socket
import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlparse

from loguru import logger

if TYPE_CHECKING:
    from roma_dspy.core.signatures import TaskNode
    from roma_dspy.types import AgentType

# Check MLflow availability at module level
try:
    import mlflow
    from mlflow.tracing.fluent import start_span
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    mlflow = None
    start_span = None


def build_roma_attributes(task: TaskNode, agent_type: AgentType, module_name: Optional[str] = None) -> dict[str, Any]:
    """
    Build ROMA-specific attributes for MLflow span enrichment.

    These attributes enable TUI grouping by module type (roma.module) and
    hierarchy reconstruction using execution/task/parent relationships.

    Args:
        task: Current task node with metadata
        agent_type: Type of ROMA agent executing
        module_name: Optional DSPy module class name

    Returns:
        Dictionary of ROMA attributes for span enrichment
    """
    attrs = {
        "roma.module": agent_type.value,
        "roma.execution_id": task.execution_id or "unknown",
        "roma.task_id": task.task_id,
        "roma.parent_task_id": task.parent_id or "root",
        "roma.depth": task.depth,
        "roma.max_depth": task.max_depth,
        "roma.status": task.status.value,
        "roma.goal": task.goal,
        "roma.agent_type": agent_type.value,
        "roma.module_name": module_name or agent_type.value,
    }

    # Add optional task attributes
    if task.task_type:
        attrs["roma.task_type"] = task.task_type.value
    if task.node_type:
        attrs["roma.node_type"] = task.node_type.value
    if hasattr(task, 'is_atomic'):
        attrs["roma.is_atomic"] = task.is_atomic

    return attrs


def _is_truthy(value: str) -> bool:
    """Return True when environment toggle is truthy."""
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ROMASpanManager:
    """
    Manager for creating MLflow wrapper spans with ROMA attributes.

    This class provides a clean, composable interface for span lifecycle
    management with proper error handling and logging.

    Usage:
        span_manager = ROMASpanManager()

        with span_manager.create_span(agent_type, task) as span:
            # Execute module
            result = await module.aforward(...)
    """

    def __init__(self, enabled: bool = True, tracking_uri: Optional[str] = None):
        """
        Initialize span manager.

        Args:
            enabled: Whether span management is enabled (default: True)
            tracking_uri: Optional explicit MLflow tracking URI for reachability checks
        """
        self._tracking_uri = tracking_uri or os.environ.get("MLFLOW_TRACKING_URI")
        resolved = enabled and MLFLOW_AVAILABLE and self._is_tracking_endpoint_supported()
        self.enabled = resolved

        if enabled and not MLFLOW_AVAILABLE:
            logger.warning("MLflow not available - span management disabled")
        elif enabled and MLFLOW_AVAILABLE and not resolved:
            logger.info("MLflow span logging disabled - tracking endpoint unavailable")

    def _is_tracking_endpoint_supported(self) -> bool:
        """Return True when current MLflow tracking URI supports span logging."""
        # Allow explicit opt-out via environment variables
        env_toggle = os.environ.get("MLFLOW_ENABLED")
        if env_toggle and not _is_truthy(env_toggle):
            logger.debug("MLflow span logging disabled via MLFLOW_ENABLED environment flag")
            return False

        if os.environ.get("ROMA_DISABLE_MLFLOW_SPANS"):
            logger.debug("MLflow span logging disabled via ROMA_DISABLE_MLFLOW_SPANS environment flag")
            return False

        if not self._tracking_uri:
            return True

        parsed = urlparse(self._tracking_uri)
        scheme = (parsed.scheme or "").lower()

        # Skip span logging for local file stores or unsupported schemes
        if scheme and scheme not in {"http", "https"}:
            logger.debug(
                "MLflow tracking URI %s uses unsupported scheme for span logging; skipping",
                self._tracking_uri,
            )
            return False

        host = parsed.hostname
        if not host:
            return True

        # Localhost hosts are safe without DNS checks
        if host in {"localhost", "127.0.0.1"}:
            return True

        port = parsed.port or (443 if scheme == "https" else 80)
        try:
            socket.getaddrinfo(host, port)
        except (socket.gaierror, OSError) as exc:
            logger.warning(
                "MLflow tracking host '%s' (URI: %s) not reachable (%s); disabling span logging",
                host,
                self._tracking_uri,
                exc,
            )
            return False

        return True

    @contextmanager
    def create_span(self, agent_type: AgentType, task: TaskNode, module_name: Optional[str] = None):
        """
        Create MLflow wrapper span with ROMA attributes.

        This context manager ensures proper span lifecycle management:
        - Creates span on entry
        - Sets ROMA attributes and inputs
        - Closes span on exit with proper exception handling
        - Propagates exceptions to MLflow for error recording

        Args:
            agent_type: Type of ROMA agent executing
            task: Current task node with metadata
            module_name: Optional DSPy module class name for metadata

        Yields:
            MLflow span object (or None if disabled/unavailable)

        Example:
            with span_manager.create_span(AgentType.ATOMIZER, task) as span:
                result = await atomizer.aforward(goal=task.goal)
        """
        if not self.enabled or start_span is None:
            # Disabled or unavailable - yield None and skip span creation
            yield None
            return

        span_context = None
        exc_type = None
        exc_val = None
        exc_tb = None

        try:
            # Build ROMA attributes
            roma_attrs = build_roma_attributes(task, agent_type, module_name)

            # Create wrapper span using MLflow fluent API
            span_context = start_span(agent_type.value)
            span = span_context.__enter__()

            # Set attributes and inputs
            span.set_attributes(roma_attrs)
            span.set_inputs({"goal": task.goal})

            # Set trace-level metadata (execution context shared across all spans in this trace)
            # This works with DSPy autolog because we're inside an active trace
            if mlflow and hasattr(mlflow, 'update_current_trace'):
                try:
                    mlflow.update_current_trace(metadata={
                        # Execution identification
                        "execution.id": task.execution_id or "unknown",
                        "execution.user": "roma-dspy",

                        # Execution configuration
                        "execution.max_depth": task.max_depth,
                        "execution.current_depth": task.depth,

                        # Task hierarchy
                        "execution.root_goal": task.goal if task.parent_id is None else None,
                        "execution.parent_task_id": task.parent_id or "root",

                        # Agent context
                        "execution.current_agent": agent_type.value,
                        "execution.task_type": task.task_type.value if task.task_type else None,
                        "execution.node_type": task.node_type.value if task.node_type else None,
                    })
                    logger.debug(f"✓ Set trace metadata for execution {task.execution_id[:8] if task.execution_id else 'unknown'}")
                except Exception as e:
                    logger.debug(f"Could not set trace metadata: {e}")

            logger.info(
                f"✓ Created MLflow wrapper span for {agent_type.value} "
                f"(task {task.task_id[:8]})"
            )

            yield span

        except Exception:
            # Capture exception info for proper propagation to MLflow
            exc_type, exc_val, exc_tb = sys.exc_info()
            raise  # Re-raise immediately - let finally handle cleanup

        finally:
            # Ensure span is closed with proper exception context
            if span_context is not None:
                try:
                    # Pass actual exception info so MLflow can record span errors
                    span_context.__exit__(exc_type, exc_val, exc_tb)
                    logger.debug(f"✓ Closed MLflow wrapper span for {agent_type.value}")
                except Exception as e:
                    # Only log cleanup failures - don't swallow original exception
                    logger.warning(
                        f"Failed to close MLflow span for {agent_type.value}: {e}"
                    )


# Global singleton instance for convenience
_default_span_manager: Optional[ROMASpanManager] = None


def get_span_manager() -> ROMASpanManager:
    """
    Get the global span manager instance.

    Returns:
        Global ROMASpanManager singleton
    """
    global _default_span_manager
    if _default_span_manager is None:
        _default_span_manager = ROMASpanManager()
    return _default_span_manager


def set_span_manager(manager: ROMASpanManager) -> None:
    """
    Set the global span manager instance.

    This allows custom span manager configuration to be injected globally.

    Args:
        manager: ROMASpanManager instance to use globally
    """
    global _default_span_manager
    _default_span_manager = manager
