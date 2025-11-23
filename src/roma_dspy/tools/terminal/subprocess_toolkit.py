"""
Clean subprocess-based terminal toolkit.

Pure subprocess execution with no external dependencies (no terminal-bench, no tmux).
Designed for Terminal-Bench InstalledAgent where ROMA runs inside containers.

⚠️  SECURITY WARNING ⚠️
====================
This toolkit executes arbitrary shell commands and Python code with the same
privileges as the Python process. NEVER pass untrusted user input to
execute_command() or execute_python() without proper validation and sanitization.

Security Risks:
- Command Injection: Shell metacharacters (;, &&, |, $, etc.) enable arbitrary command execution
- Code Execution: execute_python() runs arbitrary Python code
- Privilege Escalation: Commands run with process privileges (potentially root in containers)
- Environment Leakage: All environment variables (including secrets) are passed to subprocesses
- Resource Exhaustion: No built-in limits on CPU, memory, or process count

Safe Usage:
- Only use with trusted input or in sandboxed environments
- Validate and sanitize all input before passing to commands
- Run with minimal required privileges
- Use resource limits (containers, cgroups) to prevent DoS
- Filter environment variables to prevent secret leakage

Example Usage:
    # Basic usage with return code checking
    toolkit = SubprocessTerminalToolkit(file_storage=file_storage)
    output = await toolkit.execute_command("ls -la")
    if toolkit.last_returncode == 0:
        print("Command succeeded:", output)

    result = await toolkit.execute_python("print(2+2)")
    if toolkit.last_returncode != 0:
        print("Python execution failed!")

    # Context manager (recommended - automatic cleanup)
    async with SubprocessTerminalToolkit(file_storage=storage) as toolkit:
        output = await toolkit.execute_command("ls -la")
        # Processes automatically cleaned up on exit

    # LLM Agent Pattern: Install packages then use them
    # ✅ CORRECT: Use execute_command with 'pip install' (not 'python -m pip')
    output = await toolkit.execute_command("pip install requests numpy")
    if toolkit.last_returncode != 0:
        raise RuntimeError(f"Package installation failed: {output}")

    # ✅ THEN: Use execute_python for your logic
    result = await toolkit.execute_python('''
import requests
import numpy as np
print("Packages work!")
''')
    if toolkit.last_returncode != 0:
        raise RuntimeError(f"Python execution failed: {result}")

    # ❌ WRONG: Don't use 'python3 -m pip install'
    output = await toolkit.execute_command("python3 -m pip install requests")  # ❌ Will fail!

    # ❌ WRONG: Don't install packages inside execute_python code
    result = await toolkit.execute_python('''
import subprocess
subprocess.check_call(['pip', 'install', 'requests'])  # ❌ Will fail!
''')

    # ❌ DANGEROUS: Never pass unsanitized user input
    user_input = request.get_param("file")  # Could be "; rm -rf /"
    output = await toolkit.execute_command(f"cat {user_input}")  # ❌ COMMAND INJECTION!
"""

import asyncio
import json
import os
import re
import shlex
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Set

from loguru import logger

from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.core.storage.file_storage import FileStorage


