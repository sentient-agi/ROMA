"""
Unit tests for LLM output text parsing for artifact declarations.

Tests that the parser can detect artifact declarations in Markdown, JSON, and XML
formats from LLM output text and automatically register them.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from roma_dspy.core.artifacts.text_parser import (
    parse_markdown_artifacts,
    parse_json_artifacts,
    parse_xml_artifacts,
    parse_all_formats,
    extract_artifact_declaration,
)
from roma_dspy.types import ArtifactType


class TestMarkdownArtifactParsing:
    """Test parsing artifact declarations from Markdown text."""

    def test_parse_single_artifact_block(self, tmp_path):
        """Test parsing single artifact declaration in Markdown."""
        # Create test file
        test_file = tmp_path / "data.csv"
        test_file.write_text("col1,col2\n1,2")

        markdown = f"""
# Analysis Results

Here's the data analysis:

## ARTIFACT: Dataset
- path: {test_file}
- type: data_processed
- description: Cleaned dataset
"""

        artifacts = parse_markdown_artifacts(markdown, tmp_path)
        assert len(artifacts) == 1
        assert str(test_file) in artifacts[0]["path"]
        assert artifacts[0]["type"] == "data_processed"
        assert artifacts[0]["description"] == "Cleaned dataset"

    def test_parse_multiple_artifact_blocks(self, tmp_path):
        """Test parsing multiple artifact declarations."""
        file1 = tmp_path / "data.csv"
        file1.write_text("data")

        file2 = tmp_path / "report.md"
        file2.write_text("# Report")

        markdown = f"""
## ARTIFACT: Data File
- path: {file1}
- type: data_processed
- description: Raw data

## ARTIFACT: Report
- path: {file2}
- type: report
- description: Analysis report
"""

        artifacts = parse_markdown_artifacts(markdown, tmp_path)
        assert len(artifacts) == 2

    def test_ignore_non_artifact_sections(self, tmp_path):
        """Test that non-artifact sections are ignored."""
        markdown = """
# Analysis Results

Some regular text here.

## Data Processing
- Step 1: Load data
- Step 2: Clean data

No artifacts here.
"""

        artifacts = parse_markdown_artifacts(markdown, tmp_path)
        assert len(artifacts) == 0

    def test_skip_nonexistent_files(self, tmp_path):
        """Test that artifacts with nonexistent paths are skipped."""
        markdown = f"""
## ARTIFACT: Missing File
- path: {tmp_path / "nonexistent.csv"}
- type: data_processed
- description: This file doesn't exist
"""

        artifacts = parse_markdown_artifacts(markdown, tmp_path)
        assert len(artifacts) == 0


class TestJSONArtifactParsing:
    """Test parsing artifact declarations from JSON text."""

    def test_parse_single_artifact_json(self, tmp_path):
        """Test parsing single artifact from JSON."""
        test_file = tmp_path / "output.json"
        test_file.write_text('{"key": "value"}')

        json_text = f"""
{{
    "artifacts": [
        {{
            "path": "{test_file}",
            "type": "data_processed",
            "description": "Processed JSON data"
        }}
    ]
}}
"""

        artifacts = parse_json_artifacts(json_text, tmp_path)
        assert len(artifacts) == 1
        assert str(test_file) in artifacts[0]["path"]
        assert artifacts[0]["type"] == "data_processed"

    def test_parse_multiple_artifacts_json(self, tmp_path):
        """Test parsing multiple artifacts from JSON array."""
        file1 = tmp_path / "data1.csv"
        file1.write_text("data")

        file2 = tmp_path / "data2.csv"
        file2.write_text("data")

        json_text = f"""
{{
    "artifacts": [
        {{
            "path": "{file1}",
            "type": "data_processed",
            "description": "First dataset"
        }},
        {{
            "path": "{file2}",
            "type": "data_processed",
            "description": "Second dataset"
        }}
    ]
}}
"""

        artifacts = parse_json_artifacts(json_text, tmp_path)
        assert len(artifacts) == 2

    def test_handle_malformed_json(self, tmp_path):
        """Test that malformed JSON is handled gracefully."""
        json_text = """
{
    "artifacts": [
        { "path": "/tmp/test.csv", "type": "data_processed" // missing comma
        }
    ]
}
"""

        artifacts = parse_json_artifacts(json_text, tmp_path)
        # Should return empty list on parse error
        assert len(artifacts) == 0

    def test_no_artifacts_key(self, tmp_path):
        """Test JSON without artifacts key."""
        json_text = """
{
    "result": "success",
    "message": "No artifacts here"
}
"""

        artifacts = parse_json_artifacts(json_text, tmp_path)
        assert len(artifacts) == 0


class TestXMLArtifactParsing:
    """Test parsing artifact declarations from XML text."""

    def test_parse_single_artifact_xml(self, tmp_path):
        """Test parsing single artifact from XML."""
        test_file = tmp_path / "chart.png"
        test_file.write_bytes(b"fake png")

        xml_text = f"""
