"""Text and number formatting utilities for TUI.

Provides consistent formatting across all UI components.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from rich.markup import escape


class Formatters:
    """Formatting utilities."""

    @staticmethod
    def escape_markup(value: Any) -> str:
        """Escape Rich markup in text.

        Args:
            value: Value to escape

        Returns:
            Escaped string
        """
        if value is None:
            return ""
        return escape(str(value))

    @staticmethod
    def format_duration(seconds: float, precision: int = 3) -> str:
        """Format duration in seconds.

        Args:
            seconds: Duration in seconds
            precision: Decimal places (default: 3)

        Returns:
            Formatted string like "2.456s"
        """
        if seconds <= 0:
            return ""
        return f"{seconds:.{precision}f}s"

    @staticmethod
    def format_tokens(tokens: int) -> str:
        """Format token count with thousands separator.

        Args:
            tokens: Token count

        Returns:
            Formatted string like "1,234"
        """
        if tokens is None:
            return ""

        try:
            value = int(tokens)
        except (TypeError, ValueError):
            return ""

        if value <= 0:
            return ""
        return f"{value:,}"

    @staticmethod
    def format_cost(cost: float, precision: int = 6) -> str:
        """Format cost in dollars.

        Args:
            cost: Cost in dollars
            precision: Decimal places (default: 6)

        Returns:
            Formatted string like "$0.001234"
        """
        if cost <= 0:
            return ""
        return f"${cost:.{precision}f}"

    @staticmethod
    def format_timestamp(timestamp: str | float | None) -> str:
        """Format timestamp.

        Args:
            timestamp: Timestamp string or float

        Returns:
            Formatted string like "14:30:45" or ""
        """
        if not timestamp:
            return ""

        try:
            if isinstance(timestamp, str):
                # Try to parse ISO format
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            elif isinstance(timestamp, (int, float)):
                dt = datetime.fromtimestamp(timestamp)
            else:
                return str(timestamp)

            return dt.strftime("%H:%M:%S")
        except Exception:
            return str(timestamp)

    @staticmethod
    def truncate(text: str, max_length: int = 80, suffix: str = "…") -> str:
        """Truncate text to maximum length.

        Args:
            text: Text to truncate
            max_length: Maximum length
            suffix: Suffix to add if truncated (default: "…")

        Returns:
            Truncated text
        """
        if len(text) <= max_length:
            return text
        return text[:max_length - len(suffix)] + suffix

    @staticmethod
    def stringify(value: Any, max_width: int = 200) -> str:
        """Convert value to string representation.

        Args:
            value: Value to stringify
            max_width: Maximum width for line wrapping

        Returns:
            String representation
        """
        if value is None:
            return ""

        # Handle dict/list - format as JSON
        if isinstance(value, (dict, list)):
            try:
                text = json.dumps(value, indent=2, ensure_ascii=False)
                # Simple line wrapping if needed
                if max_width > 0:
                    lines = text.splitlines()
                    wrapped_lines = []
                    for line in lines:
                        if len(line) <= max_width:
                            wrapped_lines.append(line)
                        else:
                            # Break long lines at reasonable points
                            wrapped_lines.append(line[:max_width] + "...")
                    text = "\n".join(wrapped_lines)
                return text
            except (TypeError, ValueError):
                return str(value)

        return str(value)

    @staticmethod
    def short_snippet(value: Any, width: int = 80) -> str:
        """Create short snippet from value.

        Args:
            value: Value to create snippet from
            width: Maximum width

        Returns:
            Escaped snippet
        """
        text = Formatters.stringify(value, max_width=0)
        # Collapse whitespace
        text = " ".join(text.split())
        # Truncate
        text = Formatters.truncate(text, width)
        # Escape markup
        return Formatters.escape_markup(text)

    @staticmethod
    def format_status_icon(status: str) -> str:
        """Get status icon.

        Args:
            status: Status string

        Returns:
            Icon/emoji for status
        """
        status_lower = status.lower() if status else ""

        if "complete" in status_lower or "done" in status_lower or "success" in status_lower:
            return "✓"
        elif "fail" in status_lower or "error" in status_lower:
            return "✗"
        elif "running" in status_lower or "progress" in status_lower:
            return "⟳"
        elif "pending" in status_lower or "waiting" in status_lower:
            return "○"
        else:
            return "•"

    @staticmethod
    def format_module_tag(module: str | None) -> str:
        """Format module name as tag.

        Args:
            module: Module name

        Returns:
            Formatted tag like "[Executor]" or ""
        """
        if not module:
            return ""
        return f"[{module}] "

    @staticmethod
    def format_metric_summary(duration: float, tokens: int, cost: float) -> str:
        """Format metrics summary.

        Args:
            duration: Duration in seconds
            tokens: Token count
            cost: Cost in dollars

        Returns:
            Formatted string like " (2.5s, 1.2K tokens, $0.001)"
        """
        parts = []
        if duration > 0:
            parts.append(Formatters.format_duration(duration))
        if tokens > 0:
            parts.append(f"{Formatters.format_tokens(tokens)} tokens")
        if cost > 0:
            parts.append(Formatters.format_cost(cost))

        if parts:
            return f" ({', '.join(parts)})"
        return ""

    @staticmethod
    def format_size(size_bytes: int) -> str:
        """Format file size.

        Args:
            size_bytes: Size in bytes

        Returns:
            Formatted string like "1.2 MB"
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    @staticmethod
    def pluralize(count: int, singular: str, plural: str | None = None) -> str:
        """Pluralize word based on count.

        Args:
            count: Count
            singular: Singular form
            plural: Plural form (default: singular + "s")

        Returns:
            Pluralized string like "1 item" or "2 items"
        """
        if plural is None:
            plural = singular + "s"

        word = singular if count == 1 else plural
        return f"{count} {word}"
