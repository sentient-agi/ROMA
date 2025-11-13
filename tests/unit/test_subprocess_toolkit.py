"""
Tests for SubprocessTerminalToolkit with venv support.
"""

import asyncio
import shlex
import tempfile
from pathlib import Path
from textwrap import dedent
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from roma_dspy.config.schemas.storage import StorageConfig
from roma_dspy.core.storage.file_storage import FileStorage
from roma_dspy.tools.terminal.subprocess_toolkit import SubprocessTerminalToolkit


@pytest.fixture
def mock_file_storage():
    """Create a mock FileStorage for testing."""
    storage = MagicMock(spec=FileStorage)
    storage.execution_id = "test_exec_123"
    storage.put_json = AsyncMock()
    storage.put_text = AsyncMock()
    return storage


@pytest.fixture
def temp_working_dir():
    """Create a temporary working directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def toolkit_no_venv(mock_file_storage, temp_working_dir):
    """Create toolkit without venv."""
    return SubprocessTerminalToolkit(
        file_storage=mock_file_storage,
        working_directory=temp_working_dir
    )


@pytest.fixture
def toolkit_with_venv(mock_file_storage, temp_working_dir):
    """Create toolkit with venv."""
    return SubprocessTerminalToolkit(
        file_storage=mock_file_storage,
        working_directory=temp_working_dir,
        venv_path="/opt/roma-venv"
    )


class TestSubprocessTerminalToolkit:
    """Test SubprocessTerminalToolkit functionality."""

    @pytest.mark.asyncio
    async def test_execute_command_without_venv(self, toolkit_no_venv):
        """Test basic command execution without venv."""
        result = await toolkit_no_venv.execute_command("echo 'hello'")

        assert "hello" in result
        assert toolkit_no_venv._command_counter == 1

    @pytest.mark.asyncio
    async def test_execute_command_with_venv_activation(self, toolkit_with_venv):
        """Test that venv is activated for commands."""
        # Mock the subprocess to verify the command includes venv activation
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            await toolkit_with_venv.execute_command("pip list")

            # Verify subprocess was called with venv activation
            call_args = mock_subprocess.call_args
            command = call_args[0][0]

            assert ". /opt/roma-venv/bin/activate" in command
            assert "pip list" in command
            assert "&&" in command  # Commands chained with &&

    @pytest.mark.asyncio
    async def test_execute_python_uses_venv(self, toolkit_with_venv):
        """Test that execute_python uses explicit venv Python binary."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"42\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await toolkit_with_venv.execute_python("print(6*7)")

            # Verify explicit venv Python binary is used
            call_args = mock_subprocess.call_args
            command = call_args[0][0]

            assert "/opt/roma-venv/bin/python -c" in command
            assert "42" in result

    @pytest.mark.asyncio
    async def test_command_logging(self, toolkit_no_venv, mock_file_storage):
        """Test that commands are logged to FileStorage."""
        await toolkit_no_venv.execute_command("echo 'test'")

        # Verify logging was called
        assert mock_file_storage.put_json.called
        assert mock_file_storage.put_text.called

    @pytest.mark.asyncio
    async def test_timeout_handling(self, toolkit_no_venv):
        """Test command timeout handling."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_process.kill = MagicMock()
            mock_process.wait = AsyncMock()
            mock_subprocess.return_value = mock_process

            result = await toolkit_no_venv.execute_command("sleep 1000", timeout_sec=0.1)

            assert "timed out" in result.lower()
            assert mock_process.kill.called

    @pytest.mark.asyncio
    async def test_stderr_capture(self, toolkit_no_venv):
        """Test that stderr is captured and included in output."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"stdout\n", b"stderr\n")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            result = await toolkit_no_venv.execute_command("test")

            assert "stdout" in result
            assert "[STDERR]" in result
            assert "stderr" in result

    @pytest.mark.asyncio
    async def test_working_directory(self, toolkit_no_venv, temp_working_dir):
        """Test that working directory is used."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            await toolkit_no_venv.execute_command("pwd")

            # Verify cwd parameter was passed
            call_kwargs = mock_subprocess.call_args[1]
            assert call_kwargs["cwd"] == temp_working_dir

    @pytest.mark.asyncio
    async def test_command_counter_increments(self, toolkit_no_venv):
        """Test that command counter increments."""
        assert toolkit_no_venv._command_counter == 0

        await toolkit_no_venv.execute_command("echo 1")
        assert toolkit_no_venv._command_counter == 1

        await toolkit_no_venv.execute_command("echo 2")
        assert toolkit_no_venv._command_counter == 2

    @pytest.mark.asyncio
    async def test_error_handling(self, toolkit_no_venv):
        """Test error handling for failed commands."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_subprocess.side_effect = Exception("Test error")

            result = await toolkit_no_venv.execute_command("failing_command")

            assert "failed with error" in result.lower()

    @pytest.mark.asyncio
    async def test_python_code_escaping(self, toolkit_no_venv):
        """Test that Python code is properly escaped for shell."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            # Code with special characters
            code = 'print("hello\'s world")'
            await toolkit_no_venv.execute_python(code)

            # Verify the code was properly escaped
            call_args = mock_subprocess.call_args
            command = call_args[0][0]
            assert "python3 -c" in command


class TestVenvIntegration:
    """Integration tests for venv functionality."""

    @pytest.mark.asyncio
    async def test_venv_activation_format(self, toolkit_with_venv):
        """Test that venv activation uses correct format."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            await toolkit_with_venv.execute_command("test")

            call_args = mock_subprocess.call_args
            command = call_args[0][0]

            # Must use . (dot) not source for POSIX compatibility
            assert ". /opt/roma-venv/bin/activate" in command
            assert "source" not in command

    @pytest.mark.asyncio
    async def test_multiple_commands_with_venv(self, toolkit_with_venv):
        """Test multiple commands all use venv."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            commands = ["pip list", "python --version", "pip install pandas"]

            for cmd in commands:
                await toolkit_with_venv.execute_command(cmd)

                # Verify each command includes venv activation
                call_args = mock_subprocess.call_args
                command = call_args[0][0]
                assert ". /opt/roma-venv/bin/activate" in command
                assert cmd in command


@pytest.mark.integration
class TestRealExecution:
    """Real execution tests (only run if enabled)."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not Path("/opt/roma-venv").exists(),
        reason="Requires /opt/roma-venv to exist"
    )
    async def test_real_venv_activation(self, mock_file_storage):
        """Test real venv activation (integration test)."""
        toolkit = SubprocessTerminalToolkit(
            file_storage=mock_file_storage,
            working_directory="/tmp",
            venv_path="/opt/roma-venv"
        )

        # Test that python command uses venv
        result = await toolkit.execute_command("which python")
        assert "/opt/roma-venv" in result

    @pytest.mark.asyncio
    async def test_real_command_execution(self, mock_file_storage):
        """Test real command execution without venv."""
        toolkit = SubprocessTerminalToolkit(
            file_storage=mock_file_storage,
            working_directory="/tmp"
        )

        result = await toolkit.execute_command("echo 'hello world'")
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_real_python_execution(self, mock_file_storage):
        """Test real Python code execution."""
        toolkit = SubprocessTerminalToolkit(
            file_storage=mock_file_storage,
            working_directory="/tmp"
        )

        result = await toolkit.execute_python("print(2 + 2)")
        assert "4" in result

    @pytest.mark.asyncio
    async def test_pip_install_and_import_round_trip(self, tmp_path):
        """
        Run real pip install of a local package plus follow-up commands.

        Ensures SubprocessTerminalToolkit can handle package installation,
        then run additional commands that rely on the installed artifacts.
        """
        storage_config = StorageConfig(
            base_path=str(tmp_path / "storage"),
            flat_structure=True
        )
        storage = FileStorage(storage_config, execution_id="pip_exec")
        toolkit = SubprocessTerminalToolkit(
            file_storage=storage,
            working_directory=str(tmp_path)
        )

        # Create minimal local package (src layout + setup.cfg)
        package_dir = tmp_path / "dummy_pkg_src"
        package_dir.mkdir()
        (package_dir / "pyproject.toml").write_text(dedent("""
            [build-system]
            requires = ["setuptools", "wheel"]
            build-backend = "setuptools.build_meta"
        """).strip())
        (package_dir / "setup.cfg").write_text(dedent("""
            [metadata]
            name = dummy-toolkit-pkg
            version = 0.0.1
            description = Dummy package for subprocess toolkit tests

            [options]
            package_dir =
                =src
            packages = find:
            python_requires = >=3.8

            [options.packages.find]
            where = src
        """).strip())
        src_pkg = package_dir / "src" / "dummy_pkg"
        src_pkg.mkdir(parents=True)
        (src_pkg / "__init__.py").write_text("VALUE = 'dummy-installed'\n")

        install_target = tmp_path / "site_packages"
        install_target.mkdir(parents=True, exist_ok=True)

        install_cmd = (
            f"python3 -m pip install --no-deps --no-build-isolation "
            f"--target {shlex.quote(str(install_target))} "
            f"{shlex.quote(str(package_dir))}"
        )

        install_output = await toolkit.execute_command(install_cmd, timeout_sec=120)
        installed_init = install_target / "dummy_pkg" / "__init__.py"

        assert installed_init.exists(), "pip install did not create target package"
        assert (
            "Successfully installed" in install_output
            or "Installing collected packages" in install_output
        ), install_output

        # Run python code that imports the new package from the custom target
        python_code = dedent(f"""
            import sys
            sys.path.insert(0, "{install_target.as_posix()}")
            import dummy_pkg
            print(dummy_pkg.VALUE)
        """).strip()
        python_output = await toolkit.execute_python(python_code)
        assert "dummy-installed" in python_output

        # Run an additional pip-related command to ensure subsequent commands work
        pip_version = await toolkit.execute_command("python3 -m pip --version")
        assert "pip" in pip_version.lower()