class SubprocessTerminalToolkit(BaseToolkit):
    """Subprocess terminal execution toolkit."""

    REQUIRES_FILE_STORAGE = True
    """
    Pure subprocess-based terminal toolkit.

    Executes commands via asyncio.create_subprocess_shell with proper:
    - Working directory management
    - Timeout handling
    - Output capture (stdout + stderr)
    - Structured logging to FileStorage

    All interactions logged to artifacts/terminal/ directory.

    Attributes:
        file_storage: FileStorage for artifact logging
        working_directory: Working directory for command execution
        _command_counter: Counter for command tracking
    """

    def __init__(
        self,
        file_storage: FileStorage,
        working_directory: str = "/app",
        venv_path: Optional[str] = None,
        **kwargs,
    ):
        """
        Initialize subprocess terminal toolkit.

        Args:
            file_storage: FileStorage instance for artifact logging
            working_directory: Working directory for commands (default: /app)
            venv_path: Path to Python virtual environment (e.g., /opt/roma-venv)
            **kwargs: Additional toolkit configuration

        Raises:
            ValueError: If working_directory doesn't exist or venv_path is invalid
        """
        super().__init__(file_storage=file_storage, **kwargs)

        # Validate working directory exists
        working_dir_path = Path(working_directory)
        if not working_dir_path.exists():
            raise ValueError(
                f"working_directory '{working_directory}' does not exist. "
                f"Create the directory or provide a valid path."
            )
        if not working_dir_path.is_dir():
            raise ValueError(
                f"working_directory '{working_directory}' is not a directory."
            )

        # Validate venv_path if provided
        if venv_path:
            venv_path_obj = Path(venv_path)
            python_bin = venv_path_obj / "bin" / "python"
            pip_bin = venv_path_obj / "bin" / "pip"

            if not venv_path_obj.exists():
                logger.warning(
                    f"venv_path '{venv_path}' does not exist. "
                    f"Commands may fail. Create venv or remove venv_path parameter."
                )
            elif not python_bin.exists():
                logger.warning(
                    f"venv_path provided but {python_bin} doesn't exist. "
                    f"execute_python() will fail. Ensure venv is properly created."
                )
            elif not pip_bin.exists():
                logger.warning(
                    f"venv_path provided but {pip_bin} doesn't exist. "
                    f"pip install commands will fail. Ensure venv has pip installed."
                )

        self.file_storage = file_storage
        self.working_directory = working_directory
        self.venv_path = venv_path
        self._command_counter = 0
        self._counter_lock = asyncio.Lock()  # Thread-safe counter
        self._active_processes: Set[asyncio.subprocess.Process] = (
            set()
        )  # Process tracking
        self._last_returncode: Optional[int] = None  # For return code API

        logger.info(
            f"SubprocessTerminalToolkit initialized "
            f"(execution_id={file_storage.execution_id}, cwd={working_directory}, venv={venv_path})"
        )

    @property
    def last_returncode(self) -> Optional[int]:
        """Return the exit code from the most recent command."""
        return self._last_returncode

    def get_last_returncode(self) -> Optional[int]:
        """Backward compatible accessor for the last process return code."""
        return self._last_returncode

    def _setup_dependencies(self) -> None:
        """No external dependencies to setup."""
        pass

    def _initialize_tools(self) -> None:
        """Tools auto-discovered via BaseToolkit._register_all_tools()."""
        logger.debug("SubprocessTerminalToolkit tools initialized")

    def _is_pip_install_command(self, command: str) -> bool:
        """
        Detect actual pip install commands, not just mentions of "pip install".

        Returns True only if the command actually executes pip install,
        not if it just contains the string "pip install" (e.g., in echo, grep, comments).

        Args:
            command: Command to check

        Returns:
            bool: True if this is an actual pip install command

        Examples:
            >>> self._is_pip_install_command("pip install requests")
            True
            >>> self._is_pip_install_command("python && pip install requests")
            True
            >>> self._is_pip_install_command("echo 'pip install requests'")
            False
            >>> self._is_pip_install_command("grep 'pip install' logfile")
            False
        """
        stripped = command.strip()

        # Direct pip install at start
        if stripped.startswith("pip install"):
            return True

        # pip install after command separators (&&, ;, |)
        # Use word boundaries to ensure 'pip' is a separate command
        if re.search(r"[;&|]\s*pip\s+install\b", command):
            return True

        return False

    def _is_pip_command(self, command: str) -> bool:
        """Detect commands that invoke pip (any subcommand)."""
        stripped = command.strip()

        if stripped.startswith("pip "):
            return True

        if re.search(r"[;&|]\s*pip\s+\w+", command):
            return True

        return False

    def _rewrite_pip_command(self, command: str) -> str:
        """Route pip invocations to venv pip or python -m pip when venv_path is set."""
        if not self.venv_path:
            return command

        pip_exe = Path(self.venv_path) / "bin" / "pip"
        python_exe = Path(self.venv_path) / "bin" / "python"

        replacement = f"{python_exe} -m pip"
        if pip_exe.exists():
            replacement = str(pip_exe)

        # Replace pip at start or after command separators
        pattern = r"(^|[;&|])\s*pip(?=\s)"

        def _sub(match: re.Match) -> str:
            prefix = match.group(1)
            spacer = " " if prefix else ""
            return f"{prefix}{spacer}{replacement}"

        return re.sub(pattern, _sub, command)

    async def _store_command_log(
        self,
        command: str,
        output: str,
        duration_sec: float,
        returncode: Optional[int] = None,
        is_error: bool = False,
    ) -> None:
        """
        Store command execution metadata to FileStorage.

        Args:
            command: Executed command
            output: Command output
            duration_sec: Execution duration
            returncode: Process return code
            is_error: Whether command failed

        Note:
            Command counter may have gaps if storage fails. This is expected behavior.
        """
        # Capture timestamp once for consistency
        timestamp = datetime.utcnow()

        # Thread-safe counter increment
        async with self._counter_lock:
            self._command_counter += 1
            command_id = self._command_counter

        # Store individual command log entry (JSONL approach with separate files)
        log_entry = {
            "command_id": command_id,
            "timestamp": timestamp.isoformat(),
            "command": command,
            "output_length": len(output),
            "duration_sec": round(duration_sec, 3),
            "returncode": returncode,
            "is_error": is_error,
        }

        try:
            # Use unique filename with microseconds to prevent collisions
            log_file = f"terminal/commands/{command_id:04d}_{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.json"
            await self.file_storage.put_json(key=log_file, obj=log_entry)
        except Exception as e:
            logger.warning(f"Failed to write command log: {e}")

        # Store output to separate file (using same timestamp)
        output_file = (
            f"terminal/outputs/{command_id:04d}_{timestamp.strftime('%H%M%S_%f')}.txt"
        )
        try:
            await self.file_storage.put_text(key=output_file, text=output)
        except Exception as e:
            logger.warning(f"Failed to write command output: {e}")

    async def execute_command(
        self,
        command: str,
        timeout_sec: float = 180.0,
        env: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Execute bash command via subprocess.

        ⚠️  SECURITY WARNING: This method executes commands directly in a shell.
        NEVER pass untrusted user input to this method without sanitization.
        Commands are executed with the same privileges as the Python process.

        Vulnerabilities:
        - Shell injection via metacharacters (;, &&, |, $, `, etc.)
        - Arbitrary command execution
        - Path traversal
        - Environment variable exposure

        Use this method for:
        - Installing packages: pip install, apt-get, brew, etc.
        - Running shell commands: ls, mkdir, git, curl, etc.
        - System operations: file management, process control, etc.

        Args:
            command: Bash command to execute (MUST be trusted input only)
            timeout_sec: Maximum execution time in seconds (default: 180s)
            env: Optional environment variables dict. If None, inherits current environment.
                 Use this to filter secrets or provide custom variables.

        Returns:
            str: Combined stdout and stderr as string. Check
                `toolkit.last_returncode` (or `get_last_returncode()`) for the
                associated process exit code (0 = success, non-zero = error).

        Example:
            >>> toolkit = SubprocessTerminalToolkit(file_storage=storage)

            >>> # File operations - check return code
            >>> output = await toolkit.execute_command("ls -la")
            >>> if toolkit.last_returncode == 0:
            ...     print("Success:", output)

            >>> # ✅ CORRECT: Installing Python packages
            >>> output = await toolkit.execute_command("pip install requests numpy pandas")
            >>> if toolkit.last_returncode != 0:
            ...     print("Installation failed!")
            >>> # Then use execute_python() to import and use the packages

            >>> # Environment variable control (security improvement)
            >>> output = await toolkit.execute_command(
            ...     "echo $MY_VAR",
            ...     env={"MY_VAR": "safe_value"}  # Only pass allowed variables
            ... )

            >>> # ❌ WRONG: Don't use 'python3 -m pip install'
            >>> await toolkit.execute_command("python3 -m pip install requests")
            >>> # This fails because venv's Python doesn't have pip as a module!
            >>> # Use 'pip install' instead (shown above)

            >>> # Git operations
            >>> output = await toolkit.execute_command("git status")

            >>> # ❌ DANGEROUS: Shell injection vulnerability
            >>> user_file = input("Enter filename: ")  # User enters: "; rm -rf /"
            >>> await toolkit.execute_command(f"cat {user_file}")  # ❌ EXECUTES rm -rf /!
            >>> # Instead, validate/sanitize input or use shlex.quote()
        """
        # Initialize process to None to avoid NameError in exception handlers
        process = None

        try:
            logger.debug(
                f"[CMD {self._command_counter + 1:04d}] Executing: {command[:100]} "
                f"(cwd={self.working_directory}, timeout={timeout_sec}s)"
            )

            # Wrap command with venv-aware pip or activation
            if self.venv_path:
                venv_python = Path(self.venv_path) / "bin" / "python"
                venv_exists = venv_python.exists()

                if self._is_pip_command(command):
                    wrapped_command = self._rewrite_pip_command(command)
                    if not venv_exists:
                        logger.debug(
                            f"Venv python not found at {venv_python}, using python -m pip fallback"
                        )
                else:
                    wrapped_command = f". {self.venv_path}/bin/activate 2>/dev/null || true; {command}"
            else:
                wrapped_command = command

            # Prepare environment variables
            if env is None:
                # Inherit current environment
                command_env = os.environ.copy()
            else:
                # Use provided environment (security: only specified vars)
                command_env = env

            # Create subprocess
            start_time = datetime.utcnow()
            process = await asyncio.create_subprocess_shell(
                wrapped_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory,
                env=command_env,
            )

            # Track active process for cleanup
            self._active_processes.add(process)

            # Wait for completion with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout_sec
            )
            duration = (datetime.utcnow() - start_time).total_seconds()

            # Remove from active processes
            self._active_processes.discard(process)

            # Combine stdout and stderr
            output = stdout.decode("utf-8", errors="backslashreplace")
            if "�" in output or "\\x" in output:
                logger.warning(
                    f"Command output contained invalid UTF-8 bytes (preserved as escape sequences)"
                )

            if stderr:
                error_output = stderr.decode("utf-8", errors="backslashreplace")
                if error_output.strip():
                    output += f"\n[STDERR]\n{error_output}"

            # Store return code for API access
            self._last_returncode = process.returncode

            # Log to FileStorage
            await self._store_command_log(
                command=command,
                output=output,
                duration_sec=duration,
                returncode=process.returncode,
                is_error=(process.returncode != 0),
            )

            logger.debug(
                f"[CMD {self._command_counter:04d}] Completed "
                f"(returncode={process.returncode}, {len(output)} chars, {duration:.2f}s)"
            )

            return output

        except asyncio.TimeoutError:
            error_msg = f"Command timed out after {timeout_sec}s: {command}"
            logger.error(f"[CMD {self._command_counter + 1:04d}] {error_msg}")

            # Try to kill the process if it exists
            if process is not None:
                try:
                    process.kill()
                    await process.wait()
                    self._active_processes.discard(process)
                except Exception:
                    pass

            # Log timeout
            await self._store_command_log(
                command=command,
                output=error_msg,
                duration_sec=timeout_sec,
                returncode=None,
                is_error=True,
            )

            # Return special code -1 for timeout
            self._last_returncode = -1
            return error_msg

        except Exception as e:
            error_msg = f"Command failed with error: {e}"
            logger.error(
                f"[CMD {self._command_counter + 1:04d}] {error_msg}", exc_info=True
            )

            # Log error
            await self._store_command_log(
                command=command,
                output=error_msg,
                duration_sec=0.0,
                returncode=None,
                is_error=True,
            )

            # Return special code -2 for exception
            self._last_returncode = -2
            return error_msg

    async def execute_python(
        self,
        code: str,
        timeout_sec: float = 180.0,
        env: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Execute Python code via python -c.

        Uses the Python interpreter from venv_path if configured, otherwise falls back to python3.
        This ensures pip-installed packages are available in the same Python environment.

        IMPORTANT for LLM agents:
        - Use this ONLY for Python logic, NOT for installing packages
        - To install packages, use execute_command("pip install package") first
        - Then use this method to import and use those packages

        Args:
            code: Python code to execute (must be valid Python)
            timeout_sec: Maximum execution time in seconds (default: 180s)
            env: Optional environment variables dict. If None, inherits current environment.

        Returns:
            str: Python stdout/stderr as string. Inspect
                `toolkit.last_returncode` for success/failure state.

        Example:
            >>> # ✅ CORRECT: Basic Python execution with return code check
            >>> output = await toolkit.execute_python("print(2+2)")
            >>> if toolkit.last_returncode == 0:
            ...     print("Success:", output)
            >>> # Output: Success: 4

            >>> # ✅ CORRECT: Import packages installed via execute_command
            >>> await toolkit.execute_command("pip install requests")
            >>> output = await toolkit.execute_python('''
            ... import requests
            ... response = requests.get('https://api.github.com')
            ... print(response.status_code)
            ... ''')
            >>> if toolkit.last_returncode != 0:
            ...     print("Python code failed!")

            >>> # ✅ CORRECT: Custom environment variables
            >>> output = await toolkit.execute_python(
            ...     "import os; print(os.environ.get('MY_VAR'))",
            ...     env={"MY_VAR": "test_value"}
            ... )

            >>> # ❌ WRONG: Don't install packages inside execute_python
            >>> result = await toolkit.execute_python('''
            ... import subprocess
            ... subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests'])
            ... ''')
            >>> # This will FAIL with "No module named pip" error!
            >>> # Instead, use: await toolkit.execute_command("pip install requests")

            >>> # ❌ ALSO WRONG: Don't use 'python3 -m pip' in execute_command
            >>> await toolkit.execute_command("python3 -m pip install requests")
            >>> # This also fails with "No module named pip" in venv contexts!
            >>> # Use: await toolkit.execute_command("pip install requests")
        """
        # Use explicit Python interpreter from venv if available
        # This ensures the same Python environment as pip install
        if self.venv_path:
            venv_python = Path(self.venv_path) / "bin" / "python"
            if venv_python.exists():
                python_bin = str(venv_python)
                logger.debug(f"Using venv Python: {python_bin}")
            else:
                python_bin = "python3"
                logger.debug(
                    f"Venv Python not found at {venv_python}, using system python3"
                )
        else:
            python_bin = "python3"

        # Properly escape code for shell using shlex.quote
        escaped_code = shlex.quote(code)
        command = f"{python_bin} -c {escaped_code}"

        logger.info(f"Executing Python code with {python_bin}: {code[:100]}...")

        return await self.execute_command(
            command=command, timeout_sec=timeout_sec, env=env
        )

    async def cleanup(self) -> None:
        """
        Cleanup all active processes.

        Terminates all running subprocesses gracefully (SIGTERM) with 5s timeout,
        then kills (SIGKILL) any remaining processes.

        This method is automatically called when using the toolkit as a context manager.
        """
        if not self._active_processes:
            return

        logger.info(f"Cleaning up {len(self._active_processes)} active processes...")

        for process in list(self._active_processes):
            try:
                # Try graceful termination first
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                    logger.debug(f"Process {process.pid} terminated gracefully")
                except asyncio.TimeoutError:
                    # Force kill if termination times out
                    logger.warning(
                        f"Process {process.pid} didn't terminate, killing..."
                    )
                    process.kill()
                    await process.wait()
            except Exception as e:
                logger.warning(f"Error cleaning up process: {e}")
            finally:
                self._active_processes.discard(process)

        logger.info("All processes cleaned up")

    async def __aenter__(self):
        """Context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup active processes."""
        await self.cleanup()
        return False  # Don't suppress exceptions
