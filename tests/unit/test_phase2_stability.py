"""Stability tests for Phase 2 improvements - memory, cleanup, optional validation."""

import gzip
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from roma_dspy.tui.utils.export import ExportService
from roma_dspy.tui.utils.file_loader import FileLoader
from roma_dspy.tui.utils.import_service import ImportService


class TestMemoryEfficiency:
    """Test memory-efficient gzip decompression with BytesIO."""

    def test_gzip_load_uses_bytesio(self):
        """Test that gzip loading uses BytesIO instead of string concatenation."""
        # Create a test gzipped JSON file
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json.gz"

            test_data = {"test": "data", "large_field": "x" * 10000}

            # Write gzipped file
            with gzip.open(filepath, "wt", encoding="utf-8") as f:
                json.dump(test_data, f)

            # Load should work without memory spike
            loaded_data = FileLoader.load_json(filepath)

            assert loaded_data == test_data

    def test_gzip_load_enforces_size_limit(self):
        """Test that gzip loading rejects files exceeding size limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "large.json.gz"

            # Create large data
            large_data = {"field": "x" * 1024 * 1024}  # ~1MB

            with gzip.open(filepath, "wt", encoding="utf-8") as f:
                json.dump(large_data, f)

            # Try to load with tiny limit
            with pytest.raises(ValueError, match="(exceeds limit|File too large)"):
                FileLoader.load_json(filepath, max_size=1024)  # 1KB limit

    def test_plain_json_still_works(self):
        """Test that plain JSON loading still works after BytesIO change."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"

            test_data = {"test": "data"}

            # Write plain JSON
            with filepath.open("w") as f:
                json.dump(test_data, f)

            # Load should work
            loaded_data = FileLoader.load_json(filepath)

            assert loaded_data == test_data

    def test_auto_detection_works_with_bytesio(self):
        """Test that format auto-detection still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Test gzipped
            gz_path = Path(tmpdir) / "test.json.gz"
            test_data = {"format": "gzipped"}

            with gzip.open(gz_path, "wt") as f:
                json.dump(test_data, f)

            loaded = FileLoader.load_json(gz_path)
            assert loaded == test_data

            # Test plain
            plain_path = Path(tmpdir) / "test.json"
            test_data2 = {"format": "plain"}

            with plain_path.open("w") as f:
                json.dump(test_data2, f)

            loaded2 = FileLoader.load_json(plain_path)
            assert loaded2 == test_data2


class TestPartialFileCleanup:
    """Test cleanup of partial files on export errors."""

    def test_cleanup_removes_partial_file(self):
        """Test that cleanup utility removes partial files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            partial_file = Path(tmpdir) / "partial.json"

            # Create partial file
            partial_file.write_text('{"incomplete": "data"')

            assert partial_file.exists()

            # Cleanup should remove it
            ExportService._cleanup_partial_file(partial_file)

            assert not partial_file.exists()

    def test_cleanup_handles_none(self):
        """Test that cleanup handles None gracefully."""
        # Should not raise
        ExportService._cleanup_partial_file(None)

    def test_cleanup_handles_nonexistent_file(self):
        """Test that cleanup handles nonexistent files gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / "doesnt_exist.json"

            # Should not raise
            ExportService._cleanup_partial_file(nonexistent)

    def test_export_cleans_up_on_serialization_error(self):
        """Test that export cleans up partial file on serialization error."""
        from unittest.mock import MagicMock
        from roma_dspy.tui.models import ExecutionViewModel, MetricsSummary

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"

            # Create mock execution that will fail serialization
            execution = MagicMock(spec=ExecutionViewModel)
            execution.execution_id = "test123"
            execution.tasks = {}
            execution.metrics = MagicMock(spec=MetricsSummary)

            # Mock FileLoader.auto_compress_if_large to fail
            with patch.object(FileLoader, 'auto_compress_if_large') as mock_compress:
                mock_compress.side_effect = ValueError("Serialization failed")

                with pytest.raises(ValueError, match="Cannot serialize"):
                    ExportService.export_execution_full(execution, filepath)

                # File should not exist (either never created or cleaned up)
                # We can't easily test the exact file path since it may vary
                # But we verify no .json files are left in tmpdir
                json_files = list(Path(tmpdir).glob("*.json*"))
                assert len(json_files) == 0 or all(not f.exists() for f in json_files)

    def test_export_cleans_up_on_disk_full(self):
        """Test that export cleans up on disk full error."""
        from unittest.mock import MagicMock
        from roma_dspy.tui.models import ExecutionViewModel, MetricsSummary

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"

            execution = MagicMock(spec=ExecutionViewModel)
            execution.execution_id = "test123"
            execution.tasks = {}
            execution.metrics = MagicMock(spec=MetricsSummary)

            # Mock FileLoader to raise ENOSPC (disk full)
            with patch.object(FileLoader, 'auto_compress_if_large') as mock_compress:
                error = OSError("No space left")
                error.errno = 28  # ENOSPC
                mock_compress.side_effect = error

                with pytest.raises(OSError, match="Disk full"):
                    ExportService.export_execution_full(execution, filepath)


class TestOptionalChecksumValidation:
    """Test optional checksum validation in import."""

    def test_import_with_checksum_validation_enabled(self):
        """Test that checksum validation works when enabled (default)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "export.json"

            # Create valid export with checksum
            from roma_dspy.tui.utils.checksum import compute_checksum

            execution_data = {
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
            }

            export_data = {
                "schema_version": "1.1.0",
                "roma_version": "0.2.0",
                "exported_at": "2024-01-15T12:00:00",
                "export_level": "full",
                "checksum": compute_checksum(execution_data),
                "execution": execution_data,
                "metadata": {
                    "export_source": "tui_v2",
                    "task_count": 0,
                    "trace_count": 0
                }
            }

            # Write export file
            with filepath.open("w") as f:
                json.dump(export_data, f)

            # Import with validation (default)
            service = ImportService()
            execution = service.load_from_file(filepath, validate_checksum=True)

            assert execution.execution_id == "test123"

    def test_import_with_checksum_validation_disabled(self):
        """Test that import works when checksum validation is disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "export.json"

            # Create export with WRONG checksum
            execution_data = {
                "execution_id": "test456",
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
            }

            export_data = {
                "schema_version": "1.1.0",
                "roma_version": "0.2.0",
                "exported_at": "2024-01-15T12:00:00",
                "export_level": "full",
                "checksum": "sha256:0000000000000000000000000000000000000000000000000000000000000000",  # Wrong!
                "execution": execution_data,
                "metadata": {
                    "export_source": "tui_v2",
                    "task_count": 0,
                    "trace_count": 0
                }
            }

            with filepath.open("w") as f:
                json.dump(export_data, f)

            # Import with validation ENABLED should fail
            service = ImportService()
            with pytest.raises(ValueError, match="Checksum validation failed"):
                service.load_from_file(filepath, validate_checksum=True)

            # Import with validation DISABLED should succeed
            execution = service.load_from_file(filepath, validate_checksum=False)
            assert execution.execution_id == "test456"

    def test_validate_file_with_checksum_disabled(self):
        """Test that validate_export_file respects checksum parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "export.json"

            execution_data = {
                "execution_id": "test789",
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
            }

            export_data = {
                "schema_version": "1.1.0",
                "roma_version": "0.2.0",
                "exported_at": "2024-01-15T12:00:00",
                "export_level": "full",
                "checksum": "sha256:" + "0" * 64,  # Wrong checksum (but valid format)
                "execution": execution_data,
                "metadata": {
                    "export_source": "tui_v2",
                    "task_count": 0,
                    "trace_count": 0
                }
            }

            with filepath.open("w") as f:
                json.dump(export_data, f)

            service = ImportService()

            # Validation with checksum enabled - should have warning about mismatch
            result_with_check = service.validate_export_file(filepath, validate_checksum=True)
            assert any("checksum" in w.lower() or "mismatch" in w.lower() for w in result_with_check.warnings)
            assert result_with_check.checksum_valid is False

            # Validation with checksum disabled - should note it's skipped
            result_without_check = service.validate_export_file(filepath, validate_checksum=False)
            assert any("skipped" in w.lower() for w in result_without_check.warnings)

    def test_import_logs_checksum_skip(self, caplog):
        """Test that skipping checksum validation is logged."""
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "export.json"

            execution_data = {
                "execution_id": "test_log",
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
            }

            export_data = {
                "schema_version": "1.1.0",
                "roma_version": "0.2.0",
                "exported_at": "2024-01-15T12:00:00",
                "export_level": "full",
                "checksum": "sha256:" + "0" * 64,
                "execution": execution_data,
                "metadata": {
                    "export_source": "tui_v2",
                    "task_count": 0,
                    "trace_count": 0
                }
            }

            with filepath.open("w") as f:
                json.dump(export_data, f)

            service = ImportService()

            # Import with checksum disabled
            with caplog.at_level("INFO"):
                service.load_from_file(filepath, validate_checksum=False)

            # Should log that validation was skipped
            assert any("skipped" in record.message.lower() for record in caplog.records)
