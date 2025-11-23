"""Centralized loguru configuration for ROMA-DSPy.

Provides:
- Console and file sinks with rotation
- Standard logging interception for third-party libraries
- Context binding for execution_id/task_id
- Async-safe configuration
- Production/development presets

Example:
    Basic setup:
    >>> from roma_dspy.logging_config import configure_logging
    >>> configure_logging(level="DEBUG", log_dir="/path/to/logs")

    Context binding:
    >>> from roma_dspy.logging_config import set_execution_context
    >>> set_execution_context("exec_123")
    >>> logger.info("This log includes exec_123")
"""

from __future__ import annotations

import logging
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Union
from contextvars import ContextVar

from loguru import logger

# Context variables for structured logging (async-safe)
execution_context: ContextVar[Optional[str]] = ContextVar("execution_id", default=None)
task_context: ContextVar[Optional[str]] = ContextVar("task_id", default=None)


class InterceptHandler(logging.Handler):
    """Intercept standard logging and redirect to loguru.

    Captures logs from third-party libraries (DSPy, SQLAlchemy, etc.)
    and routes them through loguru for consistent formatting.
    """

    def emit(self, record):
        """Handle a log record from standard logging."""
        # Get corresponding loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller from where the log originated
        frame = sys._getframe(6)
        depth = 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging(
    level: str = "INFO",
    log_dir: Optional[Union[str, Path]] = None,
    console_format: str = "default",
    file_format: str = "detailed",
    rotation: str = "100 MB",
    retention: str = "30 days",
    compression: str = "zip",
    intercept_standard_logging: bool = True,
    colorize: bool = True,
    serialize: bool = False,
    backtrace: bool = True,
    diagnose: bool = False,
    enqueue: bool = True,
) -> None:
    """Configure loguru for ROMA-DSPy.

    Args:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files (None = no file logging)
        console_format: Format preset for console ("default", "detailed", "minimal")
        file_format: Format preset for file ("default", "detailed", "json")
        rotation: When to rotate log files (size or time)
        retention: How long to keep old logs
        compression: Compression format for rotated logs
        intercept_standard_logging: Capture logs from standard logging module
        colorize: Enable colored output in console
        serialize: Output JSON-formatted logs (overrides file_format)
        backtrace: Show full traceback on errors
        diagnose: Show variable values in traceback (disable in production)
        enqueue: Thread-safe logging via message queue
    """
    # Validate log level
    valid_levels = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}
    level_upper = level.upper()
    if level_upper not in valid_levels:
        raise ValueError(f"Invalid log level: {level}. Must be one of {valid_levels}")
    level = level_upper

    # Remove default handler
    logger.remove()

    # Console format templates
    console_formats = {
        "minimal": "<level>{level: <8}</level> | <level>{message}</level>",
        "default": (
            "<green>{time:HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - "
            "<level>{message}</level>"
        ),
        "detailed": (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{extra[execution_id]:<16} | "
            "{extra[task_id]:<8} | "
            "<level>{message}</level>"
        ),
    }

    # File format templates
    file_formats = {
        "default": (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{extra[execution_id]} | "
            "{extra[task_id]} | "
            "{message}"
        ),
        "detailed": (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{process.name}:{process.id} | "
            "{thread.name}:{thread.id} | "
            "{name}:{function}:{line} | "
            "{extra[execution_id]} | "
            "{extra[task_id]} | "
            "{message} | "
            "{exception}"
        ),
        "json": None,  # Will use serialize=True
    }

    # Filter function to provide context defaults
    def context_filter(record):
        record["extra"].setdefault("execution_id", execution_context.get() or "none")
        record["extra"].setdefault("task_id", task_context.get() or "none")
        return True

    # Add console handler with context defaults
    logger.add(
        sys.stderr,
        level=level,
        format=console_formats.get(console_format, console_formats["default"]),
        colorize=colorize,
        filter=context_filter,
        backtrace=backtrace,
        diagnose=diagnose,
        enqueue=enqueue,
    )

    # Add file handler if log_dir specified
    if log_dir:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)

        log_file = log_dir / "roma_dspy_{time:YYYY-MM-DD}.log"

        if serialize or file_format == "json":
            # JSON format for machine parsing
            logger.add(
                log_file,
                level=level,
                rotation=rotation,
                retention=retention,
                compression=compression,
                serialize=True,
                filter=context_filter,
                backtrace=backtrace,
                diagnose=diagnose,
                enqueue=enqueue,
            )
        else:
            # Text format for human reading
            logger.add(
                log_file,
                level=level,
                format=file_formats.get(file_format, file_formats["default"]),
                rotation=rotation,
                retention=retention,
                compression=compression,
                filter=context_filter,
                backtrace=backtrace,
                diagnose=diagnose,
                enqueue=enqueue,
            )

    # Intercept standard logging if requested
    if intercept_standard_logging:
        # Create intercept handler instance
        intercept_handler = InterceptHandler()

        # Remove all handlers from root logger
        logging.root.handlers = [intercept_handler]
        logging.root.setLevel(level)

        # Intercept specific loggers that might be configured separately
        for logger_name in ["uvicorn", "uvicorn.access", "sqlalchemy", "dspy"]:
            lib_logger = logging.getLogger(logger_name)
            lib_logger.handlers = [intercept_handler]
            lib_logger.propagate = False


