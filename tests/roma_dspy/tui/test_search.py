"""Unit tests for TUI search and filter functionality.

Tests SearchEngine, SearchOptions, and StateManager search integration.
"""

from __future__ import annotations

import pytest

from roma_dspy.tui.core.state import SearchOptions, StateManager
from roma_dspy.tui.models import TraceViewModel
from roma_dspy.tui.utils.helpers import SearchEngine


# =============================================================================
# SearchOptions Tests
# =============================================================================


class TestSearchOptions:
    """Test SearchOptions dataclass."""

    def test_default_values(self) -> None:
        """Test default SearchOptions values."""
        options = SearchOptions()
        assert options.term == ""
        assert options.case_sensitive is False
        assert options.use_regex is False
        assert options.search_in_io is False
        assert options.scope == "current"

    def test_is_active_empty_term(self) -> None:
        """Test is_active() returns False for empty term."""
        options = SearchOptions(term="")
        assert options.is_active() is False

    def test_is_active_whitespace_term(self) -> None:
        """Test is_active() returns False for whitespace-only term."""
        options = SearchOptions(term="   ")
        assert options.is_active() is False

    def test_is_active_valid_term(self) -> None:
        """Test is_active() returns True for valid term."""
        options = SearchOptions(term="error")
        assert options.is_active() is True

    def test_clear(self) -> None:
        """Test clear() resets all options."""
        options = SearchOptions(
            term="test",
            case_sensitive=True,
            use_regex=True,
            search_in_io=True,
            scope="all",
        )
        options.clear()

        assert options.term == ""
        assert options.case_sensitive is False
        assert options.use_regex is False
        assert options.search_in_io is False
        assert options.scope == "current"


# =============================================================================
# SearchEngine Tests
# =============================================================================


