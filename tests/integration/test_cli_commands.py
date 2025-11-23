"""Integration tests for CLI commands.

Tests CLI commands by mocking HTTP responses, avoiding the need for a running API server.
"""

import json
from unittest.mock import MagicMock, patch
import pytest
from typer.testing import CliRunner

from roma_dspy.cli import app


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def mock_httpx():
    """Mock httpx responses for CLI-to-API communication."""
    with patch("roma_dspy.cli.httpx") as mock:
        yield mock


class TestConfigCommands:
    """Tests for config command."""

    def test_config_tree(self, runner):
        """Test config display in tree format."""
        result = runner.invoke(app, ["config", "--format", "tree"])
        assert result.exit_code == 0
        assert "ROMA-DSPy Configuration" in result.stdout

    def test_config_json(self, runner):
        """Test config display in JSON format."""
        result = runner.invoke(app, ["config", "--format", "json"])
        assert result.exit_code == 0
        # Should be valid JSON
        config_data = json.loads(result.stdout)
        assert "project" in config_data


class TestVersionCommand:
    """Tests for version command."""

    def test_version(self, runner):
        """Test version command."""
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "ROMA-DSPy" in result.stdout or "version" in result.stdout.lower()


class TestServerCommands:
    """Tests for server commands."""

    def test_server_health_success(self, runner, mock_httpx):
        """Test server health check success."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "healthy",
            "version": "0.1.0",
            "uptime_seconds": 120.5,
            "active_executions": 3,
            "storage_connected": True,
            "cache_size": 10,
        }
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["server", "health"])
        assert result.exit_code == 0
        assert "healthy" in result.stdout.lower()

    def test_server_health_connection_error(self, runner, mock_httpx):
        """Test server health check connection error."""
        mock_httpx.get.side_effect = Exception("Connection refused")

        result = runner.invoke(app, ["server", "health"])
        assert result.exit_code == 1
        assert "error" in result.stdout.lower() or "failed" in result.stdout.lower()


class TestExecCommands:
    """Tests for execution management commands."""

    def test_exec_create_success(self, runner, mock_httpx):
        """Test creating execution via CLI."""
        mock_response = MagicMock()
        mock_response.status_code = 202
        mock_response.json.return_value = {
            "execution_id": "test-exec-123",
            "status": "running",
            "initial_goal": "Test task",
            "max_depth": 2,
            "total_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "metadata": {},
        }
        mock_httpx.post.return_value = mock_response

        result = runner.invoke(app, ["exec", "create", "Test task", "--max-depth", "2"])
        assert result.exit_code == 0
        assert "test-exec-123" in result.stdout

    def test_exec_create_validation_error(self, runner, mock_httpx):
        """Test execution creation with validation error."""
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.raise_for_status.side_effect = Exception("Validation error")
        mock_httpx.post.return_value = mock_response

        result = runner.invoke(
            app, ["exec", "create", "Test task", "--max-depth", "99"]
        )
        assert result.exit_code == 1

    def test_exec_list_success(self, runner, mock_httpx):
        """Test listing executions."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "executions": [
                {
                    "execution_id": "exec-1",
                    "status": "running",
                    "initial_goal": "Task 1",
                    "total_tasks": 10,
                    "completed_tasks": 5,
                    "created_at": "2024-01-01T00:00:00Z",
                },
                {
                    "execution_id": "exec-2",
                    "status": "completed",
                    "initial_goal": "Task 2",
                    "total_tasks": 5,
                    "completed_tasks": 5,
                    "created_at": "2024-01-01T01:00:00Z",
                },
            ],
            "total": 2,
            "offset": 0,
            "limit": 20,
        }
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["exec", "list", "--limit", "20"])
        assert result.exit_code == 0
        assert "exec-1" in result.stdout or "Task 1" in result.stdout

    def test_exec_list_with_filter(self, runner, mock_httpx):
        """Test listing executions with status filter."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "executions": [],
            "total": 0,
            "offset": 0,
            "limit": 20,
        }
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["exec", "list", "--status", "running"])
        assert result.exit_code == 0
        mock_httpx.get.assert_called_once()

    def test_exec_get_success(self, runner, mock_httpx):
        """Test getting execution details."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "execution_id": "test-exec-123",
            "status": "completed",
            "initial_goal": "Test task",
            "max_depth": 2,
            "total_tasks": 10,
            "completed_tasks": 10,
            "failed_tasks": 0,
            "config": {},
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:10:00Z",
            "metadata": {},
        }
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["exec", "get", "test-exec-123"])
        assert result.exit_code == 0
        assert "test-exec-123" in result.stdout
        assert "completed" in result.stdout.lower()

    def test_exec_get_not_found(self, runner, mock_httpx):
        """Test getting non-existent execution."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("Not found")
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["exec", "get", "missing-id"])
        assert result.exit_code == 1

    def test_exec_status_success(self, runner, mock_httpx):
        """Test polling execution status."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "execution_id": "test-exec-123",
            "status": "running",
            "progress": 0.65,
            "current_task_id": "task-5",
            "current_task_goal": "Processing data",
            "completed_tasks": 13,
            "total_tasks": 20,
            "estimated_remaining_seconds": 120,
            "last_updated": "2024-01-01T00:05:00Z",
        }
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["exec", "status", "test-exec-123"])
        assert result.exit_code == 0
        assert "running" in result.stdout.lower()
        assert "13" in result.stdout or "65" in result.stdout  # completed or progress

    def test_exec_cancel_success(self, runner, mock_httpx):
        """Test canceling execution."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "success": True,
            "message": "Execution cancelled",
        }
        mock_httpx.post.return_value = mock_response

        result = runner.invoke(app, ["exec", "cancel", "test-exec-123"])
        assert result.exit_code == 0
        assert "cancel" in result.stdout.lower() or "success" in result.stdout.lower()

    def test_exec_cancel_not_running(self, runner, mock_httpx):
        """Test canceling non-running execution."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = Exception("Not running")
        mock_httpx.post.return_value = mock_response

        result = runner.invoke(app, ["exec", "cancel", "test-exec-123"])
        assert result.exit_code == 1


