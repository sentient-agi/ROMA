"""
Clean subprocess-based terminal toolkit.

Pure subprocess execution with no external dependencies (no terminal-bench, no tmux).
Designed for Terminal-Bench InstalledAgent where ROMA runs inside containers.

Example Usage:
    # Basic usage
    toolkit = SubprocessTerminalToolkit(file_storage=file_storage)
    output = await toolkit.execute_command("ls -la")
    result = await toolkit.execute_python("print(2+2)")

    # LLM Agent Pattern: Install packages then use them
    # ✅ CORRECT: Use execute_command with 'pip install' (not 'python -m pip')
    await toolkit.execute_command("pip install requests numpy")
    # ✅ THEN: Use execute_python for your logic
    result = await toolkit.execute_python('''
import requests
import numpy as np
print("Packages work!")
''')

    # ❌ WRONG: Don't use 'python3 -m pip install'
    await toolkit.execute_command("python3 -m pip install requests")  # ❌ Will fail!

    # ❌ WRONG: Don't install packages inside execute_python code
    result = await toolkit.execute_python('''
import subprocess
subprocess.check_call(['pip', 'install', 'requests'])  # ❌ Will fail!
''')
"""

import asyncio
import json
import shlex
from datetime import datetime
from typing import Optional

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
        **kwargs
    ):
        """
        Initialize subprocess terminal toolkit.

        Args:
            file_storage: FileStorage instance for artifact logging
            working_directory: Working directory for commands (default: /app)
            venv_path: Path to Python virtual environment (e.g., /opt/roma-venv)
            **kwargs: Additional toolkit configuration
        """
        super().__init__(file_storage=file_storage, **kwargs)
        self.file_storage = file_storage
        self.working_directory = working_directory
        self.venv_path = venv_path
        self._command_counter = 0

        logger.info(
            f"SubprocessTerminalToolkit initialized "
            f"(execution_id={file_storage.execution_id}, cwd={working_directory}, venv={venv_path})"
        )

    def _setup_dependencies(self) -> None:
        """No external dependencies to setup."""
        pass

    def _initialize_tools(self) -> None:
        """Tools auto-discovered via BaseToolkit._register_all_tools()."""
        logger.debug("SubprocessTerminalToolkit tools initialized")

    async def _store_command_log(
        self,
        command: str,
        output: str,
        duration_sec: float,
        returncode: Optional[int] = None,
        is_error: bool = False
    ) -> None:
        """
        Store command execution metadata to FileStorage.

        Args:
            command: Executed command
            output: Command output
            duration_sec: Execution duration
            returncode: Process return code
            is_error: Whether command failed
        """
        self._command_counter += 1

        # Store individual command log entry (JSONL approach with separate files)
        log_entry = {
            "command_id": self._command_counter,
            "timestamp": datetime.utcnow().isoformat(),
            "command": command,
            "output_length": len(output),
            "duration_sec": round(duration_sec, 3),
            "returncode": returncode,
            "is_error": is_error,
        }

        try:
            # Use unique filename for each command log entry (FileStorage doesn't support append mode)
            log_file = f"terminal/commands/{self._command_counter:04d}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            await self.file_storage.put_json(
                key=log_file,
                obj=log_entry
            )
        except Exception as e:
            logger.warning(f"Failed to write command log: {e}")

        # Store output to separate file
        output_file = f"terminal/outputs/{self._command_counter:04d}_{datetime.utcnow().strftime('%H%M%S')}.txt"
        try:
            await self.file_storage.put_text(
                key=output_file,
                text=output
            )
        except Exception as e:
            logger.warning(f"Failed to write command output: {e}")

    async def execute_command(
        self,
        command: str,
        timeout_sec: float = 180.0
    ) -> str:
        """
        Execute bash command via subprocess.

        Use this method for:
        - Installing packages: pip install, apt-get, brew, etc.
        - Running shell commands: ls, mkdir, git, curl, etc.
        - System operations: file management, process control, etc.

        Args:
            command: Bash command to execute
            timeout_sec: Maximum execution time in seconds (default: 180s)

        Returns:
            Command output (stdout + stderr) as string

        Example:
            >>> toolkit = SubprocessTerminalToolkit(file_storage=storage)
            >>> # File operations
            >>> result = await toolkit.execute_command("ls -la")

            >>> # ✅ CORRECT: Installing Python packages
            >>> await toolkit.execute_command("pip install requests numpy pandas")
            >>> # Then use execute_python() to import and use the packages

            >>> # ❌ WRONG: Don't use 'python3 -m pip install'
            >>> await toolkit.execute_command("python3 -m pip install requests")
            >>> # This fails because venv's Python doesn't have pip as a module!
            >>> # Use 'pip install' instead (shown above)

            >>> # Git operations
            >>> await toolkit.execute_command("git status")
        """
        try:
            logger.debug(
                f"[CMD {self._command_counter + 1:04d}] Executing: {command[:100]} "
                f"(cwd={self.working_directory}, timeout={timeout_sec}s)"
            )

            # Wrap command with venv activation if venv_path is set
            if self.venv_path:
                # Use . (dot) instead of source for POSIX compatibility
                wrapped_command = f". {self.venv_path}/bin/activate && {command}"
            else:
                wrapped_command = command

            # Create subprocess
            start_time = datetime.utcnow()
            process = await asyncio.create_subprocess_shell(
                wrapped_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.working_directory,
                shell=True
            )

            # Wait for completion with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_sec
            )
            duration = (datetime.utcnow() - start_time).total_seconds()

            # Combine stdout and stderr
            output = stdout.decode('utf-8', errors='replace')
            if stderr:
                error_output = stderr.decode('utf-8', errors='replace')
                if error_output.strip():
                    output += f"\n[STDERR]\n{error_output}"

            # Log to FileStorage
            await self._store_command_log(
                command=command,
                output=output,
                duration_sec=duration,
                returncode=process.returncode,
                is_error=(process.returncode != 0)
            )

            logger.debug(
                f"[CMD {self._command_counter:04d}] Completed "
                f"(returncode={process.returncode}, {len(output)} chars, {duration:.2f}s)"
            )

            return output

        except asyncio.TimeoutError:
            error_msg = f"Command timed out after {timeout_sec}s: {command}"
            logger.error(f"[CMD {self._command_counter + 1:04d}] {error_msg}")

            # Try to kill the process
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass

            # Log timeout
            await self._store_command_log(
                command=command,
                output=error_msg,
                duration_sec=timeout_sec,
                returncode=None,
                is_error=True
            )

            return error_msg

        except Exception as e:
            error_msg = f"Command failed with error: {e}"
            logger.error(f"[CMD {self._command_counter + 1:04d}] {error_msg}", exc_info=True)

            # Log error
            await self._store_command_log(
                command=command,
                output=error_msg,
                duration_sec=0.0,
                returncode=None,
                is_error=True
            )

            return error_msg

    async def execute_python(
        self,
        code: str,
        timeout_sec: float = 180.0
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

        Returns:
            Python stdout/stderr as string

        Example:
            >>> # ✅ CORRECT: Basic Python execution
            >>> result = await toolkit.execute_python("print(2+2)")
            >>> print(result)
            4

            >>> # ✅ CORRECT: Import packages installed via execute_command
            >>> await toolkit.execute_command("pip install requests")
            >>> result = await toolkit.execute_python('''
            ... import requests
            ... response = requests.get('https://api.github.com')
            ... print(response.status_code)
            ... ''')

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
            python_bin = f"{self.venv_path}/bin/python"
        else:
            python_bin = "python3"

        # Properly escape code for shell using shlex.quote
        escaped_code = shlex.quote(code)
        command = f"{python_bin} -c {escaped_code}"

        logger.info(f"Executing Python code with {python_bin}: {code[:100]}...")

        return await self.execute_command(
            command=command,
            timeout_sec=timeout_sec
        )
