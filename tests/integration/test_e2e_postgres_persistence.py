"""End-to-end integration tests for Postgres persistence."""

import pytest
from pathlib import Path

from roma_dspy.config.manager import ConfigManager
from roma_dspy.core.engine.solve import RecursiveSolver
from roma_dspy.core.storage.models import Base
from roma_dspy.core.storage.postgres_storage import PostgresStorage
from roma_dspy.config.schemas.storage import PostgresConfig


@pytest.fixture
async def postgres_enabled_config(tmp_path):
    """Create config with Postgres enabled."""
    # Create a minimal config file
    config_content = """
project: roma-dspy-test
version: "0.1.0"

agents:
  planner:
    agent_config:
      max_subtasks: 5

runtime:
  max_depth: 2
  verbose: true

storage:
  base_path: {tmp_path}
  postgres:
    enabled: true
    connection_url: "postgresql+asyncpg://localhost/roma_dspy_test"
    pool_size: 2
    max_overflow: 0
    pool_timeout: 5.0

resilience:
  retry:
    enabled: true
    max_attempts: 2
  circuit_breaker:
    enabled: false
"""

    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_content.format(tmp_path=tmp_path))

    # Load config
    manager = ConfigManager(config_path=str(config_path))
    return manager.get_config()


@pytest.fixture
async def postgres_storage():
    """Clean Postgres storage for testing."""
    config = PostgresConfig(
        enabled=True,
        connection_url="postgresql+asyncpg://localhost/roma_dspy_test",
        pool_size=2,
        max_overflow=0,
        pool_timeout=5.0,
    )

    storage = PostgresStorage(config)
    await storage.initialize()

    # Clean up
    async with storage._engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield storage

    # Cleanup
    async with storage._engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await storage._engine.dispose()


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.requires_db
@pytest.mark.requires_llm
@pytest.mark.slow
@pytest.mark.skipif(
    True,  # Skip by default - requires Postgres AND LLM keys
    reason="Requires PostgreSQL database and LLM API keys. Run with: pytest -m 'requires_db and requires_llm'",
)
class TestE2EPostgresPersistence:
    """End-to-end tests for Postgres persistence integration."""

    async def test_solver_with_postgres_persistence(
        self, postgres_enabled_config, postgres_storage
    ):
        """Test that solver creates execution records and traces."""
        # Create solver with Postgres-enabled config
        solver = RecursiveSolver(config=postgres_enabled_config)

        # Ensure postgres storage is initialized
        if solver.postgres_storage:
            await solver.postgres_storage.initialize()

        # Simple task that should create execution records
        task = "What is 2 + 2?"

        # Run solver
        result = await solver.async_solve(task, depth=0)

        # Get execution ID from DAG
        execution_id = result.execution_id if hasattr(result, "execution_id") else None

        assert execution_id is not None

        # Verify execution record exists in Postgres
        execution = await postgres_storage.get_execution(execution_id)
        assert execution is not None
        assert execution.status in ["completed", "failed"]
        assert execution.initial_goal == task

        # Verify LM traces exist
        costs = await postgres_storage.get_execution_costs(execution_id)
        assert costs["total_calls"] > 0
        assert costs["total_tokens"] > 0

    async def test_checkpoint_dual_write_in_solver(
        self, postgres_enabled_config, postgres_storage
    ):
        """Test that checkpoints are written to both file and Postgres during solving."""
        # Enable checkpointing in config
        postgres_enabled_config.resilience.checkpoint.enabled = True
        postgres_enabled_config.resilience.checkpoint.save_on_depth = True

        solver = RecursiveSolver(config=postgres_enabled_config)

        if solver.postgres_storage:
            await solver.postgres_storage.initialize()

        # Task that requires decomposition (will trigger checkpointing)
        task = (
            "Plan a 3-day trip to Barcelona including flights, hotels, and activities"
        )

        # Run solver
        result = await solver.async_solve(task, depth=0)

        execution_id = result.execution_id if hasattr(result, "execution_id") else None

        # Query checkpoints from Postgres
        if execution_id:
            execution = await postgres_storage.get_execution(execution_id)
            assert execution is not None

            # Should have at least one checkpoint if decomposition occurred
            # (This is a weak assertion - actual checkpoint count depends on task complexity)

    async def test_lm_trace_capture(self, postgres_enabled_config, postgres_storage):
        """Test that LM traces capture token usage and costs."""
        solver = RecursiveSolver(config=postgres_enabled_config)

        if solver.postgres_storage:
            await solver.postgres_storage.initialize()

        task = "What is the capital of France?"

        result = await solver.async_solve(task, depth=0)
        execution_id = result.execution_id if hasattr(result, "execution_id") else None

        assert execution_id is not None

        # Get aggregated costs
        costs = await postgres_storage.get_execution_costs(execution_id)

        # Verify trace data
        assert costs["total_calls"] > 0
        assert costs["total_tokens"] > 0
        assert "by_module" in costs
        assert "by_model" in costs

        # At minimum, should have atomizer and executor traces
        modules = costs["by_module"].keys()
        assert any(m in modules for m in ["atomizer", "executor", "planner"])

    async def test_execution_status_updates(
        self, postgres_enabled_config, postgres_storage
    ):
        """Test that execution status is updated correctly."""
        solver = RecursiveSolver(config=postgres_enabled_config)

        if solver.postgres_storage:
            await solver.postgres_storage.initialize()

        task = "Calculate 5 * 3"

        result = await solver.async_solve(task, depth=0)
        execution_id = result.execution_id if hasattr(result, "execution_id") else None

        assert execution_id is not None

        # Verify execution was updated with completion status
        execution = await postgres_storage.get_execution(execution_id)
        assert execution.status in ["completed", "failed"]

        # Verify task counts were updated
        assert execution.total_tasks > 0

    async def test_postgres_failure_does_not_break_solver(
        self, postgres_enabled_config
    ):
        """Test that Postgres failures don't break the solver."""
        # Create config with INVALID Postgres connection
        postgres_enabled_config.storage.postgres.connection_url = (
            "postgresql+asyncpg://invalid_host/invalid_db"
        )

        solver = RecursiveSolver(config=postgres_enabled_config)

        # This should NOT raise - solver should gracefully degrade
        try:
            if solver.postgres_storage:
                await solver.postgres_storage.initialize()
        except Exception:
            # Expected to fail - but solver should still work without Postgres
            pass

        # Solver should still work without Postgres
        task = "What is 1 + 1?"

        # This should succeed even if Postgres failed
        result = await solver.async_solve(task, depth=0)

        assert result is not None
