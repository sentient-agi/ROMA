"""
Terminal interaction toolkit for Terminal-Bench integration.

Provides terminal interaction capabilities via TmuxSession with comprehensive
FileStorage integration for structured artifact logging.

All terminal interactions are logged to execution-scoped folders:
- artifacts/terminal/commands.log: Structured command log (JSONL format)
- artifacts/terminal/outputs/: Command outputs with timestamps
- artifacts/terminal/screenshots/: Terminal screenshots (optional)

Example Usage:
    from roma_dspy.tools.terminal.toolkit import TerminalToolkit

    toolkit = TerminalToolkit(session=tmux_session, file_storage=file_storage)

    # Execute command with blocking
    output = await toolkit.execute_command("ls -la", block=True, timeout_sec=30)

    # Execute Python code
    result = await toolkit.execute_python("print(2+2)", timeout_sec=60)

    # Capture screen
    screen = await toolkit.capture_screen()

    # Get incremental output
    new_output = await toolkit.get_incremental_output()
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

# Try terminal-bench first (for Terminal-Bench evaluation framework)
try:
    from terminal_bench.terminal.tmux_session import TmuxSession
    from terminal_bench.terminal.models import TerminalCommand
    TERMINAL_BENCH_AVAILABLE = True
    USING_BUILTIN_TMUX = False
except ImportError:
    # Fall back to our own tmux implementation
    try:
        from roma_dspy.tools.terminal.tmux_session import TmuxSession, TerminalCommand
        TERMINAL_BENCH_AVAILABLE = False
        USING_BUILTIN_TMUX = True
    except ImportError:
        TERMINAL_BENCH_AVAILABLE = False
        USING_BUILTIN_TMUX = False
        logger.warning(
            "Neither terminal-bench nor libtmux available. "
            "TerminalToolkit will use subprocess mode only. "
            "Install libtmux for tmux support: pip install libtmux"
        )

from roma_dspy.tools.base.base import BaseToolkit
from roma_dspy.core.storage.file_storage import FileStorage


class TerminalToolkit(BaseToolkit):
    """
    Terminal interaction toolkit with FileStorage integration.

    Provides tools for:
    - Executing bash commands (blocking and non-blocking)
    - Executing Python code
    - Capturing terminal screen state
    - Getting incremental terminal output

    All interactions logged to artifacts/terminal/ with structured metadata.

    Attributes:
        session: TmuxSession for terminal interaction
        file_storage: FileStorage for artifact logging
        _command_counter: Incrementing counter for command tracking
    """

    def __init__(
        self,
        file_storage: FileStorage,
        session: Optional["TmuxSession"] = None,
        **kwargs
    ):
        """
        Initialize terminal toolkit.

        Always uses tmux for terminal interaction. If session is not provided,
        creates own TmuxSession automatically (requires libtmux).

        Args:
            file_storage: FileStorage instance for artifact logging
            session: Optional TmuxSession instance (Terminal-Bench or external).
                    If None, creates own session using libtmux.
            **kwargs: Additional toolkit configuration

        Raises:
            ImportError: If neither terminal-bench nor libtmux is available
        """
        super().__init__(name="terminal")
        self.file_storage = file_storage
        self._command_counter = 0
        self._owns_session = False

        if session:
            # Use provided session (Terminal-Bench or custom)
            self.session = session
            self._owns_session = False
            logger.info(
                f"TerminalToolkit using external TmuxSession "
                f"(execution_id={file_storage.execution_id})"
            )
        elif TERMINAL_BENCH_AVAILABLE or USING_BUILTIN_TMUX:
            # Auto-create our own tmux session
            try:
                self.session = TmuxSession()
                self._owns_session = True
                logger.info(
                    f"TerminalToolkit created own TmuxSession "
                    f"(execution_id={file_storage.execution_id})"
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to create TmuxSession: {e}. "
                    "Ensure tmux is installed on the system."
                ) from e
        else:
            raise ImportError(
                "Neither terminal-bench nor libtmux available. "
                "Install libtmux for tmux support: pip install libtmux"
            )

    async def cleanup(self) -> None:
        """Cleanup resources - closes tmux session if we created it."""
        if self._owns_session and self.session:
            try:
                self.session.close()
                logger.info("Closed owned TmuxSession")
            except Exception as e:
                logger.warning(f"Error closing TmuxSession: {e}")

    def _set_session(self, session: "TmuxSession") -> None:
        """
        Internal method to set TmuxSession for Terminal-Bench integration.

        NOT exposed as a tool (private method). Used during toolkit initialization.

        Switches toolkit from direct mode (subprocess) to TmuxSession mode.

        Args:
            session: TmuxSession instance for terminal interaction

        Raises:
            ImportError: If terminal-bench is not installed

        Example:
            # Toolkit created in direct mode
            toolkit = TerminalToolkit(file_storage=storage)
            # Later, switch to TmuxSession mode for Terminal-Bench
            toolkit._set_session(tmux_session)
        """
        if not TERMINAL_BENCH_AVAILABLE:
            raise ImportError(
                "terminal-bench is not installed. "
                "Install with: pip install terminal-bench"
            )

        self.session = session
        logger.info(
            f"Switched to TmuxSession mode (execution_id={self.file_storage.execution_id})"
        )

    def _setup_dependencies(self) -> None:
        """
        Setup external dependencies.

        TerminalToolkit has no external dependencies - TmuxSession and FileStorage
        are provided at initialization.
        """
        pass

    def _initialize_tools(self) -> None:
        """
        Initialize toolkit-specific configuration.

        Tool registration happens automatically via BaseToolkit._register_all_tools()
        which discovers public methods (execute_command, execute_python, etc.)
        """
        logger.debug("TerminalToolkit initialized (tools will be auto-discovered)")

    async def execute_command(
        self,
        command: str,
        block: bool = True,
        timeout_sec: float = 180.0
    ) -> str:
        """
        Execute bash command with blocking support.

        Supports two execution modes:
        1. TmuxSession mode (when session is set): Uses tmux for Terminal-Bench
        2. Direct mode (no session): Uses subprocess for regular shell commands

        Args:
            command: Bash command to execute
            block: Whether to wait for command completion (default: True)
            timeout_sec: Maximum time to wait for completion (default: 180s)

        Returns:
            Terminal output as string

        Raises:
            TimeoutError: If command exceeds timeout (logged to FileStorage)
        """
        self._command_counter += 1

        logger.info(
            f"[CMD {self._command_counter:04d}] Executing: {command[:100]} "
            f"(mode={'tmux' if self.session else 'subprocess'}, block={block}, timeout={timeout_sec}s)"
        )

        # Log command to FileStorage before execution
        await self._log_command(command, "bash", block, timeout_sec)

        # Execute via TmuxSession or subprocess
        if self.session:
            # TmuxSession mode (Terminal-Bench integration)
            return await self._execute_via_tmux(command, block, timeout_sec)
        else:
            # Direct mode (subprocess)
            return await self._execute_via_subprocess(command, timeout_sec)

    async def _execute_via_tmux(
        self,
        command: str,
        block: bool,
        timeout_sec: float
    ) -> str:
        """Execute command via TmuxSession (Terminal-Bench mode)."""
        # Create TerminalCommand model
        terminal_cmd = TerminalCommand(
            command=command,
            block=block,
            max_timeout_sec=timeout_sec,
            append_enter=True
        )

        try:
            # Execute via TmuxSession
            self.session.send_command(terminal_cmd)

            # Capture output
            output = self.session.capture_pane(capture_entire=False)

            # Store output to FileStorage
            await self._store_output(command, output, is_error=False)

            logger.debug(
                f"[CMD {self._command_counter:04d}] Completed successfully "
                f"({len(output)} chars)"
            )

            return output

        except TimeoutError as e:
            error_msg = f"Command timed out after {timeout_sec}s: {command}"
            logger.error(f"[CMD {self._command_counter:04d}] {error_msg}")
            await self._store_output(command, error_msg, is_error=True)
            return error_msg

        except Exception as e:
            error_msg = f"Command failed with error: {e}"
            logger.error(f"[CMD {self._command_counter:04d}] {error_msg}", exc_info=True)
            await self._store_output(command, error_msg, is_error=True)
            return error_msg

    async def _execute_via_subprocess(
        self,
        command: str,
        timeout_sec: float
    ) -> str:
        """
        Execute command via subprocess (direct mode).

        Uses asyncio.create_subprocess_shell for async execution.
        """
        import asyncio

        try:
            # Create subprocess with timeout
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                shell=True
            )

            # Wait for completion with timeout
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout_sec
            )

            # Combine stdout and stderr
            output = stdout.decode('utf-8', errors='replace')
            if stderr:
                error_output = stderr.decode('utf-8', errors='replace')
                output += f"\n[STDERR]\n{error_output}"

            # Store output to FileStorage
            await self._store_output(command, output, is_error=(process.returncode != 0))

            logger.debug(
                f"[CMD {self._command_counter:04d}] Completed (returncode={process.returncode}, {len(output)} chars)"
            )

            return output

        except asyncio.TimeoutError:
            error_msg = f"Command timed out after {timeout_sec}s: {command}"
            logger.error(f"[CMD {self._command_counter:04d}] {error_msg}")
            await self._store_output(command, error_msg, is_error=True)

            # Kill the process
            try:
                process.kill()
                await process.wait()
            except Exception:
                pass

            return error_msg

        except Exception as e:
            error_msg = f"Command failed with error: {e}"
            logger.error(f"[CMD {self._command_counter:04d}] {error_msg}", exc_info=True)
            await self._store_output(command, error_msg, is_error=True)
            return error_msg

    async def execute_python(
        self,
        code: str,
        timeout_sec: float = 180.0
    ) -> str:
        """
        Execute Python code via python3 -c.

        Args:
            code: Python code to execute (must be valid Python)
            timeout_sec: Maximum time to wait for completion (default: 180s)

        Returns:
            Python stdout/stderr as string

        Example:
            >>> result = await toolkit.execute_python("print(2+2)")
            >>> print(result)
            4
        """
        # Escape double quotes in code
        escaped_code = code.replace('"', '\\"').replace('\n', '\\n')

        # Construct python -c command
        command = f'python3 -c "{escaped_code}"'

        logger.info(f"Executing Python code: {code[:100]}")

        # Execute via execute_command (handles logging and storage)
        return await self.execute_command(
            command=command,
            block=True,  # Always block for Python execution
            timeout_sec=timeout_sec
        )

    async def capture_screen(self) -> str:
        """
        Capture current visible terminal screen.

        Only works in TmuxSession mode. Returns empty string in direct mode.

        Returns:
            Current terminal screen content (40 lines in tmux mode, empty in direct mode)

        Example:
            >>> screen = await toolkit.capture_screen()
            >>> print(screen)
            user@container:~$ ls
            file1.txt  file2.txt  directory/
            user@container:~$
        """
        if not self.session:
            logger.warning("capture_screen requires TmuxSession (not available in direct mode)")
            return ""

        logger.debug("Capturing terminal screen")

        screen_content = self.session.capture_pane(capture_entire=False)

        # Store screenshot to FileStorage
        screenshot_num = self._command_counter
        screenshot_key = f"terminal/screenshots/screen_{screenshot_num:04d}.txt"
        await self.file_storage.put_text(screenshot_key, screen_content)

        logger.debug(
            f"Screenshot saved to {screenshot_key} ({len(screen_content)} chars)"
        )

        return screen_content

    async def get_incremental_output(self) -> str:
        """
        Get new terminal output since last call.

        Only works in TmuxSession mode. Returns empty string in direct mode.

        This method tracks terminal state changes and returns only new content.
        More efficient than capture_screen for polling terminal state.

        Returns:
            New terminal output since last call, formatted as:
            "New Terminal Output:\\n{content}" or "Current Terminal Screen:\\n{content}"

        Example:
            >>> output1 = await toolkit.get_incremental_output()
            >>> # Run some commands
            >>> output2 = await toolkit.get_incremental_output()  # Only new output
        """
        if not self.session:
            logger.warning("get_incremental_output requires TmuxSession (not available in direct mode)")
            return ""

        logger.debug("Getting incremental terminal output")

        incremental_output = self.session.get_incremental_output()

        logger.debug(f"Incremental output: {len(incremental_output)} chars")

        return incremental_output

    # ==================== FileStorage Integration ====================

    async def _log_command(
        self,
        command: str,
        command_type: str,
        block: bool,
        timeout_sec: float
    ) -> None:
        """
        Log command to artifacts/terminal/commands.log (JSONL format).

        Each line is a JSON object with command metadata:
        - timestamp: ISO 8601 timestamp
        - counter: Incrementing command counter
        - type: Command type (bash, python, etc.)
        - command: Command string
        - block: Whether command blocks
        - timeout_sec: Timeout in seconds
        - execution_id: Execution ID for correlation

        Args:
            command: Command string
            command_type: Type of command (bash, python)
            block: Whether command blocks
            timeout_sec: Timeout in seconds
        """
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "counter": self._command_counter,
            "type": command_type,
            "command": command,
            "block": block,
            "timeout_sec": timeout_sec,
            "execution_id": self.file_storage.execution_id
        }

        # Get log path (artifacts/terminal/commands.log)
        log_path = self.file_storage.get_artifacts_path("terminal/commands.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Append JSON line
        try:
            with open(log_path, "a") as f:
                f.write(json.dumps(log_entry) + "\n")

            logger.debug(f"Logged command to {log_path}")

        except Exception as e:
            # Non-fatal: command execution continues even if logging fails
            logger.warning(f"Failed to log command to FileStorage: {e}")

    async def _store_output(
        self,
        command: str,
        output: str,
        is_error: bool = False
    ) -> None:
        """
        Store command output to artifacts/terminal/outputs/.

        Output files named: cmd_{counter:04d}_{status}.txt
        - status: "output" for success, "error" for failures

        Args:
            command: Command that produced output
            output: Output string
            is_error: Whether output represents an error
        """
        # Generate output filename
        status = "error" if is_error else "output"
        output_filename = f"cmd_{self._command_counter:04d}_{status}.txt"
        output_key = f"terminal/outputs/{output_filename}"

        # Format output with command header
        content = f"Command: {command}\n"
        content += f"Timestamp: {datetime.now().isoformat()}\n"
        content += f"Status: {status}\n"
        content += f"\n{output}"

        # Store to FileStorage
        try:
            await self.file_storage.put_text(output_key, content)

            logger.debug(
                f"Stored output to {output_key} ({len(output)} chars, status={status})"
            )

        except Exception as e:
            # Non-fatal: output already captured in memory
            logger.warning(f"Failed to store output to FileStorage: {e}")