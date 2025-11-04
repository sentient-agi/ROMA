"""Tests for schema validator - v1.0.0 and v1.1.0 support with auto-detection."""

import json
from pathlib import Path

import pytest

from roma_dspy.tui.utils.schema_validator import SchemaValidator


class TestSchemaVersionSupport:
    """Test schema version support and detection."""

    def test_validator_init_default_v1_1_0(self):
        """Test validator initializes with v1.1.0 by default."""
        validator = SchemaValidator()
        assert validator.schema_version == "1.1.0"

    def test_validator_init_explicit_v1_0_0(self):
        """Test validator can be initialized with v1.0.0."""
        validator = SchemaValidator(schema_version="1.0.0")
        assert validator.schema_version == "1.0.0"

    def test_validator_init_explicit_v1_1_0(self):
        """Test validator can be initialized with v1.1.0."""
        validator = SchemaValidator(schema_version="1.1.0")
        assert validator.schema_version == "1.1.0"

    def test_validator_init_unsupported_version_raises(self):
        """Test validator raises error for unsupported version."""
        with pytest.raises(ValueError, match="Unsupported schema version"):
            SchemaValidator(schema_version="2.0.0")

        with pytest.raises(ValueError, match="Unsupported schema version"):
            SchemaValidator(schema_version="0.9.0")

    def test_load_schema_v1_0_0(self):
        """Test loading v1.0.0 schema file."""
        validator = SchemaValidator(schema_version="1.0.0")

        # Should have loaded schema
        assert validator.schema is not None
        assert validator.schema["$id"] == "https://roma-dspy.dev/schemas/export/v1.0.0.json"

    def test_load_schema_v1_1_0(self):
        """Test loading v1.1.0 schema file."""
        validator = SchemaValidator(schema_version="1.1.0")

        # Should have loaded schema
        assert validator.schema is not None
        assert validator.schema["$id"] == "https://roma-dspy.dev/schemas/export/v1.1.0.json"

    def test_detect_schema_version_v1_0_0(self):
        """Test detecting v1.0.0 from data."""
        data = {"schema_version": "1.0.0"}

        version = SchemaValidator.detect_schema_version(data)
        assert version == "1.0.0"

    def test_detect_schema_version_v1_1_0(self):
        """Test detecting v1.1.0 from data."""
        data = {"schema_version": "1.1.0"}

        version = SchemaValidator.detect_schema_version(data)
        assert version == "1.1.0"

    def test_detect_schema_version_missing_raises(self):
        """Test detection raises error if schema_version missing."""
        data = {"execution": {}}

        with pytest.raises(ValueError, match="Missing schema_version"):
            SchemaValidator.detect_schema_version(data)

    def test_detect_schema_version_invalid_type_raises(self):
        """Test detection raises error if schema_version is not string."""
        data = {"schema_version": 1.0}  # Number, not string

        with pytest.raises(ValueError, match="Invalid schema_version type"):
            SchemaValidator.detect_schema_version(data)

    def test_detect_schema_version_unsupported_raises(self):
        """Test detection raises error for unsupported version."""
        data = {"schema_version": "2.0.0"}

        with pytest.raises(ValueError, match="Unsupported schema version"):
            SchemaValidator.detect_schema_version(data)

    def test_validate_auto_switches_to_v1_0_0(self):
        """Test validate() auto-switches to v1.0.0 when data has v1.0.0."""
        # Create validator with v1.1.0 (default)
        validator = SchemaValidator()
        assert validator.schema_version == "1.1.0"

        # Validate v1.0.0 data
        data = {
            "schema_version": "1.0.0",
            "roma_version": "0.2.0",
            "exported_at": "2024-01-15T12:00:00",
            "export_level": "full",
            "checksum": "sha256:" + "0" * 64,
            "execution": {
                "execution_id": "test123",
                "root_goal": "test goal",
                "status": "completed",
                "tasks": {},
                "root_task_ids": [],
                "metrics": {
                    "total_calls": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "total_duration": 0.0,
                    "avg_latency_ms": 0.0
                }
            },
            "metadata": {
                "export_source": "tui_v2",
                "task_count": 0,
                "trace_count": 0
            }
        }

        result = validator.validate(data)

        # Validator should have switched to v1.0.0
        assert validator.schema_version == "1.0.0"

    def test_validate_auto_switches_to_v1_1_0(self):
        """Test validate() auto-switches to v1.1.0 when data has v1.1.0."""
        # Create validator with v1.0.0
        validator = SchemaValidator(schema_version="1.0.0")
        assert validator.schema_version == "1.0.0"

        # Validate v1.1.0 data
        data = {
            "schema_version": "1.1.0",
            "roma_version": "0.2.0",
            "exported_at": "2024-01-15T12:00:00",
            "export_level": "full",
            "checksum": "sha256:" + "0" * 64,
            "execution": {
                "execution_id": "test123",
                "root_goal": "test goal",
                "status": "completed",
                "tasks": {},
                "root_task_ids": [],
                "metrics": {
                    "total_calls": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "total_duration": 0.0,
                    "avg_latency_ms": 0.0
                }
            },
            "metadata": {
                "export_source": "tui_v2",
                "task_count": 0,
                "trace_count": 0
            }
        }

        result = validator.validate(data)

        # Validator should have switched to v1.1.0
        assert validator.schema_version == "1.1.0"

    def test_supported_versions_list(self):
        """Test SUPPORTED_VERSIONS constant."""
        assert "1.0.0" in SchemaValidator.SUPPORTED_VERSIONS
        assert "1.1.0" in SchemaValidator.SUPPORTED_VERSIONS
        assert len(SchemaValidator.SUPPORTED_VERSIONS) >= 2


