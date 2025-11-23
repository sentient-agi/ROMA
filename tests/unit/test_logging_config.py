"""Unit tests for loguru logging configuration."""

import logging
import sys
from pathlib import Path
from io import StringIO

import pytest
from loguru import logger

from roma_dspy.logging_config import (
    configure_logging,
    execution_context,
    task_context,
    InterceptHandler,
)


class TestContextVariables:
    """Test context variable propagation."""

    def test_execution_context_default(self):
        """Test execution context default value."""
        token = execution_context.set(None)
        try:
            assert execution_context.get() is None
        finally:
            execution_context.reset(token)

    def test_execution_context_set_get(self):
        """Test setting and getting execution context."""
        test_id = "exec_12345"
        token = execution_context.set(test_id)
        try:
            assert execution_context.get() == test_id
        finally:
            execution_context.reset(token)

    def test_task_context_default(self):
        """Test task context default value."""
        token = task_context.set(None)
        try:
            assert task_context.get() is None
        finally:
            task_context.reset(token)

    def test_task_context_set_get(self):
        """Test setting and getting task context."""
        test_id = "task_67890"
        token = task_context.set(test_id)
        try:
            assert task_context.get() == test_id
        finally:
            task_context.reset(token)

    def test_context_isolation(self):
        """Test that contexts are properly isolated."""
        exec_token = execution_context.set("exec_1")
        task_token = task_context.set("task_1")
        try:
            assert execution_context.get() == "exec_1"
            assert task_context.get() == "task_1"

            # Set new values
            exec_token2 = execution_context.set("exec_2")
            task_token2 = task_context.set("task_2")
            try:
                assert execution_context.get() == "exec_2"
                assert task_context.get() == "task_2"
            finally:
                execution_context.reset(exec_token2)
                task_context.reset(task_token2)

            # Should revert to previous values
            assert execution_context.get() == "exec_1"
            assert task_context.get() == "task_1"
        finally:
            execution_context.reset(exec_token)
            task_context.reset(task_token)


class TestInterceptHandler:
    """Test standard logging interception."""

    def test_intercept_handler_basic(self, clean_loguru):
        """Test basic interception of standard logging."""
        # Setup loguru to capture to string
        output = StringIO()
        logger.add(output, format="{message}")

        # Setup standard logging with InterceptHandler
        std_logger = logging.getLogger("test_intercept")
        std_logger.handlers = [InterceptHandler()]
        std_logger.setLevel(logging.INFO)

        # Log via standard logging
        std_logger.info("Test message")

        # Check loguru captured it
        result = output.getvalue()
        assert "Test message" in result

    def test_intercept_handler_levels(self, clean_loguru):
        """Test interception handles different log levels."""
        output = StringIO()
        logger.add(output, format="{level}: {message}")

        std_logger = logging.getLogger("test_levels")
        std_logger.handlers = [InterceptHandler()]
        std_logger.setLevel(logging.DEBUG)

        std_logger.debug("Debug msg")
        std_logger.info("Info msg")
        std_logger.warning("Warning msg")
        std_logger.error("Error msg")

        result = output.getvalue()
        assert "DEBUG: Debug msg" in result
        assert "INFO: Info msg" in result
        assert "WARNING: Warning msg" in result
        assert "ERROR: Error msg" in result


