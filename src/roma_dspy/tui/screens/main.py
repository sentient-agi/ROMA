"""Main screen for TUI.

Displays task tree, tabs with content areas, and handles navigation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Static, TabbedContent, TabPane, Tree

from roma_dspy.tui.widgets import TreeTable

if TYPE_CHECKING:
    from roma_dspy.tui.models import TaskViewModel


LM_TABLE_COLUMN_CONFIG = [
    ("module", "Module"),
    ("model", "Model"),
    ("start_time", "Start Time"),
    ("latency", "Latency (s)"),
    ("preview", "Preview"),
]

TOOL_TABLE_COLUMN_CONFIG = [
    ("name", "Tool"),
    ("tool_type", "Type"),
    ("toolkit", "Toolkit"),
    ("start_time", "Start Time"),
    ("duration", "Duration (s)"),
    ("status", "Status"),
    ("preview", "Preview"),
]


class MainScreen(Screen):
    """Main application screen with task tree and tabbed content."""

    CSS = """
    #body {
        layout: horizontal;
        height: 1fr;
    }

    #task-tree {
        width: 35%;
        border-right: solid $primary;
        background: $surface;
    }

    #detail-tabs-wrapper {
        width: 1fr;
        height: 100%;
    }

    #detail-tabs {
        border: tall $accent;
        width: 100%;
        height: 100%;
    }

    TabPane {
        layout: vertical;
        height: 1fr;
    }

    #spans-container {
        layout: vertical;
        height: 100%;
    }

    #spans-heading {
        display: none;
    }

    #spans-summary {
        display: none;
    }

    #spans-table {
        height: 60%;
    }

    #timeline-graph {
        height: 35%;
        border-top: solid $primary;
        margin-top: 1;
    }

    #timeline-graph-content {
        padding: 1 2;
    }

    #task-info, #summary-info {
        padding: 1 2;
    }

    #lm-table, #tool-table {
        height: 100%;
    }

    /* Data table styling */
    DataTable > .datatable--cursor {
        background: $accent;
    }

    DataTable > .datatable--header {
        background: $primary;
        color: $text;
    }

    /* Tree styling */
    Tree {
        background: $surface;
    }

    TreeTable {
        background: $surface;
    }
    """

    BINDINGS = [
        ("r", "reload", "Reload"),
        ("l", "toggle_live", "Live Mode"),
        ("i", "toggle_io", "Toggle I/O"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, execution_id: str) -> None:
        """Initialize main screen.

        Args:
            execution_id: Execution ID being displayed
        """
        super().__init__()
        self.execution_id = execution_id

    def compose(self) -> ComposeResult:
        """Compose main screen layout.

        Yields:
            Main screen components (without Header/Footer - those are handled by App)
        """
        logger.debug("MainScreen.compose() called")
        with Container(id="body"):
            # Left side: Task tree
            tree = Tree("Loading…", id="task-tree")
            tree.show_root = True  # Show root to display execution summary
            logger.debug("Yielding tree...")
            yield tree

            # Right side: Tabbed content
            with Container(id="detail-tabs-wrapper"):
                logger.debug("Creating tabbed content...")
                with TabbedContent(id="detail-tabs"):
                    # Spans tab with table and timeline
                    with TabPane("Spans", id="tab-spans"):
                        with Container(id="spans-container"):
                            yield Static("", id="spans-heading")
                            yield Static("", id="spans-summary")

                            spans_table = TreeTable(
                                columns=["Start Time", "Duration", "Model", "Tools"],
                                id="spans-table",
                            )
                            yield spans_table

                            with VerticalScroll(id="timeline-graph"):
                                yield Static("[dim](no timeline data)[/dim]", id="timeline-graph-content")

                    # Task Info tab
                    with TabPane("Task Info", id="tab-info"):
                        with VerticalScroll():
                            yield Static("Select a task to view details", id="task-info")

                    # Run Summary tab
                    with TabPane("Run Summary", id="tab-summary"):
                        with VerticalScroll():
                            yield Static("Loading run summary…", id="summary-info")

                    # LM Calls tab
                    with TabPane("LM Calls", id="tab-lm"):
                        lm_table = DataTable(id="lm-table", cursor_type="row")
                        lm_table.add_columns(
                            *[(label, key) for key, label in LM_TABLE_COLUMN_CONFIG]
                        )
                        yield lm_table

                    # Tool Calls tab
                    with TabPane("Tool Calls", id="tab-tools"):
                        tool_table = DataTable(id="tool-table", cursor_type="row")
                        tool_table.add_columns(
                            *[(label, key) for key, label in TOOL_TABLE_COLUMN_CONFIG]
                        )
                        yield tool_table

                    # Errors tab
                    with TabPane("Errors", id="tab-errors"):
                        error_table = DataTable(id="error-table", cursor_type="row")
                        error_table.add_columns(
                            ("Type", "type"),
                            ("Source", "source"),
                            ("Error", "error"),
                            ("Timestamp", "timestamp"),
                        )
                        yield error_table

    def on_mount(self) -> None:
        """Handle screen mount."""
        logger.debug(f"Main screen mounted for execution {self.execution_id[:8]}")

    def get_selected_task(self) -> TaskViewModel | None:
        """Get currently selected task from tree.

        Returns:
            Selected task or None
        """
        tree = self.query_one("#task-tree", Tree)

        if not tree.cursor_node:
            return None

        # Get task from node data
        node_data = tree.cursor_node.data
        if node_data and isinstance(node_data, dict):
            return node_data.get("task")

        return None

    def update_task_tree(self, tree_widget: Tree) -> None:
        """Update task tree widget.

        This is called by the app to update the tree display.

        Args:
            tree_widget: Tree widget to update
        """
        logger.debug("Task tree updated")

    def update_spans_table(self, table: TreeTable) -> None:
        """Update spans table widget.

        This is called by the app to update the spans display.

        Args:
            table: TreeTable widget to update
        """
        logger.debug("Spans table updated")

    def update_lm_table(self, table: DataTable) -> None:
        """Update LM calls table widget.

        This is called by the app to update the LM calls display.

        Args:
            table: DataTable widget to update
        """
        logger.debug("LM calls table updated")

    def update_tool_table(self, table: DataTable) -> None:
        """Update tool calls table widget.

        This is called by the app to update the tool calls display.

        Args:
            table: DataTable widget to update
        """
        logger.debug("Tool calls table updated")

    @staticmethod
    def update_task_info(app: "App", task: TaskViewModel) -> None:
        """Update task info panel.

        Args:
            app: App instance to query widgets from
            task: Task to display info for
        """
        info_widget = app.query_one("#task-info", Static)

        # Build task info text
        lines = [
            f"[bold]Task ID:[/bold] {task.task_id}",
            f"[bold]Status:[/bold] {task.status}",
            f"[bold]Module:[/bold] {task.module or 'N/A'}",
            "",
            f"[bold]Goal:[/bold]",
            task.goal or "(no goal)",
        ]

        if task.total_duration > 0:
            lines.append(f"\n[bold]Duration:[/bold] {task.total_duration:.3f}s")

        if task.total_tokens > 0:
            lines.append(f"[bold]Tokens:[/bold] {task.total_tokens:,}")

        if task.total_cost > 0:
            lines.append(f"[bold]Cost:[/bold] ${task.total_cost:.6f}")

        if task.error:
            lines.extend([
                "",
                "[bold red]Error:[/bold red]",
                f"[red]{task.error}[/red]"
            ])

        info_widget.update("\n".join(lines))
        logger.debug(f"Task info updated for task {task.task_id[:8]}")

    @staticmethod
    def update_summary(app: "App", summary_text: str) -> None:
        """Update run summary panel.

        Args:
            app: App instance to query widgets from
            summary_text: Summary text to display
        """
        summary_widget = app.query_one("#summary-info", Static)
        summary_widget.update(summary_text)
        logger.debug("Run summary updated")

    @staticmethod
    def update_timeline_graph(app: "App", graph_text: str) -> None:
        """Update timeline graph.

        Args:
            app: App instance to query widgets from
            graph_text: Graph text to display
        """
        graph_widget = app.query_one("#timeline-graph-content", Static)
        graph_widget.update(graph_text)
        logger.debug("Timeline graph updated")

    @staticmethod
    def update_spans_heading(app: "App", heading: str) -> None:
        """Update spans heading.

        Args:
            app: App instance to query widgets from
            heading: Heading text
        """
        heading_widget = app.query_one("#spans-heading", Static)
        heading_widget.update(heading)

    @staticmethod
    def update_spans_summary(app: "App", summary: str) -> None:
        """Update spans summary.

        Args:
            app: App instance to query widgets from
            summary: Summary text
        """
        summary_widget = app.query_one("#spans-summary", Static)
        summary_widget.update(summary)
