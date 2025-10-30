"""State management for TUI v2.

Centralized state management using reactive patterns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

from roma_dspy.tui.models import ExecutionViewModel, TaskViewModel, TraceViewModel


class StateManager:
    """Manages application state centrally."""

    def __init__(self) -> None:
        """Initialize state manager."""
        # Execution data
        self.execution: Optional[ExecutionViewModel] = None
        self.execution_id: str = ""

        # UI state
        self.selected_task: Optional[TaskViewModel] = None
        self.show_io: bool = False
        self.live_mode: bool = False
        self.last_update: Optional[datetime] = None

        # Table row mappings (for click handlers)
        self.lm_table_row_map: Dict[Any, TraceViewModel] = {}
        self.tool_table_row_map: Dict[Any, Dict[str, Any]] = {}

        # Bookmarks (trace IDs or task IDs)
        self.bookmarks: set[str] = set()

        logger.debug("StateManager initialized")

    def set_execution(self, execution: ExecutionViewModel) -> None:
        """Set current execution data.

        Args:
            execution: Execution view model
        """
        self.execution = execution
        self.execution_id = execution.execution_id
        logger.info(f"Execution set: {self.execution_id}")

    def select_task(self, task: TaskViewModel) -> None:
        """Select a task.

        Args:
            task: Task to select
        """
        self.selected_task = task
        logger.debug(f"Task selected: {task.task_id}")

    def toggle_io(self) -> bool:
        """Toggle I/O display.

        Returns:
            New show_io state
        """
        self.show_io = not self.show_io
        logger.info(f"I/O display toggled: {self.show_io}")
        return self.show_io

    def toggle_live_mode(self) -> bool:
        """Toggle live mode.

        Returns:
            New live_mode state
        """
        self.live_mode = not self.live_mode
        logger.info(f"Live mode toggled: {self.live_mode}")
        return self.live_mode

    def update_timestamp(self) -> None:
        """Update last update timestamp."""
        self.last_update = datetime.now()

    def clear_row_mappings(self) -> None:
        """Clear all table row mappings."""
        self.lm_table_row_map.clear()
        self.tool_table_row_map.clear()
        logger.debug("Row mappings cleared")

    def toggle_bookmark(self, item_id: str) -> bool:
        """Toggle bookmark for an item.

        Args:
            item_id: ID of item to bookmark (task_id or trace_id)

        Returns:
            True if now bookmarked, False if unbookmarked
        """
        if item_id in self.bookmarks:
            self.bookmarks.remove(item_id)
            logger.debug(f"Unbookmarked: {item_id}")
            return False
        else:
            self.bookmarks.add(item_id)
            logger.debug(f"Bookmarked: {item_id}")
            return True

    def is_bookmarked(self, item_id: str) -> bool:
        """Check if item is bookmarked.

        Args:
            item_id: ID to check

        Returns:
            True if bookmarked
        """
        return item_id in self.bookmarks

    def get_status_summary(self) -> str:
        """Get status summary string for footer.

        Returns:
            Status string
        """
        parts = []

        if self.selected_task:
            task_id_short = self.selected_task.task_id[:8]
            parts.append(f"Task: {task_id_short}")

        if self.live_mode:
            parts.append("LIVE")

        parts.append(f"I/O: {'ON' if self.show_io else 'OFF'}")

        if self.last_update:
            time_str = self.last_update.strftime("%H:%M:%S")
            parts.append(f"Updated: {time_str}")

        return " | ".join(parts) if parts else "Ready"

    def reset(self) -> None:
        """Reset all state."""
        self.execution = None
        self.execution_id = ""
        self.selected_task = None
        self.show_io = False
        self.live_mode = False
        self.last_update = None
        self.lm_table_row_map.clear()
        self.tool_table_row_map.clear()
        self.bookmarks.clear()
        logger.info("State reset")
