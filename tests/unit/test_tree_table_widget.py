"""Unit tests for TreeTable widget - NON-INTERACTIVE tests only."""

import pytest
from roma_dspy.tui.widgets import TreeTable, TreeTableNode


class TestTreeTableNode:
    """Test TreeTableNode data structure."""

    def test_node_creation(self):
        """Test basic node creation."""
        node = TreeTableNode(
            id="test-1", label="Test Node", data={"col1": "value1", "col2": "value2"}
        )
        assert node.id == "test-1"
        assert node.label == "Test Node"
        assert node.data == {"col1": "value1", "col2": "value2"}
        assert node.children == []
        assert node.parent is None
        assert node.expanded is True
        assert node.depth == 0
        assert node.is_last_sibling is False

    def test_add_child(self):
        """Test adding children to a node."""
        parent = TreeTableNode(id="parent", label="Parent", depth=0)
        child1 = TreeTableNode(id="child1", label="Child 1")
        child2 = TreeTableNode(id="child2", label="Child 2")

        parent.add_child(child1)
        parent.add_child(child2)

        assert len(parent.children) == 2
        assert child1.parent is parent
        assert child2.parent is parent
        assert child1.depth == 1
        assert child2.depth == 1
        assert child1.is_last_sibling is False
        assert child2.is_last_sibling is True

    def test_toggle_expanded(self):
        """Test expand/collapse toggle."""
        node = TreeTableNode(id="node", label="Node")
        child = TreeTableNode(id="child", label="Child")
        node.add_child(child)

        assert node.expanded is True
        node.toggle_expanded()
        assert node.expanded is False
        node.toggle_expanded()
        assert node.expanded is True

    def test_toggle_expanded_no_children(self):
        """Test toggle on leaf node (should do nothing)."""
        node = TreeTableNode(id="leaf", label="Leaf")
        assert node.expanded is True
        node.toggle_expanded()
        assert node.expanded is True  # No change

    def test_get_visible_descendants(self):
        """Test getting visible descendants."""
        root = TreeTableNode(id="root", label="Root")
        child1 = TreeTableNode(id="child1", label="Child 1")
        child2 = TreeTableNode(id="child2", label="Child 2")
        grandchild1 = TreeTableNode(id="gc1", label="GrandChild 1")

        root.add_child(child1)
        root.add_child(child2)
        child1.add_child(grandchild1)

        # All expanded
        descendants = root.get_visible_descendants()
        assert len(descendants) == 3
        assert descendants[0].id == "child1"
        assert descendants[1].id == "gc1"
        assert descendants[2].id == "child2"

        # Collapse child1
        child1.expanded = False
        descendants = root.get_visible_descendants()
        assert len(descendants) == 2
        assert descendants[0].id == "child1"
        assert descendants[1].id == "child2"

    def test_nested_depth(self):
        """Test depth calculation for deeply nested nodes."""
        root = TreeTableNode(id="root", label="Root", depth=0)
        level1 = TreeTableNode(id="l1", label="Level 1")
        level2 = TreeTableNode(id="l2", label="Level 2")
        level3 = TreeTableNode(id="l3", label="Level 3")

        root.add_child(level1)
        level1.add_child(level2)
        level2.add_child(level3)

        assert level1.depth == 1
        assert level2.depth == 2
        assert level3.depth == 3


