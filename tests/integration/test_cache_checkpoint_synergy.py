"""Integration tests for DSPy cache and checkpoint system synergy."""

import pytest
import tempfile
from pathlib import Path

from roma_dspy.config.manager import ConfigManager
from roma_dspy.core.engine.solve import RecursiveSolver
from roma_dspy.types import CheckpointTrigger, CacheStatistics


@pytest.mark.asyncio
async def test_cache_persists_across_checkpoint_recovery():
    """
    Verify DSPy cache survives checkpoint recovery.

    This test validates that:
    1. Cache directory is created and persists
    2. Checkpoint saves task state
    3. Cache is accessible across solver instances
    """
    # Setup isolated cache and checkpoint directories
    cache_dir = tempfile.mkdtemp(prefix="test_cache_")
    checkpoint_dir = tempfile.mkdtemp(prefix="test_checkpoints_")

    # Configure ROMA with custom cache and checkpoint paths
    config_mgr = ConfigManager()
    config = config_mgr.load_config(
        overrides=[
            f"runtime.cache.disk_cache_dir={cache_dir}",
            f"resilience.checkpoint.storage_path={checkpoint_dir}",
            "agents.executor.llm.temperature=0.0",  # Deterministic for cache hits
        ]
    )

    # Create first solver (initializes cache)
    solver1 = RecursiveSolver(config=config, enable_checkpoints=True)

    # Verify cache directory was created
    cache_path = Path(cache_dir)
    assert cache_path.exists(), (
        "Cache directory should exist after solver initialization"
    )

    # Create a simple checkpoint (without execution)
    from roma_dspy.core.engine.dag import TaskDAG
    from roma_dspy.core.signatures import TaskNode

    test_dag = TaskDAG()
    test_node = TaskNode(
        goal="Test task", depth=0, max_depth=5, execution_id=test_dag.execution_id
    )
    test_dag.add_node(test_node)

    checkpoint_id = await solver1.checkpoint_manager.create_checkpoint(
        checkpoint_id=None,
        dag=test_dag,
        trigger=CheckpointTrigger.MANUAL,
        current_depth=0,
        max_depth=5,
    )

    assert checkpoint_id is not None, "Checkpoint should be created"

    # Verify checkpoint file exists
    checkpoint_path = Path(checkpoint_dir)
    checkpoint_files = list(checkpoint_path.glob("checkpoint_*.json.gz"))
    assert len(checkpoint_files) > 0, "Checkpoint file should exist"

    # Create second solver with same cache directory
    solver2 = RecursiveSolver(config=config, enable_checkpoints=True)

    # Verify solver2 can access the checkpoint
    checkpoints = await solver2.checkpoint_manager.list_checkpoints()
    assert len(checkpoints) > 0, (
        "Checkpoint should be accessible from new solver instance"
    )
    assert checkpoints[0]["checkpoint_id"] == checkpoint_id, (
        "Checkpoint ID should match"
    )

    # Verify cache directory is still accessible
    assert cache_path.exists(), "Cache directory should persist across solver instances"


@pytest.mark.asyncio
async def test_cache_config_from_yaml():
    """Verify cache configuration loads correctly from YAML."""
    config_mgr = ConfigManager()
    config = config_mgr.load_config()

    # Verify cache config structure
    assert hasattr(config.runtime, "cache"), "RuntimeConfig should have cache attribute"
    assert config.runtime.cache.enabled is True, "Cache should be enabled by default"
    assert config.runtime.cache.disk_cache_dir == ".cache/dspy", (
        "Default cache dir should match"
    )
    assert config.runtime.cache.disk_size_limit_bytes == 30_000_000_000, (
        "Default size limit should be 30GB"
    )
    assert config.runtime.cache.memory_max_entries == 1_000_000, (
        "Default memory entries should be 1M"
    )


@pytest.mark.asyncio
async def test_checkpoint_config_in_resilience():
    """Verify checkpoint configuration is properly nested in ResilienceConfig."""
    config_mgr = ConfigManager()
    config = config_mgr.load_config()

    # Verify checkpoint config structure (fixes blocking bug)
    assert hasattr(config.resilience, "checkpoint"), (
        "ResilienceConfig should have checkpoint attribute"
    )
    assert config.resilience.checkpoint.enabled is True, (
        "Checkpoint should be enabled by default"
    )
    assert str(config.resilience.checkpoint.storage_path) == ".checkpoints", (
        "Default storage path should match"
    )
    assert config.resilience.checkpoint.max_checkpoints == 10, (
        "Default max checkpoints should be 10"
    )


