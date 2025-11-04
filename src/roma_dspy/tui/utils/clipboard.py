"""Clipboard utilities for TUI.

Provides robust clipboard functionality with 3-tier fallback chain.
"""

from __future__ import annotations

import atexit
import json
import tempfile
from pathlib import Path
from typing import Any, Tuple, TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from textual.app import App

# Track temp files for cleanup
_temp_files: list[Path] = []


def _cleanup_temp_files() -> None:
    """Clean up temporary clipboard files on exit."""
    for temp_file in _temp_files:
        try:
            if temp_file.exists():
                temp_file.unlink()
                logger.debug(f"Cleaned up temp clipboard file: {temp_file}")
        except Exception as exc:
            logger.warning(f"Failed to cleanup temp file {temp_file}: {exc}")


# Register cleanup handler
atexit.register(_cleanup_temp_files)


def copy_to_clipboard_safe(app: App, text: str) -> Tuple[bool, str]:
    """Safely copy text to clipboard with multiple fallback strategies.

    Fallback chain:
    1. Textual's OSC 52 clipboard
    2. pyperclip (system clipboard)
    3. Temp file as last resort

    Args:
        app: Textual app instance
        text: Text to copy

    Returns:
        Tuple of (success: bool, message: str)
    """
    if not text:
        return False, "⚠️ Nothing to copy (empty text)"

    # Strategy 1: Try OSC 52 (Textual built-in)
    try:
        app.copy_to_clipboard(text)
        logger.debug("Copied to clipboard via OSC 52")
        return True, "✓ Copied to clipboard"
    except Exception as exc:
        logger.debug(f"OSC 52 clipboard failed: {exc}")

    # Strategy 2: Try pyperclip (system clipboard)
    try:
        import pyperclip

        pyperclip.copy(text)
        logger.debug("Copied to clipboard via pyperclip")
        return True, "✓ Copied via system clipboard"
    except Exception as exc:
        logger.debug(f"pyperclip clipboard failed: {exc}")

    # Strategy 3: Save to secure temp file (last resort)
    try:
        # Use NamedTemporaryFile for security (unpredictable name, proper permissions)
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            prefix='roma_clipboard_',
            suffix='.txt',
            delete=False  # Keep file for user to access
        ) as f:
            f.write(text)
            temp_path = Path(f.name)

        # Track for cleanup on exit
        _temp_files.append(temp_path)

        logger.debug(f"Saved clipboard content to secure temp file: {temp_path}")
        return False, f"⚠️ Clipboard unavailable, saved to:\n{temp_path}"
    except Exception as exc:
        logger.error(f"All clipboard strategies failed: {exc}")
        return False, f"❌ Failed to copy: {exc}"


def copy_json_safe(app: App, data: Any) -> Tuple[bool, str]:
    """Safely copy data as pretty-printed JSON.

    For ExecutionViewModel, creates a complete export document with schema,
    checksum, and metadata (same format as file export).
    For other data types, creates simple JSON.

    Args:
        app: Textual app instance
        data: Data to copy (will be JSON serialized)

    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Import here to avoid circular dependency
        from roma_dspy.tui.models import ExecutionViewModel
        from roma_dspy.tui.utils.export import ExportService
        from roma_dspy.tui.types.export import ExportLevel

        # For ExecutionViewModel, create proper export document
        if isinstance(data, ExecutionViewModel):
            from datetime import datetime
            from roma_dspy.tui.utils.checksum import compute_checksum

            # Prepare execution data (FULL level by default for clipboard)
            execution_data = ExportService._prepare_execution_data(
                data,
                level=ExportLevel.FULL,
                exclude_io=False,
            )

            # Compute checksum
            checksum = compute_checksum(execution_data)

            # Build complete export document
            export_doc = {
                "schema_version": ExportService.SCHEMA_VERSION,
                "roma_version": ExportService.ROMA_VERSION,
                "exported_at": datetime.now().isoformat(),
                "export_level": "full",
                "checksum": checksum,
                "compressed": False,
                "privacy": {
                    "io_excluded": False,
                    "redacted": False,
                },
                "execution": execution_data,
                "metadata": {
                    "export_source": "tui_clipboard",
                    "original_api_url": None,
                    "task_count": len(data.tasks),
                    "trace_count": sum(len(t.traces) for t in data.tasks.values()),
                },
            }

            # Pretty-print export document
            json_text = json.dumps(export_doc, indent=2, default=str)

        else:
            # For non-execution data, simple JSON export
            if hasattr(data, "model_dump"):
                export_data = data.model_dump()
            elif hasattr(data, "__dict__"):
                export_data = data.__dict__
            else:
                export_data = data

            # Pretty-print JSON
            json_text = json.dumps(export_data, indent=2, default=str)

        return copy_to_clipboard_safe(app, json_text)

    except Exception as exc:
        logger.error(f"JSON serialization failed: {exc}")
        return False, f"❌ Failed to serialize JSON: {exc}"
