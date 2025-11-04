"""State management for TUI.

Centralized state management using reactive patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from loguru import logger

from roma_dspy.tui.models import ExecutionViewModel, TaskViewModel, TraceViewModel


@dataclass
class SearchOptions:
    """Search and filter options."""

    term: str = ""
    case_sensitive: bool = False
    use_regex: bool = False
    search_in_io: bool = False
    scope: str = "current"  # current, all, spans, lm, tools

    def is_active(self) -> bool:
        """Check if search is currently active."""
        return bool(self.term.strip())

    def clear(self) -> None:
        """Clear all search options."""
        self.term = ""
        self.case_sensitive = False
        self.use_regex = False
        self.search_in_io = False
        self.scope = "current"


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
        self.error_table_row_map: Dict[Any, Dict[str, Any]] = {}

        # Bookmarks (trace IDs or task IDs)
        self.bookmarks: set[str] = set()

        # Search and filter state
        self.search_options: SearchOptions = SearchOptions()
        self.filtered_traces: Optional[List[TraceViewModel]] = None
        self.filtered_tools: Optional[List[Dict[str, Any]]] = None
        self.match_count: int = 0
        self.total_count: int = 0

        # Error filter state
        self.show_errors_only: bool = False
        self.error_filter_active: bool = False

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

        # Add search status if active
        if self.is_search_active():
            search_summary = self.get_search_summary()
            if search_summary:
                parts.append(search_summary)

        if self.last_update:
            time_str = self.last_update.strftime("%H:%M:%S")
            parts.append(f"Updated: {time_str}")

        return " | ".join(parts) if parts else "Ready"

    def set_search_options(self, options: SearchOptions) -> None:
        """Set search options.

        Args:
            options: Search options to apply
        """
        self.search_options = options
        logger.debug(f"Search options set: term='{options.term}', scope={options.scope}")

    def clear_search(self) -> None:
        """Clear search state and filters."""
        self.search_options.clear()
        self.filtered_traces = None
        self.filtered_tools = None
        self.match_count = 0
        self.total_count = 0
        # Also clear error filter for consistency
        self.show_errors_only = False
        self.error_filter_active = False
        logger.info("Search and error filters cleared")

    def is_search_active(self) -> bool:
        """Check if search is currently active.

        Returns:
            True if search filter is active
        """
        return self.search_options.is_active()

    def toggle_error_filter(self) -> bool:
        """Toggle error-only filter.

        Returns:
            New error filter state
        """
        self.show_errors_only = not self.show_errors_only
        self.error_filter_active = self.show_errors_only
        logger.info(f"Error filter toggled: {self.show_errors_only}")
        return self.show_errors_only

    def is_error_filter_active(self) -> bool:
        """Check if error filter is currently active.

        Returns:
            True if error filter is active
        """
        return self.error_filter_active

    def set_search_results(
        self,
        filtered_traces: Optional[List[TraceViewModel]] = None,
        filtered_tools: Optional[List[Dict[str, Any]]] = None,
        match_count: int = 0,
        total_count: int = 0,
    ) -> None:
        """Set search results.

        Args:
            filtered_traces: Filtered trace list
            filtered_tools: Filtered tool call list
            match_count: Number of matches found
            total_count: Total number of items searched
        """
        self.filtered_traces = filtered_traces
        self.filtered_tools = filtered_tools
        self.match_count = match_count
        self.total_count = total_count
        logger.debug(f"Search results set: {match_count}/{total_count} matches")

    def get_search_summary(self) -> str:
        """Get search status summary for display.

        Returns:
            Search status string (e.g., "Filtered: 12/50 (term: 'error')")
        """
        if not self.is_search_active():
            return ""

        term = self.search_options.term
        if len(term) > 20:
            term = term[:17] + "..."

        return f"🔍 {self.match_count}/{self.total_count} ('{term}')"

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
        self.clear_search()
        logger.info("State reset")
