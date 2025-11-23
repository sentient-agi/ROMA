"""
Unit tests for NEW BUG #4: Circular reference handling in safe_dict().

Tests verify that:
1. Circular references are detected and handled without crashing
2. Deep legitimate nesting still works correctly
3. DAGs (shared references) are handled conservatively
4. Nested secrets are still redacted correctly with cycles
5. Various edge cases are handled properly
"""

import pytest
from roma_dspy.config.schemas.toolkit import ToolkitConfig


class TestSafeDictCircularReferences:
    """Test suite for circular reference detection in safe_dict()."""

    def test_simple_dict_no_cycles(self):
        """Test that simple dicts without cycles work normally."""
        config = ToolkitConfig(
            class_name="TestToolkit",
            toolkit_config={"api_key": "secret123", "timeout": 30, "retries": 3},
        )

        safe = config.safe_dict()

        assert safe["api_key"] == "***REDACTED***"
        assert safe["timeout"] == 30
        assert safe["retries"] == 3

    def test_nested_dict_no_cycles(self):
        """Test that nested dicts without cycles work normally."""
        config = ToolkitConfig(
            class_name="TestToolkit",
            toolkit_config={
                "database": {
                    "host": "localhost",
                    "credentials": {"username": "admin", "password": "secret123"},
                },
                "timeout": 30,
            },
        )

        safe = config.safe_dict()

        assert safe["database"]["host"] == "localhost"
        assert safe["database"]["credentials"]["username"] == "admin"
        assert safe["database"]["credentials"]["password"] == "***REDACTED***"
        assert safe["timeout"] == 30

    def test_self_reference_cycle_detected(self):
        """Test that self-referential cycle is detected."""
        # Create circular reference
        circular = {"key": "value", "timeout": 30}
        circular["self"] = circular

        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=circular)

        # Should not crash with RecursionError
        safe = config.safe_dict()

        # Check that cycle was detected
        assert safe["key"] == "value"
        assert safe["timeout"] == 30
        assert isinstance(safe["self"], dict)
        assert "__circular_reference__" in safe["self"]
        assert safe["self"]["__circular_reference__"] == "***REDACTED***"

    def test_deep_cycle_detected(self):
        """Test that deep cycles (a->b->c->a) are detected."""
        # Create deep cycle
        a = {"name": "a"}
        b = {"name": "b"}
        c = {"name": "c"}
        a["next"] = b
        b["next"] = c
        c["next"] = a  # Complete the cycle

        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=a)

        # Should not crash
        safe = config.safe_dict()

        # Check structure
        assert safe["name"] == "a"
        assert safe["next"]["name"] == "b"
        assert safe["next"]["next"]["name"] == "c"
        # The cycle should be detected here
        assert "__circular_reference__" in safe["next"]["next"]["next"]

    def test_dag_shared_reference_handled(self):
        """Test that DAGs (shared references without cycles) are handled."""
        # Create DAG (not a cycle, but same object referenced twice)
        shared = {"shared_key": "shared_value"}
        config_dict = {
            "branch1": shared,
            "branch2": shared,  # Same object, not a copy
        }

        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=config_dict)

        safe = config.safe_dict()

        # First branch should work
        assert safe["branch1"]["shared_key"] == "shared_value"

        # Second branch sees same object ID, treats as cycle (conservative)
        assert isinstance(safe["branch2"], dict)
        assert "__circular_reference__" in safe["branch2"]

    def test_secrets_redacted_with_cycles(self):
        """Test that secrets are still redacted correctly even with cycles."""
        # Create circular structure with secrets
        circular = {"api_key": "secret123", "timeout": 30}
        circular["nested"] = {
            "token": "bearer_xyz",
            "parent": circular,  # Cycle back to parent
        }

        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=circular)

        safe = config.safe_dict()

        # Secrets should be redacted
        assert safe["api_key"] == "***REDACTED***"
        assert safe["timeout"] == 30
        assert safe["nested"]["token"] == "***REDACTED***"

        # Cycle should be detected
        assert "__circular_reference__" in safe["nested"]["parent"]

    def test_list_with_dicts_no_cycle(self):
        """Test that lists with dicts work normally without cycles."""
        config = ToolkitConfig(
            class_name="TestToolkit",
            toolkit_config={
                "servers": [
                    {"host": "server1", "api_key": "key1"},
                    {"host": "server2", "api_key": "key2"},
                ]
            },
        )

        safe = config.safe_dict()

        assert safe["servers"][0]["host"] == "server1"
        assert safe["servers"][0]["api_key"] == "***REDACTED***"
        assert safe["servers"][1]["host"] == "server2"
        assert safe["servers"][1]["api_key"] == "***REDACTED***"

    def test_empty_dict_edge_case(self):
        """Test that empty dicts are handled correctly."""
        config = ToolkitConfig(class_name="TestToolkit", toolkit_config={})

        safe = config.safe_dict()
        assert safe == {}

    def test_none_config_edge_case(self):
        """Test that None config is handled correctly."""
        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=None)

        safe = config.safe_dict()
        assert safe == {}

    def test_none_values_in_dict(self):
        """Test that None values in dict are preserved."""
        config = ToolkitConfig(
            class_name="TestToolkit",
            toolkit_config={"optional_value": None, "api_key": "secret"},
        )

        safe = config.safe_dict()

        assert safe["optional_value"] is None
        assert safe["api_key"] == "***REDACTED***"

    def test_deep_nesting_without_cycle(self):
        """Test that deep legitimate nesting (depth > 10) works correctly."""
        # Create deeply nested structure (15 levels)
        deep = {"level": 1}
        current = deep
        for i in range(2, 16):
            current["nested"] = {"level": i}
            current = current["nested"]

        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=deep)

        # Should not crash or truncate
        safe = config.safe_dict()

        # Verify all levels present
        current = safe
        for i in range(1, 16):
            assert current["level"] == i
            if i < 15:
                current = current["nested"]

    def test_multiple_cycles_in_structure(self):
        """Test structure with multiple independent cycles."""
        # Create structure with two cycles
        cycle1 = {"name": "cycle1"}
        cycle1["self"] = cycle1

        cycle2 = {"name": "cycle2"}
        cycle2["self"] = cycle2

        config_dict = {"first": cycle1, "second": cycle2}

        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=config_dict)

        safe = config.safe_dict()

        # Both cycles should be detected
        assert safe["first"]["name"] == "cycle1"
        assert "__circular_reference__" in safe["first"]["self"]

        assert safe["second"]["name"] == "cycle2"
        assert "__circular_reference__" in safe["second"]["self"]

    def test_mixed_sensitive_and_cycles(self):
        """Test complex structure with both sensitive keys and cycles."""
        # Create complex structure
        auth = {"api_key": "secret_key", "token": "bearer_token"}

        config_dict = {
            "auth": auth,
            "nested": {"credentials": {"password": "secret_pass"}},
        }

        # Add cycle
        config_dict["nested"]["parent"] = config_dict

        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=config_dict)

        safe = config.safe_dict()

        # All secrets should be redacted
        assert safe["auth"]["api_key"] == "***REDACTED***"
        assert safe["auth"]["token"] == "***REDACTED***"
        assert safe["nested"]["credentials"]["password"] == "***REDACTED***"

        # Cycle should be detected
        assert "__circular_reference__" in safe["nested"]["parent"]

    def test_case_insensitive_secret_detection_with_cycles(self):
        """Test that secret detection is case-insensitive even with cycles."""
        circular = {"API_KEY": "secret1", "ApiKey": "secret2", "api_key": "secret3"}
        circular["self"] = circular

        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=circular)

        safe = config.safe_dict()

        # All variations should be redacted
        assert safe["API_KEY"] == "***REDACTED***"
        assert safe["ApiKey"] == "***REDACTED***"
        assert safe["api_key"] == "***REDACTED***"

        # Cycle detected
        assert "__circular_reference__" in safe["self"]

    def test_list_with_nested_cycles(self):
        """Test list containing dicts with cycles."""
        circular1 = {"id": 1}
        circular1["self"] = circular1

        circular2 = {"id": 2}
        circular2["self"] = circular2

        config = ToolkitConfig(
            class_name="TestToolkit", toolkit_config={"items": [circular1, circular2]}
        )

        safe = config.safe_dict()

        # Both items should have cycles detected
        assert safe["items"][0]["id"] == 1
        assert "__circular_reference__" in safe["items"][0]["self"]

        assert safe["items"][1]["id"] == 2
        assert "__circular_reference__" in safe["items"][1]["self"]

    def test_immutable_seen_set_pattern(self):
        """Test that immutable seen set pattern works correctly."""
        # Create Y-shaped structure (two paths to same leaf)
        leaf = {"value": "leaf"}
        branch = {
            "left": {"child": leaf},
            "right": {"child": leaf},  # Same object
        }

        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=branch)

        safe = config.safe_dict()

        # First path should work
        assert safe["left"]["child"]["value"] == "leaf"

        # Second path sees same object, treats as cycle (conservative)
        assert "__circular_reference__" in safe["right"]["child"]

    def test_placeholder_format(self):
        """Test that placeholder format is consistent and safe."""
        circular = {"key": "value"}
        circular["self"] = circular

        config = ToolkitConfig(class_name="TestToolkit", toolkit_config=circular)

        safe = config.safe_dict()

        placeholder = safe["self"]

        # Check format
        assert isinstance(placeholder, dict)
        assert len(placeholder) == 1
        assert "__circular_reference__" in placeholder
        assert placeholder["__circular_reference__"] == "***REDACTED***"

        # Should be JSON serializable
        import json

        json_str = json.dumps(safe)
        assert "__circular_reference__" in json_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