class TestTreeTableStructure:
    """Test TreeTable widget structure and state management."""

    def test_tree_table_init(self):
        """Test TreeTable initialization."""
        columns = ["Duration", "Tokens", "Model"]
        table = TreeTable(columns=columns)

        assert table.columns == columns
        assert table.roots == []
        assert table._visible_rows == []
        assert table._row_to_node == {}
        assert table.cursor_row == 0

    def test_add_root(self):
        """Test adding root nodes."""
        table = TreeTable(columns=["col1", "col2"])

        root1 = table.add_root("Root 1", {"col1": "val1", "col2": "val2"})
        assert root1.label == "Root 1"
        assert root1.depth == 0
        assert len(table.roots) == 1
        assert root1.is_last_sibling is True

        root2 = table.add_root("Root 2", {"col1": "val3", "col2": "val4"})
        assert len(table.roots) == 2
        assert root1.is_last_sibling is False
        assert root2.is_last_sibling is True

    def test_clear(self):
        """Test clearing all data."""
        table = TreeTable(columns=["col1"])
        table.add_root("Root", {"col1": "val"})
        assert len(table.roots) == 1

        table.clear()
        assert len(table.roots) == 0
        assert len(table._visible_rows) == 0
        assert table.cursor_row == 0

    def test_rebuild_visible_rows_expanded(self):
        """Test visible rows when all nodes are expanded."""
        table = TreeTable(columns=["col1"])

        root = table.add_root("Root", {"col1": "val1"})
        child1 = root.add_child(
            TreeTableNode(id="c1", label="Child 1", data={"col1": "val2"})
        )
        child2 = root.add_child(
            TreeTableNode(id="c2", label="Child 2", data={"col1": "val3"})
        )
        grandchild = child1.add_child(
            TreeTableNode(id="gc", label="GrandChild", data={"col1": "val4"})
        )

        table.rebuild_visible_rows()

        # All expanded: root, child1, grandchild, child2
        assert len(table._visible_rows) == 4
        assert table._visible_rows[0].id == root.id
        assert table._visible_rows[1].id == "c1"
        assert table._visible_rows[2].id == "gc"
        assert table._visible_rows[3].id == "c2"

    def test_rebuild_visible_rows_collapsed(self):
        """Test visible rows when nodes are collapsed."""
        table = TreeTable(columns=["col1"])

        root = table.add_root("Root", {"col1": "val1"})
        child1 = root.add_child(
            TreeTableNode(id="c1", label="Child 1", data={"col1": "val2"})
        )
        child2 = root.add_child(
            TreeTableNode(id="c2", label="Child 2", data={"col1": "val3"})
        )
        child1.add_child(
            TreeTableNode(id="gc", label="GrandChild", data={"col1": "val4"})
        )

        # Collapse child1
        child1.expanded = False
        table.rebuild_visible_rows()

        # Only root, child1 (collapsed), child2 visible
        assert len(table._visible_rows) == 3
        assert table._visible_rows[0].id == root.id
        assert table._visible_rows[1].id == "c1"
        assert table._visible_rows[2].id == "c2"

    def test_rebuild_visible_rows_multiple_roots(self):
        """Test visible rows with multiple root nodes."""
        table = TreeTable(columns=["col1"])

        root1 = table.add_root("Root 1", {"col1": "val1"})
        root1.add_child(
            TreeTableNode(id="c1", label="Child of Root1", data={"col1": "val2"})
        )

        root2 = table.add_root("Root 2", {"col1": "val3"})
        root2.add_child(
            TreeTableNode(id="c2", label="Child of Root2", data={"col1": "val4"})
        )

        table.rebuild_visible_rows()

        # root1, child1, root2, child2
        assert len(table._visible_rows) == 4
        assert table._visible_rows[0].label == "Root 1"
        assert table._visible_rows[1].id == "c1"
        assert table._visible_rows[2].label == "Root 2"
        assert table._visible_rows[3].id == "c2"

    def test_row_to_node_mapping(self):
        """Test row index to node mapping."""
        table = TreeTable(columns=["col1"])

        root = table.add_root("Root", {"col1": "val1"})
        child = root.add_child(
            TreeTableNode(id="c1", label="Child", data={"col1": "val2"})
        )

        table.rebuild_visible_rows()

        assert table._row_to_node[0] == root
        assert table._row_to_node[1] == child

    def test_cursor_constraint_on_rebuild(self):
        """Test cursor is constrained when visible rows change."""
        table = TreeTable(columns=["col1"])

        root = table.add_root("Root", {"col1": "val1"})
        child1 = root.add_child(
            TreeTableNode(id="c1", label="Child 1", data={"col1": "val2"})
        )
        child2 = root.add_child(
            TreeTableNode(id="c2", label="Child 2", data={"col1": "val3"})
        )

        table.rebuild_visible_rows()
        table.cursor_row = 2  # On child2

        # Collapse root - only root visible now
        root.expanded = False
        table.rebuild_visible_rows()

        # Cursor should be constrained to last valid row (0)
        assert table.cursor_row == 0


class TestTreeTableNavigation:
    """Test navigation actions (without actually rendering)."""

    def test_get_selected_node(self):
        """Test getting the selected node."""
        table = TreeTable(columns=["col1"])

        root = table.add_root("Root", {"col1": "val1"})
        child = root.add_child(
            TreeTableNode(id="c1", label="Child", data={"col1": "val2"})
        )

        table.rebuild_visible_rows()

        table.cursor_row = 0
        selected = table.get_selected_node()
        assert selected == root

        table.cursor_row = 1
        selected = table.get_selected_node()
        assert selected == child

    def test_get_selected_node_invalid(self):
        """Test getting selected node with invalid cursor."""
        table = TreeTable(columns=["col1"])
        table.add_root("Root", {"col1": "val1"})
        table.rebuild_visible_rows()

        table.cursor_row = 99
        selected = table.get_selected_node()
        assert selected is None


