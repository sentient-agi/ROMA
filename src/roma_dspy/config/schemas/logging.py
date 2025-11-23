"""Logging configuration schema for ROMA-DSPy."""

from pathlib import Path
from typing import Optional, Literal
from pydantic.dataclasses import dataclass
from pydantic import field_validator


@dataclass
class LoggingConfig:
    """Configuration for loguru-based logging.

    Controls log levels, output destinations, formatting, and rotation policies.
    """

    # Core settings
    level: str = "INFO"
    log_dir: Optional[str] = None  # None = console only

    # Format settings
    console_format: Literal["default", "minimal", "detailed"] = "default"
    file_format: Literal["default", "detailed", "json"] = "detailed"
    colorize: bool = True
    serialize: bool = False  # JSON serialization for structured logging

    # Rotation settings (for file logging)
    rotation: str = "100 MB"  # Size-based rotation
    retention: str = "30 days"  # Keep logs for 30 days
    compression: str = "zip"  # Compress rotated logs

    # Interception settings
    intercept_standard_logging: bool = True  # Capture logs from third-party libraries

    # Debug settings
    backtrace: bool = True  # Show full traceback on errors
    diagnose: bool = False  # Show variable values in traceback (disable in production)
    enqueue: bool = True  # Thread-safe logging

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {
            "TRACE",
            "DEBUG",
            "INFO",
            "SUCCESS",
            "WARNING",
            "ERROR",
            "CRITICAL",
        }
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return v_upper

    @field_validator("console_format")
    @classmethod
    def validate_console_format(cls, v: str) -> str:
        """Validate console format is valid."""
        valid_formats = {"default", "minimal", "detailed"}
        if v not in valid_formats:
            raise ValueError(
                f"Invalid console format: {v}. Must be one of {valid_formats}"
            )
        return v

    @field_validator("file_format")
    @classmethod
    def validate_file_format(cls, v: str) -> str:
        """Validate file format is valid."""
        valid_formats = {"default", "detailed", "json"}
        if v not in valid_formats:
            raise ValueError(
                f"Invalid file format: {v}. Must be one of {valid_formats}"
            )
        return v

    def get_log_path(self) -> Optional[Path]:
        """Get resolved log directory path."""
        if self.log_dir:
            return Path(self.log_dir).expanduser().resolve()
        return None
