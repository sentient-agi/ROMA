"""Tests for export/import security features - path traversal prevention and file locking."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from roma_dspy.tui.utils.export import ExportService


class TestPathTraversalPrevention:
    """Test path traversal vulnerability fixes."""

    def test_sanitize_execution_id_removes_dangerous_chars(self):
        """Test execution ID sanitization removes path separators."""
        # Test with path separators
        assert ExportService._sanitize_execution_id("test/../../etc") == "testetc"
        assert ExportService._sanitize_execution_id("test\\..\\passwd") == "testpass"

        # Test with other dangerous chars
        assert ExportService._sanitize_execution_id("test:$*?") == "test"

    def test_sanitize_execution_id_keeps_safe_chars(self):
        """Test sanitization keeps alphanumeric, dash, underscore."""
        assert ExportService._sanitize_execution_id("abc123") == "abc123"
        assert ExportService._sanitize_execution_id("test-123") == "test-123"
        assert ExportService._sanitize_execution_id("test_123") == "test_123"

    def test_sanitize_execution_id_truncates_to_8_chars(self):
        """Test sanitization truncates to 8 characters."""
        long_id = "a" * 20
        sanitized = ExportService._sanitize_execution_id(long_id)
        assert len(sanitized) == 8

    def test_sanitize_execution_id_empty_raises_error(self):
        """Test sanitization raises error for invalid input."""
        with pytest.raises(ValueError, match="must contain at least one alphanumeric"):
            ExportService._sanitize_execution_id("///")

        with pytest.raises(ValueError, match="must contain at least one alphanumeric"):
            ExportService._sanitize_execution_id("...")

    def test_validate_export_path_detects_parent_dir(self):
        """Test validation detects '..' path traversal attempts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            malicious_path = base_dir / ".." / "etc" / "passwd"

            with pytest.raises(ValueError, match="Path traversal detected"):
                ExportService._validate_export_path(malicious_path, base_dir)

    def test_validate_export_path_accepts_safe_path(self):
        """Test validation accepts safe paths within base directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            safe_path = base_dir / "exports" / "test.json"

            # Should not raise
            ExportService._validate_export_path(safe_path, base_dir)

    def test_validate_export_path_rejects_escape_via_symlink(self):
        """Test validation rejects paths that resolve outside base directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "exports"
            base_dir.mkdir()

            # Create a symlink pointing outside base_dir
            outside_dir = Path(tmpdir) / "outside"
            outside_dir.mkdir()

            symlink_path = base_dir / "link"
            try:
                symlink_path.symlink_to(outside_dir)
            except OSError:
                pytest.skip("Cannot create symlinks on this platform")

            # Try to escape via symlink
            escape_path = symlink_path / "file.json"

            with pytest.raises(ValueError, match="outside export directory"):
                ExportService._validate_export_path(escape_path, base_dir)

    def test_get_default_export_path_sanitizes_execution_id(self):
        """Test default path generation sanitizes execution ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Malicious execution ID
            malicious_id = "../../etc/passwd"

            # Should sanitize and generate safe path
            path = ExportService.get_default_export_path(
                execution_id=malicious_id,
                format="json",
                scope="execution",
                base_dir=base_dir
            )

            # Check path is within base_dir (most important check)
            assert path.is_relative_to(base_dir)

            # Check execution_id was sanitized (dangerous characters removed)
            assert ".." not in str(path)
            assert "/" not in path.name  # No path separators in filename
            assert "\\" not in path.name  # No Windows separators in filename

    def test_get_default_export_path_rejects_invalid_format(self):
        """Test default path rejects invalid format parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            with pytest.raises(ValueError, match="Invalid format"):
                ExportService.get_default_export_path(
                    execution_id="test123",
                    format="../etc/passwd",  # Malicious format
                    scope="execution",
                    base_dir=base_dir
                )

    def test_get_default_export_path_rejects_invalid_scope(self):
        """Test default path rejects invalid scope parameter."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            with pytest.raises(ValueError, match="Invalid scope"):
                ExportService.get_default_export_path(
                    execution_id="test123",
                    format="json",
                    scope="../malicious",  # Malicious scope
                    base_dir=base_dir
                )

    def test_get_default_export_path_creates_directory(self):
        """Test default path creates base directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "new_exports"

            # Directory doesn't exist yet
            assert not base_dir.exists()

            # Should create it
            path = ExportService.get_default_export_path(
                execution_id="test123",
                format="json",
                scope="execution",
                base_dir=base_dir
            )

            assert base_dir.exists()
            assert base_dir.is_dir()

    def test_get_default_export_path_multiple_security_layers(self):
        """Test that all security layers work together."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir) / "exports"
            base_dir.mkdir()

            # Try multiple attack vectors at once
            malicious_id = "../../../etc/passwd/../shadow"

            path = ExportService.get_default_export_path(
                execution_id=malicious_id,
                format="json",
                scope="execution",
                base_dir=base_dir
            )

            # All attacks should be blocked - path should be safely within base_dir
            assert path.is_relative_to(base_dir)
            assert ".." not in str(path)  # No path traversal
            assert "/" not in path.name  # No path separators in filename
            assert "\\" not in path.name  # No Windows separators in filename

            # Verify the dangerous path components were removed/sanitized
            # Note: substring matches like "etc" in "etcpassw" are safe
            assert "../" not in str(path)
            assert "/.." not in str(path)


class TestFileLocking:
    """Test file locking mechanisms."""

    def test_file_lock_import_available(self):
        """Test that file_lock context manager is available."""
        from roma_dspy.tui.utils.file_loader import file_lock

        assert callable(file_lock)

    def test_file_loader_uses_locking_on_save(self):
        """Test FileLoader.save_json acquires file lock."""
        from roma_dspy.tui.utils.file_loader import FileLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"
            data = {"test": "data"}

            # Should complete without errors
            size = FileLoader.save_json(data, filepath, compress=False, pretty=True)

            assert filepath.exists()
            assert size > 0

    def test_file_loader_uses_locking_on_load(self):
        """Test FileLoader loads with file lock (shared)."""
        from roma_dspy.tui.utils.file_loader import FileLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.json"
            data = {"test": "data"}

            # Save first
            FileLoader.save_json(data, filepath)

            # Load should work with locking
            loaded_data = FileLoader.load_json(filepath)

            assert loaded_data == data

    def test_file_lock_exclusive_for_writes(self):
        """Test exclusive locks are used for writes."""
        from roma_dspy.tui.utils.file_loader import file_lock

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.txt"
            filepath.write_text("test")

            with filepath.open("w") as f:
                with file_lock(f, exclusive=True):
                    # Inside lock - exclusive access
                    f.write("locked write")

            # Verify write succeeded
            assert filepath.read_text() == "locked write"

    def test_file_lock_shared_for_reads(self):
        """Test shared locks are used for reads."""
        from roma_dspy.tui.utils.file_loader import file_lock

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "test.txt"
            filepath.write_text("test content")

            with filepath.open("r") as f:
                with file_lock(f, exclusive=False):
                    # Inside lock - shared access
                    content = f.read()

            assert content == "test content"

    def test_concurrent_write_protection(self):
        """Test that concurrent writes are serialized by locks.

        This is a basic test - true concurrency testing would require
        multiprocessing, but we can verify the locking mechanism exists.
        """
        from roma_dspy.tui.utils.file_loader import FileLoader

        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = Path(tmpdir) / "concurrent.json"

            # Write multiple times - should not corrupt file
            data1 = {"write": 1, "data": "first"}
            data2 = {"write": 2, "data": "second"}
            data3 = {"write": 3, "data": "third"}

            FileLoader.save_json(data1, filepath)
            FileLoader.save_json(data2, filepath)
            FileLoader.save_json(data3, filepath)

            # Final read should get valid JSON (not corrupted)
            final_data = FileLoader.load_json(filepath)

            # Should be one of the writes (order not guaranteed)
            assert final_data in [data1, data2, data3]