class TestCheckpointCommands:
    """Tests for checkpoint management commands."""

    def test_checkpoint_list_success(self, runner, mock_httpx):
        """Test listing checkpoints."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "checkpoints": [
                {
                    "checkpoint_id": "cp-1",
                    "execution_id": "exec-123",
                    "created_at": "2024-01-01T00:00:00Z",
                    "trigger": "manual",
                    "state": "saved",
                    "file_size_bytes": 1024,
                    "compressed": True,
                }
            ],
            "total": 1,
        }
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["checkpoint", "list", "exec-123"])
        assert result.exit_code == 0
        assert "cp-1" in result.stdout or "manual" in result.stdout

    def test_checkpoint_list_empty(self, runner, mock_httpx):
        """Test listing checkpoints for execution with none."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"checkpoints": [], "total": 0}
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["checkpoint", "list", "exec-123"])
        assert result.exit_code == 0
        assert "no checkpoint" in result.stdout.lower() or "0" in result.stdout

    def test_checkpoint_get_success(self, runner, mock_httpx):
        """Test getting checkpoint details."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "checkpoint_id": "cp-123",
            "execution_id": "exec-123",
            "created_at": "2024-01-01T00:00:00Z",
            "trigger": "manual",
            "state": "saved",
            "file_path": "/tmp/checkpoint.json",
            "file_size_bytes": 2048,
            "compressed": True,
        }
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["checkpoint", "get", "cp-123"])
        assert result.exit_code == 0
        assert "cp-123" in result.stdout
        assert "manual" in result.stdout

    def test_checkpoint_delete_success(self, runner, mock_httpx):
        """Test deleting checkpoint."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_httpx.delete.return_value = mock_response

        result = runner.invoke(app, ["checkpoint", "delete", "cp-123", "--yes"])
        assert result.exit_code == 0
        assert "delete" in result.stdout.lower() or "success" in result.stdout.lower()

    def test_checkpoint_delete_not_found(self, runner, mock_httpx):
        """Test deleting non-existent checkpoint."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("Not found")
        mock_httpx.delete.return_value = mock_response

        result = runner.invoke(app, ["checkpoint", "delete", "missing-cp", "--yes"])
        assert result.exit_code == 1


class TestVisualizeCommand:
    """Tests for visualize command."""

    def test_visualize_success(self, runner, mock_httpx):
        """Test generating visualization."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "visualization": "Task Tree:\n  Root Task\n    - Subtask 1\n    - Subtask 2",
            "visualizer_type": "tree",
            "execution_id": "exec-123",
        }
        mock_httpx.post.return_value = mock_response

        result = runner.invoke(app, ["visualize", "exec-123", "--type", "tree"])
        assert result.exit_code == 0
        assert "Root Task" in result.stdout or "Subtask" in result.stdout

    def test_visualize_invalid_type(self, runner, mock_httpx):
        """Test visualization with invalid type."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.raise_for_status.side_effect = Exception(
            "Invalid visualizer type"
        )
        mock_httpx.post.return_value = mock_response

        result = runner.invoke(app, ["visualize", "exec-123", "--type", "invalid"])
        assert result.exit_code == 1

    def test_visualize_timeline(self, runner, mock_httpx):
        """Test timeline visualization."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "visualization": "Timeline:\n  00:00 - Task started\n  00:05 - Task completed",
            "visualizer_type": "timeline",
            "execution_id": "exec-123",
        }
        mock_httpx.post.return_value = mock_response

        result = runner.invoke(app, ["visualize", "exec-123", "--type", "timeline"])
        assert result.exit_code == 0

    def test_visualize_statistics(self, runner, mock_httpx):
        """Test statistics visualization."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "visualization": "Statistics:\n  Total Tasks: 10\n  Completed: 10",
            "visualizer_type": "statistics",
            "execution_id": "exec-123",
        }
        mock_httpx.post.return_value = mock_response

        result = runner.invoke(app, ["visualize", "exec-123", "--type", "statistics"])
        assert result.exit_code == 0


class TestMetricsCommand:
    """Tests for metrics command."""

    def test_metrics_success(self, runner, mock_httpx):
        """Test getting execution metrics."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "execution_id": "exec-123",
            "total_lm_calls": 50,
            "total_tokens": 10000,
            "total_cost_usd": 1.25,
            "average_latency_ms": 850.5,
            "task_breakdown": {},
        }
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["metrics", "exec-123"])
        assert result.exit_code == 0
        assert (
            "50" in result.stdout or "10000" in result.stdout or "1.25" in result.stdout
        )

    def test_metrics_with_breakdown(self, runner, mock_httpx):
        """Test metrics with task breakdown."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "execution_id": "exec-123",
            "total_lm_calls": 50,
            "total_tokens": 10000,
            "total_cost_usd": 1.25,
            "average_latency_ms": 850.5,
            "task_breakdown": {
                "task-1": {"calls": 10, "tokens": 2000, "cost_usd": 0.25},
                "task-2": {"calls": 15, "tokens": 3000, "cost_usd": 0.38},
            },
        }
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["metrics", "exec-123", "--breakdown"])
        assert result.exit_code == 0
        # Should show breakdown table
        assert (
            "task-1" in result.stdout
            or "task-2" in result.stdout
            or "calls" in result.stdout.lower()
        )

    def test_metrics_not_found(self, runner, mock_httpx):
        """Test metrics for non-existent execution."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("Not found")
        mock_httpx.get.return_value = mock_response

        result = runner.invoke(app, ["metrics", "missing-id"])
        assert result.exit_code == 1


class TestErrorHandling:
    """Tests for CLI error handling."""

    def test_invalid_command(self, runner):
        """Test handling of invalid command."""
        result = runner.invoke(app, ["invalid-command"])
        assert result.exit_code != 0

    def test_missing_required_argument(self, runner):
        """Test handling of missing required argument."""
        result = runner.invoke(app, ["exec", "get"])
        assert result.exit_code != 0

    def test_invalid_option_value(self, runner):
        """Test handling of invalid option value."""
        result = runner.invoke(
            app, ["exec", "create", "Test", "--max-depth", "invalid"]
        )
        assert result.exit_code != 0

    def test_network_error(self, runner, mock_httpx):
        """Test handling of network errors."""
        mock_httpx.get.side_effect = Exception("Network error")

        result = runner.invoke(app, ["exec", "list"])
        assert result.exit_code == 1
        assert "error" in result.stdout.lower()
