"""
Unit tests for artifact injection type system.

Tests the ArtifactInjectionMode enum and its integration with context models.
"""

import pytest
from roma_dspy.types.artifact_injection import ArtifactInjectionMode


class TestArtifactInjectionMode:
    """Test ArtifactInjectionMode enum."""

    def test_enum_values(self):
        """Test that all expected injection modes exist."""
        assert ArtifactInjectionMode.NONE == "none"
        assert ArtifactInjectionMode.DEPENDENCIES == "dependencies"
        assert ArtifactInjectionMode.SUBTASK == "subtask"
        assert ArtifactInjectionMode.FULL == "full"

    def test_enum_from_string(self):
        """Test creating enum from string values."""
        assert ArtifactInjectionMode("none") == ArtifactInjectionMode.NONE
        assert ArtifactInjectionMode("dependencies") == ArtifactInjectionMode.DEPENDENCIES
        assert ArtifactInjectionMode("subtask") == ArtifactInjectionMode.SUBTASK
        assert ArtifactInjectionMode("full") == ArtifactInjectionMode.FULL

    def test_enum_invalid_value(self):
        """Test that invalid values raise ValueError."""
        with pytest.raises(ValueError):
            ArtifactInjectionMode("invalid")

    def test_enum_iteration(self):
        """Test iterating over all modes."""
        modes = list(ArtifactInjectionMode)
        assert len(modes) == 4
        assert ArtifactInjectionMode.NONE in modes
        assert ArtifactInjectionMode.DEPENDENCIES in modes
        assert ArtifactInjectionMode.SUBTASK in modes
        assert ArtifactInjectionMode.FULL in modes

    def test_default_mode(self):
        """Test that DEPENDENCIES is the recommended default."""
        # This is a documentation test - DEPENDENCIES should be default
        default_mode = ArtifactInjectionMode.DEPENDENCIES
        assert default_mode == "dependencies"
