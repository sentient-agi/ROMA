"""Terminal interaction tools with tmux and subprocess support."""

from roma_dspy.tools.terminal.toolkit import TerminalToolkit
from roma_dspy.tools.terminal.subprocess_toolkit import SubprocessTerminalToolkit

# Optional: Export TmuxSession if available
try:
    from roma_dspy.tools.terminal.tmux_session import TmuxSession, TerminalCommand

    __all__ = [
        "TerminalToolkit",
        "SubprocessTerminalToolkit",
        "TmuxSession",
        "TerminalCommand",
    ]
except ImportError:
    __all__ = ["TerminalToolkit", "SubprocessTerminalToolkit"]