class TestSearchEngine:
    """Test SearchEngine search methods."""

    def test_compile_pattern_literal(self) -> None:
        """Test compile_pattern() with literal string."""
        pattern = SearchEngine.compile_pattern("error", case_sensitive=False, use_regex=False)
        assert pattern is not None
        assert pattern.search("This is an error") is not None
        assert pattern.search("This is an ERROR") is not None  # case insensitive

    def test_compile_pattern_literal_case_sensitive(self) -> None:
        """Test compile_pattern() with case-sensitive literal."""
        pattern = SearchEngine.compile_pattern("Error", case_sensitive=True, use_regex=False)
        assert pattern is not None
        assert pattern.search("This is an Error") is not None
        assert pattern.search("This is an error") is None  # case sensitive

    def test_compile_pattern_regex(self) -> None:
        """Test compile_pattern() with regex pattern."""
        pattern = SearchEngine.compile_pattern(r"error.*timeout", case_sensitive=False, use_regex=True)
        assert pattern is not None
        assert pattern.search("error: connection timeout") is not None
        assert pattern.search("error with timeout") is not None
        assert pattern.search("timeout error") is None  # wrong order

    def test_compile_pattern_invalid_regex(self) -> None:
        """Test compile_pattern() with invalid regex raises ValueError."""
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            SearchEngine.compile_pattern("[invalid", case_sensitive=False, use_regex=True)

    def test_search_items_generic(self) -> None:
        """Test search_items() with generic extractor."""
        items = [
            {"name": "error_handler", "type": "function"},
            {"name": "success_handler", "type": "function"},
            {"name": "error_logger", "type": "class"},
        ]

        def extract_fields(item: dict) -> list[str]:
            return [item["name"], item["type"]]

        results = SearchEngine.search_items(
            items,
            term="error",
            case_sensitive=False,
            use_regex=False,
            field_extractor=extract_fields,
        )

        assert len(results) == 2
        assert results[0]["name"] == "error_handler"
        assert results[1]["name"] == "error_logger"

    def test_search_items_no_matches(self) -> None:
        """Test search_items() with no matches."""
        items = [
            {"name": "success_handler"},
            {"name": "info_logger"},
        ]

        def extract_fields(item: dict) -> list[str]:
            return [item["name"]]

        results = SearchEngine.search_items(
            items,
            term="error",
            field_extractor=extract_fields,
        )

        assert len(results) == 0

    def test_search_traces_advanced_basic(self) -> None:
        """Test search_traces_advanced() with basic search."""
        traces = [
            TraceViewModel(
                trace_id="trace1",
                task_id="task1",
                name="ChainOfThought.forward",
                module="executor",
                inputs="What is the capital of France?",
                outputs="Paris",
            ),
            TraceViewModel(
                trace_id="trace2",
                task_id="task1",
                name="Planner.forward",
                module="planner",
                inputs="Plan a trip to Rome",
                outputs="Step 1: Book flights",
            ),
        ]

        results = SearchEngine.search_traces_advanced(
            traces,
            term="france",
            case_sensitive=False,
            use_regex=False,
            search_in_io=True,
        )

        assert len(results) == 1
        assert results[0].trace_id == "trace1"

    def test_search_traces_advanced_module_search(self) -> None:
        """Test search_traces_advanced() searching in module names."""
        traces = [
            TraceViewModel(
                trace_id="trace1",
                task_id="task1",
                name="forward",
                module="executor",
            ),
            TraceViewModel(
                trace_id="trace2",
                task_id="task1",
                name="forward",
                module="planner",
            ),
        ]

        results = SearchEngine.search_traces_advanced(
            traces,
            term="planner",
            case_sensitive=False,
            use_regex=False,
            search_in_io=False,
        )

        assert len(results) == 1
        assert results[0].trace_id == "trace2"

    def test_search_traces_advanced_regex(self) -> None:
        """Test search_traces_advanced() with regex pattern."""
        traces = [
            TraceViewModel(
                trace_id="trace1",
                task_id="task1",
                name="ChainOfThought.forward",
                module="executor",
            ),
            TraceViewModel(
                trace_id="trace2",
                task_id="task1",
                name="ReAct.forward",
                module="executor",
            ),
            TraceViewModel(
                trace_id="trace3",
                task_id="task1",
                name="Planner.forward",
                module="planner",
            ),
        ]

        results = SearchEngine.search_traces_advanced(
            traces,
            term=r"(ChainOfThought|ReAct)",
            case_sensitive=False,
            use_regex=True,
            search_in_io=False,
        )

        assert len(results) == 2
        assert results[0].trace_id == "trace1"
        assert results[1].trace_id == "trace2"

    def test_search_tool_calls_basic(self) -> None:
        """Test search_tool_calls() with basic search."""
        tool_calls = [
            {
                "call": {"tool": "calculator", "args": {"expr": "2+2"}},
                "trace": TraceViewModel(trace_id="t1", task_id="task1"),
                "module": "executor",
            },
            {
                "call": {"tool": "web_search", "args": {"query": "python"}},
                "trace": TraceViewModel(trace_id="t2", task_id="task1"),
                "module": "executor",
            },
        ]

        results = SearchEngine.search_tool_calls(
            tool_calls,
            term="calculator",
            case_sensitive=False,
            use_regex=False,
        )

        assert len(results) == 1
        assert results[0]["call"]["tool"] == "calculator"

    def test_filter_by_module(self) -> None:
        """Test filter_by_module() filters traces by module."""
        traces = [
            TraceViewModel(trace_id="t1", task_id="task1", module="executor"),
            TraceViewModel(trace_id="t2", task_id="task1", module="planner"),
            TraceViewModel(trace_id="t3", task_id="task1", module="executor"),
        ]

        results = SearchEngine.filter_by_module(traces, "executor")
        assert len(results) == 2
        assert all(t.module == "executor" for t in results)

    def test_filter_by_model(self) -> None:
        """Test filter_by_model() filters traces by model."""
        traces = [
            TraceViewModel(trace_id="t1", task_id="task1", model="gpt-4"),
            TraceViewModel(trace_id="t2", task_id="task1", model="gpt-3.5-turbo"),
            TraceViewModel(trace_id="t3", task_id="task1", model="gpt-4"),
        ]

        results = SearchEngine.filter_by_model(traces, "gpt-4")
        assert len(results) == 2
        assert all(t.model == "gpt-4" for t in results)

    def test_filter_by_duration_range(self) -> None:
        """Test filter_by_duration_range() filters by duration."""
        # Duration is in seconds, min/max is in milliseconds
        traces = [
            TraceViewModel(trace_id="t1", task_id="task1", duration=0.1),  # 100ms
            TraceViewModel(trace_id="t2", task_id="task1", duration=0.5),  # 500ms
            TraceViewModel(trace_id="t3", task_id="task1", duration=1.5),  # 1500ms
        ]

        results = SearchEngine.filter_by_duration_range(traces, min_ms=200, max_ms=1000)
        assert len(results) == 1
        assert results[0].trace_id == "t2"


# =============================================================================
# StateManager Search Integration Tests
# =============================================================================


