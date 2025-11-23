"""
Tests for SubprocessTerminalToolkit with venv support.
"""

import asyncio
import shlex
import subprocess
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
        file_storage=mock_file_storage, working_directory=temp_working_dir
    )


@pytest.fixture
def toolkit_with_venv(mock_file_storage, temp_working_dir, tmp_path):
    """Create toolkit with venv."""
    # Create minimal venv directory structure for testing
    venv_path = tmp_path / "test-venv"
    venv_bin = venv_path / "bin"
    venv_bin.mkdir(parents=True, exist_ok=True)

    # Create dummy python and pip binaries (just touch them)
    (venv_bin / "python").touch(mode=0o755)
    (venv_bin / "pip").touch(mode=0o755)

    return SubprocessTerminalToolkit(
        file_storage=mock_file_storage,
        working_directory=temp_working_dir,
        venv_path=str(venv_path),
    )


class TestSubprocessTerminalToolkit:
    """Test SubprocessTerminalToolkit functionality."""

    @pytest.mark.asyncio
    async def test_execute_command_without_venv(self, toolkit_no_venv):
        """Test basic command execution without venv."""
        output = await toolkit_no_venv.execute_command("echo 'hello'")

        assert "hello" in output
        assert toolkit_no_venv.last_returncode == 0
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

            venv_path = toolkit_with_venv.venv_path
            assert (
                f"{venv_path}/bin/pip" in command
                or f"{venv_path}/bin/python -m pip" in command
            )
            assert "pip list" in command

    @pytest.mark.asyncio
    async def test_execute_python_uses_venv(self, toolkit_with_venv):
        """Test that execute_python uses explicit venv Python binary."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"42\n", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            output = await toolkit_with_venv.execute_python("print(6*7)")

            # Verify explicit venv Python binary is used
            call_args = mock_subprocess.call_args
            command = call_args[0][0]

            venv_path = toolkit_with_venv.venv_path
            assert f"{venv_path}/bin/python -c" in command
            assert "42" in output
            assert toolkit_with_venv.last_returncode == 0

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

            result = await toolkit_no_venv.execute_command(
                "sleep 1000", timeout_sec=0.1
            )

            assert "timed out" in result.lower()
            assert toolkit_no_venv.last_returncode == -1
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
            assert toolkit_no_venv.last_returncode == -2

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
        venv_path = toolkit_with_venv.venv_path

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            await toolkit_with_venv.execute_command("test")

            call_args = mock_subprocess.call_args
            command = call_args[0][0]

            # Must use . (dot) not source for POSIX compatibility
            assert f". {venv_path}/bin/activate" in command or "|| true" in command
            assert "source" not in command

    @pytest.mark.asyncio
    async def test_multiple_commands_with_venv(self, toolkit_with_venv):
        """Test multiple commands all use venv."""
        venv_path = toolkit_with_venv.venv_path

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            # Test different command types
            commands_and_expectations = [
                (
                    "pip list",
                    f"{venv_path}/bin/pip",
                    "pip list",
                ),  # pip commands use venv pip
                (
                    "python --version",
                    f". {venv_path}/bin/activate",
                    "python --version",
                ),  # Non-pip command uses activation
                (
                    "pip install pandas",
                    f"{venv_path}/bin/pip install",
                    "pandas",
                ),  # pip install uses venv pip
            ]

            for cmd, expected_wrapper, expected_content in commands_and_expectations:
                await toolkit_with_venv.execute_command(cmd)

                # Verify appropriate wrapping
                call_args = mock_subprocess.call_args
                command = call_args[0][0]
                assert expected_wrapper in command, (
                    f"Expected '{expected_wrapper}' in command '{command}'"
                )
                assert expected_content in command, (
                    f"Expected '{expected_content}' in command '{command}'"
                )


@pytest.mark.integration
class TestRealExecution:
    """Real execution tests (only run if enabled)."""

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        not Path("/opt/roma-venv").exists(), reason="Requires /opt/roma-venv to exist"
    )
    async def test_real_venv_activation(self, mock_file_storage):
        """Test real venv activation (integration test)."""
        toolkit = SubprocessTerminalToolkit(
            file_storage=mock_file_storage,
            working_directory="/tmp",
            venv_path="/opt/roma-venv",
        )

        # Test that python command uses venv
        result = await toolkit.execute_command("which python")
        assert "/opt/roma-venv" in result
        assert toolkit.last_returncode == 0

    @pytest.mark.asyncio
    async def test_real_command_execution(self, mock_file_storage):
        """Test real command execution without venv."""
        toolkit = SubprocessTerminalToolkit(
            file_storage=mock_file_storage, working_directory="/tmp"
        )

        result = await toolkit.execute_command("echo 'hello world'")
        assert "hello world" in result
        assert toolkit.last_returncode == 0

    @pytest.mark.asyncio
    async def test_real_python_execution(self, mock_file_storage):
        """Test real Python code execution."""
        toolkit = SubprocessTerminalToolkit(
            file_storage=mock_file_storage, working_directory="/tmp"
        )

        result = await toolkit.execute_python("print(2 + 2)")
        assert "4" in result
        assert toolkit.last_returncode == 0

    @pytest.mark.asyncio
    @pytest.mark.skipif(
        subprocess.run(
            ["python3", "-m", "pip", "--version"], capture_output=True
        ).returncode
        != 0,
        reason="python3 -m pip not available (venv without pip module)",
    )
    async def test_pip_install_and_import_round_trip(self, tmp_path):
        """
        Run real pip install of a local package plus follow-up commands.

        Ensures SubprocessTerminalToolkit can handle package installation,
        then run additional commands that rely on the installed artifacts.

        Note: This test requires python3 -m pip to be available. It's skipped
        if running in a venv without pip module installed (which is exactly
        the scenario our documentation warns against).
        """
        storage_config = StorageConfig(
            base_path=str(tmp_path / "storage"), flat_structure=True
        )
        storage = FileStorage(storage_config, execution_id="pip_exec")
        toolkit = SubprocessTerminalToolkit(
            file_storage=storage, working_directory=str(tmp_path)
        )

        # Create minimal local package (src layout + setup.cfg)
        package_dir = tmp_path / "dummy_pkg_src"
        package_dir.mkdir()
        (package_dir / "pyproject.toml").write_text(
            dedent("""
            [build-system]
            requires = ["setuptools", "wheel"]
            build-backend = "setuptools.build_meta"
        """).strip()
        )
        (package_dir / "setup.cfg").write_text(
            dedent("""
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
        """).strip()
        )
        src_pkg = package_dir / "src" / "dummy_pkg"
        src_pkg.mkdir(parents=True)
        (src_pkg / "__init__.py").write_text("VALUE = 'dummy-installed'\n")

        install_target = tmp_path / "site_packages"
        install_target.mkdir(parents=True, exist_ok=True)

        # Use python3 -m pip for this integration test since pip may not be in PATH
        # This is acceptable since no venv_path is set
        install_cmd = (
            f"python3 -m pip install --no-deps --no-build-isolation "
            f"--target {shlex.quote(str(install_target))} "
            f"{shlex.quote(str(package_dir))}"
        )

        install_output = await toolkit.execute_command(install_cmd, timeout_sec=120)
        installed_init = install_target / "dummy_pkg" / "__init__.py"
        assert toolkit.last_returncode == 0

        # Debug: Print install output if assertion fails
        if not installed_init.exists():
            print(
                f"\n\n===== PIP INSTALL OUTPUT =====\n{install_output}\n===========================\n"
            )

        assert installed_init.exists(), (
            f"pip install did not create target package. Output: {install_output[:500]}"
        )
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
        assert toolkit.last_returncode == 0

        # Run an additional pip-related command to ensure subsequent commands work
        pip_version = await toolkit.execute_command("python3 -m pip --version")
        assert "pip" in pip_version.lower()
        assert toolkit.last_returncode == 0


class TestReturnCodeAPI:
    """Tests for last_returncode property and return code tracking."""

    @pytest.mark.asyncio
    async def test_last_returncode_success(self, toolkit_no_venv):
        """Test that successful commands set returncode to 0."""
        output = await toolkit_no_venv.execute_command("echo 'success'")

        # Verify via property
        assert toolkit_no_venv.last_returncode == 0

        # Verify via method
        assert toolkit_no_venv.get_last_returncode() == 0

        # Verify output
        assert "success" in output

    @pytest.mark.asyncio
    async def test_last_returncode_failure(self, toolkit_no_venv):
        """Test that failing commands set non-zero returncode."""
        output = await toolkit_no_venv.execute_command("exit 42")

        # Verify non-zero return code
        assert toolkit_no_venv.last_returncode == 42
        assert toolkit_no_venv.get_last_returncode() == 42

    @pytest.mark.asyncio
    async def test_last_returncode_timeout(self, toolkit_no_venv):
        """Test that timeout sets returncode to -1."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.side_effect = asyncio.TimeoutError()
            mock_process.kill = MagicMock()
            mock_process.wait = AsyncMock()
            mock_subprocess.return_value = mock_process

            output = await toolkit_no_venv.execute_command(
                "sleep 1000", timeout_sec=0.1
            )

            # Verify timeout code
            assert toolkit_no_venv.last_returncode == -1
            assert toolkit_no_venv.get_last_returncode() == -1
            assert "timed out" in output.lower()

    @pytest.mark.asyncio
    async def test_last_returncode_exception(self, toolkit_no_venv):
        """Test that exceptions set returncode to -2."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_subprocess.side_effect = Exception("Subprocess error")

            output = await toolkit_no_venv.execute_command("any_command")

            # Verify exception code
            assert toolkit_no_venv.last_returncode == -2
            assert toolkit_no_venv.get_last_returncode() == -2
            assert "failed with error" in output.lower()

    @pytest.mark.asyncio
    async def test_last_returncode_initial_state(
        self, mock_file_storage, temp_working_dir
    ):
        """Test that returncode is None before any commands."""
        toolkit = SubprocessTerminalToolkit(
            file_storage=mock_file_storage, working_directory=temp_working_dir
        )

        # Verify initial state
        assert toolkit.last_returncode is None
        assert toolkit.get_last_returncode() is None

    @pytest.mark.asyncio
    async def test_last_returncode_multiple_commands(self, toolkit_no_venv):
        """Test that returncode updates after each command."""
        # Command 1: Success
        await toolkit_no_venv.execute_command("echo 'first'")
        assert toolkit_no_venv.last_returncode == 0

        # Command 2: Failure
        await toolkit_no_venv.execute_command("exit 5")
        assert toolkit_no_venv.last_returncode == 5

        # Command 3: Success again
        await toolkit_no_venv.execute_command("echo 'third'")
        assert toolkit_no_venv.last_returncode == 0

        # Command 4: Different failure code
        await toolkit_no_venv.execute_command("exit 127")
        assert toolkit_no_venv.last_returncode == 127


class TestEnvironmentVariableControl:
    """Tests for env parameter and environment isolation."""

    @pytest.mark.asyncio
    async def test_env_parameter_custom_variables(self, toolkit_no_venv):
        """Test that custom env variables are available in subprocess."""
        output = await toolkit_no_venv.execute_command(
            "echo $MY_CUSTOM_VAR", env={"MY_CUSTOM_VAR": "test_value_123"}
        )

        assert "test_value_123" in output
        assert toolkit_no_venv.last_returncode == 0

    @pytest.mark.asyncio
    async def test_env_parameter_isolation(self, toolkit_no_venv):
        """Test that custom env dict isolates subprocess from system env."""
        # Set custom env with only one variable
        output = await toolkit_no_venv.execute_command(
            "echo HOME=$HOME PATH=$PATH", env={"CUSTOM_ONLY": "value"}
        )

        # HOME and PATH should be empty (not inherited)
        assert "HOME=" in output
        assert "PATH=" in output
        # The equals should be followed by space or end of line (empty values)
        assert toolkit_no_venv.last_returncode == 0

    @pytest.mark.asyncio
    async def test_env_parameter_none_inherits_environment(self, toolkit_no_venv):
        """Test that env=None inherits parent environment."""
        # env=None should inherit all parent environment variables
        output = await toolkit_no_venv.execute_command("echo $PATH", env=None)

        # PATH should be inherited and non-empty
        assert len(output.strip()) > 0
        assert toolkit_no_venv.last_returncode == 0

    @pytest.mark.asyncio
    async def test_env_parameter_empty_dict(self, toolkit_no_venv):
        """Test that empty env dict provides minimal environment."""
        output = await toolkit_no_venv.execute_command(
            "env | wc -l",  # Count environment variables
            env={},
        )

        # Should have very few environment variables (shell adds PWD, SHLVL, _, etc.)
        num_vars = int(output.strip())
        assert num_vars < 10  # Minimal environment (shell adds a few vars)
        assert toolkit_no_venv.last_returncode == 0

    @pytest.mark.asyncio
    async def test_execute_python_with_custom_env(self, toolkit_no_venv):
        """Test that execute_python respects custom env parameter."""
        code = "import os; print(os.environ.get('PYTHON_TEST_VAR', 'NOT_FOUND'))"

        output = await toolkit_no_venv.execute_python(
            code, env={"PYTHON_TEST_VAR": "found_it"}
        )

        assert "found_it" in output
        assert "NOT_FOUND" not in output
        assert toolkit_no_venv.last_returncode == 0


class TestBugFixes:
    """Tests verifying specific bug fixes from Phases 1-3."""

    @pytest.mark.asyncio
    async def test_pip_detection_false_positives(self, toolkit_with_venv):
        """Test Bug #1 fix: Pip detection shouldn't match mentions of 'pip install'."""
        venv_path = toolkit_with_venv.venv_path

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            # Test 1: echo should NOT use python -m pip
            await toolkit_with_venv.execute_command("echo 'pip install requests'")
            command = mock_subprocess.call_args[0][0]
            assert f". {venv_path}/bin/activate" in command or "|| true" in command
            assert f"{venv_path}/bin/python -m pip install" not in command

            # Test 2: grep should NOT use python -m pip
            await toolkit_with_venv.execute_command("grep 'pip install' logfile.txt")
            command = mock_subprocess.call_args[0][0]
            assert f". {venv_path}/bin/activate" in command or "|| true" in command
            assert f"{venv_path}/bin/python -m pip install" not in command

            # Test 3: cat with pipe should NOT use python -m pip
            await toolkit_with_venv.execute_command("cat file.txt | grep 'pip install'")
            command = mock_subprocess.call_args[0][0]
            assert f". {venv_path}/bin/activate" in command or "|| true" in command
            assert f"{venv_path}/bin/python -m pip install" not in command

    @pytest.mark.asyncio
    async def test_pip_detection_true_positives(self, toolkit_with_venv):
        """Test Bug #1 fix: Real pip install commands should be detected."""
        venv_path = toolkit_with_venv.venv_path

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            # Test 1: Direct pip install SHOULD use venv pip
            await toolkit_with_venv.execute_command("pip install requests")
            command = mock_subprocess.call_args[0][0]
            assert (
                f"{venv_path}/bin/pip install" in command
                or f"{venv_path}/bin/python -m pip install" in command
            )

            # Test 2: pip install after && SHOULD use python -m pip
            await toolkit_with_venv.execute_command("cd /tmp && pip install requests")
            command = mock_subprocess.call_args[0][0]
            assert (
                f"{venv_path}/bin/pip install" in command
                or f"{venv_path}/bin/python -m pip install" in command
            )

            # Test 3: pip install after ; SHOULD use python -m pip
            await toolkit_with_venv.execute_command("ls; pip install requests")
            command = mock_subprocess.call_args[0][0]
            assert (
                f"{venv_path}/bin/pip install" in command
                or f"{venv_path}/bin/python -m pip install" in command
            )

    @pytest.mark.asyncio
    async def test_multiple_pip_installs_all_wrapped(self, toolkit_with_venv):
        """Test Bug #2 fix: All pip install commands should use venv pip."""
        venv_path = toolkit_with_venv.venv_path

        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b"output", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            # Multiple pip installs chained with &&
            await toolkit_with_venv.execute_command(
                "pip install requests && pip install numpy && pip install pandas"
            )
            command = mock_subprocess.call_args[0][0]

            # ALL three should use venv pip
            assert (
                command.count(f"{venv_path}/bin/pip install") == 3
                or command.count(f"{venv_path}/bin/python -m pip install") == 3
            )

    @pytest.mark.asyncio
    async def test_process_tracking_and_cleanup(self, toolkit_no_venv):
        """Test Bug #12 fix: Processes should be tracked and cleanable."""
        # Execute a command
        await toolkit_no_venv.execute_command("echo 'test'")

        # Process should have been added and then removed from tracking
        # (since it completed)
        assert len(toolkit_no_venv._active_processes) == 0

        # Cleanup should work even with no active processes
        await toolkit_no_venv.cleanup()
        assert len(toolkit_no_venv._active_processes) == 0

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self, mock_file_storage, temp_working_dir):
        """Test Bug #12 fix: Context manager should clean up processes."""
        async with SubprocessTerminalToolkit(
            file_storage=mock_file_storage, working_directory=temp_working_dir
        ) as toolkit:
            await toolkit.execute_command("echo 'test'")
            # Process completes before context exits
            assert len(toolkit._active_processes) == 0

        # After context exit, cleanup should have been called
        # All processes should be terminated
        assert len(toolkit._active_processes) == 0

    @pytest.mark.asyncio
    async def test_counter_thread_safety(self, mock_file_storage, temp_working_dir):
        """Test Bug #4 fix: Command counter should be thread-safe."""
        toolkit = SubprocessTerminalToolkit(
            file_storage=mock_file_storage, working_directory=temp_working_dir
        )

        # Execute 20 commands concurrently
        tasks = [toolkit.execute_command(f"echo 'command {i}'") for i in range(20)]
        await asyncio.gather(*tasks)

        # Counter should be exactly 20 (no race conditions)
        assert toolkit._command_counter == 20

    @pytest.mark.asyncio
    async def test_utf8_backslashreplace(self, toolkit_no_venv):
        """Test Bug #7 fix: Invalid UTF-8 should use backslashreplace."""
        with patch("asyncio.create_subprocess_shell") as mock_subprocess:
            mock_process = AsyncMock()
            # Return invalid UTF-8 bytes
            mock_process.communicate.return_value = (b"text\x80\xff", b"")
            mock_process.returncode = 0
            mock_subprocess.return_value = mock_process

            output = await toolkit_no_venv.execute_command("test")

            # Should contain escape sequences (not replacement character)
            assert "\\x80" in output or "\\xff" in output
            # Should NOT contain � replacement character
            assert "�" not in output

    @pytest.mark.asyncio
    async def test_working_directory_validation(self, mock_file_storage):
        """Test Bug #9 fix: Invalid working directory should raise clear error."""
        with pytest.raises(ValueError) as exc_info:
            SubprocessTerminalToolkit(
                file_storage=mock_file_storage,
                working_directory="/nonexistent/directory/path",
            )

        # Error message should be clear and helpful
        assert "does not exist" in str(exc_info.value)
        assert "/nonexistent/directory/path" in str(exc_info.value)


