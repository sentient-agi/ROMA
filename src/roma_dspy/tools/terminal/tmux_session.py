"""
Tmux session wrapper for terminal interaction.

Provides a simple interface for creating and managing tmux sessions,
compatible with Terminal-Bench's TmuxSession interface.
"""

import asyncio
from typing import Optional
from loguru import logger

try:
    import libtmux
    LIBTMUX_AVAILABLE = True
except ImportError:
    LIBTMUX_AVAILABLE = False
    logger.warning("libtmux not installed. TmuxSession will not be available.")


class TmuxSession:
    """
    Wrapper around libtmux for terminal interaction.

    Provides interface compatible with Terminal-Bench's TmuxSession
    but works independently without terminal-bench dependency.
    """

    def __init__(
        self,
        session_name: Optional[str] = None,
        window_name: str = "roma",
        width: int = 200,
        height: int = 40
    ):
        """
        Initialize tmux session.

        Args:
            session_name: Tmux session name (auto-generated if None)
            window_name: Tmux window name (default: "roma")
            width: Terminal width in characters (default: 200)
            height: Terminal height in lines (default: 40)

        Raises:
            ImportError: If libtmux is not installed
            RuntimeError: If tmux is not available on system
        """
        if not LIBTMUX_AVAILABLE:
            raise ImportError(
                "libtmux is not installed. "
                "Install with: pip install libtmux"
            )

        # Create tmux server connection
        self.server = libtmux.Server()

        # Create or attach to session
        if session_name:
            # Try to attach to existing session
            self.session = self.server.find_where({"session_name": session_name})
            if not self.session:
                # Create new session
                self.session = self.server.new_session(
                    session_name=session_name,
                    window_name=window_name,
                    x=width,
                    y=height
                )
        else:
            # Create new session with auto-generated name
            self.session = self.server.new_session(
                window_name=window_name,
                x=width,
                y=height
            )

        # Get the active window and pane
        self.window = self.session.active_window
        self.pane = self.window.active_pane

        # Track last captured content for incremental output
        self._last_capture = ""

        logger.info(
            f"TmuxSession initialized: session={self.session.name}, "
            f"window={self.window.name}, size={width}x{height}"
        )

    def send_keys(self, keys: str, literal: bool = False, suppress_history: bool = False) -> None:
        """
        Send keys to tmux pane.

        Args:
            keys: Keys to send
            literal: Whether to send keys literally (no special key interpretation)
            suppress_history: Whether to suppress history (not implemented in libtmux)
        """
        self.pane.send_keys(keys, literal=literal, suppress_history=suppress_history)

    def send_command(self, command: str, append_enter: bool = True) -> None:
        """
        Send command to tmux pane.

        Args:
            command: Command string to send
            append_enter: Whether to append Enter key (default: True)
        """
        if append_enter:
            self.pane.send_keys(command, enter=True)
        else:
            self.pane.send_keys(command, enter=False)

    def capture_pane(self, capture_entire: bool = False) -> str:
        """
        Capture pane content.

        Args:
            capture_entire: Whether to capture entire scrollback (default: False)

        Returns:
            Captured pane content as string
        """
        if capture_entire:
            # Capture entire scrollback buffer
            content = self.pane.capture_pane()
        else:
            # Capture only visible area
            content = self.pane.capture_pane()

        # Join lines if returned as list
        if isinstance(content, list):
            content = "\n".join(content)

        return content

    def get_incremental_output(self) -> str:
        """
        Get new output since last call.

        Returns:
            New output since last capture, formatted with header
        """
        current_capture = self.capture_pane(capture_entire=False)

        # Calculate diff (simple approach - find new lines)
        if not self._last_capture:
            # First call - return everything
            self._last_capture = current_capture
            return f"Current Terminal Screen:\n{current_capture}"

        # Find new content
        if current_capture == self._last_capture:
            return ""

        # Return new content
        self._last_capture = current_capture
        return f"New Terminal Output:\n{current_capture}"

    def clear_screen(self) -> None:
        """Clear the tmux pane screen."""
        self.pane.send_keys("clear", enter=True)

    def close(self) -> None:
        """Close the tmux session."""
        try:
            self.session.kill_session()
            logger.info(f"Closed tmux session: {self.session.name}")
        except Exception as e:
            logger.warning(f"Error closing tmux session: {e}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close session."""
        self.close()

    def __del__(self):
        """Destructor - ensure session is closed."""
        try:
            self.close()
        except Exception:
            pass


# Compatibility with Terminal-Bench's TerminalCommand model
class TerminalCommand:
    """
    Simple command model compatible with Terminal-Bench.

    Wraps command execution parameters.
    """

    def __init__(
        self,
        command: str,
        block: bool = True,
        max_timeout_sec: float = 180.0,
        append_enter: bool = True
    ):
        """
        Initialize terminal command.

        Args:
            command: Command string to execute
            block: Whether to wait for completion (not used in simple implementation)
            max_timeout_sec: Maximum timeout (not used in simple implementation)
            append_enter: Whether to append Enter key
        """
        self.command = command
        self.block = block
        self.max_timeout_sec = max_timeout_sec
        self.append_enter = append_enter
