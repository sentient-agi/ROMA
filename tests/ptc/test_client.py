"""
Tests for PTC HTTP client.

Tests client functionality with mocked HTTP responses.
"""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from roma_dspy.ptc import (
    PTCClient,
    PTCClientError,
    PTCTimeoutError,
    PTCServiceError,
    PTCExecutionPlan,
    PTCArtifactResult,
    ScaffoldingSpec,
    CodeArtifact,
    ExecutionStatus,
    CacheStrategy,
)


@pytest.fixture
def sample_plan():
    """Create a sample execution plan."""
    return PTCExecutionPlan(
        execution_id="test-exec-001",
        scaffolding=ScaffoldingSpec(
            task_description="Build a simple API",
            requirements=["Auth", "Logging"],
        ),
        cache_strategy=CacheStrategy.NEVER  # Disable cache for most tests
    )


@pytest.fixture
def sample_result():
    """Create a sample successful result."""
    now = datetime.utcnow()
    return PTCArtifactResult(
        execution_id="test-exec-001",
        status=ExecutionStatus.SUCCESS,
        artifacts=[
            CodeArtifact(
                file_path="main.py",
                content="print('Hello')"
            )
        ],
        started_at=now,
        completed_at=now,
        duration_seconds=1.0
    )


class TestPTCClient:
    """Test PTC client basic functionality."""

    @pytest.mark.asyncio
    async def test_successful_execution(self, sample_plan, sample_result):
        """Test successful execution without retries."""
        client = PTCClient(service_url="http://localhost:8001")

        # Mock HTTP response
        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_result.model_dump(mode="json")
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            result = await client.execute(sample_plan)

            assert result.execution_id == sample_plan.execution_id
            assert result.status == ExecutionStatus.SUCCESS
            assert len(result.artifacts) == 1
            mock_post.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_error(self, sample_plan):
        """Test timeout handling."""
        client = PTCClient(
            service_url="http://localhost:8001",
            timeout=1,
            max_retries=2
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_post.side_effect = httpx.TimeoutException("Timeout")

            with pytest.raises(PTCTimeoutError, match="timed out"):
                await client.execute(sample_plan)

            # Should retry max_retries times
            assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_server_error_retry(self, sample_plan, sample_result):
        """Test retry on 5xx server errors."""
        client = PTCClient(
            service_url="http://localhost:8001",
            max_retries=3,
            retry_delay=0.01  # Fast retries for testing
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            # First two calls fail with 500, third succeeds
            error_response = MagicMock()
            error_response.status_code = 500
            error_response.text = "Internal Server Error"

            success_response = MagicMock()
            success_response.status_code = 200
            success_response.json.return_value = sample_result.model_dump(mode="json")
            success_response.raise_for_status = MagicMock()

            mock_post.side_effect = [
                httpx.HTTPStatusError("500", request=MagicMock(), response=error_response),
                httpx.HTTPStatusError("500", request=MagicMock(), response=error_response),
                success_response
            ]

            result = await client.execute(sample_plan)

            assert result.execution_id == sample_plan.execution_id
            assert mock_post.call_count == 3  # 2 failures + 1 success

    @pytest.mark.asyncio
    async def test_client_error_no_retry(self, sample_plan):
        """Test 4xx client errors are not retried."""
        client = PTCClient(
            service_url="http://localhost:8001",
            max_retries=3
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            error_response = MagicMock()
            error_response.status_code = 400
            error_response.text = "Bad Request"

            mock_post.side_effect = httpx.HTTPStatusError(
                "400", request=MagicMock(), response=error_response
            )

            with pytest.raises(PTCServiceError, match="400"):
                await client.execute(sample_plan)

            # Should NOT retry on 4xx
            assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_cache_hit(self, sample_plan, sample_result):
        """Test cache hit returns cached result without HTTP call."""
        client = PTCClient(service_url="http://localhost:8001")

        # Enable caching for this test
        cached_plan = PTCExecutionPlan(
            execution_id="test-exec-002",
            scaffolding=ScaffoldingSpec(task_description="Cached task"),
            cache_strategy=CacheStrategy.ALWAYS
        )

        # Mock cache to return a result
        with patch.object(client.cache_manager, "get") as mock_cache_get:
            mock_cache_get.return_value = sample_result

            with patch("httpx.AsyncClient.post") as mock_post:
                result = await client.execute(cached_plan)

                assert result == sample_result
                # HTTP should NOT be called
                mock_post.assert_not_called()

    @pytest.mark.asyncio
    async def test_cache_successful_results(self, sample_plan, sample_result):
        """Test successful results are cached."""
        client = PTCClient(service_url="http://localhost:8001")

        # Enable caching
        plan_with_cache = PTCExecutionPlan(
            execution_id="test-exec-003",
            scaffolding=ScaffoldingSpec(task_description="Test"),
            cache_strategy=CacheStrategy.SMART
        )

        with patch("httpx.AsyncClient.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_result.model_dump(mode="json")
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            with patch.object(client.cache_manager, "set") as mock_cache_set:
                with patch.object(client.cache_manager, "get", return_value=None):
                    result = await client.execute(plan_with_cache)

                    # Cache set should be called for successful result
                    mock_cache_set.assert_called_once()
                    call_args = mock_cache_set.call_args
                    assert call_args[0][0] == plan_with_cache  # plan
                    assert call_args[0][1].execution_id == result.execution_id  # result

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Test health check endpoint."""
        client = PTCClient(service_url="http://localhost:8001")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "healthy"}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            health = await client.health_check()

            assert health["status"] == "healthy"
            mock_get.assert_called_once_with("http://localhost:8001/health")

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test stats endpoint."""
        client = PTCClient(service_url="http://localhost:8001")

        with patch("httpx.AsyncClient.get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"executions": 42}
            mock_response.raise_for_status = MagicMock()
            mock_get.return_value = mock_response

            stats = await client.get_stats()

            assert stats["executions"] == 42

    @pytest.mark.asyncio
    async def test_async_context_manager(self, sample_plan, sample_result):
        """Test client as async context manager."""
        async with PTCClient(service_url="http://localhost:8001") as client:
            with patch("httpx.AsyncClient.post") as mock_post:
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.json.return_value = sample_result.model_dump(mode="json")
                mock_response.raise_for_status = MagicMock()
                mock_post.return_value = mock_response

                result = await client.execute(sample_plan)
                assert result.execution_id == sample_plan.execution_id


class TestPTCClientConfiguration:
    """Test client configuration options."""

    def test_service_url_normalization(self):
        """Test service URL trailing slash is removed."""
        client1 = PTCClient(service_url="http://localhost:8001/")
        client2 = PTCClient(service_url="http://localhost:8001")

        assert client1.service_url == client2.service_url
        assert not client1.service_url.endswith("/")

    def test_custom_timeout(self):
        """Test custom timeout configuration."""
        client = PTCClient(service_url="http://localhost:8001", timeout=300)

        assert client.timeout == 300
        assert client.client_config["timeout"].read == 300

    def test_custom_retry_config(self):
        """Test custom retry configuration."""
        client = PTCClient(
            service_url="http://localhost:8001",
            max_retries=5,
            retry_delay=2.0
        )

        assert client.max_retries == 5
        assert client.retry_delay == 2.0
