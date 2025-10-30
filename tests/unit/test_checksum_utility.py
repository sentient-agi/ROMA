"""Tests for checksum utility - deterministic SHA256 computation."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from roma_dspy.tui.utils.checksum import compute_checksum, verify_checksum


class TestChecksumUtility:
    """Test checksum computation and verification."""

    def test_compute_checksum_basic(self):
        """Test basic checksum computation."""
        data = {"foo": 123, "bar": "test"}
        checksum = compute_checksum(data)

        # Should be sha256:hexdigest format
        assert checksum.startswith("sha256:")
        assert len(checksum) == len("sha256:") + 64  # sha256 hex is 64 chars

    def test_compute_checksum_deterministic(self):
        """Test checksum is deterministic (same input -> same output)."""
        data = {"a": 1, "b": 2, "c": 3}

        checksum1 = compute_checksum(data)
        checksum2 = compute_checksum(data)

        assert checksum1 == checksum2

    def test_compute_checksum_key_order_independent(self):
        """Test checksum is independent of dict key order."""
        # Python 3.7+ preserves insertion order, but our checksum should not depend on it
        data1 = {"z": 1, "a": 2, "m": 3}
        data2 = {"a": 2, "m": 3, "z": 1}

        checksum1 = compute_checksum(data1)
        checksum2 = compute_checksum(data2)

        # Should be identical because we sort keys
        assert checksum1 == checksum2

    def test_compute_checksum_whitespace_independent(self):
        """Test checksum is independent of JSON whitespace."""
        data = {"test": "value", "nested": {"key": 123}}

        # Manually compute with different whitespace
        import hashlib

        # Our implementation uses no whitespace
        json_str_compact = json.dumps(data, sort_keys=True, separators=(',', ':'), default=str)
        expected_checksum = f"sha256:{hashlib.sha256(json_str_compact.encode('utf-8')).hexdigest()}"

        actual_checksum = compute_checksum(data)

        assert actual_checksum == expected_checksum

    def test_compute_checksum_with_nested_dict(self):
        """Test checksum with nested dictionaries."""
        data = {
            "execution": {
                "id": "test123",
                "tasks": {
                    "task1": {"name": "foo", "result": "bar"},
                    "task2": {"name": "baz", "result": "qux"}
                }
            }
        }

        checksum = compute_checksum(data)
        assert checksum.startswith("sha256:")

        # Should be repeatable
        assert checksum == compute_checksum(data)

    def test_compute_checksum_with_datetime(self):
        """Test checksum handles datetime objects (via default=str)."""
        data = {
            "timestamp": datetime(2024, 1, 15, 12, 30, 0),
            "value": 42
        }

        # Should not raise TypeError
        checksum = compute_checksum(data)
        assert checksum.startswith("sha256:")

    def test_compute_checksum_with_path(self):
        """Test checksum handles Path objects (via default=str)."""
        data = {
            "filepath": Path("/tmp/test.json"),
            "size": 1024
        }

        # Should not raise TypeError
        checksum = compute_checksum(data)
        assert checksum.startswith("sha256:")

    def test_compute_checksum_sensitivity_to_changes(self):
        """Test checksum changes when data changes."""
        data1 = {"key": "value1"}
        data2 = {"key": "value2"}

        checksum1 = compute_checksum(data1)
        checksum2 = compute_checksum(data2)

        assert checksum1 != checksum2

    def test_compute_checksum_with_lists(self):
        """Test checksum with list values."""
        data = {
            "items": [1, 2, 3],
            "names": ["alice", "bob", "charlie"]
        }

        checksum = compute_checksum(data)
        assert checksum.startswith("sha256:")

    def test_compute_checksum_with_none_values(self):
        """Test checksum handles None values."""
        data = {
            "value": None,
            "optional": None,
            "present": "here"
        }

        checksum = compute_checksum(data)
        assert checksum.startswith("sha256:")

    def test_verify_checksum_valid(self):
        """Test verify_checksum with matching checksum."""
        data = {"test": 123}
        checksum = compute_checksum(data)

        assert verify_checksum(data, checksum) is True

    def test_verify_checksum_invalid(self):
        """Test verify_checksum with non-matching checksum."""
        data = {"test": 123}
        wrong_checksum = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

        assert verify_checksum(data, wrong_checksum) is False

    def test_verify_checksum_data_changed(self):
        """Test verify_checksum detects data changes."""
        original_data = {"key": "original"}
        checksum = compute_checksum(original_data)

        modified_data = {"key": "modified"}

        assert verify_checksum(modified_data, checksum) is False

    def test_checksum_export_import_consistency(self):
        """Test checksum remains consistent through JSON export/import cycle.

        This is the critical test - verifying that the checksum computed
        from the final JSON string matches after a serialization round-trip.
        """
        # Simulate export data
        data = {
            "execution": {
                "execution_id": "test123",
                "tasks": {
                    "task1": {
                        "task_id": "task1",
                        "goal": "test goal",
                        "status": "completed",
                        "total_tokens": 100,
                        "total_cost": 0.001,
                    }
                },
                "metrics": {
                    "total_calls": 1,
                    "total_tokens": 100,
                    "total_cost": 0.001
                }
            }
        }

        # Compute checksum
        checksum = compute_checksum(data)

        # Simulate export: serialize to JSON string with same settings
        json_str = json.dumps(data, sort_keys=True, default=str, separators=(',', ':'))

        # Simulate import: parse JSON back to dict
        imported_data = json.loads(json_str)

        # Verify checksum matches after round-trip
        assert verify_checksum(imported_data, checksum)
        assert compute_checksum(imported_data) == checksum