class TestTreeTableHelpers:
    """Test helper methods."""

    def test_get_ancestors(self):
        """Test getting ancestor chain."""
        table = TreeTable(columns=["col1"])

        root = table.add_root("Root", {"col1": "val1"})
        child = root.add_child(
            TreeTableNode(id="c1", label="Child", data={"col1": "val2"})
        )
        grandchild = child.add_child(
            TreeTableNode(id="gc", label="GrandChild", data={"col1": "val3"})
        )

        ancestors = table._get_ancestors(grandchild)
        assert len(ancestors) == 3
        assert ancestors[0] == root
        assert ancestors[1] == child
        assert ancestors[2] == grandchild

    def test_has_sibling_below_root(self):
        """Test checking siblings for root nodes."""
        table = TreeTable(columns=["col1"])

        root1 = table.add_root("Root 1", {"col1": "val1"})
        root2 = table.add_root("Root 2", {"col1": "val2"})
        root3 = table.add_root("Root 3", {"col1": "val3"})

        assert table._has_sibling_below(root1) is True
        assert table._has_sibling_below(root2) is True
        assert table._has_sibling_below(root3) is False

    def test_has_sibling_below_children(self):
        """Test checking siblings for child nodes."""
        table = TreeTable(columns=["col1"])

        root = table.add_root("Root", {"col1": "val1"})
        child1 = root.add_child(
            TreeTableNode(id="c1", label="Child 1", data={"col1": "val2"})
        )
        child2 = root.add_child(
            TreeTableNode(id="c2", label="Child 2", data={"col1": "val3"})
        )
        child3 = root.add_child(
            TreeTableNode(id="c3", label="Child 3", data={"col1": "val4"})
        )

        assert table._has_sibling_below(child1) is True
        assert table._has_sibling_below(child2) is True
        assert table._has_sibling_below(child3) is False


class TestTreeTableContentDimensions:
    """Test content width/height calculations."""

    def test_get_content_width(self):
        """Test content width calculation."""
        columns = ["Duration", "Tokens", "Model"]
        table = TreeTable(columns=columns)

        # TREE_COLUMN_WIDTH (40) + 3 * DATA_COLUMN_WIDTH (15) = 40 + 45 = 85
        from textual.geometry import Size

        width = table.get_content_width(Size(100, 100), Size(100, 100))
        assert width == 40 + (3 * 15)

    def test_get_content_height_with_header(self):
        """Test content height with header."""
        table = TreeTable(columns=["col1"])
        table.show_header = True

        root = table.add_root("Root", {"col1": "val1"})
        root.add_child(TreeTableNode(id="c1", label="Child", data={"col1": "val2"}))
        table.rebuild_visible_rows()

        from textual.geometry import Size

        # 2 visible rows + 1 header = 3
        height = table.get_content_height(Size(100, 100), Size(100, 100), 100)
        assert height == 3

    def test_get_content_height_without_header(self):
        """Test content height without header."""
        table = TreeTable(columns=["col1"])
        table.show_header = False

        root = table.add_root("Root", {"col1": "val1"})
        root.add_child(TreeTableNode(id="c1", label="Child", data={"col1": "val2"}))
        table.rebuild_visible_rows()

        from textual.geometry import Size

        # 2 visible rows, no header = 2
        height = table.get_content_height(Size(100, 100), Size(100, 100), 100)
        assert height == 2


class TestTreeTableEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_table(self):
        """Test operations on empty table."""
        table = TreeTable(columns=["col1"])

        table.rebuild_visible_rows()
        assert len(table._visible_rows) == 0

        selected = table.get_selected_node()
        assert selected is None

    def test_single_root_no_children(self):
        """Test table with single leaf node."""
        table = TreeTable(columns=["col1"])
        root = table.add_root("Root", {"col1": "val1"})

        table.rebuild_visible_rows()
        assert len(table._visible_rows) == 1
        assert table._visible_rows[0] == root

    def test_deeply_nested_hierarchy(self):
        """Test deeply nested node hierarchy."""
        table = TreeTable(columns=["col1"])

        root = table.add_root("Root", {"col1": "val1"})
        current = root

        # Create 10 levels deep
        for i in range(10):
            child = TreeTableNode(
                id=f"level-{i}", label=f"Level {i}", data={"col1": f"val{i}"}
            )
            current.add_child(child)
            current = child

        table.rebuild_visible_rows()

        # All should be visible (all expanded by default)
        assert len(table._visible_rows) == 11  # root + 10 levels

    def test_custom_node_id(self):
        """Test custom node IDs."""
        table = TreeTable(columns=["col1"])

        root = table.add_root("Root", {"col1": "val1"}, node_id="custom-root-id")
        assert root.id == "custom-root-id"

    def test_auto_generated_node_id(self):
        """Test auto-generated node IDs."""
        table = TreeTable(columns=["col1"])

        root1 = table.add_root("Root 1", {"col1": "val1"})
        root2 = table.add_root("Root 2", {"col1": "val2"})

        assert root1.id == "node-0"
        assert root2.id == "node-1"

    def test_missing_column_data(self):
        """Test nodes with missing column data."""
        table = TreeTable(columns=["col1", "col2", "col3"])

        # Only provide col1 data
        root = table.add_root("Root", {"col1": "val1"})

        assert root.data.get("col1") == "val1"
        assert root.data.get("col2", "") == ""
        assert root.data.get("col3", "") == ""

    def test_extra_column_data(self):
        """Test nodes with extra column data."""
        table = TreeTable(columns=["col1"])

        # Provide col1 and extra columns
        root = table.add_root("Root", {"col1": "val1", "col2": "extra", "col3": "data"})

        # Should store all data
        assert root.data == {"col1": "val1", "col2": "extra", "col3": "data"}