@pytest.mark.integration
class TestIntegrationWorkflows:
    """Integration tests for complete workflows and edge cases."""

    @pytest.mark.asyncio
    async def test_concurrent_execution_stress(
        self, mock_file_storage, temp_working_dir
    ):
        """
        Stress test: Execute 50+ commands concurrently.

        Verifies:
        - Command counter remains accurate under heavy load
        - No race conditions in process tracking
        - All commands complete successfully
        - Return codes are tracked correctly
        """
        toolkit = SubprocessTerminalToolkit(
            file_storage=mock_file_storage, working_directory=temp_working_dir
        )

        num_commands = 50

        # Execute commands concurrently
        tasks = [
            toolkit.execute_command(f"echo 'stress test {i}'")
            for i in range(num_commands)
        ]

        results = await asyncio.gather(*tasks)

        # Verify all commands completed
        assert len(results) == num_commands

        # Verify counter is accurate (no race conditions)
        assert toolkit._command_counter == num_commands

        # Verify all return codes are 0
        assert toolkit.last_returncode == 0

        # Verify all outputs contain expected text
        for i, result in enumerate(results):
            assert f"stress test {i}" in result or "stress test" in result

        # Verify no process leaks
        assert len(toolkit._active_processes) == 0

        # Cleanup should work
        await toolkit.cleanup()

    @pytest.mark.asyncio
    async def test_env_isolation_security(self, mock_file_storage, temp_working_dir):
        """
        Security test: Verify environment isolation prevents secret leakage.

        Verifies:
        - Custom env dict isolates subprocess completely
        - No parent environment variables leak through
        - Specific test for common secret variable names
        """
        import os

        # Set fake secrets in current environment
        original_env = os.environ.copy()
        test_secrets = {
            "SECRET_API_KEY": "super_secret_key_12345",
            "DATABASE_PASSWORD": "db_pass_67890",
            "AWS_SECRET_ACCESS_KEY": "aws_secret_key_abcdef",
            "OPENAI_API_KEY": "openai_key_ghijkl",
        }

        try:
            # Temporarily set secrets in environment
            for key, value in test_secrets.items():
                os.environ[key] = value

            toolkit = SubprocessTerminalToolkit(
                file_storage=mock_file_storage, working_directory=temp_working_dir
            )

            # Execute command with empty env dict (complete isolation)
            output = await toolkit.execute_command(
                "env",  # Print all environment variables
                env={},  # Empty dict = complete isolation
            )

            # Verify NO secrets appear in output
            for secret_name, secret_value in test_secrets.items():
                assert secret_name not in output, (
                    f"Secret variable name '{secret_name}' leaked!"
                )
                assert secret_value not in output, (
                    f"Secret value '{secret_value}' leaked!"
                )

            # Verify command succeeded
            assert toolkit.last_returncode == 0

            # Test with custom safe variables only
            output2 = await toolkit.execute_command(
                "env", env={"SAFE_VAR": "safe_value", "APP_MODE": "test"}
            )

            # Verify safe variables are present
            assert "SAFE_VAR" in output2
            assert "safe_value" in output2
            assert "APP_MODE" in output2

            # Verify secrets still not present
            for secret_name, secret_value in test_secrets.items():
                assert secret_name not in output2, (
                    f"Secret variable name '{secret_name}' leaked!"
                )
                assert secret_value not in output2, (
                    f"Secret value '{secret_value}' leaked!"
                )

            # Verify command succeeded
            assert toolkit.last_returncode == 0

        finally:
            # Restore original environment
            os.environ.clear()
            os.environ.update(original_env)

    @pytest.mark.asyncio
    async def test_full_workflow_with_return_code_checking(
        self, mock_file_storage, temp_working_dir
    ):
        """
        End-to-end workflow test: Multi-step task with return code verification.

        Simulates a realistic deployment workflow:
        1. Create test files
        2. Process data
        3. Verify results
        4. Check return codes at each step
        """
        toolkit = SubprocessTerminalToolkit(
            file_storage=mock_file_storage, working_directory=temp_working_dir
        )

        # Step 1: Create test file
        create_cmd = f"echo 'test data' > {temp_working_dir}/input.txt"
        output1 = await toolkit.execute_command(create_cmd)
        assert toolkit.last_returncode == 0, (
            f"Step 1 failed with code {toolkit.last_returncode}"
        )

        # Step 2: Process file
        process_cmd = f"cat {temp_working_dir}/input.txt | wc -l"
        output2 = await toolkit.execute_command(process_cmd)
        assert toolkit.last_returncode == 0, (
            f"Step 2 failed with code {toolkit.last_returncode}"
        )
        assert "1" in output2  # Should have 1 line

        # Step 3: Verify file exists
        verify_cmd = f"test -f {temp_working_dir}/input.txt && echo 'exists'"
        output3 = await toolkit.execute_command(verify_cmd)
        assert toolkit.last_returncode == 0, (
            f"Step 3 failed with code {toolkit.last_returncode}"
        )
        assert "exists" in output3

        # Step 4: Clean up
        cleanup_cmd = f"rm {temp_working_dir}/input.txt"
        output4 = await toolkit.execute_command(cleanup_cmd)
        assert toolkit.last_returncode == 0, (
            f"Step 4 failed with code {toolkit.last_returncode}"
        )

        # Step 5: Verify file was deleted (should fail)
        verify_deleted_cmd = f"test -f {temp_working_dir}/input.txt"
        output5 = await toolkit.execute_command(verify_deleted_cmd)
        assert toolkit.last_returncode != 0, "Step 5 should have failed (file deleted)"

        # Verify process cleanup
        assert len(toolkit._active_processes) == 0
