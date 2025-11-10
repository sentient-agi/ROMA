"""DAG visualization modal for TUI.

Full-screen modal showing hierarchical graph visualization of task dependencies
with interactive controls for filtering, zooming, and navigation.
"""

from __future__ import annotations

from typing import Callable, Dict, Optional, Set

from loguru import logger
from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Header, Label, Static

from roma_dspy.tui.models import DAGViewModel, TaskViewModel
from roma_dspy.tui.rendering.dag_layout import Position, compute_layout
from roma_dspy.tui.rendering.dag_renderer import render_dag_rich
from roma_dspy.types import EdgeType


class DAGLegend(Static):
    """Legend showing edge types and keyboard shortcuts."""

    def compose(self) -> ComposeResult:
        """Compose the legend."""
        legend_text = Text()

        # Edge types
        legend_text.append("Edge Types: ", style="bold")
        legend_text.append("─ Dependency ", style="cyan")
        legend_text.append("═ Data Flow ", style="yellow")
        legend_text.append("┄ Control ", style="magenta")
        legend_text.append("│ Hierarchy ", style="dim")

        # Status
        legend_text.append("\n")
        legend_text.append("Status: ", style="bold")
        legend_text.append("● Complete ", style="green")
        legend_text.append("◐ Running ", style="yellow")
        legend_text.append("○ Pending ", style="dim")
        legend_text.append("✗ Failed ", style="red")
        legend_text.append("⊗ Blocked ", style="magenta")

        yield Static(legend_text, id="legend-content")


class DAGCanvas(VerticalScroll):
    """Scrollable canvas for DAG visualization."""

    BINDINGS = [
        Binding("up,k", "scroll_up", "Scroll Up", show=False),
        Binding("down,j", "scroll_down", "Scroll Down", show=False),
        Binding("left,h", "scroll_left", "Scroll Left", show=False),
        Binding("right,l", "scroll_right", "Scroll Right", show=False),
        Binding("home", "scroll_home", "Scroll to Top", show=False),
        Binding("end", "scroll_end", "Scroll to Bottom", show=False),
    ]

    def __init__(
        self,
        dag: DAGViewModel,
        positions: Dict[str, Position],
        cell_width: int = 20,
        cell_height: int = 4,
        on_node_click: Optional[Callable[[str], None]] = None,
        id: Optional[str] = None,
    ):
        super().__init__(id=id)
        self.dag = dag
        self.positions = positions
        self.cell_width = cell_width
        self.cell_height = cell_height
        self.on_node_click = on_node_click
        self._rendered_text: Optional[Text] = None

    def compose(self) -> ComposeResult:
        """Compose the canvas with rendered DAG."""
        if not self._rendered_text:
            self._rendered_text = render_dag_rich(
                self.dag,
                self.positions,
                cell_width=self.cell_width,
                cell_height=self.cell_height,
                show_metrics=True,
            )

        yield Static(self._rendered_text, id="dag-content")

    def on_click(self, event: events.Click) -> None:
        """Handle click events to detect node selection."""
        if not self.on_node_click:
            return

        # Get click coordinates relative to the canvas
        click_x = event.x
        click_y = event.y

        # Find which node was clicked based on positions
        clicked_task_id = self._get_task_at_position(click_x, click_y)

        if clicked_task_id:
            logger.info(f"Node clicked: {clicked_task_id}")
            self.on_node_click(clicked_task_id)

    def _get_task_at_position(self, x: int, y: int) -> Optional[str]:
        """Get task ID at canvas position (x, y)."""
        for task_id, position in self.positions.items():
            # Calculate node boundaries
            node_x = int(position.x * self.cell_width)
            node_y = int(position.y * self.cell_height)
            node_width = self.cell_width - 2
            node_height = self.cell_height

            # Check if click is within node bounds
            if (
                node_x <= x <= node_x + node_width + 1
                and node_y <= y <= node_y + node_height
            ):
                return task_id

        return None

    def action_scroll_up(self) -> None:
        """Scroll up."""
        self.scroll_up(animate=False)

    def action_scroll_down(self) -> None:
        """Scroll down."""
        self.scroll_down(animate=False)

    def action_scroll_left(self) -> None:
        """Scroll left."""
        self.scroll_left(animate=False)

    def action_scroll_right(self) -> None:
        """Scroll right."""
        self.scroll_right(animate=False)

    def action_scroll_home(self) -> None:
        """Scroll to top."""
        self.scroll_home(animate=False)

    def action_scroll_end(self) -> None:
        """Scroll to bottom."""
        self.scroll_end(animate=False)


