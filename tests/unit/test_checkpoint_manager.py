"""Comprehensive unit tests for CheckpointManager."""

import asyncio
import gzip
import json
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Set
from unittest.mock import Mock, patch

from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.resilience.checkpoint_manager import CheckpointManager
from roma_dspy.core.signatures import TaskNode
from roma_dspy.types import TaskType, TaskStatus, AgentType
from roma_dspy.types.checkpoint_types import (
    CheckpointTrigger,
    RecoveryStrategy,
    CheckpointState,
    CheckpointCorruptedError,
    CheckpointExpiredError,
    CheckpointNotFoundError,
)
from roma_dspy.types.checkpoint_models import CheckpointConfig, CheckpointData


class TestCheckpointManager:
    """Test CheckpointManager core functionality."""

    @pytest.fixture
    def temp_storage(self):
        """Create temporary storage directory."""
        with tempfile.TemporaryDirectory(prefix="test_checkpoints_") as temp_dir:
            yield Path(temp_dir)

    @pytest.fixture
    def test_config(self, temp_storage):
        """Create test configuration."""
        return CheckpointConfig(
            storage_path=temp_storage,
            max_checkpoints=5,
            max_age_hours=1.0,
            compress_checkpoints=False,  # Easier for testing
        )

    @pytest.fixture
    def checkpoint_manager(self, test_config):
        """Create CheckpointManager instance."""
        return CheckpointManager(test_config)

    @pytest.fixture
    def sample_task(self):
        """Create sample TaskNode for testing."""
        return TaskNode(
            task_id="test_task_1",
            goal="Test task goal",
            task_type=TaskType.THINK,
            status=TaskStatus.COMPLETED,
        )

    @pytest.fixture
    def sample_dag(self, sample_task):
        """Create sample TaskDAG for testing."""
        dag = TaskDAG("test_dag")
        dag.add_node(sample_task)
        return dag

    # ==================== Creation Tests ====================

    def test_manager_initialization_default_config(self):
        """Test CheckpointManager creates with default config."""
        manager = CheckpointManager()
        assert manager.config is not None
        assert manager.storage_path == manager.config.storage_path
        assert manager.storage_path.exists()

    def test_manager_initialization_custom_config(self, test_config):
        """Test CheckpointManager creates with custom config."""
        manager = CheckpointManager(test_config)
        assert manager.config == test_config
        assert manager.storage_path == test_config.storage_path

    def test_storage_directory_creation(self, temp_storage):
        """Test storage directory is created if it doesn't exist."""
        storage_path = temp_storage / "nested" / "checkpoint_dir"
        config = CheckpointConfig(storage_path=storage_path)

        manager = CheckpointManager(config)
        assert storage_path.exists()

    # ==================== Checkpoint Creation Tests ====================

    @pytest.mark.asyncio
    async def test_create_checkpoint_basic(self, checkpoint_manager, sample_dag):
        """Test basic checkpoint creation."""
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        assert checkpoint_id is not None
        assert checkpoint_id.startswith("checkpoint_")

        # Verify checkpoint file exists
        checkpoint_path = checkpoint_manager._get_checkpoint_path(checkpoint_id)
        assert checkpoint_path.exists()

    @pytest.mark.asyncio
    async def test_create_checkpoint_with_custom_id(
        self, checkpoint_manager, sample_dag
    ):
        """Test checkpoint creation with custom ID."""
        custom_id = "custom_checkpoint_123"

        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id=custom_id, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        assert checkpoint_id == custom_id

    @pytest.mark.asyncio
    async def test_create_checkpoint_disabled(self, temp_storage, sample_dag):
        """Test checkpoint creation when disabled."""
        config = CheckpointConfig(enabled=False, storage_path=temp_storage)
        manager = CheckpointManager(config)

        checkpoint_id = await manager.create_checkpoint(
            checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        assert checkpoint_id == ""

    @pytest.mark.asyncio
    async def test_checkpoint_compression(self, temp_storage, sample_dag):
        """Test checkpoint compression functionality."""
        config = CheckpointConfig(storage_path=temp_storage, compress_checkpoints=True)
        manager = CheckpointManager(config)

        checkpoint_id = await manager.create_checkpoint(
            checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        checkpoint_path = manager._get_checkpoint_path(checkpoint_id)
        assert checkpoint_path.suffix == ".gz"

        # Verify it's actually compressed
        with gzip.open(checkpoint_path, "rt") as f:
            data = json.load(f)
            assert data["checkpoint_id"] == checkpoint_id

    # ==================== Checkpoint Loading Tests ====================

    @pytest.mark.asyncio
    async def test_load_checkpoint_success(self, checkpoint_manager, sample_dag):
        """Test successful checkpoint loading."""
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        checkpoint_data = await checkpoint_manager.load_checkpoint(checkpoint_id)
        assert checkpoint_data.checkpoint_id == checkpoint_id
        assert checkpoint_data.trigger == CheckpointTrigger.MANUAL
        assert checkpoint_data.state == CheckpointState.VALID

    @pytest.mark.asyncio
    async def test_load_checkpoint_not_found(self, checkpoint_manager):
        """Test loading non-existent checkpoint."""
        with pytest.raises(CheckpointNotFoundError):
            await checkpoint_manager.load_checkpoint("nonexistent_checkpoint")

    @pytest.mark.asyncio
    async def test_load_checkpoint_corrupted(self, checkpoint_manager, temp_storage):
        """Test loading corrupted checkpoint."""
        # Create corrupted checkpoint file with correct naming
        corrupted_path = temp_storage / "corrupted.json"
        with open(corrupted_path, "w") as f:
            f.write("invalid json content {")

        with pytest.raises(CheckpointCorruptedError):
            await checkpoint_manager.load_checkpoint("corrupted")

    @pytest.mark.asyncio
    async def test_load_checkpoint_disabled_system(self, temp_storage):
        """Test loading checkpoint when system is disabled."""
        config = CheckpointConfig(enabled=False, storage_path=temp_storage)
        manager = CheckpointManager(config)

        with pytest.raises(Exception, match="Checkpoint system is disabled"):
            await manager.load_checkpoint("any_id")

    # ==================== Recovery Plan Tests ====================

    @pytest.mark.asyncio
    async def test_create_recovery_plan_partial(self, checkpoint_manager, sample_dag):
        """Test partial recovery plan creation."""
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        checkpoint_data = await checkpoint_manager.load_checkpoint(checkpoint_id)
        failed_tasks = {"test_task_1"}

        recovery_plan = await checkpoint_manager.create_recovery_plan(
            checkpoint_data, failed_tasks, RecoveryStrategy.PARTIAL
        )

        assert recovery_plan.strategy == RecoveryStrategy.PARTIAL
        assert "test_task_1" in recovery_plan.tasks_to_retry
        assert len(recovery_plan.tasks_to_preserve) >= 0

    @pytest.mark.asyncio
    async def test_create_recovery_plan_full(self, checkpoint_manager, sample_dag):
        """Test full recovery plan creation."""
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        checkpoint_data = await checkpoint_manager.load_checkpoint(checkpoint_id)
        failed_tasks = {"test_task_1"}

        recovery_plan = await checkpoint_manager.create_recovery_plan(
            checkpoint_data, failed_tasks, RecoveryStrategy.FULL
        )

        assert recovery_plan.strategy == RecoveryStrategy.FULL
        assert len(recovery_plan.tasks_to_retry) >= len(failed_tasks)
        assert len(recovery_plan.tasks_to_preserve) == 0

    # ==================== Lifecycle Management Tests ====================

    @pytest.mark.asyncio
    async def test_cleanup_old_checkpoints(self, checkpoint_manager, sample_dag):
        """Test cleanup of old checkpoints."""
        # Create multiple checkpoints
        checkpoint_ids = []
        for i in range(7):
            checkpoint_id = await checkpoint_manager.create_checkpoint(
                checkpoint_id=f"checkpoint_{i}",
                dag=sample_dag,
                trigger=CheckpointTrigger.MANUAL,
            )
            checkpoint_ids.append(checkpoint_id)

        # Cleanup keeping only 3
        removed_count = await checkpoint_manager.cleanup_checkpoints(keep_latest=3)
        assert removed_count == 4  # Should remove 4 out of 7

        # Verify remaining checkpoints
        remaining = await checkpoint_manager.list_checkpoints()
        assert len(remaining) == 3

    @pytest.mark.asyncio
    async def test_delete_specific_checkpoint(self, checkpoint_manager, sample_dag):
        """Test deletion of specific checkpoint."""
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id="to_delete", dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        success = await checkpoint_manager.delete_checkpoint(checkpoint_id)
        assert success is True

        # Verify checkpoint is gone
        with pytest.raises(CheckpointNotFoundError):
            await checkpoint_manager.load_checkpoint(checkpoint_id)

    @pytest.mark.asyncio
    async def test_get_checkpoint_size(self, checkpoint_manager, sample_dag):
        """Test checkpoint size calculation."""
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        size = await checkpoint_manager.get_checkpoint_size(checkpoint_id)
        assert size > 0

    @pytest.mark.asyncio
    async def test_validate_checkpoint(self, checkpoint_manager, sample_dag):
        """Test checkpoint validation."""
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        is_valid = await checkpoint_manager.validate_checkpoint(checkpoint_id)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_get_storage_stats(self, checkpoint_manager, sample_dag):
        """Test storage statistics."""
        # Create a few checkpoints
        for i in range(3):
            await checkpoint_manager.create_checkpoint(
                checkpoint_id=f"stats_test_{i}",
                dag=sample_dag,
                trigger=CheckpointTrigger.MANUAL,
            )

        stats = await checkpoint_manager.get_storage_stats()
        assert stats["total_checkpoints"] == 3
        assert stats["total_size_bytes"] > 0
        assert "storage_path" in stats

    # ==================== Context Manager Tests ====================

    @pytest.mark.asyncio
    async def test_context_manager_usage(self, test_config, sample_dag):
        """Test async context manager functionality."""
        async with CheckpointManager(test_config) as manager:
            checkpoint_id = await manager.create_checkpoint(
                checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
            )
            assert checkpoint_id is not None

        # Context manager should have called shutdown

    # ==================== Factory Method Tests ====================

    def test_create_default_factory(self):
        """Test default factory method."""
        manager = CheckpointManager.create_default()
        assert manager.config is not None
        assert manager.storage_path.exists()

    def test_create_in_memory_factory(self):
        """Test in-memory factory method."""
        manager = CheckpointManager.create_in_memory()
        assert manager.config.max_checkpoints == 5
        assert manager.config.max_age_hours == 1.0
        assert "roma_test_checkpoints_" in str(manager.storage_path)

    # ==================== Error Handling Tests ====================

    @pytest.mark.asyncio
    async def test_checkpoint_creation_failure_recovery(
        self, checkpoint_manager, sample_dag
    ):
        """Test graceful handling of checkpoint creation failures."""
        # Mock storage to fail
        with patch.object(
            checkpoint_manager,
            "_save_checkpoint",
            side_effect=Exception("Storage failed"),
        ):
            with pytest.raises(Exception, match="Checkpoint creation failed"):
                await checkpoint_manager.create_checkpoint(
                    checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
                )

    @pytest.mark.asyncio
    async def test_atomic_checkpoint_write(self, checkpoint_manager, sample_dag):
        """Test atomic checkpoint writing prevents corruption."""
        # This test verifies that checkpoint writes are atomic
        checkpoint_id = await checkpoint_manager.create_checkpoint(
            checkpoint_id=None, dag=sample_dag, trigger=CheckpointTrigger.MANUAL
        )

        # Checkpoint should exist and be valid
        checkpoint_path = checkpoint_manager._get_checkpoint_path(checkpoint_id)
        assert checkpoint_path.exists()

        # No temp files should remain
        temp_files = list(checkpoint_manager.storage_path.glob("*.tmp"))
        assert len(temp_files) == 0

    @pytest.mark.asyncio
    async def test_concurrent_checkpoint_operations(
        self, checkpoint_manager, sample_dag
    ):
        """Test concurrent checkpoint creation and cleanup."""
        # Create multiple checkpoints concurrently
        tasks = []
        for i in range(5):
            task = checkpoint_manager.create_checkpoint(
                checkpoint_id=f"concurrent_{i}",
                dag=sample_dag,
                trigger=CheckpointTrigger.MANUAL,
            )
            tasks.append(task)

        checkpoint_ids = await asyncio.gather(*tasks)
        assert len(checkpoint_ids) == 5
        assert all(cid for cid in checkpoint_ids)

    # ==================== Unique ID Generation Tests ====================

    def test_checkpoint_id_uniqueness(self, checkpoint_manager):
        """Test checkpoint ID generation produces unique IDs."""
        ids = set()
        for _ in range(100):
            checkpoint_id = checkpoint_manager._generate_checkpoint_id()
            assert checkpoint_id not in ids, f"Duplicate ID generated: {checkpoint_id}"
            ids.add(checkpoint_id)
            assert checkpoint_id.startswith("checkpoint_")

    def test_checkpoint_id_format(self, checkpoint_manager):
        """Test checkpoint ID format is correct."""
        checkpoint_id = checkpoint_manager._generate_checkpoint_id()
        parts = checkpoint_id.split("_")

        assert len(parts) == 5  # checkpoint_YYYYMMDD_HHMMSS_FFFFFF_UNIQUEID
        assert parts[0] == "checkpoint"
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 6  # HHMMSS
        assert len(parts[3]) == 6  # FFFFFF (microseconds)
        assert len(parts[4]) == 8  # UUID prefix
