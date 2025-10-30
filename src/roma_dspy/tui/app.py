"""Main TUI v2 application.

Orchestrates all components: config, state, client, renderers, screens.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger
from rich.text import Text
from rich.style import Style
from rich.styled import Styled
from rich.markup import escape as rich_escape
from textual.app import App, ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widgets import DataTable, Static, Tree
from textual.color import Color
from textual.render import measure

# Configure loguru to output ONLY to file (not stderr, to avoid interfering with TUI)
logger.remove()  # Remove default handler
logger.add("/tmp/roma_tui_v2_debug.log", level="DEBUG", rotation="10 MB")

from roma_dspy.tui.core.client import ApiClient
from roma_dspy.tui.core.config import Config
from roma_dspy.tui.core.state import StateManager
from roma_dspy.tui.models import ExecutionViewModel, TaskViewModel, TraceViewModel
from roma_dspy.tui.rendering.formatters import Formatters
from roma_dspy.tui.rendering.table_renderer import TableRenderer
from roma_dspy.tui.rendering.tree_renderer import TreeRenderer
from roma_dspy.tui.screens.main import (
    MainScreen,
    LM_TABLE_COLUMN_CONFIG,
    TOOL_TABLE_COLUMN_CONFIG,
)
from roma_dspy.tui.screens.modals import (
    DetailModal,
    ExportModal,
    HelpModal,
    ImportModal,
    LMCallDetailParser,
    ToolCallDetailParser,
)
from roma_dspy.tui.screens.welcome import WelcomeScreen
from roma_dspy.tui.transformer import DataTransformer
from roma_dspy.tui.types.export import ExportLevel
from roma_dspy.tui.utils.clipboard import copy_json_safe, copy_to_clipboard_safe
from roma_dspy.tui.utils.errors import ErrorHandler
from roma_dspy.tui.utils.export import ExportService
from roma_dspy.tui.utils.import_service import ImportService
from roma_dspy.tui.widgets import TreeNode, TreeTable


def parse_number(value: Any, default: float = 0.0) -> float:
    """Extract a numeric value from formatted table content.

    Args:
        value: Value to convert (supports str, Rich Text, numbers)
        default: Fallback value if conversion fails

    Returns:
        float: Parsed numeric value
    """
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value)

    if isinstance(value, Text):
        value = value.plain
    elif hasattr(value, "plain"):
        value = getattr(value, "plain")

    value_str = str(value).strip()
    if not value_str or value_str == "(none)":
        return default

    cleaned = value_str.replace(",", "")
    match = re.search(r"[-+]?[0-9]*\.?[0-9]+", cleaned)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return default
    return default


def _color_to_hex(color: Color) -> str:
    """Return a 6-digit hex string for a Textual Color."""
    hex_value = color.hex
    return hex_value[:7] if len(hex_value) == 9 else hex_value


def _readable_text_color(bg: Color) -> Color:
    """Choose a readable text color for the given background."""
    return Color.parse("#111111") if bg.brightness > 0.55 else Color.parse("#f8f9fb")


@dataclass
class TableSortState:
    """Sort state for a single table."""
    column: Optional[str] = None  # Column key (see table configs)
    reverse: bool = True


class DataLoaded(Message):
    """Message emitted when remote data finished loading."""

    def __init__(self, success: bool, error: Optional[str] = None) -> None:
        """Initialize message.

        Args:
            success: Whether data loaded successfully
            error: Error message if failed
        """
        super().__init__()
        self.success = success
        self.error = error


class RomaVizApp(App):
    """Main TUI v2 application."""

    TITLE = "🔷 ROMA-DSPy Visualizer"
    SUB_TITLE = ""  # Will be set dynamically to execution info

    # Import CSS from MainScreen
    CSS_PATH = None

    # Use MainScreen's CSS
    from roma_dspy.tui.screens.main import MainScreen as _MainScreenForCSS
    CSS = _MainScreenForCSS.CSS

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "reload", "Reload"),
        ("l", "toggle_live", "Toggle Live"),
        ("t", "scroll_top", "Scroll Top"),
        ("?", "help", "Help"),
        ("e", "export", "Export"),
        ("i", "import_file", "Import"),
        ("c", "copy", "Copy"),
        ("shift+c", "copy_json", "Copy JSON"),
        ("s", "sort", "Sort"),
        ("S", "sort_reverse", "Reverse Sort"),  # Use uppercase S for Shift+S
    ]

    # Sort configuration for each tab (DRY)
    # Note: Spans table excluded - it's hierarchical and shows execution order
    SORTABLE_TABLE_CONFIGS = {
        "tab-lm": {
            "tab_id": "lm",
            "table_selector": "#lm-table",
            "columns": ["module", "model", "latency", "preview"],
        },
        "tab-tools": {
            "tab_id": "tool",
            "table_selector": "#tool-table",
            "columns": ["name", "tool_type", "toolkit", "duration", "status", "preview"],
        },
    }

    # Reactive properties
    show_io = reactive(False)
    live_mode = reactive(False)

    # Sort state (per tab) - consolidated using TableSortState
    # Note: Spans excluded - hierarchical table showing execution order
    _sort_state: Dict[str, TableSortState] = {
        "lm": TableSortState(column="latency", reverse=True),
        "tool": TableSortState(column="duration", reverse=True),
    }

    def __init__(
        self,
        execution_id: Optional[str] = None,
        base_url: str = "http://localhost:8000",
        live: bool = False,
        poll_interval: float = 2.0,
        file_path: Optional[Path] = None,
    ) -> None:
        """Initialize application.

        Args:
            execution_id: Execution ID to visualize (required if file_path not provided)
            base_url: API base URL
            live: Enable live mode
            poll_interval: Polling interval in seconds
            file_path: Path to exported file (mutually exclusive with execution_id)

        Raises:
            ValueError: If neither execution_id nor file_path provided, or both provided
        """
        super().__init__()

        # Validate mutually exclusive parameters
        if execution_id and file_path:
            raise ValueError("Cannot specify both execution_id and file_path")
        if not execution_id and not file_path:
            raise ValueError("Must specify either execution_id or file_path")

        # Set mode
        self.file_path = file_path
        self.execution_id = execution_id or "file-mode"
        self.poll_interval = poll_interval

        # Load configuration
        self.config = Config.load()

        # Override base_url from config if provided as parameter
        if base_url != "http://localhost:8000":
            self.config.api.base_url = base_url

        # Initialize components (skip ApiClient if in file mode)
        if not file_path:
            self.client = ApiClient(self.config.api)
        else:
            self.client = None
        self.state = StateManager()
        self.transformer = DataTransformer()
        self.formatters = Formatters()
        self.table_renderer = TableRenderer(show_io=False)
        self.tree_renderer = TreeRenderer()
        self.error_handler = ErrorHandler()

        # Column metadata for LM/Tool tables (keeps sorting/labels DRY)
        self._column_labels: Dict[str, Dict[str, str]] = {
            "lm": {key: label for key, label in LM_TABLE_COLUMN_CONFIG},
            "tool": {key: label for key, label in TOOL_TABLE_COLUMN_CONFIG},
        }
        self._numeric_sort_columns: Dict[str, set[str]] = {
            "lm": {"latency"},
            "tool": {"duration"},
        }
        self._table_column_keys: Dict[str, Dict[str, Any]] = {"lm": {}, "tool": {}}
        self._column_highlight_state: Dict[str, Dict[str, Any]] = {
            "lm": {"active": None, "cells": {}},
            "tool": {"active": None, "cells": {}},
        }

        # Live mode state
        self.live_mode = live
        self._poll_task: Optional[asyncio.Task] = None
        self._last_update: Optional[datetime] = None
        self._active_render_task: Optional[asyncio.Task] = None

    def compose(self) -> ComposeResult:
        """Compose app - yield header, main content, and footer."""
        from textual.widgets import Footer, Header

        yield Header(show_clock=True)
        self._main_screen = MainScreen(self.execution_id)
        yield from self._main_screen.compose()
        yield Footer()

    def on_mount(self) -> None:
        """Handle app mount - show welcome screen and load data."""
        # Show welcome screen first
        welcome_screen = WelcomeScreen(self.execution_id)

        async def load_data_background() -> None:
            """Load data in background."""
            await self._load_data()
            # Mark data as loaded on welcome screen
            welcome_screen.mark_data_loaded()

        def on_welcome_dismissed(result: bool | None) -> None:
            """Handle welcome screen dismissal."""
            logger.debug(f"Welcome screen dismissed with result: {result}")

            # Now welcome screen is dismissed - render the UI
            if result and self.state.execution:
                logger.debug("Rendering tree and summary after welcome dismissal...")
                logger.debug(f"Execution has {len(self.state.execution.tasks)} tasks")
                self._populate_tree()
                logger.debug("Tree populated")
                self._render_summary_tab()
                logger.debug("Summary tab rendered")

                if self.live_mode:
                    asyncio.create_task(self._start_live_polling())
            else:
                logger.warning(f"Not rendering UI: result={result}, execution={bool(self.state.execution)}")

        # Show welcome screen with callback
        self.push_screen(welcome_screen, on_welcome_dismissed)

        # Start loading data
        asyncio.create_task(load_data_background())

        logger.info(f"App mounted for execution {self.execution_id[:8]}")

    async def on_unmount(self) -> None:
        """Handle app unmount - stop polling."""
        await self._stop_live_polling()
        logger.info("App unmounted")

    # =============================================================================
    # ACTIONS - Keyboard bindings
    # =============================================================================

    async def action_reload(self) -> None:
        """Reload data from server."""
        logger.debug("Reload action triggered")
        await self._load_data()
        self.notify("Data reloaded", severity="information", timeout=2)

    async def action_toggle_live(self) -> None:
        """Toggle live mode on/off."""
        self.live_mode = not self.live_mode
        if self.live_mode:
            await self._start_live_polling()
            self.notify("Live mode: ON", severity="information", timeout=2)
        else:
            await self._stop_live_polling()
            self.notify("Live mode: OFF", severity="information", timeout=2)

        self._update_live_mode_indicator()
        logger.info(f"Live mode toggled: {self.live_mode}")

    def action_help(self) -> None:
        """Show help modal."""
        self.push_screen(HelpModal())
        logger.debug("Help modal opened")

    def action_import_file(self) -> None:
        """Show import modal to load execution from file."""
        logger.debug("Opening import modal")

        # Callback to handle import result
        def on_import_modal_dismissed(filepath: Path | None) -> None:
            """Handle import modal result."""
            if filepath is None:
                logger.debug("Import cancelled")
                return

            logger.info(f"Importing execution from: {filepath}")
            self.notify("Loading execution...", severity="information", timeout=2)

            # Load execution in background worker
            self.run_worker(
                self._load_execution_from_file(filepath),
                name="import-execution",
                description=f"Importing {filepath.name}",
            )

        # Show import modal
        modal = ImportModal()
        self.push_screen(modal, on_import_modal_dismissed)
        logger.debug("Import modal opened")

    async def _load_execution_from_file(self, filepath: Path) -> None:
        """Load execution from file and refresh UI.

        Args:
            filepath: Path to exported file

        Raises:
            Exception: Any import errors are caught and notified to user
        """
        try:
            # Load execution using ImportService
            import_service = ImportService()

            # Run blocking file I/O in thread pool
            execution = await asyncio.to_thread(
                import_service.load_from_file,
                filepath,
                validate_checksum=True
            )

            # Update state
            self.state.execution = execution
            self.execution_id = execution.execution_id
            self.file_path = filepath

            # Switch to file mode (disable live updates)
            self.live = False

            # Refresh UI
            self._render_all_tabs()

            # Success notification
            task_count = len(execution.tasks)
            self.notify(
                f"✓ Loaded execution {execution.execution_id[:8]}... ({task_count} tasks)",
                severity="information",
                timeout=5
            )
            logger.info(f"Successfully loaded execution from {filepath}")

        except ValueError as exc:
            # Validation or checksum error
            logger.error(f"Import validation error: {exc}", exc_info=True)
            self.notify(f"❌ Import failed: {str(exc)[:80]}", severity="error", timeout=5)
        except json.JSONDecodeError as exc:
            # Invalid JSON
            logger.error(f"Import JSON error: {exc}", exc_info=True)
            self.notify(f"❌ Invalid JSON file: {str(exc)[:60]}", severity="error", timeout=5)
        except Exception as exc:
            # Other errors
            logger.error(f"Import failed: {exc}", exc_info=True)
            self.notify(f"❌ Import failed: {str(exc)[:60]}", severity="error", timeout=5)

    async def action_export(self) -> None:
        """Show export modal and handle export."""
        if not self.state.execution:
            self.notify("No execution data available", severity="warning", timeout=2)
            return

        # Get active tab
        active_tab = self._get_active_tab_id()
        has_selection = self._has_selection()

        # Show modal and wait for result
        def on_export_modal_dismissed(result: tuple[str, str, str, str, str, bool, bool] | None) -> None:
            """Handle export modal result (starts background worker)."""
            if result is None:
                logger.debug("Export cancelled")
                return

            export_format, export_scope, execution_id, filepath_str, export_level, exclude_io, redact_sensitive = result
            logger.debug(
                f"Export: format={export_format}, scope={export_scope}, level={export_level}, "
                f"exclude_io={exclude_io}, redact={redact_sensitive}, path={filepath_str}"
            )

            # Get data to export (fast operation)
            try:
                data, data_type = self._get_export_data(export_scope, active_tab)
                if data is None:
                    self.notify("No data to export", severity="warning", timeout=2)
                    return
            except Exception as exc:
                logger.error(f"Failed to get export data: {exc}", exc_info=True)
                self.notify(f"Export failed: {str(exc)[:50]}", severity="error", timeout=5)
                return

            # Use pre-generated filepath from modal (avoids race condition)
            from pathlib import Path
            filepath = Path(filepath_str)

            # Run export in background worker to avoid blocking UI
            self.run_worker(
                self._perform_export(
                    export_format, data, data_type, filepath,
                    export_level, exclude_io, redact_sensitive
                ),
                name=f"export-{export_format}",
                description=f"Exporting {data_type} to {filepath.name}",
            )
            self.notify("Exporting...", severity="information", timeout=2)

        # Show modal with callback
        modal = ExportModal(
            execution_id=self.execution_id,
            active_tab=active_tab,
            has_selection=has_selection,
        )
        self.push_screen(modal, on_export_modal_dismissed)
        logger.debug("Export modal opened")

    async def _perform_export(
        self,
        export_format: str,
        data: Any,
        data_type: str,
        filepath: Path,
        export_level: str = "full",
        exclude_io: bool = False,
        redact_sensitive: bool = False,
    ) -> None:
        """Perform export operation in background (async to avoid blocking UI).

        This method runs in a worker thread, allowing large exports without freezing the UI.

        Args:
            export_format: Export format (json, csv, markdown)
            data: Data to export
            data_type: Type of data being exported
            filepath: Output filepath
            export_level: Export level for JSON (full, compact, minimal)
            exclude_io: Exclude trace I/O data
            redact_sensitive: Redact sensitive strings (API keys, tokens)

        Raises:
            Exception: Any export errors are caught and notified to user
        """
        try:
            # Perform I/O operation (runs in thread pool, won't block UI)
            if export_format == "json":
                # Use full export for ExecutionViewModel with level and privacy options
                if isinstance(data, ExecutionViewModel):
                    # Convert string level to enum
                    level_map = {
                        "full": ExportLevel.FULL,
                        "compact": ExportLevel.COMPACT,
                        "minimal": ExportLevel.MINIMAL,
                    }
                    level_enum = level_map.get(export_level, ExportLevel.FULL)

                    # Export with full control
                    result = ExportService.export_execution_full(
                        execution=data,
                        filepath=filepath,
                        level=level_enum,
                        exclude_io=exclude_io,
                        redact_sensitive=redact_sensitive,
                        api_url=self.config.api.base_url,
                    )

                    # Log export details
                    logger.info(
                        f"Exported execution: level={result.level.value}, "
                        f"size={result.size_bytes / 1024:.1f}KB, "
                        f"compressed={result.compressed}, "
                        f"io_excluded={result.io_excluded}, "
                        f"redacted={result.redacted}"
                    )
                else:
                    # Fall back to simple JSON export for non-execution data (tabs, selections)
                    ExportService.export_to_json(data, filepath)
            elif export_format == "csv":
                self._export_csv(data, data_type, filepath)
            elif export_format == "markdown":
                if isinstance(data, ExecutionViewModel):
                    ExportService.export_to_markdown(data, filepath)
                else:
                    self.notify(
                        "Markdown export only available for full execution",
                        severity="warning",
                        timeout=3
                    )
                    return

            # Success notification with full path
            self.notify(
                f"✓ Exported to:\n{filepath}",
                severity="information",
                timeout=8
            )
            logger.info(f"Exported {data_type} to {filepath}")

        except PermissionError as exc:
            logger.error(f"Export permission denied: {exc}", exc_info=True)
            self.notify(f"❌ Permission denied: {filepath.parent}", severity="error", timeout=5)
        except OSError as exc:
            logger.error(f"Export OS error: {exc}", exc_info=True)
            error_msg = "Disk full" if exc.errno == 28 else str(exc)[:50]
            self.notify(f"❌ Export failed: {error_msg}", severity="error", timeout=5)
        except Exception as exc:
            logger.error(f"Export failed: {exc}", exc_info=True)
            self.notify(f"❌ Export failed: {str(exc)[:50]}", severity="error", timeout=5)

    def action_scroll_top(self) -> None:
        """Scroll current tab to top."""
        from textual.containers import VerticalScroll
        try:
            # Find any focused VerticalScroll widget
            for scroll in self.query(VerticalScroll):
                if scroll.has_focus_within:
                    scroll.scroll_home(animate=True)
                    logger.debug("Scrolled to top")
                    return

            # If no focused scroll, scroll the visible one in active tab
            for scroll in self.query(VerticalScroll):
                if scroll.styles.display != "none":
                    scroll.scroll_home(animate=True)
                    logger.debug("Scrolled visible scroll to top")
                    return
        except Exception as e:
            logger.error(f"Scroll top error: {e}", exc_info=True)


    def action_copy(self) -> None:
        """Copy selected item (simple format)."""
        active_tab = self._get_active_tab_id()
        data, simple_text = self._get_copy_data(active_tab)

        if not data:
            self.notify("No item selected to copy", severity="warning", timeout=2)
            return

        success, message = copy_to_clipboard_safe(self, simple_text)
        self.notify(message, severity="information" if success else "warning", timeout=2)

    def action_copy_json(self) -> None:
        """Copy selected item as JSON."""
        active_tab = self._get_active_tab_id()
        data, description = self._get_copy_data(active_tab)

        if not data:
            self.notify("No item selected to copy", severity="warning", timeout=2)
            return

        # Debug logging
        data_type = type(data).__name__
        logger.info(f"Copying data type: {data_type}, description: {description}")

        # Log if it's ExecutionViewModel
        if isinstance(data, ExecutionViewModel):
            logger.info(f"Copying ExecutionViewModel with {len(data.tasks)} tasks")

        success, message = copy_json_safe(self, data)

        # Enhance message with what was copied
        if success:
            enhanced_message = f"✓ Copied JSON: {description}\n[dim]Type: {data_type}[/dim]"
        else:
            enhanced_message = f"{message}\n({description})"

        self.notify(enhanced_message, severity="information" if success else "warning", timeout=3)

    def action_sort(self) -> None:
        """Cycle through sort columns (DRY - config-driven)."""
        active_tab = self._get_active_tab_id()
        config = self.SORTABLE_TABLE_CONFIGS.get(active_tab)

        if not config:
            if active_tab == "tab-spans":
                self.notify("Spans table shows execution order and cannot be sorted", severity="information", timeout=3)
            return

        # Cycle to next column
        tab_id = config["tab_id"]
        columns = config["columns"]
        state = self._get_sort_state(tab_id)
        idx = columns.index(state.column) if state.column in columns else 0
        self._set_sort_column(tab_id, columns[(idx + 1) % len(columns)])

        # Apply sort directly to the existing table (don't re-render!)
        try:
            table = self.query_one(config["table_selector"], DataTable)
            self._apply_table_sort(tab_id, table)
        except Exception as e:
            logger.error(f"Failed to apply sort: {e}")

        # Notify user
        state = self._get_sort_state(tab_id)
        self._notify_sort_change(tab_id, state.column, state.reverse)

    def action_sort_reverse(self) -> None:
        """Reverse sort order (DRY - config-driven)."""
        active_tab = self._get_active_tab_id()
        config = self.SORTABLE_TABLE_CONFIGS.get(active_tab)

        if not config:
            if active_tab == "tab-spans":
                self.notify("Spans table shows execution order and cannot be sorted", severity="information", timeout=3)
            return

        # Toggle reverse direction
        tab_id = config["tab_id"]
        self._toggle_sort_reverse(tab_id)

        # Apply sort directly to the existing table (don't re-render!)
        try:
            table = self.query_one(config["table_selector"], DataTable)
            self._apply_table_sort(tab_id, table)
        except Exception as e:
            logger.error(f"Failed to apply sort: {e}")

        # Notify user
        state = self._get_sort_state(tab_id)
        self._notify_sort_change(tab_id, state.column, state.reverse)

    # =============================================================================
    # SORT HELPERS (DRY)
    # =============================================================================

    def _format_sort_direction(self, reverse: bool) -> str:
        """Format sort direction with arrow."""
        return "▼ Descending" if reverse else "▲ Ascending"

    def _notify_sort_change(self, tab_id: str, column_key: Optional[str], reverse: bool) -> None:
        """Notify user of sort change with visual indicator."""
        labels = self._column_labels.get(tab_id, {})
        column_label = labels.get(column_key, column_key or "-")
        direction = self._format_sort_direction(reverse)
        arrow = "▼" if reverse else "▲"
        self.notify(
            f"[bold]{arrow} Sorted:[/bold] {column_label} ({direction})",
            severity="information",
            timeout=4,
        )

    def _get_sort_state(self, tab_id: str) -> TableSortState:
        """Get sort state for a sortable tab.

        Args:
            tab_id: Tab identifier ("lm" or "tool")

        Returns:
            TableSortState for the tab
        """
        return self._sort_state[tab_id]

    def _set_sort_column(self, tab_id: str, column: str) -> None:
        """Set sort column for a specific tab.

        Args:
            tab_id: Tab identifier ("lm" or "tool")
            column: Column name to sort by
        """
        self._sort_state[tab_id].column = column

    def _toggle_sort_reverse(self, tab_id: str) -> None:
        """Toggle sort direction for a specific tab.

        Args:
            tab_id: Tab identifier ("lm" or "tool")
        """
        self._sort_state[tab_id].reverse = not self._sort_state[tab_id].reverse

    def _handle_column_click_logic(self, tab_id: str, column_name: str) -> None:
        """Handle column click toggle logic (DRY helper).

        Implements: same column = reverse, different column = set new column.

        Args:
            tab_id: Tab identifier ("lm" or "tool")
            column_name: Column name that was clicked
        """
        if tab_id not in self._sort_state:
            return
        state = self._get_sort_state(tab_id)
        if state.column == column_name:
            # Same column - reverse sort direction
            self._toggle_sort_reverse(tab_id)
        else:
            # Different column - set new column, default to descending
            self._set_sort_column(tab_id, column_name)
            self._sort_state[tab_id].reverse = True

    def _apply_table_sort(self, tab_id: str, table, table_type: str = "data") -> None:
        """Apply current sort settings to any table (DRY helper).

        Args:
            tab_id: Tab identifier ("lm", "tool")
            table: Table widget (DataTable)
            table_type: "tree" for TreeTable, "data" for DataTable
        """
        state = self._get_sort_state(tab_id)
        column_key = state.column

        if not column_key or (hasattr(table, "row_count") and table.row_count == 0):
            if tab_id in ("lm", "tool"):
                self._refresh_sort_ui(tab_id, column_key, state.reverse, table)
            return

        if table_type == "tree":
            try:
                table.sort(column_key, reverse=state.reverse)
                logger.debug(f"{tab_id.capitalize()} tree sorted by {column_key}, reverse={state.reverse}")
            except Exception as e:
                logger.error(f"Apply {tab_id} tree sort error: {e}", exc_info=True)
                self.notify(f"Sort failed: {str(e)[:50]}", severity="error", timeout=2)
            return

        # DataTable sorting (LM/Tool tables)
        column_obj = self._get_column_key_object(tab_id, table, column_key)
        if not column_obj:
            logger.debug(f"No matching column key for '{column_key}' in {tab_id} table")
            return

        numeric_columns = self._numeric_sort_columns.get(tab_id, set())
        key_func = parse_number if column_key in numeric_columns else self._normalize_text

        try:
            logger.debug(
                f"Sorting {tab_id} table: column='{column_key}', reverse={state.reverse}, "
                f"row_count={getattr(table, 'row_count', 'n/a')}, key_func={'parse_number' if key_func is parse_number else 'normalize_text'}"
            )

            table.sort(column_obj, key=key_func, reverse=state.reverse)
            self._refresh_sort_ui(tab_id, column_key, state.reverse, table)
        except Exception as e:
            logger.error(f"Apply {tab_id} table sort error: {e}", exc_info=True)

    def _refresh_sort_ui(
        self,
        tab_id: str,
        column_key: Optional[str],
        reverse: bool,
        table: DataTable,
    ) -> None:
        """Update header and subtitle to reflect current sort."""
        if tab_id not in ("lm", "tool"):
            return

        self._update_table_sort_header(tab_id, table, column_key, reverse)
        self._update_subtitle_with_sort(tab_id, column_key, reverse)
        self._apply_column_highlight(tab_id, table, column_key)

    def _get_column_key_object(self, tab_id: str, table: DataTable, column_key: str):
        """Resolve Textual ColumnKey object for a canonical column name."""
        cache = self._table_column_keys.setdefault(tab_id, {})
        cached = cache.get(column_key)
        if cached and cached in table.columns:
            return cached

        for key in table.columns:
            if getattr(key, "value", None) == column_key:
                cache[column_key] = key
                return key
        return None

    def _apply_column_highlight(
        self,
        tab_id: str,
        table: DataTable,
        active_column: Optional[str],
    ) -> None:
        """Highlight the currently sorted column with an accent background."""
        logger.debug(f"_apply_column_highlight(tab={tab_id}, column={active_column})")
        state = self._column_highlight_state.get(tab_id)
        if state is None:
            return

        previous_column = state.get("active")
        previous_cells: Dict[Any, Any] = state.get("cells", {})

        if previous_column:
            previous_key_obj = self._get_column_key_object(tab_id, table, previous_column)
            if previous_key_obj:
                for row_key, original_value in list(previous_cells.items()):
                    try:
                        table.update_cell(row_key, previous_key_obj, original_value, update_width=False)
                    except Exception:
                        continue

        state["cells"] = {}
        state["active"] = None

        if not active_column:
            table.refresh()
            return

        column_key_obj = self._get_column_key_object(tab_id, table, active_column)
        if not column_key_obj:
            return

        if getattr(table, "row_count", 0) == 0:
            state["active"] = active_column
            table.refresh()
            return

        accent_hex = self._get_accent_color()
        try:
            accent_color = Color.parse(accent_hex)
        except Exception:
            accent_color = Color.parse("cyan")

        if accent_color.brightness <= 0.45:
            highlight_bg = accent_color.lighten(0.45)
        else:
            highlight_bg = accent_color.darken(0.2)
        text_color = _readable_text_color(highlight_bg)
        fg_hex = _color_to_hex(text_color)
        bg_hex = _color_to_hex(highlight_bg)

        for row_key in list(table.rows.keys()):
            try:
                original_value = table.get_cell(row_key, column_key_obj)
            except Exception:
                continue

            if isinstance(original_value, Text):
                stored_value = original_value.copy()
            elif isinstance(original_value, Styled) and isinstance(original_value.renderable, Text):
                stored_value = Styled(original_value.renderable.copy(), original_value.style)
            else:
                stored_value = original_value
            state["cells"][row_key] = stored_value

            base_renderable = original_value.renderable if isinstance(original_value, Styled) else original_value
            if isinstance(base_renderable, Text):
                plain = base_renderable.plain
            else:
                plain = str(base_renderable) if base_renderable is not None else ""

            markup_value = f"[{fg_hex} on {bg_hex}]{rich_escape(plain)}[/]"
            styled_value = Text.from_markup(markup_value, no_wrap=True)

            try:
                table.update_cell(row_key, column_key_obj, styled_value, update_width=False)
            except Exception:
                continue

        state["active"] = active_column
        table.refresh()


    @staticmethod
    def _normalize_text(value: Any) -> str:
        """Normalize text for case-insensitive sorting."""
        if value is None:
            return ""
        if isinstance(value, Text):
            value = value.plain
        elif hasattr(value, "plain"):
            value = getattr(value, "plain")
        return str(value).strip().lower()

    def _update_table_sort_header(
        self,
        tab_id: str,
        table: DataTable,
        active_column: Optional[str],
        reverse: bool,
    ) -> None:
        """Refresh DataTable headers with sort indicator."""
        logger.debug(f"_update_table_sort_header(tab={tab_id}, column={active_column}, reverse={reverse})")
        labels = self._column_labels.get(tab_id, {})
        arrow = "▼" if reverse else "▲"
        accent_hex = self._get_accent_color()
        try:
            accent_color = Color.parse(accent_hex)
        except Exception:
            accent_color = Color.parse("cyan")

        # DataTable stores columns keyed by ColumnKey objects.
        # Build an ordered list indexed by position so we can touch headers and cells.
        try:
            ordered_columns = table.ordered_columns()
        except TypeError:  # In case Textual changes signature
            ordered_columns = table.ordered_columns
        iterable = [column.key for column in ordered_columns] if ordered_columns else list(table.columns.keys())

        for column_key_obj in iterable:
            column = table.columns[column_key_obj]
            column_name = getattr(column_key_obj, "value", None)
            base_label = labels.get(
                column_name,
                column.label.plain if isinstance(column.label, Text) else str(column.label),
            )
            label_text = Text(base_label, no_wrap=True)

            if active_column and column_name == active_column:
                if accent_color.brightness <= 0.45:
                    header_bg = accent_color.lighten(0.5)
                else:
                    header_bg = accent_color.darken(0.12)
                header_fg = _readable_text_color(header_bg)
                accent_style = Style(color=_color_to_hex(header_fg), bgcolor=_color_to_hex(header_bg), bold=True)
                label_text.stylize(accent_style, 0, len(label_text.plain))
                label_text.append(f" {arrow}", style=accent_style)
            else:
                label_text.stylize(Style(bold=True), 0, len(label_text.plain))

            column.label = label_text
            try:
                column.content_width = max(column.content_width, measure(self.console, label_text, 1))
            except Exception:
                pass

        table.refresh()
        if active_column:
            column_key_obj = self._get_column_key_object(tab_id, table, active_column)
            if column_key_obj:
                column_index = table._column_locations.get(column_key_obj)
                if column_index is not None:
                    table.refresh_column(column_index)

    def _update_subtitle_with_sort(
        self,
        tab_id: str,
        column_key: Optional[str],
        reverse: bool,
    ) -> None:
        """Update app subtitle when current tab is sorted."""
        pane_lookup = {"lm": "tab-lm", "tool": "tab-tools"}
        tab_titles = {"lm": "LM Calls", "tool": "Tool Calls"}
        active_tab = self._get_active_tab_id()

        if pane_lookup.get(tab_id) != active_tab:
            return

        tab_title = tab_titles.get(tab_id)
        if not tab_title:
            return

        self.sub_title = tab_title if tab_title else ""

    def _get_accent_color(self) -> str:
        """Retrieve accent color from current theme."""
        try:
            accent = self.get_css_variables().get("accent")
            if isinstance(accent, Color):
                return accent.hex
            if accent:
                try:
                    return Color.parse(str(accent)).hex
                except Exception:
                    return str(accent)
        except Exception:
            pass
        return "cyan"

    # =============================================================================
    # DATA LOADING
    # =============================================================================

    async def _load_data(self) -> None:
        """Load execution data from API or file."""
        # Check if loading from file or API
        if self.file_path:
            await self._load_from_file()
        else:
            await self._load_from_api()

    async def _load_from_api(self) -> None:
        """Load execution data from API."""
        try:
            logger.debug(f"Starting data load from API for {self.execution_id}")

            # Fetch data in parallel
            execution_data, lm_traces, metrics = await self.client.fetch_all_parallel(
                self.execution_id
            )
            logger.debug(f"Data fetched: execution={bool(execution_data)}, lm_traces={len(lm_traces)}, metrics={bool(metrics)}")

            # Transform to view models
            self.state.execution = self.transformer.transform(
                mlflow_data=execution_data,
                checkpoint_data={
                    "execution_id": self.execution_id,
                    "tasks": {},
                    "root_goal": execution_data.get("summary", {}).get("root_goal", ""),
                    "status": "unknown",
                    "checkpoints": [],
                },
                lm_traces=lm_traces,
                metrics=metrics,
            )
            logger.debug(f"Data transformed: {len(self.state.execution.tasks)} tasks")
            logger.info(f"Data loaded successfully: {len(self.state.execution.tasks)} tasks")

        except Exception as exc:
            logger.error(f"Data load failed: {exc}", exc_info=True)
            self.notify(f"Load failed: {str(exc)[:50]}", severity="error", timeout=5)
            raise  # Re-raise so caller knows it failed

    async def _load_from_file(self) -> None:
        """Load execution data from exported file."""
        try:
            logger.info(f"Loading execution from file: {self.file_path}")

            # Load using ImportService (runs in thread pool to avoid blocking)
            import_service = ImportService()

            # Run blocking file I/O in thread pool
            execution = await asyncio.to_thread(
                import_service.load_from_file,
                self.file_path,
                validate_checksum=True
            )

            # Set execution in state
            self.state.execution = execution
            self.execution_id = execution.execution_id

            logger.info(
                f"Loaded execution {execution.execution_id[:8]} from file "
                f"({len(execution.tasks)} tasks)"
            )

        except FileNotFoundError as exc:
            logger.error(f"File not found: {exc}")
            self.notify(f"File not found: {self.file_path}", severity="error", timeout=5)
            raise
        except ValueError as exc:
            logger.error(f"Invalid export file: {exc}")
            self.notify(f"Invalid file: {str(exc)[:100]}", severity="error", timeout=5)
            raise
        except Exception as exc:
            logger.error(f"File load failed: {exc}", exc_info=True)
            self.notify(f"Load failed: {str(exc)[:50]}", severity="error", timeout=5)
            raise

    # =============================================================================
    # LIVE POLLING
    # =============================================================================

    async def _start_live_polling(self) -> None:
        """Start live polling background task."""
        if self._poll_task and not self._poll_task.done():
            return

        logger.info("Starting live polling")
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def _stop_live_polling(self) -> None:
        """Stop live polling background task."""
        if self._poll_task and not self._poll_task.done():
            logger.info("Stopping live polling")
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    async def _poll_loop(self) -> None:
        """Background polling loop."""
        while True:
            try:
                await asyncio.sleep(self.poll_interval)
                await self._load_data()
                self._last_update = datetime.now()
                self._update_live_mode_indicator()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Polling error: {e}", exc_info=True)

    def _update_live_mode_indicator(self) -> None:
        """Update tree label to show live mode status."""
        try:
            tree = self.query_one("#task-tree", Tree)
            status = "🔴 LIVE" if self.live_mode else ""
            last_update = f" (updated {self._last_update:%H:%M:%S})" if self._last_update else ""
            tree.root.label = f"{status} Execution {self.execution_id[:8]}{last_update}"
        except Exception:
            pass

    # =============================================================================
    # TREE POPULATION
    # =============================================================================

    def _populate_tree(self) -> None:
        """Populate task tree."""
        if not self.state.execution:
            return

        tree = self.query_one("#task-tree", Tree)
        tree.clear()
        self._update_live_mode_indicator()

        if not self.state.execution.tasks:
            tree.root.add("No tasks available")
            tree.root.expand()
            return

        tree.root.data = self.state.execution

        # Add root tasks
        for root_task_id in self.state.execution.root_task_ids:
            task = self.state.execution.tasks.get(root_task_id)
            if task:
                self._add_task_node(tree.root, task)

        tree.root.expand()
        logger.debug(f"Tree populated: {len(self.state.execution.root_task_ids)} root tasks")

    def _add_task_node(self, parent_node: Tree.TreeNode, task: TaskViewModel) -> Tree.TreeNode:
        """Add task node to tree recursively.

        Args:
            parent_node: Parent tree node
            task: Task to add

        Returns:
            Created tree node
        """
        label = self._build_task_label(task)
        node = parent_node.add(label, data=task)
        node.expand()

        # Add children recursively
        for child_id in task.subtask_ids:
            if self.state.execution:
                child_task = self.state.execution.tasks.get(child_id)
                if child_task:
                    self._add_task_node(node, child_task)

        return node

    def _build_task_label(self, task: TaskViewModel) -> str:
        """Build task tree label.

        Args:
            task: Task view model

        Returns:
            Formatted label
        """
        # Status icon
        status_icon = self.formatters.format_status_icon(task.status)

        # Module tag
        module_tag = self.formatters.format_module_tag(task.module)

        # Goal (truncated)
        goal = self.formatters.truncate(task.goal or "unknown", 60)

        # Metrics
        metrics = self.formatters.format_metric_summary(
            task.total_duration,
            task.total_tokens,
            task.total_cost,
        )

        # Error indicator
        error_icon = " ⚠️" if task.error else ""

        return f"{status_icon} {module_tag}{goal}{metrics}{error_icon}"

    # =============================================================================
    # EVENT HANDLERS
    # =============================================================================

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree node selection."""
        data = event.node.data
        logger.debug(f"Tree node selected: {type(data).__name__ if data else 'None'}")
        logger.debug(f"Event node label: {event.node.label}")

        # Cancel any in-progress render
        if self._active_render_task and not self._active_render_task.done():
            logger.debug("Cancelling previous render task")
            self._active_render_task.cancel()

        if isinstance(data, TaskViewModel):
            logger.debug(f"Rendering views for task {data.task_id[:8]}, goal='{data.goal[:50] if data.goal else 'none'}'")
            self._active_render_task = asyncio.create_task(
                self._render_task_views_async(data)
            )
            logger.debug(f"Created async render task: {self._active_render_task}")
        elif isinstance(data, ExecutionViewModel):
            logger.debug("Rendering execution-level views")
            self._active_render_task = asyncio.create_task(
                self._render_execution_views_async(data)
            )
        else:
            logger.debug(f"Node data is not TaskViewModel or ExecutionViewModel: {type(data)}")

    def on_tree_table_node_selected(self, event: TreeTable.NodeSelected) -> None:
        """Handle TreeTable node selection - show span detail modal."""
        span = event.node.data.get("span_obj")
        if span:
            self._show_span_detail(span)

    def on_tree_table_column_header_clicked(self, event: TreeTable.ColumnHeaderClicked) -> None:
        """Handle column header click for sorting."""
        column_name = event.column_name

        # Determine which table was clicked (only spans table uses TreeTable currently)
        active_tab = self._get_active_tab_id()
        if active_tab != "tab-spans":
            return

        # Spans table keeps execution order; ignore header clicks.
        return

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        """Handle DataTable header clicks for sorting."""
        # Determine which table was clicked
        active_tab = self._get_active_tab_id()

        if active_tab == "tab-lm":
            column_key_obj = event.column_key
            column_key = getattr(column_key_obj, "value", None)
            if not column_key:
                logger.warning("LM header click without column key")
                return

            # Toggle logic (DRY)
            self._handle_column_click_logic("lm", column_key)

            # Re-render table with new sort (task or execution level)
            source = self.state.selected_task or self.state.execution
            if source:
                self._render_lm_table(source)

            state = self._get_sort_state("lm")
            self._notify_sort_change("lm", state.column, state.reverse)

        elif active_tab == "tab-tools":
            column_key_obj = event.column_key
            column_key = getattr(column_key_obj, "value", None)
            if not column_key:
                logger.warning("Tool header click without column key")
                return

            # Toggle logic (DRY)
            self._handle_column_click_logic("tool", column_key)

            # Re-render table with new sort (task or execution level)
            source = self.state.selected_task or self.state.execution
            if source:
                self._render_tool_table(source)

            state = self._get_sort_state("tool")
            self._notify_sort_change("tool", state.column, state.reverse)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle DataTable row selection - show detail modal."""
        # Check if this is an LM call
        trace = self.state.lm_table_row_map.get(event.row_key)
        if trace:
            self._show_span_detail(trace)
            return

        # Check if this is a tool call
        tool_item = self.state.tool_table_row_map.get(event.row_key)
        if tool_item:
            self._show_tool_call_detail(tool_item)


    # =============================================================================
    # RENDERING
    # =============================================================================

    async def _render_task_views_async(self, task: TaskViewModel) -> None:
        """Render task views asynchronously.

        Args:
            task: Task to render
        """
        logger.debug(f"_render_task_views_async called for task {task.task_id[:8]}")
        try:
            self.state.selected_task = task
            await self._render_views_for_traces_async(task.traces, task_info=task)
            logger.debug(f"Rendered all views for task {task.task_id[:8]}")

        except asyncio.CancelledError:
            logger.debug("Task view render cancelled")
            raise
        except Exception as exc:
            logger.error(f"Task view render error: {exc}", exc_info=True)

    async def _render_execution_views_async(self, execution: ExecutionViewModel) -> None:
        """Render execution-level views (aggregated across all tasks).

        Args:
            execution: Execution to render
        """
        logger.debug("Rendering execution-level views")
        try:
            self.state.selected_task = None

            # Collect all traces from all tasks
            all_traces = []
            for task in execution.tasks.values():
                all_traces.extend(task.traces)

            logger.debug(f"Collected {len(all_traces)} total traces from {len(execution.tasks)} tasks")

            await self._render_views_for_traces_async(all_traces, source=execution)
            self._render_summary_tab()

            logger.debug("Execution-level views rendered")

        except asyncio.CancelledError:
            logger.debug("Execution view render cancelled")
            raise
        except Exception as exc:
            logger.error(f"Execution view render error: {exc}", exc_info=True)

    async def _render_views_for_traces_async(
        self,
        traces: list[TraceViewModel],
        task_info: Optional[TaskViewModel] = None,
        source: Optional[TaskViewModel | ExecutionViewModel] = None
    ) -> None:
        """Render all views for given traces (DRY method used by both task and execution rendering).

        Args:
            traces: Traces to render
            task_info: Optional task info to display in Task Info tab (None for execution-level)
            source: Source object (Task or Execution) for table rendering
        """
        # Render spans tab
        try:
            logger.debug(f"Rendering spans tab for {len(traces)} traces")
            await self._render_spans_tab_async(traces)
            logger.debug("Spans tab rendered successfully")
        except Exception as exc:
            logger.error(f"Spans tab render failed: {exc}", exc_info=True)

        # Render other tabs
        try:
            logger.debug("Rendering task info, LM table, and tool table...")

            # Use source for all rendering (defaults to task_info if not provided)
            table_source = source or task_info

            # Render info tab (task or execution level)
            if table_source:
                self._render_info_tab(table_source)
                self._render_lm_table(table_source)
                self._render_tool_table(table_source)
            logger.debug("Tables rendered successfully")
        except Exception as exc:
            logger.error(f"Tabs render failed: {exc}", exc_info=True)

    async def _render_spans_tab_async(self, traces: list[TraceViewModel]) -> None:
        """Render spans tab asynchronously.

        Args:
            traces: Traces to render spans for
        """
        spans_table = self.query_one("#spans-table", TreeTable)
        spans_table.clear()

        # Build span tree
        tree_nodes = self.tree_renderer.build_span_tree_nodes(traces)
        logger.debug(f"Built {len(tree_nodes)} top-level span tree nodes")

        # Add nodes to TreeTable
        for node_data in tree_nodes:
            self._add_span_tree_node(spans_table.root, node_data)

        logger.debug(f"Added {len(tree_nodes)} nodes to spans table")

        # Rebuild visible rows after adding all nodes
        spans_table.rebuild_visible_rows()
        logger.debug(f"Spans table after rebuild: visible_rows={len(spans_table._visible_rows)}, virtual_size={spans_table.virtual_size}")
        spans_table.refresh(layout=True)
        logger.debug("Spans table refreshed with layout=True")

        # Update heading and summary - hide them for cleaner look
        MainScreen.update_spans_heading(self, "")
        MainScreen.update_spans_summary(self, "")

        # Render timeline graph (depth 2 = root + 2 levels of children)
        timeline = self.tree_renderer.render_timeline_graph(traces, max_depth=2)
        MainScreen.update_timeline_graph(self, timeline)

    def _add_span_tree_node(
        self,
        parent: TreeNode,
        node_data: Dict[str, Any]
    ) -> TreeNode:
        """Add span tree node recursively.

        Args:
            parent: Parent node
            node_data: Node data dict

        Returns:
            Created node
        """
        span = node_data["span"]
        label = node_data["label"]

        # Build column data dict
        start_time = self.formatters.format_timestamp(span.start_time) if span.start_time else ""
        duration = self.formatters.format_duration(span.duration)
        model = span.model or ""
        tools = str(len(span.tool_calls)) if span.tool_calls else ""

        # Create node with column data
        column_data = {
            "Start Time": start_time,
            "Duration": duration,
            "Model": model,
            "Tools": tools,
            "span_obj": span,  # Store span object for click handling
        }
        node = parent.add(label, data=column_data)

        # Add children recursively
        for child_data in node_data.get("children", []):
            self._add_span_tree_node(node, child_data)

        # TreeNode.expanded defaults to True, so children are visible by default
        return node

    def _render_info_tab(self, source: TaskViewModel | ExecutionViewModel) -> None:
        """Render info tab (polymorphic - task or execution level).

        Args:
            source: Task or Execution to render info for
        """
        info_widget = self.query_one("#task-info", Static)

        if isinstance(source, TaskViewModel):
            # Task-level info
            lines = [
                f"[bold]Execution ID:[/bold] {self.state.execution.execution_id if self.state.execution else 'N/A'}",
                f"[bold]Task ID:[/bold] {source.task_id}",
                f"[bold]Status:[/bold] {source.status}",
                f"[bold]Module:[/bold] {source.module or 'N/A'}",
                "",
                f"[bold]Goal:[/bold]",
                source.goal or "(no goal)",
            ]

            if source.total_duration > 0:
                lines.append(f"\n[bold]Duration:[/bold] {source.total_duration:.3f}s")

            if source.total_tokens > 0:
                lines.append(f"[bold]Tokens:[/bold] {source.total_tokens:,}")

            if source.total_cost > 0:
                lines.append(f"[bold]Cost:[/bold] ${source.total_cost:.6f}")

            if source.error:
                lines.extend([
                    "",
                    "[bold red]Error:[/bold red]",
                    f"[red]{source.error}[/red]"
                ])

            info_widget.update("\n".join(lines))
            logger.debug(f"Task info rendered for task {source.task_id[:8]}")

        else:
            # Execution-level info - aggregate metrics
            total_duration = sum(t.total_duration for t in source.tasks.values())
            total_tokens = sum(t.total_tokens for t in source.tasks.values())
            total_cost = sum(t.total_cost for t in source.tasks.values())

            lines = [
                f"[bold]Execution ID:[/bold] {source.execution_id}",
                f"[bold]Root Goal:[/bold] {source.root_goal or 'N/A'}",
                "",
                f"[bold]Tasks:[/bold] {len(source.tasks)}",
                f"[bold]Root Tasks:[/bold] {len(source.root_task_ids)}",
                "",
                f"[bold]Total Duration:[/bold] {total_duration:.3f}s",
                f"[bold]Total Tokens:[/bold] {total_tokens:,}",
                f"[bold]Total Cost:[/bold] ${total_cost:.6f}",
            ]

            info_widget.update("\n".join(lines))
            logger.debug("Execution info rendered")

    def _render_lm_table(self, source: TaskViewModel | ExecutionViewModel) -> None:
        """Render LM calls table.

        Args:
            source: Task or Execution to render LM calls for
        """
        lm_table = self.query_one("#lm-table", DataTable)
        logger.debug(f"LM table before render: row_count={lm_table.row_count}")

        if isinstance(source, TaskViewModel):
            # Task-level
            self.table_renderer.render_lm_table(
                lm_table,
                source,
                "task",
                self.state.lm_table_row_map,
            )
        else:
            # Execution-level - pass execution as source with "all" mode
            self.table_renderer.render_lm_table(
                lm_table,
                source,
                "all",
                self.state.lm_table_row_map,
            )

        logger.debug(f"LM table after render: row_count={lm_table.row_count}")

        # Apply current sort settings (AFTER table is fully populated)
        self._apply_table_sort("lm", lm_table)

        # NOTE: Don't call refresh() after sort - it may clear the sort order
        logger.debug("LM table sorted and ready")

    def _render_tool_table(self, source: TaskViewModel | ExecutionViewModel) -> None:
        """Render tool calls table.

        Args:
            source: Task or Execution to render tool calls for
        """
        tool_table = self.query_one("#tool-table", DataTable)

        if isinstance(source, TaskViewModel):
            # Task-level
            self.table_renderer.render_tool_table(
                tool_table,
                source,
                "task",
                self.state.tool_table_row_map,
            )
        else:
            # Execution-level - pass execution as source with "all" mode
            self.table_renderer.render_tool_table(
                tool_table,
                source,
                "all",
                self.state.tool_table_row_map,
            )

        # Apply current sort settings (AFTER table is fully populated)
        self._apply_table_sort("tool", tool_table)

        # NOTE: Don't call refresh() after sort - it may clear the sort order

    def _render_summary_tab(self) -> None:
        """Render summary tab."""
        if not self.state.execution:
            return

        lines = [
            f"[bold]Execution ID:[/bold] {self.state.execution.execution_id}",
            f"[bold]Root Goal:[/bold] {self.state.execution.root_goal or 'N/A'}",
            "",
            f"[bold]Tasks:[/bold] {len(self.state.execution.tasks)}",
            f"[bold]Root Tasks:[/bold] {len(self.state.execution.root_task_ids)}",
        ]

        # Add data sources info
        if self.state.execution.data_sources:
            lines.append("")
            lines.append("[bold]Data Sources:[/bold]")
            for source, available in self.state.execution.data_sources.items():
                status = "✓" if available else "✗"
                lines.append(f"  {status} {source}")

        # Add warnings if any
        if self.state.execution.warnings:
            lines.append("")
            lines.append("[bold red]Warnings:[/bold red]")
            for warning in self.state.execution.warnings[:5]:
                lines.append(f"  ⚠ {warning}")

        summary_text = "\n".join(lines)
        MainScreen.update_summary(self, summary_text)

    # =============================================================================
    # MODAL HELPERS
    # =============================================================================

    def _show_span_detail(self, span: TraceViewModel) -> None:
        """Show span detail modal.

        Args:
            span: Span to show
        """
        try:
            parser = LMCallDetailParser()
            self.push_screen(
                DetailModal(
                    source_obj=span,
                    parser=parser,
                    show_io=self.show_io,
                )
            )
            logger.debug(f"Opened span detail for {span.trace_id[:8]}")
        except Exception as e:
            logger.error(f"Failed to show span detail: {e}", exc_info=True)
            self.notify(f"Failed to show detail: {str(e)[:50]}", severity="error", timeout=3)

    def _show_tool_call_detail(self, tool_item: Dict[str, Any]) -> None:
        """Show tool call detail modal.

        Args:
            tool_item: Tool call dict with 'call', 'trace', 'module'
        """
        try:
            parser = ToolCallDetailParser()
            self.push_screen(
                DetailModal(
                    source_obj=tool_item,
                    parser=parser,
                    show_io=self.show_io,
                )
            )
            logger.debug("Opened tool call detail")
        except Exception as e:
            logger.error(f"Failed to show tool call detail: {e}", exc_info=True)
            self.notify(f"Failed to show detail: {str(e)[:50]}", severity="error", timeout=3)

    # =============================================================================
    # HELPER METHODS
    # =============================================================================

    def _get_active_tab_id(self) -> str:
        """Get ID of currently active tab."""
        try:
            from textual.widgets import TabbedContent
            tabs = self.query_one(TabbedContent)
            active = tabs.active
            return active if active else "spans"
        except Exception:
            return "spans"

    def _has_selection(self) -> bool:
        """Check if an item is currently selected."""
        active_tab = self._get_active_tab_id()

        try:
            if active_tab == "tab-spans":
                spans_table = self.query_one("#spans-table", TreeTable)
                return spans_table.get_selected_node() is not None
            elif active_tab == "tab-lm":
                lm_table = self.query_one("#lm-table", DataTable)
                return lm_table.cursor_row >= 0
            elif active_tab == "tab-tools":
                tool_table = self.query_one("#tool-table", DataTable)
                return tool_table.cursor_row >= 0
        except Exception:
            pass

        return False

    def _build_task_subtree(self, task: TaskViewModel) -> ExecutionViewModel:
        """Build an execution view containing a task and all its descendants.

        Args:
            task: Root task of the subtree

        Returns:
            ExecutionViewModel with the task and all descendants
        """
        # Collect all descendant task IDs recursively
        def collect_descendants(task_id: str, collected: set) -> None:
            if task_id in collected:
                return
            collected.add(task_id)
            task_obj = self.state.execution.tasks.get(task_id)
            if task_obj:
                for subtask_id in task_obj.subtask_ids:
                    collect_descendants(subtask_id, collected)

        task_ids = set()
        collect_descendants(task.task_id, task_ids)

        # Build filtered task dict
        filtered_tasks = {
            tid: self.state.execution.tasks[tid]
            for tid in task_ids
            if tid in self.state.execution.tasks
        }

        # Create execution view with filtered tasks
        return ExecutionViewModel(
            execution_id=self.state.execution.execution_id,
            root_goal=f"Subtree: {task.goal[:100]}",
            status=self.state.execution.status,
            tasks=filtered_tasks,
            root_task_ids=[task.task_id],  # Selected task is the new root
            checkpoints=[],  # Checkpoints not relevant for subtree
        )

    def _get_currently_selected_node(self) -> tuple[Any, str]:
        """Get the currently selected node from the task tree.

        Returns:
            Tuple of (node_data, description) or (None, "")
        """
        try:
            task_tree = self.query_one("#task-tree", Tree)
            # Check cursor_node regardless of focus - user might be on a different tab
            # but still have a task/execution selected in the tree
            if task_tree.cursor_node and task_tree.cursor_node.data:
                node_data = task_tree.cursor_node.data
                logger.debug(f"Task tree cursor_node.data type: {type(node_data).__name__}")

                if isinstance(node_data, ExecutionViewModel):
                    logger.info(f"Detected ExecutionViewModel with {len(node_data.tasks)} tasks")
                    return node_data, "Full execution"
                elif isinstance(node_data, TaskViewModel):
                    # Build subtree with this task and all descendants
                    subtree = self._build_task_subtree(node_data)
                    task_count = len(subtree.tasks)
                    logger.info(f"Built subtree for task {node_data.task_id[:8]} with {task_count} tasks")
                    if task_count == 1:
                        return subtree, f"Task {node_data.task_id[:8]}"
                    else:
                        return subtree, f"Task {node_data.task_id[:8]} + {task_count-1} descendant{'s' if task_count > 2 else ''}"
            else:
                logger.debug("Task tree has no cursor_node or no data")
        except Exception as e:
            logger.error(f"Get selected node error: {e}", exc_info=True)
        return None, ""

    def _get_export_data(self, scope: str, active_tab: str) -> tuple[Any, str]:
        """Get data for export based on scope.

        Args:
            scope: Export scope (execution, tab, selected)
            active_tab: Active tab ID

        Returns:
            Tuple of (data, data_type)
        """
        if scope == "execution":
            return self.state.execution, "execution"

        elif scope == "tab":
            if active_tab == "tab-spans":
                # Get all visible traces from spans table
                if self.state.selected_task:
                    return self.state.selected_task.traces, "spans"
                else:
                    all_traces = []
                    for task in self.state.execution.tasks.values():
                        all_traces.extend(task.traces)
                    return all_traces, "spans"

            elif active_tab == "tab-lm":
                # Get LM traces
                lm_traces = [trace for trace in self.state.lm_table_row_map.values()]
                return lm_traces, "lm_calls"

            elif active_tab == "tab-tools":
                # Get tool calls
                tool_calls = [item["call"] for item in self.state.tool_table_row_map.values()]
                return tool_calls, "tool_calls"

        elif scope == "selected":
            # Check task tree for selection first
            selected_data, description = self._get_currently_selected_node()
            if selected_data:
                return selected_data, "execution"

            # Fall back to state.selected_task if tree doesn't have focus
            if self.state.selected_task:
                subtree = self._build_task_subtree(self.state.selected_task)
                return subtree, "execution"

        return None, None

    def _export_csv(self, data: Any, data_type: str, filepath: Any) -> None:
        """Export data as CSV.

        Args:
            data: Data to export
            data_type: Type of data
            filepath: Output path
        """
        if data_type == "spans" or data_type == "lm_calls":
            ExportService.export_spans_to_csv(data, filepath)
        elif data_type == "tool_calls":
            ExportService.export_tool_calls_to_csv(data, filepath)
        else:
            raise ValueError(f"CSV export not supported for {data_type}")

    def _get_copy_data(self, active_tab: str) -> tuple[Any, str]:
        """Get data for copy operation.

        Priority:
        1. If task tree has FOCUS → use task tree selection (user just clicked tree)
        2. If active tab has specific item → use that (user clicked on span/lm/tool)
        3. Execution-level view fallback

        Args:
            active_tab: Active tab ID

        Returns:
            Tuple of (data, simple_text)
        """
        try:
            # Priority 1: Check if task tree has focus (user just clicked on tree)
            task_tree = self.query_one("#task-tree", Tree)
            if task_tree.has_focus:
                logger.debug("Task tree has focus - using tree selection")
                selected_data, description = self._get_currently_selected_node()
                if selected_data:
                    task_count = len(selected_data.tasks) if isinstance(selected_data, ExecutionViewModel) else 1
                    simple = f"{description} ({task_count} task{'s' if task_count != 1 else ''})"
                    logger.info(f"Copying from focused task tree: {simple}")
                    return selected_data, simple

            # Priority 2: Check if active tab has a specific item selected
            if active_tab == "tab-spans":
                spans_table = self.query_one("#spans-table", TreeTable)
                node = spans_table.get_selected_node()
                if node:
                    span = node.data.get("span_obj")
                    if span:
                        logger.debug(f"Copying selected span: {span.name}")
                        simple = f"Span '{span.name}' ({span.duration:.2f}s)"
                        return span, simple

            elif active_tab == "tab-lm":
                lm_table = self.query_one("#lm-table", DataTable)
                if lm_table.cursor_row >= 0:
                    row_key = lm_table.get_row_at(lm_table.cursor_row)
                    trace = self.state.lm_table_row_map.get(row_key)
                    if trace:
                        logger.debug(f"Copying LM call: {trace.model}")
                        simple = f"LM Call: {trace.model} ({trace.tokens} tokens)"
                        return trace, simple

            elif active_tab == "tab-tools":
                tool_table = self.query_one("#tool-table", DataTable)
                if tool_table.cursor_row >= 0:
                    row_key = tool_table.get_row_at(tool_table.cursor_row)
                    tool_item = self.state.tool_table_row_map.get(row_key)
                    if tool_item:
                        call = tool_item.get("call", {})
                        tool_name = call.get("tool", "unknown")
                        logger.debug(f"Copying tool call: {tool_name}")
                        simple = f"Tool: {tool_name}"
                        return tool_item, simple

            # Priority 3: Execution-level view (no specific selection anywhere)
            if active_tab == "tab-spans" and not self.state.selected_task and self.state.execution:
                task_count = len(self.state.execution.tasks)
                simple = f"Full execution ({task_count} task{'s' if task_count != 1 else ''})"
                logger.debug(f"Copying execution-level view: {simple}")
                return self.state.execution, simple

        except Exception as e:
            logger.error(f"Get copy data error: {e}", exc_info=True)

        return None, ""

def run_viz(
    execution_id: Optional[str] = None,
    base_url: str = "http://localhost:8000",
    live: bool = False,
    poll_interval: float = 2.0,
    file_path: Optional[Path] = None,
) -> None:
    """Run the TUI v2 application.

    Args:
        execution_id: Execution ID to visualize (mutually exclusive with file_path)
        base_url: API base URL
        live: Enable live mode (only for API mode)
        poll_interval: Polling interval in seconds (only for API mode)
        file_path: Path to exported file to load (mutually exclusive with execution_id)

    Raises:
        ValueError: If neither or both execution_id and file_path are provided
    """
    try:
        app = RomaVizApp(
            execution_id=execution_id,
            base_url=base_url,
            live=live,
            poll_interval=poll_interval,
            file_path=file_path,
        )

        if file_path:
            logger.info(f"Starting TUI v2 with file: {file_path}")
        else:
            logger.info(f"Starting TUI v2 for execution {execution_id}")

        app.run()
    except Exception as e:
        logger.error(f"Fatal error in run_viz: {e}", exc_info=True)
        print(f"\n\nFATAL ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        raise
