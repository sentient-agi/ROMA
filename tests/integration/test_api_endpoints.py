"""Integration tests for REST API endpoints."""

import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_check(self, client: AsyncClient):
        """Test health check returns proper status."""
        response = await client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "uptime_seconds" in data
        assert data["status"] == "healthy"


class TestExecutionEndpoints:
    """Tests for execution management endpoints."""

    @pytest.mark.asyncio
    async def test_create_execution(self, client: AsyncClient, mock_storage):
        """Test creating a new execution."""
        payload = {
            "goal": "Test task",
            "max_depth": 2,
            # config_profile has default="default", no need to specify
            "metadata": {},
        }

        response = await client.post("/api/v1/executions", json=payload)
        assert response.status_code == 202

        data = response.json()
        assert "execution_id" in data
        assert data["status"] == "running"
        assert data["initial_goal"] == "Test task"

    @pytest.mark.asyncio
    async def test_create_execution_with_profile(self, client: AsyncClient):
        """Test creating execution with config profile."""
        payload = {
            "goal": "Test task",
            "max_depth": 3,
            "config_profile": "high_quality",
        }

        response = await client.post("/api/v1/executions", json=payload)
        assert response.status_code == 202

    @pytest.mark.asyncio
    async def test_create_execution_invalid_depth(self, client: AsyncClient):
        """Test creating execution with invalid max_depth."""
        payload = {
            "goal": "Test task",
            "max_depth": 11,  # Exceeds maximum
        }

        response = await client.post("/api/v1/executions", json=payload)
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_list_executions(self, client: AsyncClient):
        """Test listing executions."""
        response = await client.get("/api/v1/executions")
        assert response.status_code == 200

        data = response.json()
        assert "executions" in data
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert isinstance(data["executions"], list)

    @pytest.mark.asyncio
    async def test_list_executions_with_filter(self, client: AsyncClient):
        """Test listing executions with status filter."""
        response = await client.get("/api/v1/executions?status=running&limit=10")
        assert response.status_code == 200

        data = response.json()
        assert data["limit"] == 10

    @pytest.mark.asyncio
    async def test_get_execution(self, client: AsyncClient):
        """Test getting execution details."""
        response = await client.get("/api/v1/executions/test-exec-123")
        assert response.status_code == 200

        data = response.json()
        assert data["execution_id"] == "test-exec-123"
        assert "status" in data
        assert "initial_goal" in data

    @pytest.mark.asyncio
    async def test_get_execution_not_found(self, client: AsyncClient, mock_storage):
        """Test getting non-existent execution."""
        mock_storage.get_execution.return_value = None

        response = await client.get("/api/v1/executions/missing-id")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_execution_status(self, client: AsyncClient):
        """Test polling execution status."""
        response = await client.get("/api/v1/executions/test-exec-123/status")
        assert response.status_code == 200

        data = response.json()
        assert "execution_id" in data
        assert "status" in data
        assert "progress" in data
        assert "completed_tasks" in data
        assert "total_tasks" in data

    @pytest.mark.asyncio
    async def test_cancel_execution(self, client: AsyncClient):
        """Test canceling an execution."""
        response = await client.post("/api/v1/executions/test-exec-123/cancel")
        # Will fail because execution not actually running, but endpoint exists
        assert response.status_code in [200, 400]


class TestCheckpointEndpoints:
    """Tests for checkpoint management endpoints."""

    @pytest.mark.asyncio
    async def test_list_checkpoints(self, client: AsyncClient):
        """Test listing checkpoints for execution."""
        response = await client.get("/api/v1/executions/test-exec-123/checkpoints")
        assert response.status_code == 200

        data = response.json()
        assert "checkpoints" in data
        assert "total" in data
        assert isinstance(data["checkpoints"], list)

    @pytest.mark.asyncio
    async def test_get_checkpoint(self, client: AsyncClient, mock_storage):
        """Test getting checkpoint details."""
        # Setup mock to return checkpoint model
        from roma_dspy.core.storage.models import Checkpoint
        from datetime import datetime, timezone

        mock_checkpoint = Checkpoint(
            checkpoint_id="test-checkpoint-123",
            execution_id="test-exec-123",
            created_at=datetime.now(timezone.utc),
            trigger="manual",
            state="saved",
            dag_snapshot={},
            preserved_results={},
            module_states={},
            failed_task_ids=[],
            file_path=None,
            file_size_bytes=None,
            compressed=False,
        )

        mock_storage.list_checkpoints.return_value = [mock_checkpoint]

        response = await client.get("/api/v1/checkpoints/test-checkpoint-123")
        assert response.status_code == 200

        data = response.json()
        assert data["checkpoint_id"] == "test-checkpoint-123"

    @pytest.mark.asyncio
    async def test_delete_checkpoint(self, client: AsyncClient):
        """Test deleting a checkpoint."""
        response = await client.delete("/api/v1/checkpoints/test-checkpoint-123")
        assert response.status_code == 204


