"""Integration tests for error filter functionality.

Tests the complete error filtering flow including state management,
filter logic, and integration with search.
"""

from __future__ import annotations

import pytest

from roma_dspy.tui.core.state import StateManager, SearchOptions
from roma_dspy.tui.models import TraceViewModel


class TestErrorFilterState:
    """Test error filter state management."""

    def test_initial_state(self):
        """Error filter should be disabled initially."""
        state = StateManager()
        assert state.show_errors_only is False
        assert state.error_filter_active is False
        assert state.is_error_filter_active() is False

    def test_toggle_error_filter(self):
        """Toggling error filter should update state."""
        state = StateManager()

        # First toggle: enable
        result = state.toggle_error_filter()
        assert result is True
        assert state.show_errors_only is True
        assert state.error_filter_active is True
        assert state.is_error_filter_active() is True

        # Second toggle: disable
        result = state.toggle_error_filter()
        assert result is False
        assert state.show_errors_only is False
        assert state.error_filter_active is False
        assert state.is_error_filter_active() is False

    def test_clear_search_clears_error_filter(self):
        """clear_search() should clear both search and error filter."""
        state = StateManager()

        # Enable both filters
        state.set_search_options(SearchOptions(term="test"))
        state.toggle_error_filter()

        assert state.is_search_active() is True
        assert state.is_error_filter_active() is True

        # Clear search
        state.clear_search()

        # Both should be cleared
        assert state.is_search_active() is False
        assert state.is_error_filter_active() is False
        assert state.show_errors_only is False
        assert state.error_filter_active is False

    def test_error_filter_independent_of_search(self):
        """Error filter should work independently of search."""
        state = StateManager()

        # Enable error filter only
        state.toggle_error_filter()
        assert state.is_error_filter_active() is True
        assert state.is_search_active() is False

        # Enable search
        state.set_search_options(SearchOptions(term="test"))
        assert state.is_search_active() is True
        assert state.is_error_filter_active() is True  # Still active

        # Disable error filter
        state.toggle_error_filter()
        assert state.is_error_filter_active() is False
        assert state.is_search_active() is True  # Search still active


class TestErrorFilterLogic:
    """Test error filtering logic helpers."""

    def test_filter_traces_with_errors(self):
        """Should filter to only traces with failed tool calls."""
        from roma_dspy.tui.utils.helpers import ToolExtractor

        # Mock traces with and without errors
        traces = [
            TraceViewModel(
                trace_id="trace1",
                task_id="task1",
                start_time="2024-01-01T00:00:00",
                tool_calls=[
                    {"name": "tool1", "error": "Some error"},  # Failed
                ],
            ),
            TraceViewModel(
                trace_id="trace2",
                task_id="task1",
                start_time="2024-01-01T00:00:01",
                tool_calls=[
                    {"name": "tool2", "output": "success"},  # Success
                ],
            ),
            TraceViewModel(
                trace_id="trace3",
                task_id="task1",
                start_time="2024-01-01T00:00:02",
                tool_calls=[
                    {"name": "tool3", "exception": "Error"},  # Failed
                ],
            ),
        ]

        # Filter to errors only
        extractor = ToolExtractor()
        filtered = []
        for trace in traces:
            if trace.tool_calls:
                has_errors = any(not extractor.is_successful(call) for call in trace.tool_calls)
                if has_errors:
                    filtered.append(trace)

        # Should only have trace1 and trace3 (the failed ones)
        assert len(filtered) == 2
        assert filtered[0].trace_id == "trace1"
        assert filtered[1].trace_id == "trace3"

    def test_filter_tools_with_errors(self):
        """Should filter to only failed tool calls."""
        from roma_dspy.tui.utils.helpers import ToolExtractor

        tools = [
            {"name": "tool1", "output": "success"},  # Success
            {"name": "tool2", "error": "Failed"},  # Failed
            {"name": "tool3", "result": "ok"},  # Success
            {"name": "tool4", "exception": "Error"},  # Failed
        ]

        extractor = ToolExtractor()
        filtered = [call for call in tools if not extractor.is_successful(call)]

        # Should only have tool2 and tool4
        assert len(filtered) == 2
        assert filtered[0]["name"] == "tool2"
        assert filtered[1]["name"] == "tool4"


class TestSearchAndErrorFilterCombination:
    """Test combination of search and error filters."""

    def test_both_filters_active(self):
        """Both search and error filter can be active simultaneously."""
        state = StateManager()

        # Enable search
        state.set_search_options(SearchOptions(term="error", scope="current"))
        assert state.is_search_active() is True

        # Enable error filter
        state.toggle_error_filter()
        assert state.is_error_filter_active() is True

        # Both should be active
        assert state.is_search_active() is True
        assert state.is_error_filter_active() is True

    def test_clear_disables_both(self):
        """Clearing should disable both filters."""
        state = StateManager()

        # Enable both
        state.set_search_options(SearchOptions(term="test"))
        state.toggle_error_filter()

        # Clear
        state.clear_search()

        # Both should be disabled
        assert state.is_search_active() is False
        assert state.is_error_filter_active() is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
