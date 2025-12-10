"""
Tests for PTC cache manager.

Tests cache key computation, caching strategies, and Redis operations.
"""

import pytest
from datetime import datetime

from roma_dspy.ptc.cache import PTCCacheManager
from roma_dspy.ptc.schemas import (
    PTCExecutionPlan,
    PTCArtifactResult,
    ScaffoldingSpec,
    CodeArtifact,
    LLMProvider,
    CacheStrategy,
    ExecutionStatus,
)


class TestCacheKeyComputation:
    """Test cache key computation logic."""

    def test_identical_plans_same_key(self):
        """Identical plans should produce the same cache key."""
        plan1 = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(
                task_description="Build API",
                requirements=["Auth", "Logging"],
                dependencies=["fastapi"]
            )
        )

        plan2 = PTCExecutionPlan(
            execution_id="exec-002",  # Different execution ID
            scaffolding=ScaffoldingSpec(
                task_description="Build API",
                requirements=["Auth", "Logging"],
                dependencies=["fastapi"]
            )
        )

        key1 = PTCCacheManager.compute_cache_key(plan1)
        key2 = PTCCacheManager.compute_cache_key(plan2)

        assert key1 == key2, "Identical plans should have same cache key"

    def test_case_insensitive_hashing(self):
        """Cache key should be case-insensitive for task descriptions."""
        plan1 = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(task_description="Build API")
        )

        plan2 = PTCExecutionPlan(
            execution_id="exec-002",
            scaffolding=ScaffoldingSpec(task_description="build api")
        )

        key1 = PTCCacheManager.compute_cache_key(plan1)
        key2 = PTCCacheManager.compute_cache_key(plan2)

        assert key1 == key2, "Cache key should be case-insensitive"

    def test_different_requirements_different_key(self):
        """Different requirements should produce different cache keys."""
        plan1 = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(
                task_description="Build API",
                requirements=["Auth"]
            )
        )

        plan2 = PTCExecutionPlan(
            execution_id="exec-002",
            scaffolding=ScaffoldingSpec(
                task_description="Build API",
                requirements=["Logging"]
            )
        )

        key1 = PTCCacheManager.compute_cache_key(plan1)
        key2 = PTCCacheManager.compute_cache_key(plan2)

        assert key1 != key2, "Different requirements should have different cache keys"

    def test_order_independent_requirements(self):
        """Requirements order should not affect cache key."""
        plan1 = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(
                task_description="Build API",
                requirements=["Auth", "Logging", "Metrics"]
            )
        )

        plan2 = PTCExecutionPlan(
            execution_id="exec-002",
            scaffolding=ScaffoldingSpec(
                task_description="Build API",
                requirements=["Metrics", "Auth", "Logging"]
            )
        )

        key1 = PTCCacheManager.compute_cache_key(plan1)
        key2 = PTCCacheManager.compute_cache_key(plan2)

        assert key1 == key2, "Requirements order should not affect cache key"

    def test_llm_config_affects_key(self):
        """Different LLM configuration should produce different cache keys."""
        plan1 = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(task_description="Build API"),
            primary_llm=LLMProvider.CLAUDE
        )

        plan2 = PTCExecutionPlan(
            execution_id="exec-002",
            scaffolding=ScaffoldingSpec(task_description="Build API"),
            primary_llm=LLMProvider.KIMI
        )

        key1 = PTCCacheManager.compute_cache_key(plan1)
        key2 = PTCCacheManager.compute_cache_key(plan2)

        assert key1 != key2, "Different LLM config should have different cache keys"


class TestCacheStrategy:
    """Test cache strategy logic."""

    def test_never_strategy_always_skips_cache(self):
        """NEVER strategy should never use cache."""
        manager = PTCCacheManager()

        plan = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(task_description="Test"),
            cache_strategy=CacheStrategy.NEVER
        )

        # Even with a cached result
        cached_result = PTCArtifactResult(
            execution_id="exec-001",
            status=ExecutionStatus.SUCCESS,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=1.0
        )

        assert manager.should_use_cache(plan, cached_result) is False

    def test_always_strategy_uses_cache(self):
        """ALWAYS strategy should use cache when available."""
        manager = PTCCacheManager()

        plan = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(task_description="Test"),
            cache_strategy=CacheStrategy.ALWAYS
        )

        cached_result = PTCArtifactResult(
            execution_id="exec-001",
            status=ExecutionStatus.SUCCESS,
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=1.0
        )

        assert manager.should_use_cache(plan, cached_result) is True

    def test_smart_strategy_validates_success(self):
        """SMART strategy should reject failed cached results."""
        manager = PTCCacheManager()

        plan = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(task_description="Test"),
            cache_strategy=CacheStrategy.SMART
        )

        # Failed cached result
        failed_result = PTCArtifactResult(
            execution_id="exec-001",
            status=ExecutionStatus.FAILURE,
            error_message="Failed",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=1.0
        )

        assert manager.should_use_cache(plan, failed_result) is False

    def test_smart_strategy_validates_tests(self):
        """SMART strategy should reject cache without tests when tests are required."""
        manager = PTCCacheManager()

        plan = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(task_description="Test"),
            cache_strategy=CacheStrategy.SMART,
            enable_testing=True
        )

        # Successful result but no tests
        result_without_tests = PTCArtifactResult(
            execution_id="exec-001",
            status=ExecutionStatus.SUCCESS,
            test_results=None,  # No tests
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            duration_seconds=1.0
        )

        assert manager.should_use_cache(plan, result_without_tests) is False

    def test_no_cached_result_returns_false(self):
        """All strategies should return False when no cached result exists."""
        manager = PTCCacheManager()

        for strategy in [CacheStrategy.ALWAYS, CacheStrategy.NEVER, CacheStrategy.SMART]:
            plan = PTCExecutionPlan(
                execution_id="exec-001",
                scaffolding=ScaffoldingSpec(task_description="Test"),
                cache_strategy=strategy
            )

            assert manager.should_use_cache(plan, None) is False


class TestCacheKeyFormat:
    """Test cache key format and structure."""

    def test_cache_key_length(self):
        """Cache key should be 16 characters (64 bits)."""
        plan = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(task_description="Test")
        )

        cache_key = PTCCacheManager.compute_cache_key(plan)

        assert len(cache_key) == 16, "Cache key should be 16 hex characters"
        assert all(c in "0123456789abcdef" for c in cache_key), "Cache key should be hex"

    def test_cache_key_deterministic(self):
        """Same plan should always produce the same cache key."""
        plan = PTCExecutionPlan(
            execution_id="exec-001",
            scaffolding=ScaffoldingSpec(
                task_description="Build API",
                requirements=["Auth"],
                dependencies=["fastapi"]
            )
        )

        key1 = PTCCacheManager.compute_cache_key(plan)
        key2 = PTCCacheManager.compute_cache_key(plan)
        key3 = PTCCacheManager.compute_cache_key(plan)

        assert key1 == key2 == key3, "Cache key should be deterministic"
