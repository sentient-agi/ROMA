"""Centralized error handling for TUI.

Provides consistent error handling, logging, and user feedback.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from loguru import logger


class TUIError(Exception):
    """Base exception for TUI errors."""
    pass


class APIError(TUIError):
    """API request failed."""
    pass


class RenderError(TUIError):
    """Rendering failed."""
    pass


class ValidationError(TUIError):
    """Input validation failed."""
    pass


class ErrorHandler:
    """Centralized error handling."""

    @staticmethod
    def handle_api_error(
        error: Exception,
        context: str,
        fallback_value: Any = None
    ) -> Any:
        """Handle API errors with logging and optional fallback.

        Args:
            error: The exception that occurred
            context: Context string (e.g., "fetch_execution")
            fallback_value: Value to return on error (default: None)

        Returns:
            Fallback value
        """
        logger.error(f"API Error in {context}: {error}", exc_info=True)
        # In TUI, we'll show a notification to the user
        return fallback_value

    @staticmethod
    def handle_render_error(
        error: Exception,
        context: str,
        graceful: bool = True
    ) -> Optional[str]:
        """Handle rendering errors with graceful degradation.

        Args:
            error: The exception that occurred
            context: Context string (e.g., "render_lm_table")
            graceful: Whether to degrade gracefully

        Returns:
            Error message for display, or None if graceful=False
        """
        logger.error(f"Render Error in {context}: {error}", exc_info=True)

        if graceful:
            return f"[dim red]Error rendering {context}: {str(error)[:100]}[/dim red]"
        return None

    @staticmethod
    def handle_validation_error(
        error: Exception,
        field: str
    ) -> str:
        """Handle validation errors.

        Args:
            error: The exception that occurred
            field: Field name that failed validation

        Returns:
            User-friendly error message
        """
        logger.warning(f"Validation Error for {field}: {error}")
        return f"Invalid {field}: {str(error)}"

    @staticmethod
    def wrap_safe(
        func: Callable,
        error_handler: Callable[[Exception], Any],
        *args,
        **kwargs
    ) -> Any:
        """Wrap a function with error handling.

        Args:
            func: Function to wrap
            error_handler: Function to handle errors
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Function result or error handler result
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return error_handler(e)

    @staticmethod
    async def wrap_safe_async(
        func: Callable,
        error_handler: Callable[[Exception], Any],
        *args,
        **kwargs
    ) -> Any:
        """Wrap an async function with error handling.

        Args:
            func: Async function to wrap
            error_handler: Function to handle errors
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Function result or error handler result
        """
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            return error_handler(e)

    @staticmethod
    def log_and_continue(error: Exception, context: str) -> None:
        """Log error and continue execution.

        Args:
            error: The exception that occurred
            context: Context string
        """
        logger.error(f"Error in {context}: {error}", exc_info=True)

    @staticmethod
    def create_error_message(
        title: str,
        error: Exception,
        suggestions: Optional[list[str]] = None
    ) -> str:
        """Create formatted error message for display.

        Args:
            title: Error title
            error: The exception
            suggestions: Optional list of suggestions

        Returns:
            Formatted error message
        """
        msg = f"[bold red]{title}[/bold red]\n\n"
        msg += f"[red]{str(error)}[/red]\n"

        if suggestions:
            msg += "\n[bold]Suggestions:[/bold]\n"
            for suggestion in suggestions:
                msg += f"  • {suggestion}\n"

        return msg