<artifacts>
    <artifact>
        <path>{test_file}</path>
        <type>plot</type>
        <description>Price chart</description>
    </artifact>
</artifacts>
"""

        artifacts = parse_xml_artifacts(xml_text, tmp_path)
        assert len(artifacts) == 1
        assert str(test_file) in artifacts[0]["path"]
        assert artifacts[0]["type"] == "plot"

    def test_parse_multiple_artifacts_xml(self, tmp_path):
        """Test parsing multiple artifacts from XML."""
        file1 = tmp_path / "chart1.png"
        file1.write_bytes(b"png1")

        file2 = tmp_path / "chart2.png"
        file2.write_bytes(b"png2")

        xml_text = f"""
<artifacts>
    <artifact>
        <path>{file1}</path>
        <type>plot</type>
        <description>Chart 1</description>
    </artifact>
    <artifact>
        <path>{file2}</path>
        <type>plot</type>
        <description>Chart 2</description>
    </artifact>
</artifacts>
"""

        artifacts = parse_xml_artifacts(xml_text, tmp_path)
        assert len(artifacts) == 2

    def test_handle_malformed_xml(self, tmp_path):
        """Test that malformed XML is handled gracefully."""
        xml_text = """
<artifacts>
    <artifact>
        <path>/tmp/test.png</path>
        <type>plot
        <!-- missing closing tag -->
    </artifact>
</artifacts>
"""

        artifacts = parse_xml_artifacts(xml_text, tmp_path)
        # Should return empty list on parse error
        assert len(artifacts) == 0

    def test_skip_artifacts_outside_execution_dir(self, tmp_path):
        """Test that artifacts outside execution directory are skipped."""
        xml_text = """
<artifacts>
    <artifact>
        <path>/tmp/outside_file.txt</path>
        <type>document</type>
        <description>Outside execution dir</description>
    </artifact>
</artifacts>
"""

        artifacts = parse_xml_artifacts(xml_text, tmp_path)
        # Should skip file outside execution directory
        assert len(artifacts) == 0


class TestParseAllFormats:
    """Test unified parsing across all formats."""

    def test_parse_mixed_content(self, tmp_path):
        """Test parsing text containing multiple formats."""
        file1 = tmp_path / "data.csv"
        file1.write_text("data")

        file2 = tmp_path / "chart.png"
        file2.write_bytes(b"png")

        mixed_text = f"""
# Analysis Report

## ARTIFACT: Dataset
- path: {file1}
- type: data_processed
- description: Raw data

Some analysis text here...

<artifacts>
    <artifact>
        <path>{file2}</path>
        <type>plot</type>
        <description>Price chart</description>
    </artifact>
</artifacts>
"""

        artifacts = parse_all_formats(mixed_text, tmp_path)
        # Should find both artifacts from MD and XML
        assert len(artifacts) >= 2

    def test_deduplication_across_formats(self, tmp_path):
        """Test that same file declared in multiple formats is deduplicated."""
        test_file = tmp_path / "data.csv"
        test_file.write_text("data")

        # Same file declared in both MD and JSON
        mixed_text = f"""
## ARTIFACT: Data
- path: {test_file}
- type: data_processed
- description: Dataset