class TestSchemaValidation:
    """Test schema validation logic."""

    def test_validate_minimal_valid_export(self):
        """Test validation with minimal valid export."""
        validator = SchemaValidator()

        data = {
            "schema_version": "1.1.0",
            "roma_version": "0.2.0",
            "exported_at": "2024-01-15T12:00:00",
            "export_level": "minimal",
            "checksum": "sha256:" + "0" * 64,
            "execution": {
                "execution_id": "test123",
                "root_goal": "test",
                "status": "completed",
                "tasks": {},
                "root_task_ids": [],
                "metrics": {
                    "total_calls": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "total_duration": 0.0,
                    "avg_latency_ms": 0.0
                }
            },
            "metadata": {
                "export_source": "tui_v2",
                "task_count": 0,
                "trace_count": 0
            }
        }

        result = validator.validate(data)

        assert result.valid is True
        assert len(result.errors) == 0
        assert result.schema_version == "1.1.0"
        assert result.execution_id == "test123"

    def test_validate_missing_required_field(self):
        """Test validation fails for missing required field."""
        validator = SchemaValidator()

        data = {
            "schema_version": "1.1.0",
            # Missing roma_version (required)
            "exported_at": "2024-01-15T12:00:00",
            "export_level": "full",
            "checksum": "sha256:" + "0" * 64,
            "execution": {},
            "metadata": {
                "export_source": "tui_v2",
                "task_count": 0,
                "trace_count": 0
            }
        }

        result = validator.validate(data)

        assert result.valid is False
        assert len(result.errors) > 0
        assert any("roma_version" in err.lower() for err in result.errors)

    def test_validate_invalid_checksum_format(self):
        """Test validation fails for invalid checksum format."""
        validator = SchemaValidator()

        data = {
            "schema_version": "1.1.0",
            "roma_version": "0.2.0",
            "exported_at": "2024-01-15T12:00:00",
            "export_level": "full",
            "checksum": "invalid_checksum",  # Wrong format
            "execution": {
                "execution_id": "test123",
                "root_goal": "test",
                "status": "completed",
                "tasks": {},
                "root_task_ids": [],
                "metrics": {
                    "total_calls": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "total_duration": 0.0,
                    "avg_latency_ms": 0.0
                }
            },
            "metadata": {
                "export_source": "tui_v2",
                "task_count": 0,
                "trace_count": 0
            }
        }

        result = validator.validate(data)

        assert result.valid is False
        assert any("checksum" in err.lower() for err in result.errors)

    def test_validate_reference_integrity_missing_task(self):
        """Test validation detects missing task references."""
        validator = SchemaValidator()

        data = {
            "schema_version": "1.1.0",
            "roma_version": "0.2.0",
            "exported_at": "2024-01-15T12:00:00",
            "export_level": "full",
            "checksum": "sha256:" + "0" * 64,
            "execution": {
                "execution_id": "test123",
                "root_goal": "test",
                "status": "completed",
                "tasks": {
                    "task1": {
                        "task_id": "task1",
                        "goal": "test",
                        "status": "completed",
                        "traces": [],
                        "total_duration": 0.0,
                        "total_tokens": 0,
                        "total_cost": 0.0,
                        "subtask_ids": ["task2"]  # task2 doesn't exist!
                    }
                },
                "root_task_ids": ["task1"],
                "metrics": {
                    "total_calls": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "total_duration": 0.0,
                    "avg_latency_ms": 0.0
                }
            },
            "metadata": {
                "export_source": "tui_v2",
                "task_count": 1,
                "trace_count": 0
            }
        }

        result = validator.validate(data)

        # Should have error about missing subtask
        assert any("task2" in err and "not found" in err for err in result.errors)

    def test_validate_circular_reference_detection(self):
        """Test validation detects circular task references."""
        validator = SchemaValidator()

        data = {
            "schema_version": "1.1.0",
            "roma_version": "0.2.0",
            "exported_at": "2024-01-15T12:00:00",
            "export_level": "full",
            "checksum": "sha256:" + "0" * 64,
            "execution": {
                "execution_id": "test123",
                "root_goal": "test",
                "status": "completed",
                "tasks": {
                    "task1": {
                        "task_id": "task1",
                        "goal": "test",
                        "status": "completed",
                        "traces": [],
                        "total_duration": 0.0,
                        "total_tokens": 0,
                        "total_cost": 0.0,
                        "subtask_ids": ["task2"]
                    },
                    "task2": {
                        "task_id": "task2",
                        "goal": "test",
                        "status": "completed",
                        "traces": [],
                        "total_duration": 0.0,
                        "total_tokens": 0,
                        "total_cost": 0.0,
                        "subtask_ids": ["task1"]  # Circular reference!
                    }
                },
                "root_task_ids": ["task1"],
                "metrics": {
                    "total_calls": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "total_duration": 0.0,
                    "avg_latency_ms": 0.0
                }
            },
            "metadata": {
                "export_source": "tui_v2",
                "task_count": 2,
                "trace_count": 0
            }
        }

        result = validator.validate(data)

        # Should detect circular reference
        assert any("circular" in err.lower() for err in result.errors)

    def test_validate_backward_compatibility_v1_0_0(self):
        """Test validator can validate v1.0.0 exports."""
        # Start with v1.1.0 validator
        validator = SchemaValidator()

        # v1.0.0 export
        data = {
            "schema_version": "1.0.0",
            "roma_version": "0.2.0",
            "exported_at": "2024-01-15T12:00:00",
            "export_level": "full",
            "checksum": "sha256:" + "0" * 64,
            "execution": {
                "execution_id": "test123",
                "root_goal": "test",
                "status": "completed",
                "tasks": {},
                "root_task_ids": [],
                "metrics": {
                    "total_calls": 0,
                    "total_tokens": 0,
                    "total_cost": 0.0,
                    "total_duration": 0.0,
                    "avg_latency_ms": 0.0
                }
            },
            "metadata": {
                "export_source": "tui_v2",
                "task_count": 0,
                "trace_count": 0
            }
        }

        result = validator.validate(data)

        # Should validate successfully and switch to v1.0.0
        assert result.valid is True
        assert validator.schema_version == "1.0.0"