class TestConfigureLogging:
    """Test configure_logging function."""

    def test_configure_basic(self, clean_loguru, tmp_path):
        """Test basic logging configuration."""
        configure_logging(
            level="INFO",
            log_dir=None,  # Console only
            console_format="default",
        )

        # Should have at least one handler (console)
        assert len(logger._core.handlers) >= 1

    def test_configure_with_file_logging(self, clean_loguru, tmp_path):
        """Test logging configuration with file output."""
        log_dir = tmp_path / "logs"
        configure_logging(
            level="DEBUG",
            log_dir=log_dir,
            console_format="minimal",
            file_format="detailed",
        )

        # Should have handlers for console and file
        assert len(logger._core.handlers) >= 2

        # Test that log file is created
        logger.info("Test file logging")

        # Check file exists
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) > 0

    def test_configure_with_context_filter(self, clean_loguru, tmp_path):
        """Test that context filter adds execution_id and task_id."""
        output = StringIO()
        configure_logging(
            level="INFO",
            log_dir=None,
            console_format="detailed",
            colorize=False,
        )
        logger.add(
            output, format="{extra[execution_id]} | {extra[task_id]} | {message}"
        )

        # Set context
        exec_token = execution_context.set("exec_123")
        task_token = task_context.set("task_456")
        try:
            logger.info("Test message")
            result = output.getvalue()
            assert "exec_123" in result
            assert "task_456" in result
        finally:
            execution_context.reset(exec_token)
            task_context.reset(task_token)

    def test_configure_with_rotation(self, clean_loguru, tmp_path):
        """Test file rotation configuration."""
        log_dir = tmp_path / "logs"
        configure_logging(
            level="INFO",
            log_dir=log_dir,
            rotation="10 KB",  # Small rotation for testing
            retention="1 day",
            compression="zip",
        )

        # Write enough data to trigger rotation
        for i in range(1000):
            logger.info(f"Test message {i}" * 10)

        # Check that log files exist
        log_files = list(log_dir.glob("*.log*"))
        assert len(log_files) > 0

    def test_configure_intercept_standard_logging(self, clean_loguru):
        """Test interception of standard logging."""
        configure_logging(
            level="INFO",
            log_dir=None,
            intercept_standard_logging=True,
        )

        # Check that root logger has InterceptHandler
        root_handlers = logging.root.handlers
        assert any(isinstance(h, InterceptHandler) for h in root_handlers)

    def test_configure_without_intercept(self, clean_loguru):
        """Test configuration without standard logging interception."""
        # Clear root handlers first
        logging.root.handlers = []

        configure_logging(
            level="INFO",
            log_dir=None,
            intercept_standard_logging=False,
        )

        # Root logger should not have InterceptHandler
        root_handlers = logging.root.handlers
        assert not any(isinstance(h, InterceptHandler) for h in root_handlers)

    def test_configure_json_serialization(self, clean_loguru, tmp_path):
        """Test JSON serialization for structured logging."""
        log_dir = tmp_path / "logs"
        configure_logging(
            level="INFO",
            log_dir=log_dir,
            file_format="json",
            serialize=True,
        )

        logger.info("Test JSON message", extra={"custom_field": "custom_value"})

        # Read log file and verify JSON format
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) > 0

        content = log_files[0].read_text()
        # JSON logs should contain structured data
        assert '"message"' in content or '"text"' in content

    def test_configure_level_validation(self, clean_loguru):
        """Test that log level is properly set."""
        configure_logging(level="DEBUG")

        # Logger should accept DEBUG messages
        output = StringIO()
        logger.add(output, format="{level}: {message}", level="DEBUG")
        logger.debug("Debug test")

        result = output.getvalue()
        assert "DEBUG: Debug test" in result


class TestLoggingIntegration:
    """Integration tests for logging system."""

    def test_end_to_end_logging(self, clean_loguru, tmp_path):
        """Test complete logging flow with context."""
        log_dir = tmp_path / "logs"
        configure_logging(
            level="INFO",
            log_dir=log_dir,
            console_format="default",
            file_format="detailed",
        )

        # Set execution context
        exec_token = execution_context.set("test_exec_789")
        task_token = task_context.set("test_task_101")
        try:
            # Log various messages
            logger.info("Starting test operation")
            logger.debug("Debug information")
            logger.warning("Warning message")
            logger.error("Error occurred")

            # Verify logs were written
            log_files = list(log_dir.glob("*.log"))
            assert len(log_files) > 0

            content = log_files[0].read_text()
            assert "Starting test operation" in content
            assert "test_exec_789" in content
            assert "test_task_101" in content
        finally:
            execution_context.reset(exec_token)
            task_context.reset(task_token)

    def test_multiple_handlers(self, clean_loguru, tmp_path):
        """Test logging with multiple handlers."""
        log_dir = tmp_path / "logs"
        output = StringIO()

        configure_logging(
            level="INFO",
            log_dir=log_dir,
            console_format="minimal",
        )

        # Add custom handler
        logger.add(output, format="{level}: {message}")

        logger.info("Test multiple handlers")

        # Check custom handler received message
        assert "INFO: Test multiple handlers" in output.getvalue()

        # Check file also received message
        log_files = list(log_dir.glob("*.log"))
        if log_files:
            content = log_files[0].read_text()
            assert "Test multiple handlers" in content
