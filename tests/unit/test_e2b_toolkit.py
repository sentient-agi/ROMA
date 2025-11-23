"""Tests for E2B toolkit."""

import asyncio
import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from roma_dspy.tools.core.e2b import E2BToolkit


class MockExecution:
    """Mock execution result from E2B sandbox."""

    def __init__(self, results=None, stdout=None, stderr=None, error=None):
        self.results = results or [Mock(text="42")]
        self.logs = Mock()
        self.logs.stdout = stdout or []
        self.logs.stderr = stderr or []
        self.error = error


class MockCommandResult:
    """Mock command result for E2B commands.run()."""

    def __init__(self, exit_code=0, stdout="", stderr="", error=None):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr
        self.error = error


class MockAsyncSandbox:
    """Mock E2B AsyncSandbox for testing."""

    def __init__(self, sandbox_id="test-sandbox-123"):
        self.sandbox_id = sandbox_id
        self._running = True
        self.files = AsyncMock()
        self.commands = AsyncMock()

    async def is_running(self):
        """Mock async is_running check."""
        return self._running

    async def run_code(self, code):
        """Mock async code execution."""
        return MockExecution()

    async def kill(self):
        """Mock async sandbox kill."""
        self._running = False

    def get_host(self, port):
        """Mock get_host (this one is sync in E2B SDK)."""
        return f"https://test-sandbox.e2b.dev:{port}"


@pytest.fixture
def mock_e2b():
    """Mock E2B module for all tests."""
    # Mock the import at the builtins level
    mock_sandbox_class = AsyncMock()
    # Make create() return a MockAsyncSandbox instance
    mock_sandbox_class.create = AsyncMock(return_value=MockAsyncSandbox())

    mock_e2b_module = Mock()
    mock_e2b_module.AsyncSandbox = mock_sandbox_class

    with patch.dict("sys.modules", {"e2b_code_interpreter": mock_e2b_module}):
        yield mock_sandbox_class