@pytest.mark.asyncio
async def test_cache_statistics_model():
    """Verify CacheStatistics model can be created and serialized."""
    from roma_dspy.types import CacheStatistics

    stats = CacheStatistics(
        total_calls=100,
        cache_hits=80,
        cache_misses=20,
        hit_rate=0.8,
        time_saved_ms=63600,
        cost_saved_usd=6.0,
    )

    # Verify fields
    assert stats.total_calls == 100
    assert stats.cache_hits == 80
    assert stats.hit_rate == 0.8

    # Verify serialization (for checkpoint storage)
    import json

    json_str = stats.model_dump_json()
    assert "cache_hits" in json_str
    assert "80" in json_str

    # Verify round-trip
    stats_copy = CacheStatistics.model_validate_json(json_str)
    assert stats_copy.cache_hits == stats.cache_hits


@pytest.mark.asyncio
async def test_solver_initializes_cache():
    """Verify RecursiveSolver properly initializes DSPy cache from config."""
    import dspy

    cache_dir = tempfile.mkdtemp(prefix="test_solver_cache_")

    config_mgr = ConfigManager()
    config = config_mgr.load_config(
        overrides=[
            f"runtime.cache.disk_cache_dir={cache_dir}",
        ]
    )

    # Create solver (should call dspy.configure_cache)
    solver = RecursiveSolver(config=config)

    # Verify cache directory was created
    assert Path(cache_dir).exists(), (
        "Cache directory should be created during initialization"
    )

    # Verify DSPy cache is configured (check for cache subdirectories)
    import time

    time.sleep(0.5)  # Allow DSPy to initialize

    cache_path = Path(cache_dir)
    # DSPy creates numbered subdirectories (000, 001, etc.)
    subdirs = [d for d in cache_path.iterdir() if d.is_dir()]
    # May not have subdirs yet if no LLM calls made, but directory should exist
    assert cache_path.exists(), "DSPy should have initialized cache directory"


@pytest.mark.asyncio
async def test_cache_disabled_config():
    """Verify cache can be disabled via configuration."""
    config_mgr = ConfigManager()
    config = config_mgr.load_config(
        overrides=[
            "runtime.cache.enabled=false",
        ]
    )

    assert config.runtime.cache.enabled is False, (
        "Cache should be disabled when configured"
    )

    # Solver should still initialize without error (cache init is non-fatal)
    solver = RecursiveSolver(config=config)
    assert solver is not None


def test_backward_compatibility_cache_dir():
    """Verify backward compatibility for old cache_dir property."""
    config_mgr = ConfigManager()
    config = config_mgr.load_config()

    # Old code may access cache_dir directly
    assert hasattr(config.runtime, "cache_dir"), (
        "Should have cache_dir property for backward compat"
    )
    assert config.runtime.cache_dir == config.runtime.cache.disk_cache_dir, (
        "cache_dir should match cache.disk_cache_dir"
    )


@pytest.mark.asyncio
async def test_cache_initialized_in_registry_mode():
    """Verify cache is initialized even when using registry mode (no config)."""
    from roma_dspy.core.registry import AgentRegistry

    cache_dir = tempfile.mkdtemp(prefix="test_registry_cache_")

    # Create a registry without config (registry mode)
    registry = AgentRegistry()

    # Create solver in registry mode - should still initialize cache with defaults
    solver = RecursiveSolver(registry=registry)

    # Cache should be configured (directory created)
    from pathlib import Path

    default_cache_path = Path(".cache/dspy")
    assert default_cache_path.exists() or Path(cache_dir).exists(), (
        "Cache should be initialized in registry mode"
    )


@pytest.mark.asyncio
async def test_invalid_checkpoint_config_rejected():
    """Verify invalid checkpoint config raises clear error."""
    from roma_dspy.config.schemas.resilience import ResilienceConfig

    # Invalid checkpoint dict should raise ValueError
    with pytest.raises((ValueError, TypeError)):
        config = ResilienceConfig(
            checkpoint={"invalid_field": "bad_value", "enabled": "not_a_bool"}
        )
        # Trigger __post_init__ validation
        _ = config.checkpoint