class DAGStatsBar(Static):
    """Statistics bar showing DAG metrics."""

    def __init__(self, dag: DAGViewModel, id: Optional[str] = None):
        super().__init__(id=id)
        self.dag = dag

    def compose(self) -> ComposeResult:
        """Compose the stats bar."""
        stats_text = Text()

        # Basic stats
        stats_text.append(f"Nodes: {self.dag.total_nodes} ", style="bold cyan")
        stats_text.append(f"Edges: {self.dag.total_edges} ", style="bold yellow")
        stats_text.append(f"Depth: {self.dag.max_depth} ", style="bold magenta")

        # Critical path
        if self.dag.critical_path:
            stats_text.append(
                f"Critical Path: {len(self.dag.critical_path)} tasks ", style="bold red"
            )

        # Parallelism
        stats_text.append(
            f"Parallelism: {self.dag.parallelism_factor:.2f}x ", style="bold green"
        )

        # Blocked/Ready
        if self.dag.blocked_tasks:
            stats_text.append(
                f"Blocked: {len(self.dag.blocked_tasks)} ", style="bold magenta"
            )
        if self.dag.ready_tasks:
            stats_text.append(f"Ready: {len(self.dag.ready_tasks)} ", style="bold cyan")

        yield Static(stats_text)


class DAGFilterBar(Horizontal):
    """Filter bar for toggling edge types."""

    def __init__(
        self,
        enabled_edges: Set[EdgeType],
        on_toggle: callable,
        id: Optional[str] = None,
    ):
        super().__init__(id=id)
        self.enabled_edges = enabled_edges
        self.on_toggle = on_toggle

    def compose(self) -> ComposeResult:
        """Compose the filter bar."""
        filter_text = Text()
        filter_text.append("Filters: ", style="bold")

        for edge_type in [
            EdgeType.DEPENDENCY,
            EdgeType.DATA_FLOW,
            EdgeType.CONTROL_FLOW,
            EdgeType.PARENT_CHILD,
        ]:
            enabled = edge_type in self.enabled_edges
            symbol = "[✓]" if enabled else "[ ]"
            style = "green" if enabled else "dim"
            filter_text.append(f"{symbol} {edge_type.description}  ", style=style)

        yield Static(filter_text)


class DAGMinimap(Static):
    """Minimap showing overview of entire DAG with viewport indicator."""

    def __init__(
        self,
        dag: DAGViewModel,
        positions: Dict[str, Position],
        id: Optional[str] = None,
    ):
        super().__init__(id=id)
        self.dag = dag
        self.positions = positions

    def compose(self) -> ComposeResult:
        """Compose the minimap."""
        if not self.positions:
            yield Static("No layout", id="minimap-content")
            return

        # Calculate bounding box
        min_x = min(pos.x for pos in self.positions.values())
        max_x = max(pos.x for pos in self.positions.values())
        min_y = min(pos.y for pos in self.positions.values())
        max_y = max(pos.y for pos in self.positions.values())

        width = max_x - min_x + 1
        height = max_y - min_y + 1

        # Minimap dimensions (scaled down)
        minimap_width = min(40, int(width * 2))
        minimap_height = min(10, int(height * 0.5))

        # Create simple minimap representation
        minimap_text = Text()
        minimap_text.append("Minimap: ", style="bold")
        minimap_text.append(f"{self.dag.total_nodes} nodes ", style="cyan")
        minimap_text.append(f"({minimap_width}x{minimap_height})", style="dim")

        # Simple grid representation
        grid = [[" " for _ in range(minimap_width)] for _ in range(minimap_height)]

        # Scale positions to minimap
        for task_id, pos in self.positions.items():
            # Normalize position
            norm_x = (pos.x - min_x) / width if width > 0 else 0
            norm_y = (pos.y - min_y) / height if height > 0 else 0

            # Scale to minimap
            map_x = int(norm_x * (minimap_width - 1))
            map_y = int(norm_y * (minimap_height - 1))

            # Clamp to bounds
            map_x = max(0, min(map_x, minimap_width - 1))
            map_y = max(0, min(map_y, minimap_height - 1))

            # Get task status indicator
            task = self.dag.nodes.get(task_id)
            if task:
                if task.status in ("completed", "done"):
                    grid[map_y][map_x] = "●"
                elif task.status in ("running", "in_progress"):
                    grid[map_y][map_x] = "◐"
                elif task.status in ("failed", "error"):
                    grid[map_y][map_x] = "✗"
                else:
                    grid[map_y][map_x] = "○"

        # Render grid
        minimap_text.append("\n")
        for row in grid:
            minimap_text.append("".join(row))
            minimap_text.append("\n")

        yield Static(minimap_text, id="minimap-content")


