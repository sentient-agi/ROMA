"""
Redis Cache Strategy for PTC Integration

Implements caching logic for PTC executions to reduce API costs
and improve response times.
"""

import hashlib
import json
from datetime import datetime, timedelta
from typing import Optional
from loguru import logger

try:
    import redis.asyncio as redis
except ImportError:
    import redis  # Fallback to sync redis

from .schemas import PTCExecutionPlan, PTCArtifactResult, CacheStrategy


class PTCCacheManager:
    """
    Manages Redis caching for PTC executions.

    Cache Key Strategy:
    -------------------
    ptc:exec:{hash} - Stores PTCArtifactResult
    ptc:meta:{hash} - Stores metadata (timestamp, TTL, etc.)

    Hash Computation:
    ----------------
    Hash is computed from:
    - Scaffolding spec (task, requirements, dependencies)
    - LLM configuration (primary_llm, fallback_llm)
    - Test configuration (enable_testing)

    This ensures semantically equivalent requests hit the same cache,
    while different configurations get separate cache entries.
    """

    # Cache key prefixes
    EXEC_PREFIX = "ptc:exec:"
    META_PREFIX = "ptc:meta:"

    # Default TTL (1 hour)
    DEFAULT_TTL = 3600

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Initialize cache manager.

        Args:
            redis_client: Redis client instance. If None, will attempt to
                         connect using environment variables.
        """
        self.redis = redis_client

    async def _ensure_connection(self):
        """Ensure Redis connection is established."""
        if self.redis is None:
            import os
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self.redis = await redis.from_url(redis_url, decode_responses=True)

    @staticmethod
    def compute_cache_key(plan: PTCExecutionPlan) -> str:
        """
        Compute deterministic cache key for an execution plan.

        The key is based on:
        - Task description and requirements
        - Dependencies
        - LLM configuration
        - Test enablement

        Args:
            plan: Execution plan to hash

        Returns:
            SHA256 hash (first 16 chars) for cache key
        """
        # Normalize the inputs for consistent hashing
        cache_input = {
            "task_description": plan.scaffolding.task_description.strip().lower(),
            "requirements": sorted([r.strip().lower() for r in plan.scaffolding.requirements]),
            "dependencies": sorted([d.strip().lower() for d in plan.scaffolding.dependencies]),
            "architecture": plan.scaffolding.architecture,
            "primary_llm": plan.primary_llm.value,
            "fallback_llm": plan.fallback_llm.value if plan.fallback_llm else None,
            "enable_testing": plan.enable_testing,
        }

        # Serialize to JSON with sorted keys for consistency
        json_str = json.dumps(cache_input, sort_keys=True)

        # Compute SHA256 hash
        hash_obj = hashlib.sha256(json_str.encode())
        hash_hex = hash_obj.hexdigest()

        # Use first 16 characters (64 bits) - sufficient for uniqueness
        return hash_hex[:16]

    def should_use_cache(
        self,
        plan: PTCExecutionPlan,
        cached_result: Optional[PTCArtifactResult] = None
    ) -> bool:
        """
        Determine if cache should be used based on strategy.

        Args:
            plan: Execution plan with cache strategy
            cached_result: Cached result if found, None otherwise

        Returns:
            True if cache should be used, False to regenerate
        """
        # NEVER strategy: always skip cache
        if plan.cache_strategy == CacheStrategy.NEVER:
            logger.debug(f"Cache strategy NEVER - skipping cache for {plan.execution_id}")
            return False

        # No cached result available
        if cached_result is None:
            logger.debug(f"No cached result found for {plan.execution_id}")
            return False

        # ALWAYS strategy: use cache if available
        if plan.cache_strategy == CacheStrategy.ALWAYS:
            logger.debug(f"Cache strategy ALWAYS - using cache for {plan.execution_id}")
            return True

        # SMART strategy: validate cache freshness
        if plan.cache_strategy == CacheStrategy.SMART:
            # Check if cached result was successful
            if not cached_result.success:
                logger.debug(f"Cached result was not successful - regenerating for {plan.execution_id}")
                return False

            # Check if cached result had tests (if testing is enabled in plan)
            if plan.enable_testing and cached_result.test_results is None:
                logger.debug(f"Plan requires testing but cache has no tests - regenerating for {plan.execution_id}")
                return False

            logger.debug(f"Cache strategy SMART - using valid cache for {plan.execution_id}")
            return True

        # Default: don't use cache
        return False

    async def get(self, plan: PTCExecutionPlan) -> Optional[PTCArtifactResult]:
        """
        Retrieve cached result for execution plan.

        Args:
            plan: Execution plan to look up

        Returns:
            Cached PTCArtifactResult if found and valid, None otherwise
        """
        await self._ensure_connection()

        cache_key = self.compute_cache_key(plan)
        exec_key = self.EXEC_PREFIX + cache_key

        try:
            # Get cached result
            cached_json = await self.redis.get(exec_key)

            if cached_json is None:
                logger.debug(f"Cache miss for key: {cache_key}")
                return None

            # Deserialize
            result = PTCArtifactResult.model_validate_json(cached_json)

            # Check if we should use this cached result
            if self.should_use_cache(plan, result):
                logger.info(f"Cache hit for key: {cache_key} (execution_id: {plan.execution_id})")
                return result
            else:
                logger.debug(f"Cache found but invalidated for key: {cache_key}")
                return None

        except Exception as e:
            logger.error(f"Error retrieving from cache: {e}")
            return None

    async def set(
        self,
        plan: PTCExecutionPlan,
        result: PTCArtifactResult,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Store result in cache.

        Args:
            plan: Execution plan (for key computation)
            result: Result to cache
            ttl: Time-to-live in seconds (None = use plan.cache_ttl or default)

        Returns:
            True if successfully cached, False otherwise
        """
        await self._ensure_connection()

        # Don't cache if strategy is NEVER
        if plan.cache_strategy == CacheStrategy.NEVER:
            logger.debug(f"Cache strategy NEVER - skipping cache write for {plan.execution_id}")
            return False

        # Don't cache failed results (unless explicitly requested)
        if not result.success:
            logger.debug(f"Result was not successful - skipping cache for {plan.execution_id}")
            return False

        cache_key = self.compute_cache_key(plan)
        exec_key = self.EXEC_PREFIX + cache_key
        meta_key = self.META_PREFIX + cache_key

        # Determine TTL
        ttl = ttl or plan.cache_ttl or self.DEFAULT_TTL

        try:
            # Serialize result
            result_json = result.model_dump_json()

            # Store result with TTL
            await self.redis.setex(exec_key, ttl, result_json)

            # Store metadata
            metadata = {
                "cached_at": datetime.utcnow().isoformat(),
                "execution_id": result.execution_id,
                "cache_key": cache_key,
                "ttl": ttl,
            }
            await self.redis.setex(meta_key, ttl, json.dumps(metadata))

            logger.info(f"Cached result for key: {cache_key} (TTL: {ttl}s, execution_id: {plan.execution_id})")
            return True

        except Exception as e:
            logger.error(f"Error storing in cache: {e}")
            return False

    async def invalidate(self, plan: PTCExecutionPlan) -> bool:
        """
        Invalidate cache entry for execution plan.

        Args:
            plan: Execution plan to invalidate

        Returns:
            True if cache was invalidated, False otherwise
        """
        await self._ensure_connection()

        cache_key = self.compute_cache_key(plan)
        exec_key = self.EXEC_PREFIX + cache_key
        meta_key = self.META_PREFIX + cache_key

        try:
            # Delete both keys
            deleted = await self.redis.delete(exec_key, meta_key)
            logger.info(f"Invalidated cache for key: {cache_key} (deleted {deleted} keys)")
            return deleted > 0

        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
            return False

    async def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        await self._ensure_connection()

        try:
            # Count cached executions
            exec_keys = await self.redis.keys(f"{self.EXEC_PREFIX}*")
            meta_keys = await self.redis.keys(f"{self.META_PREFIX}*")

            # Get Redis info
            info = await self.redis.info("memory")

            return {
                "cached_executions": len(exec_keys),
                "metadata_entries": len(meta_keys),
                "used_memory_human": info.get("used_memory_human", "unknown"),
                "maxmemory_human": info.get("maxmemory_human", "unknown"),
            }

        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {"error": str(e)}

    async def clear_all(self) -> int:
        """
        Clear all PTC cache entries.

        WARNING: This deletes all cached executions!

        Returns:
            Number of keys deleted
        """
        await self._ensure_connection()

        try:
            # Get all PTC cache keys
            exec_keys = await self.redis.keys(f"{self.EXEC_PREFIX}*")
            meta_keys = await self.redis.keys(f"{self.META_PREFIX}*")

            all_keys = exec_keys + meta_keys

            if not all_keys:
                logger.info("No PTC cache entries to clear")
                return 0

            # Delete all keys
            deleted = await self.redis.delete(*all_keys)
            logger.warning(f"Cleared all PTC cache: deleted {deleted} keys")
            return deleted

        except Exception as e:
            logger.error(f"Error clearing cache: {e}")
            return 0