{{
    "artifacts": [
        {{
            "path": "{test_file}",
            "type": "data_processed",
            "description": "Same dataset"
        }}
    ]
}}
"""

        artifacts = parse_all_formats(mixed_text, tmp_path)
        # Should deduplicate and return only 1 artifact
        assert len(artifacts) == 1


class TestExtractArtifactDeclaration:
    """Test extracting structured artifact info from text."""

    def test_extract_valid_declaration(self):
        """Test extracting artifact info from valid declaration."""
        declaration = {
            "path": "/tmp/test.csv",
            "type": "data_processed",
            "description": "Test dataset"
        }

        extracted = extract_artifact_declaration(declaration)
        assert extracted["path"] == "/tmp/test.csv"
        assert extracted["type"] == "data_processed"
        assert extracted["description"] == "Test dataset"

    def test_handle_missing_required_fields(self):
        """Test handling declarations missing required fields."""
        # Missing path
        declaration = {
            "type": "data_processed",
            "description": "Test dataset"
        }

        extracted = extract_artifact_declaration(declaration)
        assert extracted is None

    def test_default_values(self):
        """Test default values for optional fields."""
        declaration = {
            "path": "/tmp/test.csv"
            # Missing type and description
        }

        extracted = extract_artifact_declaration(declaration)
        assert extracted is not None
        assert extracted["path"] == "/tmp/test.csv"
        assert "type" in extracted
        assert "description" in extracted


class TestTextParserIntegration:
    """Integration tests for text parser."""

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_parse_and_register_from_llm_output(self, mock_get_context, tmp_path):
        """Test complete workflow: parse LLM output and register artifacts."""
        from roma_dspy.core.artifacts import ArtifactRegistry
        from roma_dspy.core.artifacts.text_parser import parse_and_register_artifacts

        # Setup mock context
        context = Mock()
        context.execution_id = "test_exec_123"
        context.artifact_registry = ArtifactRegistry()
        context.file_storage = Mock()
        context.file_storage.root = tmp_path
        mock_get_context.return_value = context

        # Create test files
        data_file = tmp_path / "analysis.csv"
        data_file.write_text("result,value\n1,2")

        chart_file = tmp_path / "chart.png"
        chart_file.write_bytes(b"fake png")

        # Simulate LLM output with artifact declarations
        llm_output = f"""
I've completed the analysis and generated the following artifacts:

## ARTIFACT: Analysis Results
- path: {data_file}
- type: data_processed
- description: Cleaned analysis results

## ARTIFACT: Visualization
- path: {chart_file}
- type: plot
- description: Price trend chart
"""

        # Parse and register
        count = await parse_and_register_artifacts(
            text=llm_output,
            execution_id="test_exec_123"
        )

        # Should register both artifacts
        assert count == 2

        # Verify artifacts in registry
        artifacts = await context.artifact_registry.get_all()
        assert len(artifacts) == 2

        # Check artifact types
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.DATA_PROCESSED in types
        assert ArtifactType.PLOT in types

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_deduplication_with_existing_artifacts(self, mock_get_context, tmp_path):
        """Test that parser doesn't re-register existing artifacts."""
        from roma_dspy.core.artifacts import ArtifactRegistry, ArtifactBuilder
        from roma_dspy.core.artifacts.text_parser import parse_and_register_artifacts

        # Setup mock context
        context = Mock()
        context.execution_id = "test_exec_123"
        context.artifact_registry = ArtifactRegistry()
        context.file_storage = Mock()
        context.file_storage.root = tmp_path
        mock_get_context.return_value = context

        # Create and register file first
        data_file = tmp_path / "data.csv"
        data_file.write_text("data")

        artifact_builder = ArtifactBuilder()
        artifact = await artifact_builder.build(
            name="data",
            artifact_type=ArtifactType.DATA_PROCESSED,
            storage_path=str(data_file),
            created_by_task="test_exec_123",
            created_by_module="TestModule",
            description="Existing artifact",
            derived_from=[],
        )
        await context.artifact_registry.register(artifact)

        # Try to register same file via text parsing
        llm_output = f"""
## ARTIFACT: Data
- path: {data_file}
- type: data_processed
- description: Same data file
"""

        count = await parse_and_register_artifacts(
            text=llm_output,
            execution_id="test_exec_123"
        )

        # Should skip (count = 0)
        assert count == 0

        # Should still have only 1 artifact
        artifacts = await context.artifact_registry.get_all()
        assert len(artifacts) == 1
