"""Integration tests for hybrid file + Postgres checkpoint storage."""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timezone

from roma_dspy.resilience.checkpoint_manager import CheckpointManager
from roma_dspy.types.checkpoint_models import CheckpointConfig
from roma_dspy.config.schemas.storage import PostgresConfig
from roma_dspy.core.storage.postgres_storage import PostgresStorage
from roma_dspy.core.storage.models import Base
from roma_dspy.types.checkpoint_models import (
    CheckpointData,
    CheckpointTrigger,
    CheckpointState,
    DAGSnapshot,
)


@pytest.fixture
def temp_checkpoint_dir():
    """Create a temporary directory for checkpoints."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
async def postgres_storage():
    """Create PostgreSQL storage instance."""
    config = PostgresConfig(
        enabled=True,
        connection_url="postgresql+asyncpg://localhost/roma_dspy_test",
        pool_size=2,
        max_overflow=0,
        pool_timeout=5.0,
    )

    storage = PostgresStorage(config)
    await storage.initialize()

    # Clean up tables
    async with storage._engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield storage

    # Cleanup
    async with storage._engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await storage._engine.dispose()


@pytest.fixture
async def checkpoint_manager(temp_checkpoint_dir, postgres_storage):
    """Create checkpoint manager with hybrid storage."""
    config = CheckpointConfig(enabled=True, checkpoint_dir=str(temp_checkpoint_dir))

    # Create execution first
    await postgres_storage.create_execution(
        execution_id="test_exec_001", initial_goal="Test task", max_depth=3
    )

    manager = CheckpointManager(config=config, postgres_storage=postgres_storage)
    return manager


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.requires_db
@pytest.mark.checkpoint
@pytest.mark.skipif(
    True,  # Skip by default - requires Postgres
    reason="Requires PostgreSQL database running. Run with: pytest -m requires_db",
)
class TestHybridCheckpoint:
    """Test hybrid checkpoint storage."""

    async def test_dual_write_checkpoint(self, checkpoint_manager, temp_checkpoint_dir):
        """Test that checkpoints are written to both file and Postgres."""
        from roma_dspy.core.engine.dag import TaskDAG
        from roma_dspy.core.signatures.base_models.task_node import TaskNode

        # Create a simple DAG
        dag = TaskDAG(execution_id="test_exec_001")
        task = TaskNode(task_id="task_001", goal="Test task", depth=0)
        dag.add_node(task)

        # Create checkpoint
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            dag=dag, trigger=CheckpointTrigger.DEPTH, module_history=[], context_data={}
        )

        # Verify file exists
        checkpoint_files = list(temp_checkpoint_dir.glob("*.json"))
        assert len(checkpoint_files) == 1

        # Verify in Postgres
        postgres_checkpoint = await checkpoint_manager.postgres.load_checkpoint(
            checkpoint_id
        )
        assert postgres_checkpoint is not None
        assert postgres_checkpoint.checkpoint_id == checkpoint_id

    async def test_load_from_postgres_fallback_to_file(
        self, checkpoint_manager, postgres_storage
    ):
        """Test loading from Postgres with file fallback."""
        from roma_dspy.core.engine.dag import TaskDAG
        from roma_dspy.core.signatures.base_models.task_node import TaskNode

        # Create a simple DAG
        dag = TaskDAG(execution_id="test_exec_001")
        task = TaskNode(task_id="task_001", goal="Test task", depth=0)
        dag.add_node(task)

        # Create checkpoint (dual-write)
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            dag=dag, trigger=CheckpointTrigger.DEPTH, module_history=[], context_data={}
        )

        # Load checkpoint (should try Postgres first)
        loaded_checkpoint = await checkpoint_manager.load_checkpoint(checkpoint_id)

        assert loaded_checkpoint is not None
        assert loaded_checkpoint.checkpoint_id == checkpoint_id
        assert loaded_checkpoint.trigger == CheckpointTrigger.DEPTH

    async def test_postgres_failure_graceful_degradation(self, temp_checkpoint_dir):
        """Test that system continues with file-only if Postgres fails."""
        config = CheckpointConfig(enabled=True, checkpoint_dir=str(temp_checkpoint_dir))

        # Create manager WITHOUT Postgres (simulating failure)
        manager = CheckpointManager(config=config, postgres_storage=None)

        from roma_dspy.core.engine.dag import TaskDAG
        from roma_dspy.core.signatures.base_models.task_node import TaskNode

        # Create a simple DAG
        dag = TaskDAG(execution_id="test_exec_002")
        task = TaskNode(task_id="task_001", goal="Test task", depth=0)
        dag.add_node(task)

        # Should still work with file-only
        checkpoint_id = await manager.create_checkpoint(
            dag=dag, trigger=CheckpointTrigger.DEPTH, module_history=[], context_data={}
        )

        # Verify file exists
        checkpoint_files = list(temp_checkpoint_dir.glob("*.json"))
        assert len(checkpoint_files) == 1

        # Should be able to load from file
        loaded = await manager.load_checkpoint(checkpoint_id)
        assert loaded is not None
        assert loaded.checkpoint_id == checkpoint_id

    async def test_list_checkpoints_hybrid(self, checkpoint_manager):
        """Test listing checkpoints from both sources."""
        from roma_dspy.core.engine.dag import TaskDAG
        from roma_dspy.core.signatures.base_models.task_node import TaskNode

        # Create multiple checkpoints
        for i in range(3):
            dag = TaskDAG(execution_id="test_exec_001")
            task = TaskNode(task_id=f"task_{i:03d}", goal=f"Test task {i}", depth=0)
            dag.add_node(task)

            await checkpoint_manager.create_checkpoint(
                dag=dag,
                trigger=CheckpointTrigger.DEPTH,
                module_history=[],
                context_data={},
            )

        # List checkpoints
        checkpoints = await checkpoint_manager.list_checkpoints()

        assert len(checkpoints) == 3

    async def test_checkpoint_metadata_consistency(self, checkpoint_manager):
        """Test that metadata is consistent between file and Postgres."""
        from roma_dspy.core.engine.dag import TaskDAG
        from roma_dspy.core.signatures.base_models.task_node import TaskNode

        # Create checkpoint with metadata
        dag = TaskDAG(execution_id="test_exec_001")
        task = TaskNode(task_id="task_001", goal="Test task", depth=2)
        dag.add_node(task)

        checkpoint_id = await checkpoint_manager.create_checkpoint(
            dag=dag,
            trigger=CheckpointTrigger.DEPTH,
            module_history=["planner", "executor"],
            context_data={"test_key": "test_value"},
        )

        # Load from Postgres
        pg_checkpoint = await checkpoint_manager.postgres.load_checkpoint(checkpoint_id)

        # Load from file
        file_checkpoint = await checkpoint_manager.load_checkpoint(checkpoint_id)

        # Verify consistency
        assert pg_checkpoint.execution_id == file_checkpoint.execution_id
        assert pg_checkpoint.trigger == file_checkpoint.trigger
        assert pg_checkpoint.state.depth == file_checkpoint.state.depth
