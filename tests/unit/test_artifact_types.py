"""Unit tests for artifact type definitions."""

import pytest

from roma_dspy.types import ArtifactType


class TestArtifactType:
    """Test ArtifactType enum."""

    def test_enum_values(self):
        """Test that all enum values are defined correctly."""
        assert ArtifactType.DATA_FETCH.value == "data_fetch"
        assert ArtifactType.DATA_PROCESSED.value == "data_processed"
        assert ArtifactType.DATA_ANALYSIS.value == "data_analysis"
        assert ArtifactType.REPORT.value == "report"
        assert ArtifactType.PLOT.value == "plot"
        assert ArtifactType.CODE.value == "code"
        assert ArtifactType.IMAGE.value == "image"
        assert ArtifactType.DOCUMENT.value == "document"

    def test_from_string_valid(self):
        """Test from_string with valid values."""
        assert ArtifactType.from_string("data_fetch") == ArtifactType.DATA_FETCH
        assert ArtifactType.from_string("DATA_FETCH") == ArtifactType.DATA_FETCH
        assert ArtifactType.from_string("report") == ArtifactType.REPORT
        assert ArtifactType.from_string("REPORT") == ArtifactType.REPORT

    def test_from_string_invalid(self):
        """Test from_string with invalid values."""
        with pytest.raises(ValueError, match="Invalid artifact type"):
            ArtifactType.from_string("invalid_type")

        with pytest.raises(ValueError, match="Invalid artifact type"):
            ArtifactType.from_string("INVALID")

    def test_is_data_property(self):
        """Test is_data property."""
        assert ArtifactType.DATA_FETCH.is_data is True
        assert ArtifactType.DATA_PROCESSED.is_data is True
        assert ArtifactType.DATA_ANALYSIS.is_data is True
        assert ArtifactType.REPORT.is_data is False
        assert ArtifactType.PLOT.is_data is False
        assert ArtifactType.CODE.is_data is False

    def test_is_document_property(self):
        """Test is_document property."""
        assert ArtifactType.REPORT.is_document is True
        assert ArtifactType.PLOT.is_document is True
        assert ArtifactType.CODE.is_document is True
        assert ArtifactType.IMAGE.is_document is True
        assert ArtifactType.DOCUMENT.is_document is True
        assert ArtifactType.DATA_FETCH.is_document is False
        assert ArtifactType.DATA_PROCESSED.is_document is False

    def test_enum_is_string(self):
        """Test that enum values are strings (DSPy compatibility)."""
        assert isinstance(ArtifactType.DATA_FETCH, str)
        assert isinstance(ArtifactType.REPORT, str)
