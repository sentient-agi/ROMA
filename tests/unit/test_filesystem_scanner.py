"""
Unit tests for filesystem scanner for automatic artifact detection.

Tests that the scanner can detect files created during execution and
automatically register them as artifacts with proper deduplication.
"""

import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from time import time

from roma_dspy.core.artifacts.filesystem_scanner import (
    scan_execution_directory,
    auto_register_scanned_files,
    should_skip_file,
)
from roma_dspy.types import ArtifactType


class TestFilesystemScanner:
    """Test scanning execution directory for new files."""

    @pytest.mark.asyncio
    async def test_scan_finds_new_files(self, tmp_path):
        """Test that scanner finds files created after start_time."""
        start_time = time()

        # Create files after start_time
        file1 = tmp_path / "data.csv"
        file1.write_text("col1,col2\n1,2")

        file2 = tmp_path / "report.md"
        file2.write_text("# Report")

        # Scan directory
        found_files = scan_execution_directory(
            execution_dir=tmp_path,
            start_time=start_time
        )

        # Should find both files
        assert len(found_files) >= 2
        file_paths = {str(f) for f in found_files}
        assert str(file1) in file_paths
        assert str(file2) in file_paths

    @pytest.mark.asyncio
    async def test_scan_ignores_old_files(self, tmp_path):
        """Test that scanner ignores files created before start_time."""
        # Create old file
        old_file = tmp_path / "old.txt"
        old_file.write_text("old content")

        # Wait a bit and set start_time
        import time as time_module
        time_module.sleep(0.1)
        start_time = time()

        # Create new file
        new_file = tmp_path / "new.txt"
        new_file.write_text("new content")

        # Scan directory
        found_files = scan_execution_directory(
            execution_dir=tmp_path,
            start_time=start_time
        )

        # Should only find new file
        file_paths = {str(f) for f in found_files}
        assert str(new_file) in file_paths
        assert str(old_file) not in file_paths

    @pytest.mark.asyncio
    async def test_scan_recursive(self, tmp_path):
        """Test that scanner recursively finds files in subdirectories."""
        start_time = time()

        # Create nested directory structure
        subdir = tmp_path / "artifacts" / "data"
        subdir.mkdir(parents=True)

        file_in_subdir = subdir / "nested.json"
        file_in_subdir.write_text('{"data": "value"}')

        # Scan directory
        found_files = scan_execution_directory(
            execution_dir=tmp_path,
            start_time=start_time
        )

        # Should find nested file
        file_paths = {str(f) for f in found_files}
        assert str(file_in_subdir) in file_paths

    @pytest.mark.asyncio
    async def test_scan_skips_temp_files(self, tmp_path):
        """Test that scanner skips temporary and hidden files."""
        start_time = time()

        # Create temp/hidden files
        temp1 = tmp_path / "file.tmp"
        temp1.write_text("temp")

        temp2 = tmp_path / ".hidden"
        temp2.write_text("hidden")

        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        pyc = pycache / "module.pyc"
        pyc.write_text("bytecode")

        ds_store = tmp_path / ".DS_Store"
        ds_store.write_text("macos")

        # Create valid file
        valid = tmp_path / "valid.txt"
        valid.write_text("valid")

        # Scan directory
        found_files = scan_execution_directory(
            execution_dir=tmp_path,
            start_time=start_time
        )

        # Should only find valid file
        file_paths = {str(f) for f in found_files}
        assert str(valid) in file_paths
        assert str(temp1) not in file_paths
        assert str(temp2) not in file_paths
        assert str(pyc) not in file_paths
        assert str(ds_store) not in file_paths


class TestSkipFileRules:
    """Test file skipping rules."""

    def test_skip_tmp_extension(self):
        """Test that .tmp files are skipped."""
        assert should_skip_file(Path("file.tmp")) is True

    def test_skip_hidden_files(self):
        """Test that hidden files are skipped."""
        assert should_skip_file(Path(".hidden")) is True
        assert should_skip_file(Path(".gitignore")) is True

    def test_skip_pycache(self):
        """Test that __pycache__ files are skipped."""
        assert should_skip_file(Path("__pycache__/module.pyc")) is True

    def test_skip_ds_store(self):
        """Test that .DS_Store files are skipped."""
        assert should_skip_file(Path(".DS_Store")) is True

    def test_dont_skip_valid_files(self):
        """Test that valid files are not skipped."""
        assert should_skip_file(Path("data.csv")) is False
        assert should_skip_file(Path("report.md")) is False
        assert should_skip_file(Path("chart.png")) is False


