"""ROMA-DSPy TUI - Modern Interactive Visualizer.

Features:
- Zero code duplication
- Clean separation of concerns (SOLID principles)
- Unified rendering engine
- Configuration management
- Centralized error handling
- File loading for offline viewing
"""

from roma_dspy.tui.app import RomaVizApp, run_viz

__all__ = ["RomaVizApp", "run_viz"]