class TestStateManagerSearch:
    """Test StateManager search state management."""

    def test_set_search_options(self) -> None:
        """Test set_search_options() stores options."""
        state = StateManager()
        options = SearchOptions(term="error", scope="all")

        state.set_search_options(options)

        assert state.search_options.term == "error"
        assert state.search_options.scope == "all"

    def test_is_search_active_default(self) -> None:
        """Test is_search_active() returns False by default."""
        state = StateManager()
        assert state.is_search_active() is False

    def test_is_search_active_after_set(self) -> None:
        """Test is_search_active() returns True after setting options."""
        state = StateManager()
        options = SearchOptions(term="error")
        state.set_search_options(options)

        assert state.is_search_active() is True

    def test_clear_search(self) -> None:
        """Test clear_search() resets all search state."""
        state = StateManager()

        # Set search state
        options = SearchOptions(term="error")
        state.set_search_options(options)
        state.set_search_results(
            filtered_traces=[TraceViewModel(trace_id="t1", task_id="task1")],
            match_count=1,
            total_count=10,
        )

        # Clear search
        state.clear_search()

        assert state.search_options.term == ""
        assert state.filtered_traces is None
        assert state.filtered_tools is None
        assert state.match_count == 0
        assert state.total_count == 0
        assert state.is_search_active() is False

    def test_get_search_summary_no_search(self) -> None:
        """Test get_search_summary() returns empty string when no search active."""
        state = StateManager()
        assert state.get_search_summary() == ""

    def test_get_search_summary_with_results(self) -> None:
        """Test get_search_summary() formats summary correctly."""
        state = StateManager()
        options = SearchOptions(term="error")
        state.set_search_options(options)
        state.set_search_results(match_count=12, total_count=50)

        summary = state.get_search_summary()
        assert "12/50" in summary
        assert "error" in summary
        assert "🔍" in summary

    def test_get_search_summary_long_term(self) -> None:
        """Test get_search_summary() truncates long search terms."""
        state = StateManager()
        long_term = "this is a very long search term that should be truncated"
        options = SearchOptions(term=long_term)
        state.set_search_options(options)
        state.set_search_results(match_count=5, total_count=20)

        summary = state.get_search_summary()
        # Should be truncated to 20 chars (17 + "...")
        assert len(summary) < len(long_term) + 20  # Account for emoji and counts

    def test_get_status_summary_includes_search(self) -> None:
        """Test get_status_summary() includes search status when active."""
        state = StateManager()
        options = SearchOptions(term="error")
        state.set_search_options(options)
        state.set_search_results(match_count=10, total_count=50)

        status = state.get_status_summary()
        assert "🔍 10/50" in status
        assert "error" in status

    def test_get_status_summary_no_search(self) -> None:
        """Test get_status_summary() excludes search when inactive."""
        state = StateManager()
        status = state.get_status_summary()
        assert "🔍" not in status

    def test_reset_clears_search(self) -> None:
        """Test reset() clears all search state."""
        state = StateManager()

        # Set search state
        options = SearchOptions(term="error")
        state.set_search_options(options)
        state.set_search_results(match_count=5, total_count=20)

        # Reset
        state.reset()

        assert state.search_options.term == ""
        assert state.filtered_traces is None
        assert state.match_count == 0
        assert state.is_search_active() is False


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================


class TestSearchEdgeCases:
    """Test edge cases and error handling."""

    def test_search_empty_list(self) -> None:
        """Test searching empty list returns empty list."""
        results = SearchEngine.search_items(
            [],
            term="test",
            field_extractor=lambda x: [str(x)],
        )
        assert results == []

    def test_search_none_values(self) -> None:
        """Test searching handles None values gracefully."""
        traces = [
            TraceViewModel(trace_id="t1", task_id="task1", name=None, module=None),
            TraceViewModel(trace_id="t2", task_id="task1", name="forward", module="executor"),
        ]

        results = SearchEngine.search_traces_advanced(
            traces,
            term="forward",
            case_sensitive=False,
            use_regex=False,
            search_in_io=False,
        )

        assert len(results) == 1
        assert results[0].trace_id == "t2"

    def test_filter_by_duration_none_values(self) -> None:
        """Test duration filtering handles None/0 duration gracefully."""
        # Duration is in seconds, min/max is in milliseconds
        traces = [
            TraceViewModel(trace_id="t1", task_id="task1", duration=None),
            TraceViewModel(trace_id="t2", task_id="task1", duration=0),
            TraceViewModel(trace_id="t3", task_id="task1", duration=0.5),  # 500ms
        ]

        results = SearchEngine.filter_by_duration_range(traces, min_ms=100, max_ms=1000)
        assert len(results) == 1
        assert results[0].trace_id == "t3"

    def test_special_regex_characters_literal_search(self) -> None:
        """Test literal search properly escapes special regex characters."""
        pattern = SearchEngine.compile_pattern("test[0]", case_sensitive=False, use_regex=False)
        assert pattern is not None
        # Should match literal "test[0]", not "test0" or "testX"
        assert pattern.search("test[0]") is not None
        assert pattern.search("test0") is None