class DAGModal(ModalScreen):
    """
    Full-screen modal for DAG visualization.

    Shows hierarchical graph of task dependencies with:
    - Interactive node and edge display
    - Edge type filtering
    - Keyboard navigation
    - Critical path highlighting
    - Status visualization
    """

    BINDINGS = [
        Binding("g,escape,q", "close", "Close", show=True, priority=True),
        Binding("1", "toggle_dependencies", "Dependencies", show=True),
        Binding("2", "toggle_data_flow", "Data Flow", show=True),
        Binding("3", "toggle_control_flow", "Control Flow", show=True),
        Binding("4", "toggle_hierarchy", "Hierarchy", show=True),
        Binding("c", "highlight_critical_path", "Critical Path", show=True),
        Binding("b", "highlight_blocked", "Blocked Tasks", show=True),
        Binding("p", "highlight_parallel", "Parallel Clusters", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("+,=", "zoom_in", "Zoom In", show=False),
        Binding("-,_", "zoom_out", "Zoom Out", show=False),
    ]

    CSS = """
    DAGModal {
        align: center middle;
    }

    #dag-container {
        width: 100%;
        height: 100%;
        background: $surface;
        border: tall $primary;
    }

    #dag-header {
        height: 3;
        dock: top;
        background: $primary;
        color: $text;
        padding: 1;
    }

    #dag-stats {
        height: 2;
        dock: top;
        background: $surface-darken-1;
        padding: 0 1;
    }

    #dag-filters {
        height: 2;
        dock: top;
        background: $surface-darken-2;
        padding: 0 1;
    }

    #dag-canvas {
        height: 1fr;
        background: $surface;
    }

    #dag-legend {
        height: 4;
        dock: bottom;
        background: $surface-darken-1;
        padding: 1;
    }

    #dag-footer {
        height: 1;
        dock: bottom;
    }
    """

    def __init__(
        self,
        dag: DAGViewModel,
        name: Optional[str] = None,
        id: Optional[str] = None,
        classes: Optional[str] = None,
    ):
        super().__init__(name=name, id=id, classes=classes)
        self.dag = dag
        self.positions: Dict[str, Position] = {}
        self.enabled_edges: Set[EdgeType] = {
            EdgeType.DEPENDENCY,
            EdgeType.DATA_FLOW,
            EdgeType.CONTROL_FLOW,
        }
        self.layout_algorithm = "hierarchical"
        self.cell_width = 20
        self.cell_height = 4
        self.collapsed_nodes: Set[str] = set()  # Set of collapsed planning node IDs

        # Advanced filters
        self.status_filter: Optional[Set[str]] = None  # None = show all
        self.module_filter: Optional[Set[str]] = None  # None = show all
        self.depth_filter: Optional[int] = None  # None = show all depths
        self.show_only_critical_path: bool = False
        self.show_only_blocked: bool = False
        self.show_only_ready: bool = False

        # Replay state
        self.replay_mode: bool = False
        self.replay_time: float = 0.0  # Current replay timestamp
        self.replay_min_time: float = 0.0
        self.replay_max_time: float = 0.0
        self.replay_speed: float = 1.0  # Playback speed multiplier
        self._compute_replay_timeline()

    def compose(self) -> ComposeResult:
        """Compose the modal."""
        # Compute initial layout
        self._compute_layout()

        with Container(id="dag-container"):
            # Header
            yield Static(
                f"DAG View - {self.dag.execution_id[:8]}... ({self.dag.total_nodes} nodes)",
                id="dag-header",
            )

            # Stats bar
            yield DAGStatsBar(self.dag, id="dag-stats")

            # Filter bar
            yield DAGFilterBar(
                self.enabled_edges, self._on_filter_toggle, id="dag-filters"
            )

            # Canvas with node click handler
            yield DAGCanvas(
                self.dag,
                self.positions,
                cell_width=self.cell_width,
                cell_height=self.cell_height,
                on_node_click=self._on_node_click,
                id="dag-canvas",
            )

            # Legend
            yield DAGLegend(id="dag-legend")

            # Footer with keybindings
            yield Footer(id="dag-footer")

    def _on_node_click(self, task_id: str) -> None:
        """Handle node click event."""
        logger.info(f"Task selected from DAG: {task_id}")

        # Dismiss modal and return selected task ID
        self.dismiss(task_id)

    def _compute_layout(self) -> None:
        """Compute DAG layout."""
        logger.debug(f"Computing {self.layout_algorithm} layout")

        # Filter DAG by enabled edge types
        filtered_dag = self._filter_dag_by_edges()

        # Compute layout
        self.positions = compute_layout(
            filtered_dag, algorithm=self.layout_algorithm, spacing_x=1.5, spacing_y=1.0
        )

        logger.debug(f"Layout computed: {len(self.positions)} nodes positioned")

    def _filter_dag_by_edges(self) -> DAGViewModel:
        """Create filtered copy of DAG with enabled edge types and advanced filters."""
        from copy import deepcopy

        # Apply advanced node filters
        filtered_nodes = self._apply_node_filters(self.dag.nodes)

        # Filter edges to only include edges between remaining nodes
        filtered_node_ids = set(filtered_nodes.keys())
        filtered_edges = [
            edge for edge in self.dag.edges
            if edge.edge_type in self.enabled_edges
            and edge.from_task_id in filtered_node_ids
            and edge.to_task_id in filtered_node_ids
        ]

        # Recompute metrics for filtered DAG
        filtered_critical_path = [
            task_id for task_id in self.dag.critical_path
            if task_id in filtered_node_ids
        ]

        filtered_parallel_clusters = [
            [task_id for task_id in cluster if task_id in filtered_node_ids]
            for cluster in self.dag.parallel_clusters
        ]
        # Remove empty clusters
        filtered_parallel_clusters = [c for c in filtered_parallel_clusters if c]

        filtered_blocked = [
            task_id for task_id in self.dag.blocked_tasks
            if task_id in filtered_node_ids
        ]

        filtered_ready = [
            task_id for task_id in self.dag.ready_tasks
            if task_id in filtered_node_ids
        ]

        filtered_dag = DAGViewModel(
            nodes=filtered_nodes,
            edges=filtered_edges,
            critical_path=filtered_critical_path,
            parallel_clusters=filtered_parallel_clusters,
            blocked_tasks=filtered_blocked,
            ready_tasks=filtered_ready,
            subgraphs=self.dag.subgraphs,
            dag_id=self.dag.dag_id,
            execution_id=self.dag.execution_id,
            total_nodes=len(filtered_nodes),
            total_edges=len(filtered_edges),
            max_depth=max((task.depth for task in filtered_nodes.values()), default=0),
            parallelism_factor=(
                len(filtered_nodes) / len(filtered_critical_path)
                if filtered_critical_path else 1.0
            ),
        )

        return filtered_dag

    def _apply_node_filters(self, nodes: Dict[str, TaskViewModel]) -> Dict[str, TaskViewModel]:
        """Apply advanced filters to nodes."""
        filtered = nodes.copy()

        # Filter by status
        if self.status_filter:
            filtered = {
                task_id: task for task_id, task in filtered.items()
                if task.status in self.status_filter
            }

        # Filter by module
        if self.module_filter:
            filtered = {
                task_id: task for task_id, task in filtered.items()
                if task.module in self.module_filter
            }

        # Filter by depth
        if self.depth_filter is not None:
            filtered = {
                task_id: task for task_id, task in filtered.items()
                if task.depth == self.depth_filter
            }

        # Show only critical path
        if self.show_only_critical_path:
            critical_path_set = set(self.dag.critical_path)
            filtered = {
                task_id: task for task_id, task in filtered.items()
                if task_id in critical_path_set
            }

        # Show only blocked tasks
        if self.show_only_blocked:
            blocked_set = set(self.dag.blocked_tasks)
            filtered = {
                task_id: task for task_id, task in filtered.items()
                if task_id in blocked_set
            }

        # Show only ready tasks
        if self.show_only_ready:
            ready_set = set(self.dag.ready_tasks)
            filtered = {
                task_id: task for task_id, task in filtered.items()
                if task_id in ready_set
            }

        return filtered

    def _on_filter_toggle(self, edge_type: EdgeType) -> None:
        """Toggle edge type filter."""
        if edge_type in self.enabled_edges:
            self.enabled_edges.remove(edge_type)
        else:
            self.enabled_edges.add(edge_type)

        self.refresh_layout()

    def action_close(self) -> None:
        """Close the modal."""
        self.dismiss()

    def action_toggle_dependencies(self) -> None:
        """Toggle dependency edges."""
        self._on_filter_toggle(EdgeType.DEPENDENCY)

    def action_toggle_data_flow(self) -> None:
        """Toggle data flow edges."""
        self._on_filter_toggle(EdgeType.DATA_FLOW)

    def action_toggle_control_flow(self) -> None:
        """Toggle control flow edges."""
        self._on_filter_toggle(EdgeType.CONTROL_FLOW)

    def action_toggle_hierarchy(self) -> None:
        """Toggle hierarchy edges."""
        self._on_filter_toggle(EdgeType.PARENT_CHILD)

    def action_highlight_critical_path(self) -> None:
        """Toggle critical path filter."""
        self.show_only_critical_path = not self.show_only_critical_path

        # Reset other exclusive filters
        if self.show_only_critical_path:
            self.show_only_blocked = False
            self.show_only_ready = False

        logger.info(f"Critical path filter: {'ON' if self.show_only_critical_path else 'OFF'}")
        self.refresh_layout()
        self.notify(
            f"Critical path filter: {'ON' if self.show_only_critical_path else 'OFF'} "
            f"({len(self.dag.critical_path)} tasks)",
            title="Critical Path Filter",
            severity="information",
        )

    def action_highlight_blocked(self) -> None:
        """Toggle blocked tasks filter."""
        self.show_only_blocked = not self.show_only_blocked

        # Reset other exclusive filters
        if self.show_only_blocked:
            self.show_only_critical_path = False
            self.show_only_ready = False

        logger.info(f"Blocked tasks filter: {'ON' if self.show_only_blocked else 'OFF'}")
        self.refresh_layout()
        self.notify(
            f"Blocked tasks filter: {'ON' if self.show_only_blocked else 'OFF'} "
            f"({len(self.dag.blocked_tasks)} tasks)",
            title="Blocked Tasks Filter",
            severity="warning" if self.show_only_blocked and self.dag.blocked_tasks else "information",
        )

    def action_highlight_parallel(self) -> None:
        """Highlight parallel clusters."""
        # TODO: Implement parallel cluster highlighting
        logger.info(f"Parallel clusters: {len(self.dag.parallel_clusters)}")
        self.notify(
            f"Parallel clusters: {len(self.dag.parallel_clusters)}",
            title="Parallel Execution",
            severity="information",
        )

    def action_refresh(self) -> None:
        """Refresh the layout."""
        self.refresh_layout()

    def action_zoom_in(self) -> None:
        """Zoom in (increase cell size)."""
        self.cell_width = min(self.cell_width + 2, 40)
        self.cell_height = min(self.cell_height + 1, 8)
        self.refresh_layout()
        self.notify(f"Zoom: {self.cell_width}x{self.cell_height}", severity="information")

    def action_zoom_out(self) -> None:
        """Zoom out (decrease cell size)."""
        self.cell_width = max(self.cell_width - 2, 10)
        self.cell_height = max(self.cell_height - 1, 2)
        self.refresh_layout()
        self.notify(f"Zoom: {self.cell_width}x{self.cell_height}", severity="information")

    def refresh_layout(self) -> None:
        """Refresh the layout and re-render."""
        self._compute_layout()

        # Update canvas
        canvas = self.query_one("#dag-canvas", DAGCanvas)
        canvas.dag = self._filter_dag_by_edges()
        canvas.positions = self.positions
        canvas._rendered_text = render_dag_rich(
            canvas.dag,
            self.positions,
            cell_width=self.cell_width,
            cell_height=self.cell_height,
            show_metrics=True,
        )

        # Update filter bar
        filter_bar = self.query_one("#dag-filters", DAGFilterBar)
        filter_bar.enabled_edges = self.enabled_edges

        # Trigger re-render
        canvas.refresh()
        filter_bar.refresh()

    def _compute_replay_timeline(self) -> None:
        """Compute timeline bounds for replay mode from task traces."""
        if not self.dag.nodes:
            return

        # Find earliest start and latest end time from all tasks
        min_time = float('inf')
        max_time = float('-inf')

        for task in self.dag.nodes.values():
            if not task.traces:
                continue

            for trace in task.traces:
                if trace.start_ts is not None:
                    min_time = min(min_time, trace.start_ts)
                    if trace.duration > 0:
                        end_time = trace.start_ts + trace.duration
                        max_time = max(max_time, end_time)

        # Set timeline bounds
        if min_time != float('inf') and max_time != float('-inf'):
            self.replay_min_time = min_time
            self.replay_max_time = max_time
            self.replay_time = min_time
            logger.debug(
                f"Computed replay timeline: {min_time:.2f}s to {max_time:.2f}s "
                f"(duration: {max_time - min_time:.2f}s)"
            )
        else:
            logger.warning("No valid timestamps found in traces for replay")