class TestAutoRegisterScannedFiles:
    """Test automatic registration of scanned files."""

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_register_scanned_files(self, mock_get_context, tmp_path):
        """Test that scanned files are registered as artifacts."""
        from roma_dspy.core.artifacts import ArtifactRegistry

        # Setup mock context
        context = Mock()
        context.execution_id = "test_exec_123"
        context.artifact_registry = ArtifactRegistry()
        mock_get_context.return_value = context

        # Create test files
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("col1,col2\n1,2")

        md_file = tmp_path / "report.md"
        md_file.write_text("# Report")

        # Register files
        count = await auto_register_scanned_files(
            file_paths=[str(csv_file), str(md_file)],
            execution_id="test_exec_123"
        )

        # Should register both
        assert count == 2

        # Verify artifacts in registry
        artifacts = await context.artifact_registry.get_all()
        assert len(artifacts) == 2

        # Check artifact types inferred from extensions
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.DATA_PROCESSED in types
        assert ArtifactType.REPORT in types

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_deduplication_skips_existing(self, mock_get_context, tmp_path):
        """Test that deduplication prevents re-registering existing files."""
        from roma_dspy.core.artifacts import ArtifactRegistry, ArtifactBuilder

        # Setup mock context
        context = Mock()
        context.execution_id = "test_exec_123"
        context.artifact_registry = ArtifactRegistry()
        mock_get_context.return_value = context

        # Create and register file first time
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("col1,col2\n1,2")

        # First registration
        artifact_builder = ArtifactBuilder()
        artifact = await artifact_builder.build(
            name="data",
            artifact_type=ArtifactType.DATA_PROCESSED,
            storage_path=str(csv_file),
            created_by_task="test_exec_123",
            created_by_module="TestModule",
            description="Test data",
            derived_from=[],
        )
        await context.artifact_registry.register(artifact)

        # Try to register same file again
        count = await auto_register_scanned_files(
            file_paths=[str(csv_file)],
            execution_id="test_exec_123"
        )

        # Should skip (count = 0)
        assert count == 0

        # Should still have only 1 artifact
        artifacts = await context.artifact_registry.get_all()
        assert len(artifacts) == 1

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_no_context_returns_zero(self, mock_get_context):
        """Test that missing context returns 0 without error."""
        mock_get_context.return_value = None

        count = await auto_register_scanned_files(
            file_paths=["/tmp/test.txt"],
            execution_id="test_exec_123"
        )

        assert count == 0

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_metadata_includes_scanner_source(self, mock_get_context, tmp_path):
        """Test that registered artifacts include scanner metadata."""
        from roma_dspy.core.artifacts import ArtifactRegistry

        # Setup mock context
        context = Mock()
        context.execution_id = "test_exec_123"
        context.artifact_registry = ArtifactRegistry()
        mock_get_context.return_value = context

        # Create file
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        # Register file
        await auto_register_scanned_files(
            file_paths=[str(test_file)],
            execution_id="test_exec_123"
        )

        # Check metadata
        artifacts = await context.artifact_registry.get_all()
        assert len(artifacts) == 1

        artifact = artifacts[0]
        assert artifact.created_by_module == "filesystem_scanner"
        assert "Auto-detected by filesystem scanner" in artifact.metadata.description


class TestFilesystemScannerIntegration:
    """Integration tests for filesystem scanner."""

    @patch('roma_dspy.core.context.ExecutionContext.get')
    @pytest.mark.asyncio
    async def test_end_to_end_scan_and_register(self, mock_get_context, tmp_path):
        """Test complete workflow: scan directory and register all new files."""
        from roma_dspy.core.artifacts import ArtifactRegistry

        # Setup mock context
        context = Mock()
        context.execution_id = "test_exec_123"
        context.artifact_registry = ArtifactRegistry()
        mock_get_context.return_value = context

        start_time = time()

        # Create various files
        (tmp_path / "data.csv").write_text("col1,col2\n1,2")
        (tmp_path / "report.md").write_text("# Report")
        (tmp_path / "chart.png").write_bytes(b"fake png")
        (tmp_path / "script.py").write_text("print('hello')")

        # Create temp file (should be skipped)
        (tmp_path / "temp.tmp").write_text("temp")

        # Scan and register
        found_files = scan_execution_directory(tmp_path, start_time)
        count = await auto_register_scanned_files(
            file_paths=[str(f) for f in found_files],
            execution_id="test_exec_123"
        )

        # Should register 4 valid files (skip temp)
        assert count == 4

        # Verify all artifacts registered
        artifacts = await context.artifact_registry.get_all()
        assert len(artifacts) == 4

        # Verify correct types inferred
        types = {a.artifact_type for a in artifacts}
        assert ArtifactType.DATA_PROCESSED in types
        assert ArtifactType.REPORT in types
        assert ArtifactType.PLOT in types
        assert ArtifactType.CODE in types