class TestE2BToolkit:
    """Test E2BToolkit functionality."""

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    def test_initialization_with_api_key(self, mock_e2b):
        """Test toolkit initialization with API key."""
        toolkit = E2BToolkit(timeout=600)

        assert toolkit.api_key == "test_api_key_12345"
        assert toolkit.timeout == 600
        assert (
            toolkit.template == "roma-dspy-sandbox"
        )  # Default template when no E2B_TEMPLATE_ID is set
        assert toolkit.auto_reinitialize is True

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_api_key(self, mock_e2b):
        """Test toolkit fails without API key."""
        with pytest.raises(ValueError, match="E2B_API_KEY is required"):
            E2BToolkit()

    @patch.dict(os.environ, {"E2B_API_KEY": "test_key"})
    def test_missing_dependency(self):
        """Test toolkit fails without e2b library."""
        # Mock the e2b_code_interpreter import to fail
        with patch.dict("sys.modules", {"e2b_code_interpreter": None}):
            with pytest.raises(
                ImportError, match="e2b-code-interpreter library is required"
            ):
                E2BToolkit()

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_create_sandbox(self, mock_e2b):
        """Test sandbox creation."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()

        async with toolkit._lock:
            sandbox = await toolkit._create_sandbox()

        assert sandbox == mock_sandbox
        assert toolkit._sandbox_id == "test-sandbox-123"
        assert toolkit._created_at > 0

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_ensure_sandbox_alive_creates_if_none(self, mock_e2b):
        """Test _ensure_sandbox_alive creates sandbox if none exists."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()
        sandbox = await toolkit._ensure_sandbox_alive()

        assert sandbox is not None
        assert toolkit._sandbox_id == "test-sandbox-123"

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_ensure_sandbox_alive_returns_running_sandbox(self, mock_e2b):
        """Test _ensure_sandbox_alive returns existing running sandbox."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()
        await toolkit._ensure_sandbox_alive()
        create_calls = mock_e2b.create.call_count

        sandbox = await toolkit._ensure_sandbox_alive()

        assert sandbox == mock_sandbox
        assert mock_e2b.create.call_count == create_calls

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_ensure_sandbox_alive_reinitializes_dead_sandbox(self, mock_e2b):
        """Test _ensure_sandbox_alive reinitializes dead sandbox."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()
        await toolkit._ensure_sandbox_alive()

        mock_sandbox._running = False
        new_mock_sandbox = MockAsyncSandbox("new-sandbox-456")
        mock_e2b.create.return_value = new_mock_sandbox

        sandbox = await toolkit._ensure_sandbox_alive()

        assert sandbox == new_mock_sandbox
        assert toolkit._sandbox_id == "new-sandbox-456"

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_run_python_code(self, mock_e2b):
        """Test Python code execution."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()
        result = await toolkit.run_python_code("print('hello')")
        data = json.loads(result)

        assert data["success"] is True
        assert "42" in data["results"]
        assert data["sandbox_id"] == "test-sandbox-123"

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_run_python_code_error_handling(self, mock_e2b):
        """Test error handling in code execution."""
        mock_sandbox = AsyncMock()
        mock_sandbox.sandbox_id = "test-sandbox-123"
        mock_sandbox.is_running.return_value = True
        mock_sandbox.run_code.side_effect = Exception("Execution failed")
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()
        result = await toolkit.run_python_code("bad code")
        data = json.loads(result)

        assert data["success"] is False
        assert "Execution failed" in data["error"]

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_run_command(self, mock_e2b):
        """Test command execution."""
        mock_sandbox = MockAsyncSandbox()
        mock_result = MockCommandResult(exit_code=0, stdout="Success!", stderr="")
        mock_sandbox.commands.run.return_value = mock_result
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()
        result = await toolkit.run_command("echo hello")
        data = json.loads(result)

        assert data["success"] is True
        assert data["exit_code"] == 0
        assert data["stdout"] == "Success!"

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_get_sandbox_status_no_sandbox(self, mock_e2b):
        """Test status when no sandbox exists."""
        toolkit = E2BToolkit()
        result = await toolkit.get_sandbox_status()
        data = json.loads(result)

        assert data["success"] is True
        assert data["status"] == "no_sandbox"

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_get_sandbox_status_running(self, mock_e2b):
        """Test status of running sandbox."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()
        await toolkit._ensure_sandbox_alive()

        result = await toolkit.get_sandbox_status()
        data = json.loads(result)

        assert data["success"] is True
        assert data["status"] == "running"
        assert data["sandbox_id"] == "test-sandbox-123"

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_restart_sandbox(self, mock_e2b):
        """Test manual sandbox restart."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()
        await toolkit._ensure_sandbox_alive()
        old_id = toolkit._sandbox_id

        new_sandbox = MockAsyncSandbox("restarted-sandbox")
        mock_e2b.create.return_value = new_sandbox

        result = await toolkit.restart_sandbox()
        data = json.loads(result)

        assert data["success"] is True
        assert data["old_sandbox_id"] == old_id

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_upload_file(self, mock_e2b):
        """Test file upload to sandbox."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            toolkit = E2BToolkit()
            result = await toolkit.upload_file(temp_path, "/home/user/test.txt")
            data = json.loads(result)

            assert data["success"] is True
            assert data["remote_path"] == "/home/user/test.txt"
        finally:
            Path(temp_path).unlink()

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_download_file(self, mock_e2b):
        """Test file download from sandbox."""
        mock_sandbox = MockAsyncSandbox()
        mock_sandbox.files.read.return_value = b"downloaded content"
        mock_e2b.create.return_value = mock_sandbox

        with tempfile.TemporaryDirectory() as temp_dir:
            local_path = Path(temp_dir) / "downloaded.txt"
            toolkit = E2BToolkit()
            result = await toolkit.download_file("/home/user/file.txt", str(local_path))
            data = json.loads(result)

            assert data["success"] is True
            assert local_path.exists()

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_thread_safety(self, mock_e2b):
        """Test async-safe concurrent operations."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()

        async def run_code():
            result = await toolkit.run_python_code("x = 1")
            return result

        results = await asyncio.gather(*[run_code() for _ in range(5)])

        assert len(results) == 5
        for result in results:
            data = json.loads(result)
            assert data["success"] is True

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_cleanup_on_destruction(self, mock_e2b):
        """Test sandbox cleanup via aclose()."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit()
        await toolkit._ensure_sandbox_alive()

        await toolkit.aclose()

        assert mock_sandbox._running is False

    @patch.dict(os.environ, {"E2B_API_KEY": "test_api_key_12345"})
    @pytest.mark.asyncio
    async def test_auto_reinitialize_disabled(self, mock_e2b):
        """Test behavior when auto_reinitialize is disabled."""
        mock_sandbox = MockAsyncSandbox()
        mock_e2b.create.return_value = mock_sandbox

        toolkit = E2BToolkit(auto_reinitialize=False)
        await toolkit._ensure_sandbox_alive()

        mock_sandbox._running = False

        with pytest.raises(RuntimeError, match="Sandbox died"):
            await toolkit._ensure_sandbox_alive()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
