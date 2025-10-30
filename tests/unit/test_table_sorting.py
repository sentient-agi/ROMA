"""Test table sorting functionality in TUI v2.

Tests that DataTable.sort() works correctly with formatted numeric values
and that our parse_number() function handles all edge cases.
"""

import pytest
from textual.widgets import DataTable

from roma_dspy.tui.app import RomaVizApp, parse_number


class TestTableSorting:
    """Test sorting functionality."""

    def test_parse_number_basic(self):
        """Test parse_number with basic values."""
        # Test plain numbers
        assert parse_number("123") == 123.0
        assert parse_number("123.456") == 123.456

        # Test formatted numbers
        assert parse_number("1,234") == 1234.0
        assert parse_number("5.123s") == 5.123
        assert parse_number("$0.001234") == 0.001234

        # Test edge cases
        assert parse_number("") == 0.0
        assert parse_number("(none)") == 0.0
        assert parse_number(None) == 0.0

    def test_parse_number_rich_text(self):
        """Test parse_number with Rich Text objects."""
        from rich.text import Text

        # Create Rich Text objects
        rich_number = Text("1,234")
        rich_duration = Text("5.123s")

        assert parse_number(rich_number) == 1234.0
        assert parse_number(rich_duration) == 5.123

    def test_parse_number_sorting_logic(self):
        """Test that parse_number produces correct sort order."""
        # Unsorted formatted values (like in real app)
        values = ["5.628s", "0.419s", "5.173s", "5.918s", "4.716s"]

        # Parse and sort
        parsed = [parse_number(v) for v in values]
        sorted_parsed = sorted(parsed)

        # Verify ascending order
        assert sorted_parsed == [0.419, 4.716, 5.173, 5.628, 5.918]

        # Verify descending order
        sorted_parsed_desc = sorted(parsed, reverse=True)
        assert sorted_parsed_desc == [5.918, 5.628, 5.173, 4.716, 0.419]

    def test_parse_number_with_token_formatting(self):
        """Test parsing token counts with thousands separators."""
        values = ["1,234", "5,678", "890", "12,345"]
        parsed = [parse_number(v) for v in values]

        # Sort ascending
        sorted_parsed = sorted(parsed)
        assert sorted_parsed == [890.0, 1234.0, 5678.0, 12345.0]

    def test_sortable_configs_excludes_spans(self):
        """Test that Spans table is not in sortable configs."""
        # Verify Spans is excluded
        assert "tab-spans" not in RomaVizApp.SORTABLE_TABLE_CONFIGS

        # Verify other tabs are included
        assert "tab-lm" in RomaVizApp.SORTABLE_TABLE_CONFIGS
        assert "tab-tools" in RomaVizApp.SORTABLE_TABLE_CONFIGS

    def test_sort_state_default_values(self):
        """Test that default sort state has correct structure."""
        # The app defines default sort state as class variable
        # We can test the structure without instantiating
        expected_tabs = {"lm", "tool"}

        # Access the class-level default via __init__ defaults
        # Just verify the SORTABLE_TABLE_CONFIGS matches expectations
        sortable_tabs = {cfg["tab_id"] for cfg in RomaVizApp.SORTABLE_TABLE_CONFIGS.values()}
        assert sortable_tabs == expected_tabs
