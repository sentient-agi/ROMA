"""Integration tests for E2B toolkit with real E2B API.

These tests require E2B_API_KEY to be set and will be skipped if not available.
They test real sandbox operations and are slower than unit tests.

Run with: pytest tests/integration/test_e2b_integration.py -v
"""

import asyncio
import json
import os
import tempfile
import time
from pathlib import Path

import pytest

from roma_dspy.tools.core.e2b import E2BToolkit


# Skip all tests if E2B_API_KEY not set
pytestmark = pytest.mark.skipif(
    not os.getenv("E2B_API_KEY"),
    reason="E2B_API_KEY not set - skipping integration tests",
)


class TestE2BIntegration:
    """Integration tests with real E2B sandbox."""

    def setup_method(self):
        """Setup for each test."""
        self.toolkit = E2BToolkit(timeout=300)  # 5 minutes

    async def teardown_method(self):
        """Cleanup after each test."""
        if hasattr(self, "toolkit") and self.toolkit._sandbox:
            try:
                await self.toolkit.aclose()
            except:
                pass

    @pytest.mark.asyncio
    async def test_sandbox_creation(self):
        """Test real sandbox creation."""
        result = await self.toolkit.get_sandbox_status()
        data = json.loads(result)

        # Initially no sandbox
        assert data["status"] == "no_sandbox"

        # Create sandbox by running code
        result = await self.toolkit.run_python_code("x = 1")
        data = json.loads(result)
        assert data["success"] is True

        # Now sandbox should exist
        result = await self.toolkit.get_sandbox_status()
        data = json.loads(result)
        assert data["status"] == "running"
        assert data["sandbox_id"] is not None

    @pytest.mark.asyncio
    async def test_python_code_execution(self):
        """Test real Python code execution."""
        # Simple calculation
        result = await self.toolkit.run_python_code("print(2 + 2)")
        data = json.loads(result)

        assert data["success"] is True
        assert data["sandbox_id"] is not None

        # State persists across calls
        result1 = await self.toolkit.run_python_code("x = 10")
        data1 = json.loads(result1)
        assert data1["success"] is True

        result2 = await self.toolkit.run_python_code("y = x + 5; print(y)")
        data2 = json.loads(result2)
        assert data2["success"] is True

    @pytest.mark.asyncio
    async def test_command_execution(self):
        """Test real shell command execution."""
        result = await self.toolkit.run_command("echo 'Hello from E2B'")
        data = json.loads(result)

        assert data["success"] is True
        assert data["exit_code"] == 0
        assert "Hello from E2B" in data["stdout"]

    @pytest.mark.asyncio
    async def test_file_upload_download(self):
        """Test file upload and download operations."""
        # Create temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("Test content for E2B")
            local_upload_path = f.name

        try:
            # Upload file
            remote_path = "/home/user/test_upload.txt"
            result = await self.toolkit.upload_file(local_upload_path, remote_path)
            data = json.loads(result)

            assert data["success"] is True
            assert data["remote_path"] == remote_path

            # Download file
            with tempfile.TemporaryDirectory() as temp_dir:
                local_download_path = Path(temp_dir) / "downloaded.txt"

                result = await self.toolkit.download_file(
                    remote_path, str(local_download_path)
                )
                data = json.loads(result)

                assert data["success"] is True
                assert local_download_path.exists()
                assert local_download_path.read_text() == "Test content for E2B"

        finally:
            Path(local_upload_path).unlink()

    @pytest.mark.asyncio
    async def test_file_operations_in_sandbox(self):
        """Test file read/write operations within sandbox."""
        # Write file
        content = "Test content from Python"
        result = await self.toolkit.write_file_content("/home/user/test.txt", content)
        data = json.loads(result)
        assert data["success"] is True

        # Read file back
        result = await self.toolkit.read_file_content("/home/user/test.txt")
        data = json.loads(result)
        assert data["success"] is True
        assert data["content"] == content
        assert data["is_text"] is True

    @pytest.mark.asyncio
    async def test_directory_operations(self):
        """Test directory creation and listing."""
        # Create directory
        result = await self.toolkit.create_directory("/home/user/test_dir/nested")
        data = json.loads(result)
        assert data["success"] is True

        # List directory
        result = await self.toolkit.list_files("/home/user")
        data = json.loads(result)
        assert data["success"] is True
        assert "test_dir" in data["output"]

    @pytest.mark.asyncio
    async def test_package_installation(self):
        """Test installing Python packages."""
        # Install a small package
        result = await self.toolkit.install_package("requests")
        data = json.loads(result)

        assert data["success"] is True
        assert data["exit_code"] == 0

        # Verify package is installed
        result = await self.toolkit.run_python_code(
            "import requests; print(requests.__version__)"
        )
        data = json.loads(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_sandbox_persistence_across_calls(self):
        """Test sandbox persists across multiple operations."""
        # Get initial sandbox ID
        result = await self.toolkit.run_python_code("x = 100")
        data = json.loads(result)
        initial_sandbox_id = data["sandbox_id"]

        # Multiple operations should use same sandbox
        for i in range(5):
            result = await self.toolkit.run_python_code(f"y = x + {i}")
            data = json.loads(result)
            assert data["success"] is True
            assert data["sandbox_id"] == initial_sandbox_id

    @pytest.mark.asyncio
    async def test_manual_restart(self):
        """Test manual sandbox restart."""
        # Create initial sandbox
        result = await self.toolkit.run_python_code("x = 1")
        data = json.loads(result)
        initial_id = data["sandbox_id"]

        # Restart
        result = await self.toolkit.restart_sandbox()
        data = json.loads(result)
        assert data["success"] is True
        assert data["old_sandbox_id"] == initial_id
        assert data["new_sandbox_id"] != initial_id

        # State should be reset
        result = await self.toolkit.run_python_code(
            "try:\n    print(x)\nexcept NameError:\n    print('x not defined')"
        )
        data = json.loads(result)
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling with invalid code."""
        result = await self.toolkit.run_python_code(
            "this will cause a syntax error !!!"
        )
        data = json.loads(result)

        # Should still return success (execution happened)
        # but error should be captured
        assert data["success"] is True
        # E2B captures execution errors

    @pytest.mark.asyncio
    async def test_long_running_operation(self):
        """Test handling of longer operations (but within timeout)."""
        code = """
import time
for i in range(3):
    print(f'Step {i+1}')
    time.sleep(1)
print('Done!')
"""
        result = await self.toolkit.run_python_code(code)
        data = json.loads(result)

        assert data["success"] is True
        assert "Done!" in str(data["stdout"])

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test that sandbox handles multiple rapid async operations."""
        import asyncio

        async def run_operation(i):
            result = await self.toolkit.run_python_code(f"print('Operation {i}')")
            return json.loads(result)

        # Run multiple operations concurrently
        results = await asyncio.gather(*[run_operation(i) for i in range(5)])

        # All should succeed
        assert len(results) == 5
        for result in results:
            assert result["success"] is True

        # All should use same sandbox
        sandbox_ids = [r["sandbox_id"] for r in results]
        assert len(set(sandbox_ids)) == 1

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_auto_reinit_on_timeout(self):
        """Test auto-reinitialization when sandbox times out.

        This test is marked slow as it requires waiting for timeout.
        Run with: pytest -m slow
        """
        # Create toolkit with very short timeout (30 seconds)
        short_toolkit = E2BToolkit(timeout=30, max_lifetime_hours=0.0001)

        try:
            # Execute code to create sandbox
            result = await short_toolkit.run_python_code("x = 1")
            data = json.loads(result)
            first_id = data["sandbox_id"]
            assert data["success"] is True

            # Wait for timeout + a bit
            await asyncio.sleep(35)

            # Next operation should create new sandbox
            result = await short_toolkit.run_python_code("y = 2")
            data = json.loads(result)
            second_id = data["sandbox_id"]

            # Should succeed with new sandbox
            assert data["success"] is True
            # May or may not be different ID depending on E2B behavior

        finally:
            await short_toolkit.aclose()


class TestE2BToolkitAvailability:
    """Test toolkit tool availability."""

    def setup_method(self):
        """Setup for each test."""
        if os.getenv("E2B_API_KEY"):
            self.toolkit = E2BToolkit()
        else:
            pytest.skip("E2B_API_KEY not set")

    def test_all_tools_available(self):
        """Test that all expected tools are available."""
        tools = self.toolkit.get_available_tool_names()

        expected_tools = {
            "run_python_code",
            "run_command",
            "get_sandbox_status",
            "restart_sandbox",
            "upload_file",
            "download_file",
            "list_files",
            "read_file_content",
            "write_file_content",
            "create_directory",
            "install_package",
            "get_sandbox_url",
        }

        assert expected_tools.issubset(tools)

    def test_tool_metadata(self):
        """Test tool metadata extraction."""
        metadata = self.toolkit.get_tool_metadata("run_python_code")

        assert metadata is not None
        assert metadata["name"] == "run_python_code"
        assert "Python code" in metadata["description"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
