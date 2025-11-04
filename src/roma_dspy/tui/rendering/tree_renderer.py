"""Tree rendering for TUI.

Handles task tree and span tree rendering.
"""

from __future__ import annotations

from typing import List

from loguru import logger
from textual.widgets import Tree

from roma_dspy.tui.models import ExecutionViewModel, TaskViewModel, TraceViewModel
from roma_dspy.tui.rendering.formatters import Formatters
from roma_dspy.tui.utils.helpers import ToolExtractor


class TreeRenderer:
    """Tree rendering utilities."""

    def __init__(self) -> None:
        """Initialize tree renderer."""
        self.formatters = Formatters()
        self.tool_extractor = ToolExtractor()

    def render_task_tree(
        self,
        tree_widget: Tree,
        execution: ExecutionViewModel
    ) -> None:
        """Render task hierarchy tree.

        Args:
            tree_widget: Textual Tree widget
            execution: Execution data
        """
        # Clear existing tree
        tree_widget.clear()
        tree_widget.root.expand()

        # Set root label
        root_label = f"Execution {execution.execution_id[:8]}"
        if execution.root_goal:
            root_label += f": {execution.root_goal[:50]}"
        tree_widget.root.set_label(root_label)

        # Build tree from root tasks
        for root_task_id in execution.root_task_ids:
            task = execution.tasks.get(root_task_id)
            if task:
                self._add_task_node(tree_widget.root, task, execution)

        logger.debug(f"Rendered task tree: {len(execution.root_task_ids)} root tasks")

    def _add_task_node(
        self,
        parent_node: Tree.TreeNode,
        task: TaskViewModel,
        execution: ExecutionViewModel
    ) -> Tree.TreeNode:
        """Add task node to tree recursively.

        Args:
            parent_node: Parent tree node
            task: Task to add
            execution: Execution data for child lookup

        Returns:
            Created tree node
        """
        # Build label
        label = self._build_task_label(task)

        # Create node
        node = parent_node.add(label, data={"task": task})
        node.expand()

        # Add children recursively
        for child_id in task.subtask_ids:
            child_task = execution.tasks.get(child_id)
            if child_task:
                self._add_task_node(node, child_task, execution)

        return node

    def _build_task_label(self, task: TaskViewModel) -> str:
        """Build task tree label with icons and metrics.

        Args:
            task: Task view model

        Returns:
            Formatted label string
        """
        # Status icon
        status_icon = self.formatters.format_status_icon(task.status)

        # Module tag
        module_tag = ""
        if task.module:
            module_tag = f"[{task.module}] "

        # Goal (truncated)
        goal = self.formatters.truncate(task.goal or "unknown", 60)

        # Metrics
        metrics = ""
        if task.total_duration > 0 or task.total_tokens > 0:
            metrics = self.formatters.format_metric_summary(
                task.total_duration,
                task.total_tokens,
                task.total_cost
            )

        # Error indicator
        error_icon = " ⚠️" if task.error else ""

        return f"{status_icon} {module_tag}{goal}{metrics}{error_icon}"

    def build_span_tree_nodes(
        self,
        spans: List[TraceViewModel]
    ) -> List[dict]:
        """Build hierarchical tree structure from flat span list.

        Args:
            spans: Flat list of traces

        Returns:
            List of root node dictionaries with nested children
        """
        if not spans:
            return []

        # Build parent-child map
        children_map = {}
        roots = []

        for span in spans:
            if span.parent_trace_id:
                if span.parent_trace_id not in children_map:
                    children_map[span.parent_trace_id] = []
                children_map[span.parent_trace_id].append(span)
            else:
                roots.append(span)

        # Sort roots and children by start time
        roots.sort(key=lambda s: s.start_ts or 0)
        for children in children_map.values():
            children.sort(key=lambda s: s.start_ts or 0)

        # Build tree recursively
        def build_node(span: TraceViewModel) -> dict:
            """Build node dict with children."""
            node = {
                "span": span,
                "label": self._build_span_label(span),
                "children": []
            }

            # Add children recursively
            if span.trace_id in children_map:
                for child_span in children_map[span.trace_id]:
                    node["children"].append(build_node(child_span))

            return node

        return [build_node(root) for root in roots]

    def _build_span_label(self, span: TraceViewModel) -> str:
        """Build span tree label with formatting.

        Args:
            span: Trace view model

        Returns:
            Formatted label with Rich markup
        """
        # Check if span has any failed tool calls
        error_icon = ""
        if span.tool_calls:
            has_errors = any(
                not self.tool_extractor.is_successful(tool_call)
                for tool_call in span.tool_calls
            )
            if has_errors:
                error_icon = "❌ "

        # Name (without module prefix)
        name = self.formatters.truncate(span.name or "unknown", 40)

        # Duration
        duration = ""
        if span.duration > 0:
            duration = f" ({self.formatters.format_duration(span.duration)})"

        # Model/tokens (for LM calls)
        details = ""
        if span.model:
            details = f" [{span.model}"
            if span.tokens > 0:
                details += f", {self.formatters.format_tokens(span.tokens)} tokens"
            details += "]"
        return f"{error_icon}{name}{duration}{details}"

    def _get_span_plain_name(self, span: TraceViewModel) -> str:
        """Get plain span name without formatting (for timeline labels).

        Args:
            span: Trace view model

        Returns:
            Plain text name without Rich markup
        """
        return span.name or "unknown"

    def render_timeline_graph(
        self,
        spans: List[TraceViewModel],
        max_bars: int = 50,
        max_depth: int | None = 1
    ) -> str:
        """Render ASCII timeline graph.

        Args:
            spans: List of traces
            max_bars: Maximum number of bars to show
            max_depth: Maximum depth of spans to show (None = all depths, 0 = root only, 1 = root + children, etc.)

        Returns:
            Formatted timeline string
        """
        if not spans:
            return "[dim](no timeline data)[/dim]"

        # Build parent map to determine depth and hierarchy
        parent_map = {s.trace_id: s.parent_trace_id for s in spans}
        children_map = {}
        for span in spans:
            if span.parent_trace_id:
                if span.parent_trace_id not in children_map:
                    children_map[span.parent_trace_id] = []
                children_map[span.parent_trace_id].append(span)

        def get_depth(span: TraceViewModel) -> int:
            """Calculate span depth in hierarchy."""
            depth = 0
            current_id = span.parent_trace_id
            while current_id and depth < 10:  # Safety limit
                depth += 1
                current_id = parent_map.get(current_id)
            return depth

        def get_tree_prefix(span: TraceViewModel, is_last_child: bool) -> str:
            """Get tree-style prefix for span (like ├─ or └─)."""
            depth = get_depth(span)
            if depth == 0:
                return ""
            elif is_last_child:
                return "  └─ "
            else:
                return "  ├─ "

        # Filter by depth (None = all depths)
        timeline_spans = [s for s in spans if max_depth is None or get_depth(s) <= max_depth]

        # Fallback to all spans if filter produces empty result
        if not timeline_spans:
            timeline_spans = spans

        # Filter and sort spans
        sorted_spans = sorted(timeline_spans, key=lambda s: s.start_ts or 0)

        # Truncate if too many
        was_truncated = len(sorted_spans) > max_bars
        if was_truncated:
            # Keep longest-running spans
            sorted_spans = sorted(sorted_spans, key=lambda s: s.duration, reverse=True)[:max_bars]
            # Re-sort by start time
            sorted_spans = sorted(sorted_spans, key=lambda s: s.start_ts or 0)

        # Calculate timeline bounds
        max_duration = max((s.duration for s in sorted_spans), default=1.0)

        lines = []
        label_width = 30
        graph_width = 60

        # Check if we have start times
        has_start = any(s.start_ts is not None for s in sorted_spans)

        if has_start:
            # Timeline with offsets
            starts = [s.start_ts for s in sorted_spans if s.start_ts is not None]
            earliest = min(starts) if starts else 0.0

            ends = []
            for span in sorted_spans:
                start = span.start_ts or earliest
                ends.append(start + span.duration)
            max_end = max(ends) if ends else earliest + max_duration

            total_span = max(max_end - earliest, max_duration)
            if total_span <= 0:
                total_span = max_duration or 1.0

            logger.debug(f"Timeline: earliest={earliest:.3f}, max_end={max_end:.3f}, total_span={total_span:.3f}")

            # Timeline header
            total_label = f"{total_span:.2f}s"
            spacer = max(0, graph_width - len(total_label) - 2)
            lines.append(" " * (label_width + 1) + f"[dim]0s{' ' * spacer}{total_label}[/dim]")

        # Shared function for building timeline label with tree prefix (DRY)
        def build_timeline_label(span: TraceViewModel, idx: int) -> str:
            """Build timeline label with tree prefix."""
            # Determine if this is the last child of its parent
            parent_id = span.parent_trace_id
            is_last = False
            if parent_id and parent_id in children_map:
                siblings = [s for s in children_map[parent_id] if s in sorted_spans]
                if siblings and span == siblings[-1]:
                    is_last = True

            # Add tree-style prefix
            tree_prefix = get_tree_prefix(span, is_last)
            plain_name = self._get_span_plain_name(span)

            # Build label with tree prefix, respecting max width
            max_name_width = label_width - len(tree_prefix) - 1
            truncated_name = plain_name[:max_name_width]
            return f"{tree_prefix}{truncated_name}"

        # Render bars (works for both timestamp and non-timestamp modes)
        if has_start:
            # Timeline with offsets
            for i, span in enumerate(sorted_spans):
                name = build_timeline_label(span, i)

                start = span.start_ts
                if start is None:
                    offset_cols = 0
                else:
                    offset_cols = int(((start - earliest) / total_span) * graph_width)

                offset_cols = max(0, min(offset_cols, graph_width - 1))

                width_cols = max(1, int((span.duration / total_span) * graph_width))
                if offset_cols + width_cols > graph_width:
                    width_cols = max(1, graph_width - offset_cols)

                logger.debug(f"  {name}: start_ts={start}, offset={offset_cols}, width={width_cols}, duration={span.duration:.3f}s")

                bar = (" " * offset_cols + "█" * width_cols).ljust(graph_width)
                lines.append(f"{name:<{label_width}} {bar} {span.duration:.2f}s")
        else:
            # Simple bars (no timestamps)
            for i, span in enumerate(sorted_spans):
                name = build_timeline_label(span, i)
                width_cols = max(1, int((span.duration / max_duration) * graph_width))
                bar = ("█" * width_cols).ljust(graph_width)
                lines.append(f"{name:<{label_width}} {bar} {span.duration:.2f}s")

            lines.append("[dim]Start timestamps unavailable; bars scaled by duration only.[/dim]")

        # Truncation note
        if was_truncated:
            lines.append(f"[dim]Showing top {max_bars} longest spans (out of {len(spans)} total)[/dim]")

        return "\n".join(lines)
