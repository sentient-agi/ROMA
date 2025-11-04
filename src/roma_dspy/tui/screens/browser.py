"""Browser screen for listing and filtering executions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from textual import events
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static

if TYPE_CHECKING:
    from roma_dspy.tui.core.client import ApiClient


class BrowserScreen(Screen):
    """Screen for browsing all executions with filtering."""

    BINDINGS = [
        ("f", "filter", "Filter"),
        ("r", "refresh", "Refresh"),
        ("s", "sort", "Sort"),
        ("enter", "select", "Open"),
        ("q", "quit", "Quit"),
    ]

    CSS = """
    BrowserScreen {
        background: $surface;
    }

    #browser-container {
        layout: vertical;
        height: 100%;
        width: 100%;
    }

    #browser-header {
        padding: 1 2;
        background: $primary;
        color: $text;
    }

    #filter-info {
        padding: 0 2;
        background: $accent;
        color: $text;
        height: auto;
    }

    #executions-table {
        height: 1fr;
        border: tall $primary;
    }

    DataTable {
        height: 100%;
    }
    """

    def __init__(
        self,
        api_client: ApiClient,
        status_filter: str | None = None,
        profile_filter: str | None = None,
        experiment_filter: str | None = None
    ) -> None:
        """Initialize browser screen.

        Args:
            api_client: API client for fetching executions
            status_filter: Filter by status
            profile_filter: Filter by profile
            experiment_filter: Filter by experiment name
        """
        super().__init__()
        self.api_client = api_client
        self.status_filter = status_filter
        self.profile_filter = profile_filter
        self.experiment_filter = experiment_filter
        self.executions_data = []
        self.loading = False
        self.sort_column = "created"  # Default sort column
        self.sort_reverse = True  # Default: newest first

    def compose(self) -> ComposeResult:
        """Compose browser screen layout."""
        yield Header()

        with Container(id="browser-container"):
            yield Static(
                "[bold]ROMA-DSPy Execution Browser[/bold]",
                id="browser-header"
            )
            yield Static("", id="filter-info")

            table = DataTable(id="executions-table", cursor_type="row")
            table.zebra_stripes = True
            yield table

        yield Footer()

    def on_mount(self) -> None:
        """Initialize table and load data when mounted."""
        table = self.query_one("#executions-table", DataTable)

        # Add columns
        table.add_columns(
            "Execution ID",
            "Profile",
            "Experiment",
            "Status",
            "Goal",
            "Created ↓"  # Show initial sort indicator
        )

        # Update filter info
        self._update_filter_info()

        # Load executions
        self.refresh_executions()

    def _update_filter_info(self) -> None:
        """Update filter information display."""
        filter_info = self.query_one("#filter-info", Static)

        filters = []
        if self.status_filter:
            filters.append(f"Status: {self.status_filter}")
        if self.profile_filter:
            filters.append(f"Profile: {self.profile_filter}")
        if self.experiment_filter:
            filters.append(f"Experiment: {self.experiment_filter}")

        if filters:
            filter_text = "Filters: " + " | ".join(filters)
            filter_info.update(f"[yellow]{filter_text}[/yellow]")
        else:
            filter_info.update("[dim]No filters applied[/dim]")

    def refresh_executions(self) -> None:
        """Fetch and display executions from API."""
        if self.loading:
            return

        self.loading = True
        logger.info("Fetching executions from API")

        # Run async fetch in the app's event loop
        self.run_worker(
            self._fetch_executions(),
            exclusive=True,
            name="fetch_executions"
        )

    async def _fetch_executions(self) -> None:
        """Async worker to fetch executions."""
        try:
            # Fetch from API
            response = await self.api_client.list_executions(
                status=self.status_filter,
                profile=self.profile_filter,
                experiment_name=self.experiment_filter,
                limit=100
            )

            self.executions_data = response.get("executions", [])
            logger.info(f"Fetched {len(self.executions_data)} executions")

            # Update table directly (we're already in async context)
            self._populate_table()

        except Exception as e:
            logger.error(f"Failed to fetch executions: {e}")
            self._show_error(f"Failed to load executions: {e}")
        finally:
            self.loading = False

    def _sort_executions(self) -> None:
        """Sort executions data by current sort column."""
        if not self.executions_data:
            return

        # Define sort key functions
        sort_keys = {
            "id": lambda x: x.get("execution_id", ""),
            "profile": lambda x: x.get("profile", ""),
            "experiment": lambda x: x.get("experiment_name", ""),
            "status": lambda x: x.get("status", ""),
            "goal": lambda x: x.get("initial_goal", ""),
            "created": lambda x: x.get("created_at", ""),
        }

        key_fn = sort_keys.get(self.sort_column, sort_keys["created"])
        self.executions_data.sort(key=key_fn, reverse=self.sort_reverse)

    def _populate_table(self) -> None:
        """Populate table with execution data."""
        table = self.query_one("#executions-table", DataTable)
        table.clear()

        if not self.executions_data:
            table.add_row("", "", "", "", "[dim]No executions found[/dim]", "")
            return

        # Sort data before populating
        self._sort_executions()

        for execution in self.executions_data:
            # Format created_at timestamp
            created_at = execution.get("created_at", "")
            if created_at:
                # Extract date and time (first 16 chars: "YYYY-MM-DD HH:MM")
                created_at = created_at[:16] if len(created_at) >= 16 else created_at

            # Show full execution ID
            exec_id = execution.get("execution_id", "")

            # Truncate goal if too long
            goal = execution.get("initial_goal", "")
            if len(goal) > 60:
                goal = goal[:57] + "..."

            # Color status
            status = execution.get("status", "unknown")
            if status == "completed":
                status_display = f"[green]{status}[/green]"
            elif status == "failed":
                status_display = f"[red]{status}[/red]"
            elif status == "running":
                status_display = f"[yellow]{status}[/yellow]"
            else:
                status_display = f"[dim]{status}[/dim]"

            table.add_row(
                exec_id,  # Show full ID
                execution.get("profile", "unknown"),
                execution.get("experiment_name", "unknown"),
                status_display,
                goal,
                created_at,
                key=exec_id  # Store full ID as key
            )

    def _show_error(self, message: str) -> None:
        """Show error message in table."""
        table = self.query_one("#executions-table", DataTable)
        table.clear()
        table.add_row("", "", "", "", f"[red]{message}[/red]", "")

    def action_filter(self) -> None:
        """Show filter modal with API client for dropdown options.

        Follows DIP: Passes API client dependency to modal.
        """
        from roma_dspy.tui.screens.browser_modal import BrowserFilterModal

        def handle_filters(filters: dict[str, str | None] | None) -> None:
            """Handle filter modal result."""
            if filters is not None:
                self.status_filter = filters.get("status")
                self.profile_filter = filters.get("profile")
                self.experiment_filter = filters.get("experiment")
                self._update_filter_info()
                self.refresh_executions()

        self.app.push_screen(
            BrowserFilterModal(
                api_client=self.api_client,
                current_status=self.status_filter,
                current_profile=self.profile_filter,
                current_experiment=self.experiment_filter
            ),
            handle_filters
        )

    def _update_column_headers(self) -> None:
        """Update column headers to show sort indicator."""
        table = self.query_one("#executions-table", DataTable)

        # Column name mapping
        column_names = {
            "id": "Execution ID",
            "profile": "Profile",
            "experiment": "Experiment",
            "status": "Status",
            "goal": "Goal",
            "created": "Created"
        }

        # Clear and re-add columns with sort indicators
        table.clear(columns=True)

        columns = ["id", "profile", "experiment", "status", "goal", "created"]
        for col in columns:
            name = column_names[col]
            if col == self.sort_column:
                arrow = " ↓" if self.sort_reverse else " ↑"
                name += arrow
            table.add_column(name, key=col)

    def action_sort(self) -> None:
        """Cycle through sort columns."""
        columns = ["id", "profile", "experiment", "status", "goal", "created"]
        current_idx = columns.index(self.sort_column) if self.sort_column in columns else 0

        # Move to next column
        next_idx = (current_idx + 1) % len(columns)
        self.sort_column = columns[next_idx]

        # Toggle reverse if same column (but we're cycling, so just use default)
        # For created, default is reverse (newest first)
        # For others, default is forward (A-Z)
        self.sort_reverse = self.sort_column == "created"

        logger.info(f"Sorting by {self.sort_column} (reverse={self.sort_reverse})")

        # Update headers and repopulate
        self._update_column_headers()
        self._populate_table()

    def action_refresh(self) -> None:
        """Refresh executions list."""
        logger.info("Refreshing executions")
        self.refresh_executions()

    def _get_selected_execution_id(self) -> str | None:
        """Get execution ID from currently selected row.

        Returns:
            Execution ID if valid selection, None otherwise
        """
        table = self.query_one("#executions-table", DataTable)

        # Validate cursor position
        if table.cursor_row is None:
            logger.debug("No row selected")
            return None

        if table.cursor_row >= len(self.executions_data):
            logger.warning(f"Cursor row {table.cursor_row} out of bounds (length: {len(self.executions_data)})")
            return None

        if not self.executions_data:
            logger.warning("No executions data available")
            return None

        # Extract execution ID
        execution = self.executions_data[table.cursor_row]
        execution_id = execution.get("execution_id")

        if not execution_id:
            logger.warning(f"No execution_id in row data: {execution}")
            return None

        return execution_id

    def _open_selected_execution(self) -> None:
        """Open the currently selected execution in detail view.

        Single Responsibility: Only handles opening execution from selection.
        Called by: Enter key, double-click, row selection events.
        """
        execution_id = self._get_selected_execution_id()

        if execution_id:
            logger.info(f"Opening execution: {execution_id}")
            self.dismiss(execution_id)
        else:
            logger.debug("No valid execution to open")

    def action_select(self) -> None:
        """Action handler for 'select' binding."""
        self._open_selected_execution()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection event (Enter key on DataTable)."""
        logger.info(f"Row selected event: row {event.cursor_row}")
        self._open_selected_execution()

    def on_key(self, event: events.Key) -> None:
        """Handle key press events."""
        if event.key == "enter":
            logger.info("Enter key detected")
            self._open_selected_execution()
            event.prevent_default()
            event.stop()

    def _is_double_click(self, row: int) -> bool:
        """Check if current click is a double-click on same row.

        Args:
            row: Current cursor row

        Returns:
            True if double-click detected (within 0.5s on same row)
        """
        import time

        current_time = time.time()

        # Initialize tracking on first click
        if not hasattr(self, '_last_click_time'):
            self._last_click_time = 0
            self._last_click_row = -1

        # Calculate time difference and check same row
        time_diff = current_time - self._last_click_time
        same_row = self._last_click_row == row
        is_double = time_diff < 0.5 and same_row

        # Update tracking
        self._last_click_time = current_time
        self._last_click_row = row

        return is_double

    async def on_click(self, event: events.Click) -> None:
        """Handle click events for double-click detection."""
        # Only handle left button clicks
        if event.button != 1:
            return

        # Get table widget
        try:
            table = self.query_one("#executions-table", DataTable)
        except Exception as e:
            logger.error(f"Failed to get table: {e}")
            return

        # Check if click is within table bounds
        if not table.region.contains(event.screen_x, event.screen_y):
            return

        # Check for double-click on valid row
        if table.cursor_row is not None and table.cursor_row < len(self.executions_data):
            if self._is_double_click(table.cursor_row):
                logger.info(f"Double-click detected on row {table.cursor_row}")
                self._open_selected_execution()

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()
