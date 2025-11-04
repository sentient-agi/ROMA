"""Runtime helpers for module execution and DAG manipulation."""

from __future__ import annotations

import asyncio
import inspect
import time
from datetime import datetime
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, TYPE_CHECKING

import dspy
from loguru import logger

from roma_dspy.core.artifacts.filesystem_scanner import (
    scan_execution_directory,
    auto_register_scanned_files,
)
from roma_dspy.core.artifacts.text_parser import parse_and_register_artifacts
from roma_dspy.core.context import ExecutionContext
from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.core.observability import get_span_manager
from roma_dspy.core.registry import AgentRegistry
from roma_dspy.core.signatures import SubTask, TaskNode
from roma_dspy.resilience import with_module_resilience, measure_execution_time
from roma_dspy.tools.base.manager import ToolkitManager
from roma_dspy.types import ModuleResult, NodeType, TaskStatus, AgentType, TokenMetrics
from roma_dspy.types.artifact_injection import ArtifactInjectionMode

if TYPE_CHECKING:
    from ..context import ContextManager


SolveFn = Callable[[TaskNode, TaskDAG, int], TaskNode]
AsyncSolveFn = Callable[[TaskNode, TaskDAG, int], Awaitable[TaskNode]]


class ContextStore:
    """Thread-safe storage for task execution contexts with O(1) lookup."""

    def __init__(self) -> None:
        self._store: Dict[str, str] = {}
        self._lock = asyncio.Lock()
        # Map subgraph_id -> {index -> task_id}
        self._index_maps: Dict[str, Dict[int, str]] = {}

        # Execution context for LM tracing
        self._execution_id: Optional[str] = None
        self._postgres_storage: Optional[Any] = None

    def __getstate__(self) -> dict:
        """
        Customize pickling/deepcopy behaviour.

        asyncio.Lock instances hold a thread lock that isn't pickleable. During
        deepcopy(), we drop the lock and recreate it in __setstate__.
        """
        state = self.__dict__.copy()
        state.pop("_lock", None)
        return state

    def __setstate__(self, state: dict) -> None:
        self.__dict__.update(state)
        self._lock = asyncio.Lock()

    async def store_result(self, task_id: str, result: str) -> None:
        """
        Store task result in a thread-safe manner.

        Args:
            task_id: Unique task identifier
            result: Task execution result
        """
        async with self._lock:
            self._store[task_id] = result

    def store_result_sync(self, task_id: str, result: str) -> None:
        """
        Store task result synchronously without async locking.

        WARNING: Not thread-safe. Use only in synchronous execution contexts
        where async locking is not available.

        Args:
            task_id: Unique task identifier
            result: Task execution result
        """
        self._store[task_id] = result

    def get_result(self, task_id: str) -> Optional[str]:
        """
        Retrieve task result with O(1) lookup.

        Args:
            task_id: Unique task identifier

        Returns:
            Task result or None if not found
        """
        return self._store.get(task_id)

    def register_index_mapping(self, subgraph_id: str, index: int, task_id: str) -> None:
        """
        Register mapping between subtask index and task_id for a subgraph.

        Args:
            subgraph_id: ID of the subgraph
            index: Integer index of subtask in the list (0-based)
            task_id: Actual task ID
        """
        if subgraph_id not in self._index_maps:
            self._index_maps[subgraph_id] = {}
        self._index_maps[subgraph_id][index] = task_id

    def get_task_id_from_index(self, subgraph_id: str, index: int) -> Optional[str]:
        """
        Get task_id from subtask index within a subgraph.

        Args:
            subgraph_id: ID of the subgraph
            index: Integer index of subtask

        Returns:
            Task ID or None if not found
        """
        return self._index_maps.get(subgraph_id, {}).get(index)

    def set_execution_context(
        self,
        execution_id: str,
        postgres_storage: Optional[Any] = None
    ) -> None:
        """Set execution context for LM trace persistence.

        Args:
            execution_id: Unique execution identifier
            postgres_storage: Optional PostgresStorage instance
        """
        self._execution_id = execution_id
        self._postgres_storage = postgres_storage

    def get_execution_context(self) -> tuple[Optional[str], Optional[Any]]:
        """Get execution context for LM tracing.

        Returns:
            Tuple of (execution_id, postgres_storage)
        """
        return self._execution_id, self._postgres_storage

    def get_context_for_dependencies(self, dep_ids: List[str]) -> str:
        """
        Build context string from dependency task results.

        Args:
            dep_ids: List of dependency task IDs

        Returns:
            Formatted context string with all dependency results
        """
        contexts = []
        for dep_id in dep_ids:
            result = self.get_result(dep_id)
            if result:
                contexts.append(f"[Task {dep_id[:8]}]: {result}")
        return "\n\n".join(contexts) if contexts else ""

    def get_context_for_dependency_indices(
        self,
        subgraph_id: str,
        dep_indices: List[str]
    ) -> str:
        """
        Build context string from dependency indices within a subgraph.

        Args:
            subgraph_id: ID of the subgraph
            dep_indices: List of string indices (e.g., ['0', '1'])

        Returns:
            Formatted context string with all dependency results
        """
        contexts = []
        index_map = self._index_maps.get(subgraph_id, {})

        for dep_idx_str in dep_indices:
            try:
                dep_idx = int(dep_idx_str)
                task_id = index_map.get(dep_idx)
                if task_id:
                    result = self.get_result(task_id)
                    if result:
                        contexts.append(f"[Subtask {dep_idx}]: {result}")
            except (ValueError, TypeError):
                continue

        return "\n\n".join(contexts) if contexts else ""

    def clear_subgraph(self, task_ids: List[str]) -> None:
        """
        Clear results for specific tasks to free memory.

        Args:
            task_ids: List of task IDs to remove from store
        """
        for task_id in task_ids:
            self._store.pop(task_id, None)

    def get_all_contexts(self) -> Dict[str, str]:
        """
        Get all stored contexts for inspection/debugging.

        Returns:
            Dictionary mapping task_id to result
        """
        return dict(self._store)

    def get_context_summary(self) -> str:
        """
        Get human-readable summary of all stored contexts.

        Returns:
            Formatted string showing all task results
        """
        if not self._store:
            return "No contexts stored yet."

        lines = ["Context Store Summary:", "=" * 80]
        for task_id, result in self._store.items():
            lines.append(f"\nTask ID: {task_id[:8]}...")
            result_str = str(result) if not isinstance(result, str) else result
            lines.append(f"Result: {result_str[:200]}{'...' if len(result_str) > 200 else ''}")
            lines.append("-" * 80)
        return "\n".join(lines)

    def get_task_index(self, subgraph_id: str, task_id: str) -> Optional[int]:
        """
        Get the index of a task within its subgraph.

        Args:
            subgraph_id: ID of the subgraph
            task_id: Task ID to look up

        Returns:
            Integer index or None if not found
        """
        index_map = self._index_maps.get(subgraph_id, {})
        for idx, tid in index_map.items():
            if tid == task_id:
                return idx
        return None