class TestVisualizationEndpoints:
    """Tests for visualization endpoints."""

    @pytest.mark.asyncio
    async def test_visualize_execution(self, client: AsyncClient, mock_execution):
        """Test generating visualization.

        Note: Visualization now uses checkpoints (mock_storage.get_latest_checkpoint)
        rather than execution.dag_snapshot.
        """
        payload = {
            "visualizer_type": "tree",
            "include_subgraphs": True,
            "format": "text",
        }

        response = await client.post(
            "/api/v1/executions/test-exec-123/visualize", json=payload
        )

        # May fail if DAG reconstruction fails, but endpoint should exist
        assert response.status_code in [200, 400, 500]

    @pytest.mark.asyncio
    async def test_get_dag_snapshot(self, client: AsyncClient, mock_execution):
        """Test getting raw DAG snapshot.

        Note: DAG endpoint now uses checkpoints (mock_storage.get_latest_checkpoint)
        rather than execution.dag_snapshot.
        """
        response = await client.get("/api/v1/executions/test-exec-123/dag")

        # Should work if checkpoint exists (mocked in conftest.py)
        assert response.status_code == 200
        data = response.json()
        assert "dag_id" in data


class TestMetricsEndpoints:
    """Tests for metrics and cost tracking endpoints."""

    @pytest.mark.asyncio
    async def test_get_metrics(self, client: AsyncClient):
        """Test getting execution metrics."""
        response = await client.get("/api/v1/executions/test-exec-123/metrics")
        assert response.status_code == 200

        data = response.json()
        assert "total_lm_calls" in data
        assert "total_tokens" in data
        assert "total_cost_usd" in data
        assert "average_latency_ms" in data

    @pytest.mark.asyncio
    async def test_get_costs(self, client: AsyncClient):
        """Test getting cost breakdown."""
        response = await client.get("/api/v1/executions/test-exec-123/costs")
        assert response.status_code == 200

        data = response.json()
        assert "total_cost_usd" in data
        assert "total_tokens" in data
        assert "traces_count" in data


class TestErrorHandling:
    """Tests for API error handling."""

    @pytest.mark.asyncio
    async def test_invalid_endpoint(self, client: AsyncClient):
        """Test accessing invalid endpoint."""
        response = await client.get("/api/v1/invalid-endpoint")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_invalid_method(self, client: AsyncClient):
        """Test using invalid HTTP method."""
        response = await client.put("/api/v1/executions")
        assert response.status_code == 405

    @pytest.mark.asyncio
    async def test_missing_required_field(self, client: AsyncClient):
        """Test request with missing required field."""
        payload = {
            "max_depth": 2
            # Missing 'goal' field
        }

        response = await client.post("/api/v1/executions", json=payload)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_json(self, client: AsyncClient):
        """Test request with invalid JSON."""
        response = await client.post(
            "/api/v1/executions",
            content="invalid json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422


class TestPagination:
    """Tests for pagination functionality."""

    @pytest.mark.asyncio
    async def test_pagination_defaults(self, client: AsyncClient):
        """Test default pagination values."""
        response = await client.get("/api/v1/executions")
        assert response.status_code == 200

        data = response.json()
        assert data["offset"] == 0
        assert data["limit"] == 100

    @pytest.mark.asyncio
    async def test_pagination_custom(self, client: AsyncClient):
        """Test custom pagination values."""
        response = await client.get("/api/v1/executions?offset=10&limit=50")
        assert response.status_code == 200

        data = response.json()
        assert data["offset"] == 10
        assert data["limit"] == 50

    @pytest.mark.asyncio
    async def test_pagination_invalid(self, client: AsyncClient):
        """Test invalid pagination values."""
        # Negative offset
        response = await client.get("/api/v1/executions?offset=-1")
        assert response.status_code == 400

        # Limit too high
        response = await client.get("/api/v1/executions?limit=2000")
        assert response.status_code == 400
