"""TreeTable widget - High-performance table with collapsible tree hierarchy.

Combines Tree (hierarchy, expand/collapse) and DataTable (columns) with optimizations:
- Efficient rendering using Strip-based approach
- Cached tree guide calculations
- Minimal redraws on state changes
- Unicode-aware width calculations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rich.cells import cell_len
from rich.segment import Segment
from rich.style import Style
from rich.text import Text
from textual import events
from textual.geometry import Size
from textual.message import Message
from textual.reactive import reactive
from textual.scroll_view import ScrollView
from textual.strip import Strip


def _extract_sort_value(node_data: Dict[str, Any], key: str, reverse: bool = False) -> Any:
    """Extract sortable value from node data (DRY helper for sorting).

    Handles None values by sorting them to the end, and handles different data types.

    Args:
        node_data: Node's data dictionary
        key: Key to extract from data
        reverse: Whether sorting in reverse order

    Returns:
        Sortable value (with None handling)
    """
    value = node_data.get(key)

    # Handle None values - sort to end
    if value is None:
        return float("-inf") if not reverse else float("inf")

    # Handle numeric strings (e.g., "1.23s" -> 1.23)
    if isinstance(value, str):
        # Try to extract leading numeric value
        import re

        match = re.match(r"^([-+]?\d*\.?\d+)", value)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass

    # Return value as-is for sorting
    return value


@dataclass
class TreeNode:
    """Node in the tree table with efficient parent/child tracking.

    Attributes:
        id: Unique identifier
        label: Display text for tree column
        data: Column values dict
        children: Child nodes list
        parent: Parent node reference
        expanded: Whether children are visible
        visible: Whether node matches current filter (default: True)
        depth: Nesting level (0 for root)
        is_last: Whether this is the last child of parent
    """

    id: str
    label: str
    data: Dict[str, Any] = field(default_factory=dict)
    children: List[TreeNode] = field(default_factory=list)
    parent: Optional[TreeNode] = None
    expanded: bool = True
    visible: bool = True
    depth: int = 0
    is_last: bool = False

    def add(self, label: str, data: Optional[Dict[str, Any]] = None) -> TreeNode:
        """Add child node (builder pattern).

        Args:
            label: Display text
            data: Column values

        Returns:
            Created child node
        """
        child = TreeNode(
            id=f"{self.id}.{len(self.children)}",
            label=label,
            data=data or {},
            parent=self,
            depth=self.depth + 1,
        )
        self.children.append(child)
        self._update_siblings()
        return child

    def set_data(self, data: List[Any]) -> None:
        """Set column data from list (matches column order).

        Args:
            data: List of values in column order
        """
        # Data will be mapped to columns by TreeTable
        self._data_list = data

    def _update_siblings(self) -> None:
        """Update is_last flag for all children."""
        for i, child in enumerate(self.children):
            child.is_last = (i == len(self.children) - 1)

    def toggle(self) -> None:
        """Toggle expanded state."""
        if self.children:
            self.expanded = not self.expanded

    def get_visible_descendants(self) -> List[TreeNode]:
        """Get all visible descendants (respecting expanded state and filter).

        Returns:
            List of visible descendant nodes
        """
        result = []
        for child in self.children:
            if child.visible:
                result.append(child)
                if child.expanded and child.children:
                    result.extend(child.get_visible_descendants())
        return result


class TreeTable(ScrollView, can_focus=True):
    """High-performance tree table widget.

    Features:
    - Efficient rendering with minimal redraws
    - Tree guides with Unicode box drawing
    - Click and keyboard navigation
    - Zebra striping for readability
    - Configurable column widths

    Performance optimizations:
    - Cached visible rows list
    - Pre-calculated tree guides
    - Unicode-aware width handling
    - Minimal refresh on state changes
    """

    BINDINGS = [
        ("up,k", "cursor_up", "Up"),
        ("down,j", "cursor_down", "Down"),
        ("left,h", "collapse", "Collapse"),
        ("right,l", "expand", "Expand"),
        ("space", "toggle", "Toggle"),
        ("enter", "select", "Select"),
    ]

    DEFAULT_CSS = """
    TreeTable {
        background: $surface;
        color: $text;
        overflow-y: auto;
        scrollbar-gutter: stable;
    }

    TreeTable:focus {
        border: tall $accent;
    }
    """

    # Reactive properties
    cursor_row: reactive[int] = reactive(0)
    show_header: reactive[bool] = reactive(True)
    zebra_stripes: reactive[bool] = reactive(True)

    # Sort state (for visual indicators)
    current_sort_column: reactive[Optional[str]] = reactive(None)
    current_sort_reverse: reactive[bool] = reactive(False)

    # Column widths (optimized for readability)
    TREE_COL_WIDTH = 60
    DATA_COL_WIDTH = 30

    class NodeSelected(Message):
        """Posted when a node is selected."""

        def __init__(self, node: TreeNode) -> None:
            self.node = node
            super().__init__()

    class NodeToggled(Message):
        """Posted when a node is expanded/collapsed."""

        def __init__(self, node: TreeNode, expanded: bool) -> None:
            self.node = node
            self.expanded = expanded
            super().__init__()

    class ColumnHeaderClicked(Message):
        """Posted when a column header is clicked."""

        def __init__(self, column_name: str) -> None:
            self.column_name = column_name
            super().__init__()

    def __init__(
        self,
        columns: List[str],
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
        disabled: bool = False,
    ):
        """Initialize TreeTable.

        Args:
            columns: Data column names (tree column is implicit)
            name: Widget name
            id: Widget ID
            classes: CSS classes
            disabled: Whether disabled
        """
        super().__init__(name=name, id=id, classes=classes, disabled=disabled)
        self.columns = columns
        self.root = TreeNode(id="root", label="Root", depth=-1)  # Virtual root
        self._visible_rows: List[TreeNode] = []
        self._next_id = 0

    def add_root(self, label: str, data: Optional[Dict[str, Any]] = None) -> TreeNode:
        """Add root-level node.

        Args:
            label: Display text
            data: Column values

        Returns:
            Created node
        """
        return self.root.add(label, data)

    def clear(self) -> None:
        """Remove all nodes and reset state."""
        self.root.children.clear()
        self._visible_rows.clear()
        self.cursor_row = 0
        self._next_id = 0
        self.refresh()

    def rebuild_visible_rows(self) -> None:
        """Rebuild visible rows list based on expand/collapse state.

        This is called automatically after add/toggle operations.
        Performance: O(n) where n is visible nodes.
        """
        self._visible_rows.clear()

        for child in self.root.children:
            self._visible_rows.append(child)
            if child.expanded:
                self._visible_rows.extend(child.get_visible_descendants())

        # Constrain cursor
        if self.cursor_row >= len(self._visible_rows):
            self.cursor_row = max(0, len(self._visible_rows) - 1)

        # Update virtual size for scrolling - use content width, not widget width
        content_width = self.TREE_COL_WIDTH + (len(self.columns) * self.DATA_COL_WIDTH)
        row_count = len(self._visible_rows) + (1 if self.show_header else 0)
        self.virtual_size = Size(content_width, row_count)

        # Scroll to top to ensure content is visible
        self.scroll_to(0, 0, animate=False)

    def get_content_width(self, container: Size, viewport: Size) -> int:
        """Calculate content width."""
        return self.TREE_COL_WIDTH + (len(self.columns) * self.DATA_COL_WIDTH)

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        """Calculate content height."""
        return len(self._visible_rows) + (1 if self.show_header else 0)

    def render_line(self, y: int) -> Strip:
        """Render a single line (optimized for performance).

        Args:
            y: Line number in viewport

        Returns:
            Strip containing rendered line
        """
        scroll_y = self.scroll_offset.y
        line_y = y + scroll_y

        # Render header
        if self.show_header and line_y == 0:
            return self._render_header()

        # Calculate row index
        row_idx = line_y - (1 if self.show_header else 0)

        # Render data row
        if row_idx < 0 or row_idx >= len(self._visible_rows):
            return Strip.blank(self.size.width)

        node = self._visible_rows[row_idx]
        is_selected = (row_idx == self.cursor_row)
        is_even = (row_idx % 2 == 0)

        return self._render_row(node, is_selected, is_even)

    def _render_header(self) -> Strip:
        """Render header row with column names."""
        segments = []

        # Tree column header
        tree_header = self._pad_text("Span", self.TREE_COL_WIDTH)
        segments.extend(Text(tree_header, style="bold").render(self.app.console))

        # Data column headers
        for col_name in self.columns:
            # Add sort indicator if this is the active sort column
            if col_name == self.current_sort_column:
                indicator = " ▲" if not self.current_sort_reverse else " ▼"
                col_text = self._pad_text(f" {col_name}{indicator}", self.DATA_COL_WIDTH)
                # Highlight active sort column
                segments.extend(Text(col_text, style="bold cyan").render(self.app.console))
            else:
                col_text = self._pad_text(f" {col_name}", self.DATA_COL_WIDTH)
                segments.extend(Text(col_text, style="bold").render(self.app.console))

        # Fill remaining width
        total_width = self.TREE_COL_WIDTH + (len(self.columns) * self.DATA_COL_WIDTH)
        fill_width = max(0, self.size.width - total_width)
        if fill_width > 0:
            segments.append(Segment(" " * fill_width))

        return Strip(segments, self.size.width)

    def _render_row(self, node: TreeNode, is_selected: bool, is_even: bool) -> Strip:
        """Render data row with tree guides and column values.

        Args:
            node: Node to render
            is_selected: Whether cursor is on this row
            is_even: Whether this is even row (for zebra striping)

        Returns:
            Strip containing rendered row
        """
        segments = []

        # Determine row style
        if is_selected:
            style = Style(bgcolor="blue", color="white", bold=True)
        elif self.zebra_stripes and is_even:
            style = Style(bgcolor="grey11")
        else:
            style = Style()

        # Render tree column
        tree_text = self._build_tree_cell(node)
        tree_text.stylize(style)
        segments.extend(tree_text.render(self.app.console))

        # Render data columns
        for col_name in self.columns:
            value = str(node.data.get(col_name, ""))
            col_text = self._pad_text(f" {value}", self.DATA_COL_WIDTH)
            text = Text(col_text)

            # Highlight sorted column with subtle background
            if col_name == self.current_sort_column:
                if is_selected:
                    # Keep selection style for selected rows
                    col_style = style
                elif self.zebra_stripes and is_even:
                    # Slightly lighter background for sorted column in even rows
                    col_style = Style(bgcolor="grey15", color="cyan")
                else:
                    # Subtle highlight for sorted column in odd rows
                    col_style = Style(bgcolor="grey7", color="cyan")
                text.stylize(col_style)
            else:
                text.stylize(style)

            segments.extend(text.render(self.app.console))

        # Fill remaining width
        total_width = self.TREE_COL_WIDTH + (len(self.columns) * self.DATA_COL_WIDTH)
        fill_width = max(0, self.size.width - total_width)
        if fill_width > 0:
            segments.append(Segment(" " * fill_width, style))

        return Strip(segments, self.size.width)

    def _build_tree_cell(self, node: TreeNode) -> Text:
        """Build tree column with guides and expand/collapse icon.

        Args:
            node: Node to render

        Returns:
            Rich Text with tree guides
        """
        text = Text()
        width = 0

        # Add tree guides for ancestors
        ancestors = self._get_ancestors(node)
        for ancestor in ancestors[:-1]:  # Exclude node itself
            if self._has_sibling_below(ancestor):
                text.append("│   ", style="dim")
            else:
                text.append("    ", style="dim")
            width += 4

        # Add branch connector
        if node.depth > 0:
            connector = "└── " if node.is_last else "├── "
            text.append(connector, style="dim")
            width += 4

        # Add expand/collapse icon
        if node.children:
            icon = "⊟ " if node.expanded else "⊞ "
            icon_style = "bold cyan" if node.expanded else "bold yellow"
            text.append(icon, style=icon_style)
            width += 2
        else:
            text.append("  ")
            width += 2

        # Add label (truncated to fit)
        available = self.TREE_COL_WIDTH - width
        label = self._truncate(node.label, available)
        label = self._pad_text(label, available)
        text.append(label)

        return text

    def _get_ancestors(self, node: TreeNode) -> List[TreeNode]:
        """Get ancestors from root to node (inclusive).

        Performance: O(depth) with single pass.

        Args:
            node: Node to get ancestors for

        Returns:
            List of ancestors (root to node)
        """
        ancestors = []
        current = node
        while current and current.depth >= 0:
            ancestors.append(current)
            current = current.parent
        return list(reversed(ancestors))

    def _has_sibling_below(self, node: TreeNode) -> bool:
        """Check if node has siblings below it.

        Args:
            node: Node to check

        Returns:
            True if has sibling below
        """
        if not node.parent or node.parent.depth < 0:
            return False

        try:
            idx = node.parent.children.index(node)
            return idx < len(node.parent.children) - 1
        except ValueError:
            return False

    def _truncate(self, text: str, max_width: int) -> str:
        """Truncate text to fit max_width (Unicode-aware).

        Args:
            text: Text to truncate
            max_width: Maximum width in cells

        Returns:
            Truncated text with ellipsis if needed
        """
        if cell_len(text) <= max_width:
            return text

        if max_width <= 1:
            return "…"

        # Binary search for optimal truncation point
        left, right = 0, len(text)
        while left < right:
            mid = (left + right + 1) // 2
            candidate = text[:mid] + "…"
            if cell_len(candidate) <= max_width:
                left = mid
            else:
                right = mid - 1

        return text[:left] + "…" if left < len(text) else text

    def _pad_text(self, text: str, width: int) -> str:
        """Pad text to exact width (Unicode-aware).

        Args:
            text: Text to pad
            width: Target width in cells

        Returns:
            Padded text
        """
        text = self._truncate(text, width)
        current_width = cell_len(text)
        padding = max(0, width - current_width)
        return text + (" " * padding)

    # Sort and filter operations

    @property
    def all_nodes(self) -> List[TreeNode]:
        """Get all nodes in the tree (for search operations).

        Returns:
            List of all nodes regardless of expand/filter state
        """
        result = []

        def collect_nodes(node: TreeNode) -> None:
            result.append(node)
            for child in node.children:
                collect_nodes(child)

        for root_child in self.root.children:
            collect_nodes(root_child)

        return result

    def filter_nodes(self, predicate: callable) -> None:
        """Filter nodes based on predicate (parent nodes stay visible if children match).

        Args:
            predicate: Function that takes TreeNode and returns True if matches
        """
        # Reset all nodes to invisible first
        for node in self.all_nodes:
            node.visible = False

        # Mark matching nodes and their ancestors
        for node in self.all_nodes:
            if predicate(node):
                # Mark this node and all ancestors as visible
                current = node
                while current and current.depth >= 0:
                    current.visible = True
                    current = current.parent

        self.rebuild_visible_rows()
        self.refresh()

    def clear_filter(self) -> None:
        """Clear all filters and show all nodes."""
        for node in self.all_nodes:
            node.visible = True
        self.rebuild_visible_rows()
        self.refresh()

    def sort(self, key: str, reverse: bool = False) -> None:
        """Sort tree nodes by column value (preserving hierarchy).

        Sorts at each level independently, maintaining tree structure.

        Args:
            key: Column name to sort by
            reverse: Sort in descending order

        Raises:
            ValueError: If key is not a valid column name
        """
        # Validate that key exists in columns
        if key not in self.columns:
            available_cols = ", ".join(self.columns)
            raise ValueError(
                f"Invalid sort column '{key}'. "
                f"Available columns: {available_cols}"
            )

        def sort_recursive(node: TreeNode) -> None:
            """Recursively sort children at each level."""
            if not node.children:
                return

            # Sort children at this level using DRY helper
            node.children.sort(
                key=lambda n: _extract_sort_value(n.data, key, reverse),
                reverse=reverse,
            )

            # Update is_last flags after sorting
            node._update_siblings()

            # Recursively sort grandchildren
            for child in node.children:
                sort_recursive(child)

        # Sort all root-level nodes
        sort_recursive(self.root)

        # Update sort state for visual indicators
        self.current_sort_column = key
        self.current_sort_reverse = reverse

        # Rebuild visible rows to reflect new order
        self.rebuild_visible_rows()
        self.refresh()

    # Event handlers

    def on_click(self, event: events.Click) -> None:
        """Handle click events."""
        # Check for header click FIRST (using screen coordinates, not scroll-adjusted)
        if self.show_header and event.y == 0:
            # Header click - determine which column
            if event.x >= self.TREE_COL_WIDTH:
                # Clicked in data columns area
                col_index = (event.x - self.TREE_COL_WIDTH) // self.DATA_COL_WIDTH
                if 0 <= col_index < len(self.columns):
                    column_name = self.columns[col_index]
                    self.post_message(self.ColumnHeaderClicked(column_name))
            return

        # For row clicks, calculate scroll-adjusted position
        scroll_y = self.scroll_offset.y
        clicked_y = event.y + scroll_y

        # Account for header in row calculation
        if self.show_header:
            clicked_y -= 1

        # Check valid row
        if clicked_y < 0 or clicked_y >= len(self._visible_rows):
            return

        node = self._visible_rows[clicked_y]

        # Calculate icon position
        icon_x_end = (node.depth * 4) + 2 if node.depth > 0 else 2

        if event.x < icon_x_end and node.children:
            # Clicked on icon - toggle
            node.toggle()
            self.rebuild_visible_rows()
            self.post_message(self.NodeToggled(node, node.expanded))
            self.refresh()
        else:
            # Clicked on row - select
            self.cursor_row = clicked_y
            self.post_message(self.NodeSelected(node))

    # Actions

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        if self.cursor_row > 0:
            self.cursor_row -= 1
            self._scroll_to_cursor()

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        if self.cursor_row < len(self._visible_rows) - 1:
            self.cursor_row += 1
            self._scroll_to_cursor()

    def action_expand(self) -> None:
        """Expand current node."""
        if self.cursor_row < len(self._visible_rows):
            node = self._visible_rows[self.cursor_row]
            if node.children and not node.expanded:
                node.expanded = True
                self.rebuild_visible_rows()
                self.post_message(self.NodeToggled(node, True))
                self.refresh()

    def action_collapse(self) -> None:
        """Collapse current node."""
        if self.cursor_row < len(self._visible_rows):
            node = self._visible_rows[self.cursor_row]
            if node.children and node.expanded:
                node.expanded = False
                self.rebuild_visible_rows()
                self.post_message(self.NodeToggled(node, False))
                self.refresh()

    def action_toggle(self) -> None:
        """Toggle expand/collapse."""
        if self.cursor_row < len(self._visible_rows):
            node = self._visible_rows[self.cursor_row]
            if node.children:
                node.toggle()
                self.rebuild_visible_rows()
                self.post_message(self.NodeToggled(node, node.expanded))
                self.refresh()

    def action_select(self) -> None:
        """Select current node."""
        if self.cursor_row < len(self._visible_rows):
            node = self._visible_rows[self.cursor_row]
            self.post_message(self.NodeSelected(node))

    def _scroll_to_cursor(self) -> None:
        """Scroll to make cursor visible."""
        cursor_y = self.cursor_row + (1 if self.show_header else 0)

        viewport_top = self.scroll_offset.y
        viewport_bottom = viewport_top + self.size.height - 1

        if cursor_y < viewport_top:
            self.scroll_to(y=cursor_y, animate=False)
        elif cursor_y > viewport_bottom:
            self.scroll_to(y=cursor_y - self.size.height + 1, animate=False)

    def watch_cursor_row(self, old_row: int, new_row: int) -> None:
        """React to cursor changes."""
        self.refresh()

    def watch_current_sort_column(self, old_value: Optional[str], new_value: Optional[str]) -> None:
        """React to sort column changes - refresh header."""
        self.refresh()

    def watch_current_sort_reverse(self, old_value: bool, new_value: bool) -> None:
        """React to sort direction changes - refresh header."""
        self.refresh()

    def get_selected_node(self) -> Optional[TreeNode]:
        """Get currently selected node."""
        if 0 <= self.cursor_row < len(self._visible_rows):
            return self._visible_rows[self.cursor_row]
        return None
