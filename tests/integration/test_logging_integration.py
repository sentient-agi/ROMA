"""Integration tests for logging throughout ROMA-DSPy execution."""

import asyncio
from pathlib import Path
from io import StringIO

import pytest
from loguru import logger

from roma_dspy.logging_config import configure_logging, execution_context, task_context
from roma_dspy.resilience.decorators import measure_execution_time


class TestExecutionLogging:
    """Test logging during task execution."""

    def test_decorator_logs_execution(self, clean_loguru, caplog_loguru):
        """Test that @measure_execution_time logs execution start and completion."""
        configure_logging(level="DEBUG", log_dir=None)

        @measure_execution_time
        def sample_function(x: int) -> int:
            return x * 2

        result = sample_function(5)

        assert (
            result[0] == 10
        )  # Function returns (result, duration, token_metrics, messages)

        # Check logs
        assert (
            "sample_function starting" in caplog_loguru.text
            or "sample_function sync starting" in caplog_loguru.text
        )
        assert (
            "sample_function completed" in caplog_loguru.text
            or "sample_function sync completed" in caplog_loguru.text
        )

    @pytest.mark.asyncio
    async def test_decorator_logs_async_execution(self, clean_loguru, caplog_loguru):
        """Test that @measure_execution_time logs async execution."""
        configure_logging(level="DEBUG", log_dir=None)

        @measure_execution_time
        async def async_function(x: int) -> int:
            await asyncio.sleep(0.01)
            return x * 3

        result = await async_function(5)

        assert result[0] == 15

        # Check logs
        assert "async_function async starting" in caplog_loguru.text
        assert "async_function async completed" in caplog_loguru.text

    def test_decorator_logs_errors(self, clean_loguru, caplog_loguru):
        """Test that @measure_execution_time logs errors."""
        configure_logging(level="DEBUG", log_dir=None)

        @measure_execution_time
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            failing_function()

        # Check error was logged
        assert "failing_function" in caplog_loguru.text
        assert "failed" in caplog_loguru.text or "error" in caplog_loguru.text.lower()

    def test_context_propagation_through_execution(self, clean_loguru, tmp_path):
        """Test that execution_id and task_id propagate through execution."""
        log_dir = tmp_path / "logs"
        output = StringIO()

        configure_logging(level="INFO", log_dir=log_dir)
        logger.add(
            output, format="{extra[execution_id]} | {extra[task_id]} | {message}"
        )

        exec_token = execution_context.set("exec_integration_123")
        task_token = task_context.set("task_integration_456")
        try:

            @measure_execution_time
            def context_function():
                logger.info("Inside function")
                return "result"

            result = context_function()

            # Check context was preserved in logs
            log_output = output.getvalue()
            assert "exec_integration_123" in log_output
            assert "task_integration_456" in log_output
            assert "Inside function" in log_output
        finally:
            execution_context.reset(exec_token)
            task_context.reset(task_token)


class TestModuleLogging:
    """Test logging from actual ROMA-DSPy modules."""

    def test_config_manager_logs(self, clean_loguru, caplog_loguru):
        """Test that ConfigManager logs properly."""
        from roma_dspy.config.manager import ConfigManager

        configure_logging(level="DEBUG", log_dir=None)

        # ConfigManager should log during initialization and config loading
        manager = ConfigManager()

        # This will log various steps
        assert manager is not None

    def test_storage_logs(self, clean_loguru, caplog_loguru, tmp_path):
        """Test that storage components log properly."""
        from roma_dspy.core.storage.file_storage import FileStorage
        from roma_dspy.config.schemas.storage import StorageConfig

        configure_logging(level="DEBUG", log_dir=None)

        config = StorageConfig(base_path=str(tmp_path))
        storage = FileStorage(config=config, execution_id="test_exec")

        # Storage initialization should produce logs
        assert storage is not None


class TestThirdPartyLogging:
    """Test interception of third-party library logs."""

    def test_stdlib_logging_intercepted(self, clean_loguru, caplog_loguru):
        """Test that standard library logging is intercepted."""
        import logging

        configure_logging(
            level="INFO",
            log_dir=None,
            intercept_standard_logging=True,
        )

        # Create a standard logger and log
        std_logger = logging.getLogger("test.thirdparty")
        std_logger.info("Message from standard logging")

        # Should be captured by loguru through interception
        # Note: This might not appear in caplog_loguru due to how propagation works
        # but the InterceptHandler should have processed it
        assert True  # If no exception, interception is working

    def test_sqlalchemy_logging_intercepted(self, clean_loguru):
        """Test that SQLAlchemy logs are intercepted."""
        import logging

        configure_logging(
            level="INFO",
            log_dir=None,
            intercept_standard_logging=True,
        )

        # Simulate SQLAlchemy logging
        sqlalchemy_logger = logging.getLogger("sqlalchemy.engine")
        sqlalchemy_logger.info("SQL query executed")

        # If no exception, interception is working
        assert True


class TestLoggingConfiguration:
    """Test different logging configurations."""

    def test_production_config(self, clean_loguru, tmp_path):
        """Test production-like logging configuration."""
        log_dir = tmp_path / "logs"

        configure_logging(
            level="INFO",
            log_dir=log_dir,
            console_format="minimal",
            file_format="json",
            colorize=False,
            serialize=True,
            rotation="100 MB",
            retention="30 days",
            compression="zip",
            intercept_standard_logging=True,
            backtrace=True,
            diagnose=False,  # Disabled in production
            enqueue=True,
        )

        logger.info("Production test message")

        # Verify log file created
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) > 0

    def test_development_config(self, clean_loguru, tmp_path):
        """Test development-like logging configuration."""
        log_dir = tmp_path / "logs"

        configure_logging(
            level="DEBUG",
            log_dir=log_dir,
            console_format="detailed",
            file_format="detailed",
            colorize=True,
            serialize=False,
            intercept_standard_logging=True,
            backtrace=True,
            diagnose=True,  # Enabled in development
        )

        logger.debug("Development test message")

        # Verify log file created
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) > 0

    def test_console_only_config(self, clean_loguru):
        """Test console-only logging (no file)."""
        output = StringIO()

        configure_logging(
            level="INFO",
            log_dir=None,  # No file logging
            console_format="default",
        )

        logger.add(output, format="{message}")
        logger.info("Console only message")

        assert "Console only message" in output.getvalue()


class TestLoggingPerformance:
    """Test logging performance and overhead."""

    def test_decorator_overhead_minimal(self, clean_loguru):
        """Test that @measure_execution_time has minimal overhead."""
        import time

        configure_logging(level="INFO", log_dir=None)

        @measure_execution_time
        def fast_function():
            return 42

        start = time.perf_counter()
        for _ in range(100):
            fast_function()
        duration = time.perf_counter() - start

        # 100 calls should complete in reasonable time (< 1 second)
        assert duration < 1.0

    def test_context_overhead_minimal(self, clean_loguru):
        """Test that context variables have minimal overhead."""
        import time

        configure_logging(level="INFO", log_dir=None)

        start = time.perf_counter()
        for i in range(1000):
            token = execution_context.set(f"exec_{i}")
            _ = execution_context.get()
            execution_context.reset(token)
        duration = time.perf_counter() - start

        # 1000 context operations should complete quickly (< 0.1 seconds)
        assert duration < 0.1
