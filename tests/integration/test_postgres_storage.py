"""Integration tests for PostgreSQL storage layer."""

import pytest
from datetime import datetime, timezone
from roma_dspy.core.storage.postgres_storage import PostgresStorage
from roma_dspy.core.storage.models import Base, Execution, Checkpoint
from roma_dspy.config.schemas.storage import PostgresConfig
from roma_dspy.types.checkpoint_models import CheckpointData, CheckpointTrigger
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool


@pytest.fixture
async def postgres_config():
    """Postgres configuration for testing."""
    return PostgresConfig(
        enabled=True,
        connection_url="postgresql+asyncpg://localhost/roma_dspy_test",
        pool_size=2,
        max_overflow=0,
        pool_timeout=5.0,
        echo_sql=True,
    )


@pytest.fixture
async def postgres_storage(postgres_config):
    """Create and initialize a PostgresStorage instance."""
    storage = PostgresStorage(postgres_config)
    await storage.initialize()

    # Clean up all tables
    async with storage._engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield storage

    # Cleanup
    async with storage._engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await storage._engine.dispose()


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_db
@pytest.mark.skipif(
    True,  # Skip by default - requires Postgres
    reason="Requires PostgreSQL database running. Run with: pytest -m requires_db",
)
class TestPostgresStorage:
    """Test PostgreSQL storage operations."""

    async def test_create_and_retrieve_execution(self, postgres_storage):
        """Test creating and retrieving execution records."""
        execution_id = "test_exec_001"

        # Create execution
        execution = await postgres_storage.create_execution(
            execution_id=execution_id,
            initial_goal="Test task",
            max_depth=3,
            config={"test": "config"},
            metadata={"version": "1.0"},
        )

        assert execution.execution_id == execution_id
        assert execution.status == "running"
        assert execution.initial_goal == "Test task"
        assert execution.max_depth == 3

        # Retrieve execution
        retrieved = await postgres_storage.get_execution(execution_id)
        assert retrieved is not None
        assert retrieved.execution_id == execution_id
        assert retrieved.status == "running"

    async def test_update_execution(self, postgres_storage):
        """Test updating execution status and metrics."""
        execution_id = "test_exec_002"

        # Create execution
        await postgres_storage.create_execution(
            execution_id=execution_id, initial_goal="Test task", max_depth=3
        )

        # Update execution
        await postgres_storage.update_execution(
            execution_id=execution_id,
            status="completed",
            total_tasks=10,
            completed_tasks=9,
            failed_tasks=1,
        )

        # Verify update
        execution = await postgres_storage.get_execution(execution_id)
        assert execution.status == "completed"
        assert execution.total_tasks == 10
        assert execution.completed_tasks == 9
        assert execution.failed_tasks == 1

    async def test_save_and_load_checkpoint(self, postgres_storage):
        """Test checkpoint persistence."""
        execution_id = "test_exec_003"
        checkpoint_id = "test_cp_001"

        # Create execution first
        await postgres_storage.create_execution(
            execution_id=execution_id, initial_goal="Test task", max_depth=3
        )

        # Create checkpoint data
        from roma_dspy.types.checkpoint_models import CheckpointState, DAGSnapshot

        checkpoint_data = CheckpointData(
            checkpoint_id=checkpoint_id,
            execution_id=execution_id,
            created_at=datetime.now(timezone.utc),
            trigger=CheckpointTrigger.DEPTH,
            state=CheckpointState(
                depth=2, tasks_completed=5, module_history=[], context_data={}
            ),
            root_dag=DAGSnapshot(nodes=[], edges=[], execution_id=execution_id),
            file_path="/test/checkpoint.json",
        )

        # Save checkpoint
        await postgres_storage.save_checkpoint(checkpoint_data)

        # Load checkpoint
        loaded = await postgres_storage.load_checkpoint(checkpoint_id)
        assert loaded is not None
        assert loaded.checkpoint_id == checkpoint_id
        assert loaded.execution_id == execution_id
        assert loaded.trigger == CheckpointTrigger.DEPTH

    async def test_save_lm_trace(self, postgres_storage):
        """Test LM trace persistence."""
        execution_id = "test_exec_004"

        # Create execution first
        await postgres_storage.create_execution(
            execution_id=execution_id, initial_goal="Test task", max_depth=3
        )

        # Save LM trace
        trace = await postgres_storage.save_lm_trace(
            execution_id=execution_id,
            task_id="task_001",
            module_name="planner",
            model="gpt-4",
            provider="openai",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            prompt_cost=0.001,
            completion_cost=0.002,
            total_cost=0.003,
            latency_ms=250,
            metadata={"temperature": 0.7},
        )

        assert trace.execution_id == execution_id
        assert trace.task_id == "task_001"
        assert trace.module_name == "planner"
        assert trace.model == "gpt-4"
        assert trace.total_tokens == 150
        assert trace.total_cost == 0.003

    async def test_get_execution_costs(self, postgres_storage):
        """Test execution cost aggregation."""
        execution_id = "test_exec_005"

        # Create execution
        await postgres_storage.create_execution(
            execution_id=execution_id, initial_goal="Test task", max_depth=3
        )

        # Save multiple LM traces
        await postgres_storage.save_lm_trace(
            execution_id=execution_id,
            task_id="task_001",
            module_name="planner",
            model="gpt-4",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            total_cost=0.003,
        )

        await postgres_storage.save_lm_trace(
            execution_id=execution_id,
            task_id="task_002",
            module_name="executor",
            model="gpt-4",
            prompt_tokens=200,
            completion_tokens=100,
            total_tokens=300,
            total_cost=0.006,
        )

        # Get aggregated costs
        costs = await postgres_storage.get_execution_costs(execution_id)

        assert costs["total_cost"] == 0.009
        assert costs["total_tokens"] == 450
        assert costs["total_calls"] == 2
        assert "by_module" in costs
        assert "by_model" in costs

    async def test_concurrent_operations(self, postgres_storage):
        """Test concurrent database operations."""
        import asyncio

        # Create multiple executions concurrently
        async def create_execution(exec_id: str):
            return await postgres_storage.create_execution(
                execution_id=exec_id, initial_goal=f"Task {exec_id}", max_depth=3
            )

        results = await asyncio.gather(
            create_execution("exec_001"),
            create_execution("exec_002"),
            create_execution("exec_003"),
            return_exceptions=True,
        )

        # All should succeed
        assert all(isinstance(r, Execution) for r in results)
        assert len(results) == 3