class ModuleRuntime:
    """Module orchestration using AgentRegistry for task-aware agent selection."""

    def __init__(
        self,
        registry: AgentRegistry,
        context_manager: Optional["ContextManager"] = None,
        config: Optional[Any] = None
    ) -> None:
        self.registry = registry
        self.context_store = ContextStore()
        self.context_manager = context_manager  # Set by solver after initialization
        self.config = config  # ROMAConfig for accessing agent configurations

    # ------------------------------------------------------------------
    # Helper: Extract tools data from agent for context building
    # ------------------------------------------------------------------

    async def _get_tools_data_async(self, agent: "BaseModule") -> list[dict]:
        """Extract tool information from agent for context building.

        Returns:
            List of dicts with 'name' and 'description' keys
        """
        if not (hasattr(agent, '_toolkit_configs') and agent._toolkit_configs):
            return []

        ctx = ExecutionContext.get()
        if not (ctx and ctx.file_storage):
            return []

        try:
            manager = ToolkitManager.get_instance()
            tools_dict = await manager.get_tools_for_execution(
                execution_id=ctx.execution_id,
                file_storage=ctx.file_storage,
                toolkit_configs=agent._toolkit_configs
            )
            return [
                {"name": name, "description": getattr(tool, "__doc__", "No description available")}
                for name, tool in tools_dict.items()
            ]
        except Exception as e:
            logger.warning(f"Failed to load toolkit tools: {e}")
            return []

    def _extract_token_usage(self, result: Any) -> tuple[int, int, int]:
        """Extract token usage from DSPy result.

        Returns:
            Tuple of (prompt_tokens, completion_tokens, total_tokens)
        """
        usage = getattr(result, 'get_lm_usage', lambda: None)()
        if not usage or not isinstance(usage, dict):
            return 0, 0, 0

        # Get first model's usage data
        for model_usage in usage.values():
            if isinstance(model_usage, dict):
                prompt = model_usage.get('prompt_tokens', 0)
                completion = model_usage.get('completion_tokens', 0)
                total = model_usage.get('total_tokens', prompt + completion)
                return prompt, completion, total

        return 0, 0, 0

    async def _persist_lm_trace(
        self,
        execution_id: str,
        postgres: Any,
        module: Any,
        result: Any,
        start_time: float,
        task_id: str
    ) -> None:
        """Persist LM call trace to Postgres with retry logic for FK violations."""
        max_retries = 3
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                latency_ms = int((time.time() - start_time) * 1000)
                prompt_tokens, completion_tokens, total_tokens = self._extract_token_usage(result)

                # Get model configuration
                lm = getattr(module, 'lm', None) or getattr(module, '_lm', None)
                model = getattr(lm, 'model', 'unknown') if lm else 'unknown'
                temperature = getattr(lm, 'kwargs', {}).get('temperature') if lm else None
                max_tokens = getattr(lm, 'kwargs', {}).get('max_tokens') if lm else None

                # Get cost
                usage = getattr(result, 'get_lm_usage', lambda: {})()
                cost_usd = usage.get('cost') if isinstance(usage, dict) else None
                if not cost_usd and hasattr(result, 'metrics'):
                    cost_usd = getattr(result.metrics, 'cost', None)

                await postgres.save_lm_trace(
                    execution_id=execution_id,
                    task_id=task_id,
                    module_name=module.__class__.__name__.lower(),
                    model=model,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    cost_usd=cost_usd,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    prediction_strategy=str(getattr(module, '_prediction_strategy', None)),
                    latency_ms=latency_ms,
                    metadata={"success": True}
                )
                return

            except Exception as e:
                error_str = str(e).lower()
                is_fk_violation = any(k in error_str for k in ('foreign key', 'fkey', 'violates foreign key constraint'))

                if is_fk_violation and attempt < max_retries - 1:
                    logger.warning(f"FK violation on attempt {attempt + 1}/{max_retries}, retrying...")
                    await asyncio.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.warning(f"Failed to persist LM trace: {e}")
                    return

    async def _execute_agent_with_tracing(
        self,
        agent_type: AgentType,
        task: TaskNode,
        dag: TaskDAG,
        *,
        prepare_module_kwargs: Callable[[TaskNode, Optional[str]], dict],
        process_result: Callable[[TaskNode, Any, float, Any, Any, TaskDAG], TaskNode],
    ) -> TaskNode:
        """Execute agent with MLflow tracing and LM persistence.

        Eliminates ~175 lines of duplicate code by extracting common execution pattern.
        """
        agent = self.registry.get_agent(agent_type, task.task_type)

        # Build context with tools if available
        context = None
        if self.context_manager:
            tools_data = await self._get_tools_data_async(agent)

            # Get artifact injection mode from agent config (default: FULL)
            injection_mode_str = "full"  # Default
            if self.config and hasattr(self.config, 'agents') and self.config.agents:
                agent_config = self.config.agents.get_config_for_agent(agent_type)
                if agent_config and hasattr(agent_config, 'artifact_injection_mode'):
                    injection_mode_str = agent_config.artifact_injection_mode
            injection_mode = ArtifactInjectionMode.from_string(injection_mode_str)

            # Executor, Planner, Aggregator have specialized async context builders with artifact injection
            if agent_type == AgentType.EXECUTOR:
                context = await self.context_manager.build_executor_context(
                    task, tools_data, self, dag, injection_mode
                )
            elif agent_type == AgentType.PLANNER:
                context = await self.context_manager.build_planner_context(
                    task, tools_data, self, dag, injection_mode
                )
            elif agent_type == AgentType.AGGREGATOR:
                context = await self.context_manager.build_aggregator_context(
                    task, tools_data, self, dag, injection_mode
                )
            else:
                # Atomizer, Verifier use fundamental context only (no artifacts)
                context = self.context_manager.build_basic_context(task, tools_data)

        try:
            start_time = time.time()
            module_kwargs = prepare_module_kwargs(task, context)

            # Preserve existing DSPy callbacks via dspy_context parameter
            existing_callbacks = list(dspy.settings.callbacks) if hasattr(dspy.settings, 'callbacks') else []
            module_kwargs['dspy_context'] = {'callbacks': existing_callbacks}

            # Execute with ROMA span wrapper
            span_manager = get_span_manager()
            with span_manager.create_span(agent_type, task, agent.__class__.__name__):
                result, duration, token_metrics, messages = await self._async_execute_module(
                    agent, **module_kwargs
                )

            # Persist LM trace
            execution_id, postgres = self.context_store.get_execution_context()
            if postgres and execution_id:
                await self._persist_lm_trace(
                    execution_id, postgres, agent, result, start_time, task.task_id
                )

            # Artifact detection (multi-layer approach):
            # 1. Priority registration: DataStorage.store_parquet (already runs automatically)
            # 2. Tool output detection: track_tool_invocation decorator (already runs automatically)
            # 3. Text parser: Parse LLM output for explicit artifact declarations (MD/JSON/XML)
            # 4. Filesystem scanner: Scan for any remaining files not caught by above layers (fallback)
            await self._run_text_parser(task, result)
            await self._run_filesystem_scanner(task, start_time)

            return process_result(task, result, duration, token_metrics, messages, dag)

        except Exception as e:
            self._enhance_error_context(e, agent_type, task)
            raise

    # ------------------------------------------------------------------
    # Core module execution helpers
    # ------------------------------------------------------------------


    async def atomize_async(self, task: TaskNode, dag: TaskDAG) -> TaskNode:
        task = task.transition_to(TaskStatus.ATOMIZING)

        def prepare_kwargs(t, context):
            # Module.aforward now uses: (goal, *, context=...)
            return {"goal": t.goal, "context": context}

        def process_result(t, result, duration, token_metrics, messages, dag):
            t = self._record_module_result(
                t,
                "atomizer",
                t.goal,
                {"is_atomic": result.is_atomic, "node_type": result.node_type.value},
                duration,
                token_metrics=token_metrics,
                messages=messages,
            )
            t = t.set_node_type(result.node_type)
            dag.update_node(t)
            return t

        return await self._execute_agent_with_tracing(
            AgentType.ATOMIZER,
            task,
            dag,
            prepare_module_kwargs=prepare_kwargs,
            process_result=process_result,
        )

    def transition_from_atomizing(self, task: TaskNode, dag: TaskDAG) -> TaskNode:
        if task.node_type == NodeType.EXECUTE:
            task = task.transition_to(TaskStatus.EXECUTING)
        else:
            task = task.transition_to(TaskStatus.PLANNING)
        dag.update_node(task)
        return task


    async def plan_async(self, task: TaskNode, dag: TaskDAG) -> TaskNode:
        def prepare_kwargs(t, context):
            return {"goal": t.goal, "context": context}

        def process_result(t, result, duration, token_metrics, messages, dag):
            t = self._record_module_result(
                t,
                "planner",
                t.goal,
                {
                    "subtasks": [s.model_dump() for s in result.subtasks],
                    "dependencies": result.dependencies_graph,
                },
                duration,
                token_metrics=token_metrics,
                messages=messages,
            )
            t = self._create_subtask_graph(t, dag, result)
            t = t.transition_to(TaskStatus.PLAN_DONE)
            dag.update_node(t)
            return t

        return await self._execute_agent_with_tracing(
            AgentType.PLANNER,
            task,
            dag,
            prepare_module_kwargs=prepare_kwargs,
            process_result=process_result,
        )


    async def execute_async(self, task: TaskNode, dag: TaskDAG) -> TaskNode:
        # Capture context in closure for use in process_result
        context_captured = None

        def prepare_kwargs(t: TaskNode, context: Optional[str]) -> dict:
            nonlocal context_captured
            context_captured = context
            # FIX: Executor.aforward expects "context" parameter (ExecutorSignature.context)
            return {"goal": t.goal, "context": context}

        def process_result(t: TaskNode, result: Any, duration: float, token_metrics: Any, messages: Any, dag: TaskDAG) -> TaskNode:
            # Record with context metadata
            metadata = {}
            if context_captured and isinstance(context_captured, str):
                metadata["context_received"] = context_captured[:200] + "..." if len(context_captured) > 200 else context_captured
                if t.dependencies:
                    metadata["dependency_ids"] = list(t.dependencies)
            # Capture sources for provenance tracking
            if hasattr(result, 'sources') and result.sources:
                metadata["sources"] = result.sources

            t = self._record_module_result(
                t, "executor", t.goal, result.output, duration,
                metadata=metadata, token_metrics=token_metrics, messages=messages
            )
            t = t.with_result(result.output)
            dag.update_node(t)
            return t

        task = await self._execute_agent_with_tracing(
            AgentType.EXECUTOR,
            task,
            dag,
            prepare_module_kwargs=prepare_kwargs,
            process_result=process_result,
        )

        # Store result for future dependent tasks
        await self.context_store.store_result(task.task_id, task.result)
        return task


    async def force_execute_async(self, task: TaskNode, dag: TaskDAG) -> TaskNode:
        task = task.set_node_type(NodeType.EXECUTE)
        task = task.transition_to(TaskStatus.EXECUTING)
        dag.update_node(task)

        # Capture context in closure for use in process_result
        context_captured = None

        def prepare_kwargs(t: TaskNode, context: Optional[str]) -> dict:
            nonlocal context_captured
            context_captured = context
            # FIX: Executor.aforward expects "context" parameter (ExecutorSignature.context)
            return {"goal": t.goal, "context": context}

        def process_result(t: TaskNode, result: Any, duration: float, token_metrics: Any, messages: Any, dag: TaskDAG) -> TaskNode:
            # Record with context metadata (forced execution has additional metadata)
            metadata = {"forced": True, "depth": t.depth}
            if context_captured and isinstance(context_captured, str):
                metadata["context_received"] = context_captured[:200] + "..." if len(context_captured) > 200 else context_captured
                if t.dependencies:
                    metadata["dependency_ids"] = list(t.dependencies)
            # Capture sources for provenance tracking
            if hasattr(result, 'sources') and result.sources:
                metadata["sources"] = result.sources

            t = self._record_module_result(
                t, "executor", t.goal, result.output, duration,
                metadata=metadata, token_metrics=token_metrics, messages=messages
            )
            t = t.with_result(result.output)
            dag.update_node(t)
            return t

        task = await self._execute_agent_with_tracing(
            AgentType.EXECUTOR,
            task,
            dag,
            prepare_module_kwargs=prepare_kwargs,
            process_result=process_result,
        )

        # Store result for future dependent tasks
        await self.context_store.store_result(task.task_id, task.result)
        return task


    async def aggregate_async(
        self,
        task: TaskNode,
        subgraph: Optional[TaskDAG],
        dag: TaskDAG,
    ) -> TaskNode:
        if task.status != TaskStatus.PLAN_DONE:
            return task
        task = task.transition_to(TaskStatus.AGGREGATING)

        # Collect subtask results for aggregation
        subtask_results = self._collect_subtask_results(subgraph)

        def prepare_kwargs(t: TaskNode, context: Optional[str]) -> dict:
            return {
                "original_goal": t.goal,
                "subtasks_results": subtask_results,
                "context": context,
            }

        def process_result(t: TaskNode, result: Any, duration: float, token_metrics: Any, messages: Any, dag: TaskDAG) -> TaskNode:
            t = self._record_module_result(
                t,
                "aggregator",
                {"original_goal": t.goal, "subtask_count": len(subtask_results)},
                result.synthesized_result,
                duration,
                token_metrics=token_metrics,
                messages=messages,
            )
            t = t.with_result(result.synthesized_result)
            dag.update_node(t)
            return t

        return await self._execute_agent_with_tracing(
            AgentType.AGGREGATOR,
            task,
            dag,
            prepare_module_kwargs=prepare_kwargs,
            process_result=process_result,
        )

    # ------------------------------------------------------------------
    # Subgraph helpers
    # ------------------------------------------------------------------

    async def process_subgraph_async(
        self,
        task: TaskNode,
        dag: TaskDAG,
        solve_fn: AsyncSolveFn,
    ) -> TaskNode:
        subgraph = dag.get_subgraph(task.subgraph_id) if task.subgraph_id else None
        if subgraph:
            await self.solve_subgraph_async(subgraph, solve_fn)
            task = await self.aggregate_async(task, subgraph, dag)
        return task

    async def solve_subgraph_async(
        self,
        subgraph: TaskDAG,
        solve_fn: AsyncSolveFn,
    ) -> None:
        pending = set(subgraph.graph.nodes())
        completed: set[str] = set()

        while pending:
            ready = self._get_ready_tasks(subgraph, pending, completed)
            if not ready:
                break

            solved_tasks = await self._execute_tasks_parallel(ready, subgraph, solve_fn)
            for solved_task in solved_tasks:
                subgraph.update_node(solved_task)
                pending.remove(solved_task.task_id)
                completed.add(solved_task.task_id)

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    @measure_execution_time
    @with_module_resilience(module_name="module_execution")
    async def _async_execute_module(self, module, *args, **kwargs):
        return await module.aforward(*args, **kwargs)

    async def _run_text_parser(self, task: TaskNode, result: Any) -> None:
        """
        Run text parser to detect explicit artifact declarations in LLM output.

        Parses LLM output for artifact declarations in Markdown, JSON, and XML formats.
        This layer catches explicitly declared artifacts before filesystem scanning.

        Args:
            task: Task node being executed
            result: Module execution result (may contain artifact declarations)
        """
        try:
            # Extract text from result
            text = None
            if hasattr(result, 'output') and result.output:
                text = str(result.output)
            elif isinstance(result, str):
                text = result

            if not text:
                return

            # Parse and register artifacts
            execution_id = task.execution_id
            await parse_and_register_artifacts(text, execution_id)

        except Exception as e:
            # Silent failure - don't break execution
            logger.debug(f"Text parser failed for task {task.task_id}: {e}")

    async def _run_filesystem_scanner(self, task: TaskNode, start_time: float) -> None:
        """
        Run filesystem scanner to detect and register artifacts created during execution.

        This is a fallback detection layer that catches files not already registered
        by priority registration (parquet files) or tool output detection.

        Args:
            task: Task node being executed
            start_time: Execution start timestamp for filtering new files
        """
        try:
            # Get execution context
            ctx = ExecutionContext.get()
            if not ctx or not ctx.file_storage:
                return

            # Scan execution directory for new files
            from pathlib import Path
            execution_dir = Path(ctx.file_storage.root)
            found_files = scan_execution_directory(execution_dir, start_time)

            # Auto-register with deduplication
            if found_files:
                execution_id = task.execution_id or ctx.execution_id
                await auto_register_scanned_files(
                    file_paths=[str(f) for f in found_files],
                    execution_id=execution_id
                )

        except Exception as e:
            # Silent failure - don't break execution
            logger.debug(f"Filesystem scanner failed for task {task.task_id}: {e}")

    def _record_module_result(
        self,
        task: TaskNode,
        module_name: str,
        input_data,
        output_data,
        duration: float,
        metadata: Optional[dict] = None,
        token_metrics: Optional[TokenMetrics] = None,
        messages: Optional[list] = None,
    ) -> TaskNode:
        module_result = ModuleResult(
            module_name=module_name,
            input=input_data,
            output=output_data,
            timestamp=datetime.now(),
            duration=duration,
            metadata=metadata or {},
            token_metrics=token_metrics,
            messages=messages,
        )
        return task.record_module_execution(module_name, module_result)

    def _create_subtask_graph(self, task: TaskNode, dag: TaskDAG, planner_result) -> TaskNode:
        subtask_nodes: List[TaskNode] = []

        # Create TaskNodes for each subtask
        for idx, subtask in enumerate(planner_result.subtasks):
            subtask_node = TaskNode(
                goal=subtask.goal,
                task_type=subtask.task_type,  # Propagate task_type for proper retry/backoff policies
                parent_id=task.task_id,
                depth=task.depth + 1,
                max_depth=task.max_depth,
                execution_id=task.execution_id or dag.execution_id,
            )
            subtask_nodes.append(subtask_node)

        # Build index -> task_id mapping before creating subgraph
        index_to_task_id: Dict[str, str] = {}
        for idx, subtask_node in enumerate(subtask_nodes):
            index_to_task_id[str(idx)] = subtask_node.task_id

        # Convert index-based dependencies to task_id-based dependencies
        task_id_dependencies: Optional[Dict[str, List[str]]] = None
        if planner_result.dependencies_graph:
            task_id_dependencies = {}
            for subtask_idx_str, dep_indices in planner_result.dependencies_graph.items():
                # Validate that subtask_idx is valid
                try:
                    subtask_idx = int(subtask_idx_str)
                    if subtask_idx < 0 or subtask_idx >= len(subtask_nodes):
                        continue  # Skip invalid indices
                except (ValueError, TypeError):
                    continue  # Skip non-integer keys

                # Convert subtask index to task_id
                if subtask_idx_str in index_to_task_id:
                    subtask_task_id = index_to_task_id[subtask_idx_str]
                    # Convert dependency indices to task_ids
                    dep_task_ids = []
                    for dep_idx in dep_indices:
                        # Validate dependency index
                        try:
                            dep_idx_int = int(dep_idx)
                            # Prevent self-dependencies
                            if dep_idx_int == subtask_idx:
                                continue
                            # Validate dependency is within bounds
                            if dep_idx_int < 0 or dep_idx_int >= len(subtask_nodes):
                                continue
                            if dep_idx in index_to_task_id:
                                dep_task_ids.append(index_to_task_id[dep_idx])
                        except (ValueError, TypeError):
                            continue

                    if dep_task_ids:
                        task_id_dependencies[subtask_task_id] = dep_task_ids

        # Create the subgraph with converted dependencies
        dag.create_subgraph(task.task_id, subtask_nodes, task_id_dependencies)

        # Get the updated task with subgraph_id from DAG
        updated_task = dag.get_node(task.task_id)
        subgraph_id = updated_task.subgraph_id

        # Register index -> task_id mappings in the context store
        if subgraph_id:
            for idx, subtask_node in enumerate(subtask_nodes):
                self.context_store.register_index_mapping(
                    subgraph_id,
                    idx,
                    subtask_node.task_id
                )

        # Update metrics while preserving all other fields (including execution_history)
        # Use the original task parameter which has execution_history, but get subgraph_id from DAG
        updated_metrics = task.metrics.model_copy()
        updated_metrics.subtasks_created = len(subtask_nodes)
        return task.model_copy(update={
            "metrics": updated_metrics,
            "subgraph_id": subgraph_id
        })

    def _collect_subtask_results(self, subgraph: Optional[TaskDAG]) -> List[SubTask]:
        collected: List[SubTask] = []
        if subgraph:
            for node in subgraph.get_all_tasks(include_subgraphs=False):
                # Retrieve context that was used for this task
                context_input = None
                if node.dependencies:
                    dep_ids = list(node.dependencies)
                    context_input = self.context_store.get_context_for_dependencies(dep_ids)

                collected.append(
                    SubTask(
                        goal=node.goal,
                        task_type=node.task_type,
                        dependencies=[],
                        result=str(node.result) if node.result else "",
                        context_input=context_input,
                    )
                )
        return collected

    def _get_ready_tasks(
        self,
        subgraph: TaskDAG,
        pending: set[str],
        completed: set[str],
    ) -> List[TaskNode]:
        ready: List[TaskNode] = []
        for task_id in pending:
            task = subgraph.get_node(task_id)
            dependencies = subgraph.get_task_dependencies(task_id)
            if all(dep.task_id in completed for dep in dependencies):
                ready.append(task)
        return ready

    async def _execute_tasks_parallel(
        self,
        tasks: Iterable[TaskNode],
        subgraph: TaskDAG,
        solve_fn: AsyncSolveFn,
    ) -> List[TaskNode]:
        coros = []
        for task in tasks:
            if task.status in (TaskStatus.PENDING, TaskStatus.READY):
                coros.append(solve_fn(task, subgraph, task.depth))
        return await asyncio.gather(*coros) if coros else []

    def _enhance_error_context(self, error: Exception, agent_type: AgentType, task: Optional[TaskNode]) -> None:
        """Enhance error with agent and task context for better debugging."""
        task_id = task.task_id if task is not None else "unknown"
        error_msg = f"[{agent_type.value.upper()}] Task '{task_id}' failed: {str(error)}"
        if hasattr(error, 'args') and error.args:
            error.args = (error_msg,) + error.args[1:]
        else:
            error.args = (error_msg,)