def configure_from_config(config: "LoggingConfig") -> None:
    """Initialize logging from LoggingConfig object.

    This helper function maps a LoggingConfig object to configure_logging() parameters,
    making it easy to initialize logging from configuration files.

    Args:
        config: LoggingConfig object from configuration

    Example:
        >>> from roma_dspy.config.manager import ConfigManager
        >>> config_mgr = ConfigManager()
        >>> config = config_mgr.load_config()
        >>> configure_from_config(config.logging)
    """
    configure_logging(
        level=config.level,
        log_dir=config.get_log_path(),
        console_format=config.console_format,
        file_format=config.file_format,
        rotation=config.rotation,
        retention=config.retention,
        compression=config.compression,
        intercept_standard_logging=config.intercept_standard_logging,
        colorize=config.colorize,
        serialize=config.serialize,
        backtrace=config.backtrace,
        diagnose=config.diagnose,
        enqueue=config.enqueue,
    )


def set_execution_context(execution_id: str) -> None:
    """Set execution_id for all subsequent logs in this context.

    Args:
        execution_id: Unique execution identifier
    """
    execution_context.set(execution_id)


def set_task_context(task_id: str) -> None:
    """Set task_id for all subsequent logs in this context.

    Args:
        task_id: Unique task identifier
    """
    task_context.set(task_id)


def get_logger():
    """Get configured loguru logger instance.

    Use this in modules instead of importing logger directly
    to ensure proper binding of context variables.

    Returns:
        Loguru logger with context bound
    """
    return logger.bind(
        execution_id=execution_context.get() or "none",
        task_id=task_context.get() or "none",
    )


def configure_for_development():
    """Quick configuration for development with detailed console output."""
    configure_logging(
        level="DEBUG",
        console_format="detailed",
        colorize=True,
        log_dir=Path.home() / ".roma_dspy" / "logs",
    )


def configure_for_production():
    """Quick configuration for production with JSON file logging."""
    configure_logging(
        level="INFO",
        console_format="minimal",
        colorize=False,
        log_dir=Path("/var/log/roma_dspy"),
        file_format="json",
        serialize=True,
        rotation="500 MB",
        retention="90 days",
    )


@contextmanager
def execution_context_manager(execution_id: str):
    """Context manager for execution_id.

    Automatically sets and resets execution context for structured logging.

    Args:
        execution_id: Unique execution identifier

    Example:
        >>> with execution_context_manager("exec_123"):
        ...     logger.info("Processing task")  # Log includes exec_123
    """
    token = execution_context.set(execution_id)
    try:
        yield
    finally:
        execution_context.reset(token)


@contextmanager
def task_context_manager(task_id: str):
    """Context manager for task_id.

    Automatically sets and resets task context for structured logging.

    Args:
        task_id: Unique task identifier

    Example:
        >>> with task_context_manager("task_456"):
        ...     logger.info("Executing subtask")  # Log includes task_456
    """
    token = task_context.set(task_id)
    try:
        yield
    finally:
        task_context.reset(token)


# Public API
__all__ = [
    # Configuration functions
    "configure_logging",
    "configure_from_config",
    "configure_for_development",
    "configure_for_production",
    # Context management
    "set_execution_context",
    "set_task_context",
    "execution_context_manager",
    "task_context_manager",
    "get_logger",
    # Context variables (for advanced use)
    "execution_context",
    "task_context",
    # Interception
    "InterceptHandler",
]
