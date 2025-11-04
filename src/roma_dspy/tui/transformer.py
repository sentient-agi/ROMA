"""Data transformer for TUI visualization.

Transforms raw API data into clean, deduplicated view models with clear priority rules:
- Task hierarchy: Execution data tasks (from MLflow/ExecutionDataService)
- Traces: MLflow (rich) > LM traces (fallback)
- Zero duplication: Use ONE source for traces
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set

from loguru import logger

from roma_dspy.tui.models import (
    CheckpointViewModel,
    DataSource,
    ExecutionViewModel,
    MetricsSummary,
    TaskViewModel,
    TraceViewModel,
)


class DataTransformer:
    """
    Transforms raw API data into clean, deduplicated view models.

    Strategy:
    1. Build task hierarchy from checkpoints (authoritative)
    2. Collect traces from MLflow (rich) OR LM traces (fallback)
    3. Correlate traces to tasks via O(1) task_id lookup
    4. Compute aggregated metrics
    5. No duplication!
    """

    def transform(
        self,
        mlflow_data: Dict[str, Any],
        checkpoint_data: Dict[str, Any],
        lm_traces: List[Dict[str, Any]],
        metrics: Dict[str, Any],
    ) -> ExecutionViewModel:
        """
        Transform raw data into clean view model.

        Args:
            mlflow_data: MLflow trace response (may be empty)
            checkpoint_data: Checkpoint snapshot (task hierarchy)
            lm_traces: PostgreSQL LM trace records
            metrics: Aggregated metrics

        Returns:
            ExecutionViewModel (deduplicated)
        """
        logger.info("Transforming execution data...")

        # Detect available data sources
        has_mlflow = bool(mlflow_data.get("tasks") or mlflow_data.get("fallback_spans"))
        has_checkpoint = bool(checkpoint_data.get("tasks"))
        has_lm_traces = bool(lm_traces)

        data_sources = {
            "mlflow": has_mlflow,
            "checkpoint": has_checkpoint,
            "lm_traces": has_lm_traces,
        }

        logger.info(f"Data sources: {data_sources}")

        # 1. Build task hierarchy (from checkpoints - authoritative)
        tasks = self._build_task_hierarchy(checkpoint_data, mlflow_data)

        # 2. Collect traces (deduplicated: MLflow OR LM traces)
        traces = self._collect_traces(
            mlflow_data=mlflow_data if has_mlflow else {},
            lm_traces=lm_traces if has_lm_traces else [],
            prefer_mlflow=has_mlflow,
        )

        logger.info(
            f"Collected {len(traces)} traces "
            f"(MLflow: {sum(1 for t in traces if t.source == DataSource.MLFLOW)}, "
            f"LM: {sum(1 for t in traces if t.source == DataSource.LM_TRACE)})"
        )

        # 3. Correlate traces to tasks
        self._correlate_traces_to_tasks(tasks, traces)

        # 3.5. Enrich trace modules from tasks and infer from names
        self._enrich_trace_modules(tasks)

        # 4. Compute aggregated metrics for tasks
        self._compute_task_metrics(tasks)

        # 5. Find root tasks
        root_task_ids = self._find_root_tasks(tasks)

        # 6. Build checkpoints view models
        checkpoints = self._build_checkpoints(checkpoint_data)

        # 7. Build metrics summary
        metrics_summary = self._build_metrics_summary(metrics, traces, tasks)

        # 8. Collect warnings
        warnings = []
        mlflow_warning = mlflow_data.get("warning")
        if mlflow_warning:
            warnings.append(f"MLflow: {mlflow_warning}")
        if not has_mlflow:
            warnings.append("MLflow traces unavailable - using PostgreSQL LM traces")
        if not has_checkpoint:
            warnings.append("No checkpoint data available")

        # Extract execution metadata
        execution_id = checkpoint_data.get("execution_id", "unknown")
        if not execution_id or execution_id == "unknown":
            execution_id = mlflow_data.get("execution_id", "unknown")

        root_goal = checkpoint_data.get("root_goal", "")
        if not root_goal:
            summary = mlflow_data.get("summary", {})
            root_goal = summary.get("root_goal", f"Execution {execution_id}")

        status = checkpoint_data.get("status", "unknown")
        if status == "unknown":
            status = mlflow_data.get("status", "unknown")

        return ExecutionViewModel(
            execution_id=execution_id,
            root_goal=root_goal,
            status=status,
            tasks=tasks,
            root_task_ids=root_task_ids,
            checkpoints=checkpoints,
            metrics=metrics_summary,
            data_sources=data_sources,
            warnings=warnings,
        )

    # ════════════════════════════════════════════════════════════
    # Step 1: Build Task Hierarchy (from checkpoints + mlflow)
    # ════════════════════════════════════════════════════════════

    def _build_task_hierarchy(
        self, checkpoint_data: Dict[str, Any], mlflow_data: Dict[str, Any]
    ) -> Dict[str, TaskViewModel]:
        """
        Build task hierarchy from checkpoint snapshot and MLflow data.

        Checkpoints are authoritative for task structure, but MLflow may
        have additional tasks not in checkpoints.
        """
        tasks: Dict[str, TaskViewModel] = {}

        # Start with checkpoint tasks (authoritative)
        checkpoint_tasks = checkpoint_data.get("tasks", {})
        if isinstance(checkpoint_tasks, dict):
            for task_id, task_data in checkpoint_tasks.items():
                tasks[task_id] = TaskViewModel(
                    task_id=task_id,
                    parent_task_id=task_data.get("parent_task_id"),
                    goal=task_data.get("goal", ""),
                    status=task_data.get("status", "unknown"),
                    module=task_data.get("module"),
                    task_type=task_data.get("task_type"),
                    node_type=task_data.get("node_type"),
                    depth=task_data.get("depth", 0),
                    result=task_data.get("result"),
                    error=task_data.get("error"),
                    traces=[],  # Will be populated in correlate step
                    subtask_ids=[],
                )

        # Merge MLflow tasks (enrich checkpoint tasks or add new ones)
        mlflow_tasks = mlflow_data.get("tasks", [])
        if isinstance(mlflow_tasks, dict):
            mlflow_tasks = list(mlflow_tasks.values())

        for task in mlflow_tasks:
            if not isinstance(task, dict):
                continue

            task_id = task.get("task_id")
            if not task_id:
                continue

            if task_id in tasks:
                # Enrich existing checkpoint task with MLflow module
                if task.get("module") and not tasks[task_id].module:
                    tasks[task_id].module = task.get("module")
                    logger.debug(f"Enriched task {task_id[:8]} with MLflow module: {task.get('module')}")
            else:
                # Add new task from MLflow
                tasks[task_id] = TaskViewModel(
                    task_id=task_id,
                    parent_task_id=task.get("parent_task_id"),
                    goal=task.get("goal", ""),
                    status=task.get("status", "unknown"),
                    module=task.get("module"),
                    task_type=task.get("task_type"),
                    node_type=task.get("node_type"),
                    depth=task.get("depth", 0),
                    result=task.get("result"),
                    traces=[],
                    subtask_ids=[],
                )

        # Build parent-child relationships
        for task in tasks.values():
            if task.parent_task_id and task.parent_task_id in tasks:
                parent = tasks[task.parent_task_id]
                if task.task_id not in parent.subtask_ids:
                    parent.subtask_ids.append(task.task_id)

        logger.info(f"Built task hierarchy: {len(tasks)} tasks")
        return tasks

    # ════════════════════════════════════════════════════════════
    # Step 2: Collect Traces (DEDUPLICATED!)
    # ════════════════════════════════════════════════════════════

    def _collect_traces(
        self,
        mlflow_data: Dict[str, Any],
        lm_traces: List[Dict[str, Any]],
        prefer_mlflow: bool,
    ) -> List[TraceViewModel]:
        """
        Collect traces with deduplication strategy.

        Strategy:
        - If MLflow available: Use MLflow (rich data)
        - Else: Use LM traces (metrics only)
        - NEVER both (zero duplication!)
        """
        traces: List[TraceViewModel] = []

        if prefer_mlflow and mlflow_data:
            # Use MLflow (rich traces)
            traces = self._collect_mlflow_traces(mlflow_data)
            logger.info(f"Using MLflow traces: {len(traces)} traces")
        else:
            # Fallback to LM traces (lightweight)
            traces = self._collect_lm_traces(lm_traces)
            logger.info(f"Using LM traces fallback: {len(traces)} traces")

        return traces

    def _collect_mlflow_traces(self, mlflow_data: Dict[str, Any]) -> List[TraceViewModel]:
        """
        Extract traces from MLflow response (ExecutionDataService format).

        Expected format: tasks[].agent_executions[].spans[]
        This preserves all agent executions (atomizer, planner, executor, aggregator, verifier).
        """
        traces: List[TraceViewModel] = []

        mlflow_tasks = mlflow_data.get("tasks", [])
        if isinstance(mlflow_tasks, dict):
            mlflow_tasks = list(mlflow_tasks.values())

        for task in mlflow_tasks:
            if not isinstance(task, dict):
                continue

            task_id = task.get("task_id")
            agent_executions = task.get("agent_executions", [])

            for agent_exec in agent_executions:
                if not isinstance(agent_exec, dict):
                    continue

                agent_type = agent_exec.get("agent_type", "unknown")
                agent_spans = agent_exec.get("spans", [])

                for span in agent_spans:
                    if not isinstance(span, dict):
                        continue

                    # Use agent_type as module if span doesn't have one
                    module = span.get("module") or agent_type

                    # Extract tokens - prioritize span-level, fallback to agent-level
                    # ExecutionDataService assigns trace-level tokens to LM call spans
                    span_tokens = self._safe_int(span.get("tokens"), 0)
                    if span_tokens == 0:
                        # Fallback: use agent-level tokens if this is the only LM span
                        agent_metrics = agent_exec.get("metrics", {})
                        agent_tokens = self._safe_int(agent_metrics.get("tokens"), 0)
                        # Only assign if there's exactly one span (avoids double-counting)
                        if agent_tokens > 0 and len(agent_spans) == 1:
                            span_tokens = agent_tokens

                    trace = TraceViewModel(
                        trace_id=span.get("span_id", f"mlflow-{id(span)}"),
                        task_id=task_id or "unknown",
                        parent_trace_id=span.get("parent_id"),  # Fixed: API returns parent_id, not parent_span_id
                        name=span.get("name", "Unknown"),
                        module=module,
                        duration=self._safe_float(span.get("duration"), 0.0),
                        tokens=span_tokens,
                        cost=self._safe_float(span.get("cost"), 0.0),
                        inputs=span.get("inputs"),
                        outputs=span.get("outputs"),
                        reasoning=span.get("reasoning"),
                        tool_calls=span.get("tool_calls", []),
                        start_time=span.get("start_time"),
                        start_ts=self._safe_float(span.get("start_ts")),
                        model=span.get("model"),
                        error=span.get("error"),  # Extract error message from API
                        exception=span.get("exception"),  # Extract exception type from API
                        source=DataSource.MLFLOW,
                        has_full_io=bool(span.get("inputs") or span.get("outputs")),
                    )
                    traces.append(trace)

        # Also check fallback_spans (from MLflow response)
        fallback_spans = mlflow_data.get("fallback_spans", [])
        for span in fallback_spans:
            if not isinstance(span, dict):
                continue

            trace = TraceViewModel(
                trace_id=span.get("span_id", f"fallback-{id(span)}"),
                task_id=span.get("task_id"),  # Don't default to "unknown" - let Phase 2/3 matching handle it
                parent_trace_id=span.get("parent_span_id") or span.get("parent_id"),
                name=span.get("name", "Unknown"),
                module=span.get("module"),
                duration=self._safe_float(span.get("duration"), 0.0),
                tokens=self._safe_int(span.get("tokens"), 0),
                cost=self._safe_float(span.get("cost"), 0.0),
                inputs=span.get("inputs"),
                outputs=span.get("outputs"),
                tool_calls=span.get("tool_calls", []),
                start_time=span.get("start_time"),
                start_ts=self._safe_float(span.get("start_ts")),
                model=span.get("model"),
                error=span.get("error"),  # Extract error message from API
                exception=span.get("exception"),  # Extract exception type from API
                source=DataSource.MLFLOW,
                has_full_io=bool(span.get("inputs") or span.get("outputs")),
            )
            traces.append(trace)

        return traces

    def _collect_lm_traces(self, lm_traces: List[Dict[str, Any]]) -> List[TraceViewModel]:
        """Extract traces from PostgreSQL LM trace records."""
        traces: List[TraceViewModel] = []

        for lm_trace in lm_traces:
            if not isinstance(lm_trace, dict):
                continue

            # Convert latency from ms to seconds
            latency_ms = self._safe_float(lm_trace.get("latency_ms"), 0.0)
            duration = latency_ms / 1000.0

            # Extract tool calls from metadata
            metadata = lm_trace.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            tool_calls = metadata.get("tool_calls", [])
            if not isinstance(tool_calls, list):
                tool_calls = []

            trace = TraceViewModel(
                trace_id=f"lm-{lm_trace.get('trace_id')}",
                task_id=lm_trace.get("task_id", "unknown"),
                parent_trace_id=None,  # LM traces don't have parent hierarchy
                name=lm_trace.get("module_name", "Unknown"),
                module=lm_trace.get("module_name"),
                duration=duration,
                tokens=self._safe_int(lm_trace.get("total_tokens"), 0),
                cost=self._safe_float(lm_trace.get("cost_usd"), 0.0),
                inputs=(
                    {"preview": lm_trace.get("prompt_preview")}
                    if lm_trace.get("prompt_preview")
                    else None
                ),
                outputs=(
                    {"preview": lm_trace.get("response_preview")}
                    if lm_trace.get("response_preview")
                    else None
                ),
                reasoning=metadata.get("reasoning"),
                tool_calls=tool_calls,
                start_time=lm_trace.get("created_at"),
                start_ts=self._safe_float(lm_trace.get("start_ts")),
                model=lm_trace.get("model"),
                temperature=self._safe_float(lm_trace.get("temperature")),
                source=DataSource.LM_TRACE,
                has_full_io=False,  # Only previews, not full I/O
            )
            traces.append(trace)

        return traces

    # ════════════════════════════════════════════════════════════
    # Step 3: Correlate Traces to Tasks
    # ════════════════════════════════════════════════════════════

    def _correlate_traces_to_tasks(
        self, tasks: Dict[str, TaskViewModel], traces: List[TraceViewModel]
    ) -> None:
        """
        Correlate traces to tasks (modifies tasks in-place).

        Strategy:
        1. Direct task_id match (O(1) lookup)
        2. Goal text matching (fallback for orphaned root traces)
        3. Parent hierarchy matching (for nested spans without goal)
        """
        # Index traces by task_id for O(1) lookup
        traces_by_task: Dict[str, List[TraceViewModel]] = defaultdict(list)
        trace_lookup: Dict[str, TraceViewModel] = {t.trace_id: t for t in traces}
        matched_traces: Set[str] = set()

        # Phase 1: Direct task_id match
        for trace in traces:
            if trace.task_id and trace.task_id in tasks:
                traces_by_task[trace.task_id].append(trace)
                matched_traces.add(trace.trace_id)

        # Phase 2: Goal matching for orphaned ROOT traces ONLY
        # Only match root traces (no parent) to prevent subtask traces from
        # being incorrectly matched to parent tasks with the same goal
        for trace in traces:
            if trace.trace_id in matched_traces:
                continue
            # IMPORTANT: Only match ROOT traces by goal
            # Child traces will be handled by Phase 3 parent hierarchy
            if trace.parent_trace_id:
                continue  # Skip - not a root trace
            matched_task_id = self._match_trace_to_task_by_goal(trace, tasks)
            if matched_task_id:
                traces_by_task[matched_task_id].append(trace)
                matched_traces.add(trace.trace_id)
                logger.debug(
                    f"Matched orphaned root trace {trace.trace_id} to task {matched_task_id} by goal"
                )

        # Phase 3: Parent hierarchy matching for nested spans WITHOUT task_id
        # Match child spans to same task as their parent ONLY if they don't have a task_id
        # This prevents spans from subtasks being incorrectly assigned to parent tasks
        max_iterations = 10
        for _ in range(max_iterations):
            newly_matched = 0
            for trace in traces:
                if trace.trace_id in matched_traces:
                    continue
                # IMPORTANT: Only use parent hierarchy if trace has NO task_id
                # If it has a task_id, it was already matched (or should be orphaned)
                if trace.task_id:
                    continue  # Skip - should have been matched in Phase 1
                # Check if parent is matched
                if trace.parent_trace_id and trace.parent_trace_id in trace_lookup:
                    parent = trace_lookup[trace.parent_trace_id]
                    # Find which task the parent belongs to
                    for task_id, task_traces in traces_by_task.items():
                        if parent in task_traces:
                            traces_by_task[task_id].append(trace)
                            matched_traces.add(trace.trace_id)
                            newly_matched += 1
                            logger.debug(
                                f"Matched trace {trace.trace_id} to task {task_id} via parent {trace.parent_trace_id}"
                            )
                            break
            if newly_matched == 0:
                break  # No more progress

        # Assign traces to tasks
        for task_id, task_traces in traces_by_task.items():
            if task_id in tasks:
                tasks[task_id].traces = sorted(task_traces, key=lambda t: t.start_ts or 0.0)

        matched = sum(len(t.traces) for t in tasks.values())
        orphaned = len(traces) - matched
        logger.info(f"Correlated traces: {matched} matched, {orphaned} orphaned")

    def _match_trace_to_task_by_goal(
        self, trace: TraceViewModel, tasks: Dict[str, TaskViewModel]
    ) -> Optional[str]:
        """
        Fallback: match trace to task by comparing goal text.

        This is only used for orphaned traces where task_id is missing.

        IMPORTANT: Only matches if goal is UNIQUE (not shared by multiple tasks).
        This prevents subtask traces from being incorrectly matched to parent tasks.
        """
        # Extract goal from trace inputs (if available)
        trace_goal = None
        if trace.inputs and isinstance(trace.inputs, dict):
            trace_goal = trace.inputs.get("goal") or trace.inputs.get("original_goal")

        if not trace_goal:
            return None

        # Normalize goal
        normalized_trace_goal = self._normalize_goal(trace_goal)

        # Find ALL tasks with matching goal
        matching_task_ids = []
        for task_id, task in tasks.items():
            normalized_task_goal = self._normalize_goal(task.goal)
            if normalized_trace_goal == normalized_task_goal:
                matching_task_ids.append(task_id)

        # Only return match if goal is UNIQUE
        if len(matching_task_ids) == 1:
            return matching_task_ids[0]
        elif len(matching_task_ids) > 1:
            logger.debug(
                f"Trace {trace.trace_id[:8]} goal matches {len(matching_task_ids)} tasks - skipping ambiguous match"
            )
            return None

        return None

    @staticmethod
    def _normalize_goal(goal: str) -> str:
        """Normalize goal text for matching."""
        # Lowercase, remove extra whitespace, remove punctuation
        normalized = goal.lower().strip()
        normalized = re.sub(r"\s+", " ", normalized)
        normalized = re.sub(r"[^\w\s]", "", normalized)
        return normalized

    # ════════════════════════════════════════════════════════════
    # Step 3.5: Enrich Trace Modules
    # ════════════════════════════════════════════════════════════

    def _enrich_trace_modules(self, tasks: Dict[str, TaskViewModel]) -> None:
        """
        Enrich trace modules from task's checkpoint data.

        The module field in traces may be None if MLflow spans don't have the
        'roma.module' attribute. We can enrich this by checking if there's only
        one module that executed for this task (from checkpoint execution_history).

        Strategy:
        - If trace already has module: keep it
        - If task has only one module in execution_history: use that
        - Otherwise: leave as None (will group under "Other")
        """
        enriched_count = 0
        for task in tasks.values():
            # Skip if no traces
            if not task.traces:
                continue

            # Check traces that need enrichment
            traces_needing_module = [t for t in task.traces if not t.module]
            if not traces_needing_module:
                continue  # All traces already have modules

            # Try to infer from task's single module (if task has only one module)
            if task.module:
                # Task has explicit module - use it for traces without module
                for trace in traces_needing_module:
                    trace.module = task.module
                    enriched_count += 1
                    logger.debug(
                        f"Enriched trace {trace.trace_id[:8]} module from task.module: {task.module}"
                    )

        logger.info(f"Module enrichment: {enriched_count} traces enriched")

    # ════════════════════════════════════════════════════════════
    # Step 4: Compute Task Metrics
    # ════════════════════════════════════════════════════════════

    def _compute_task_metrics(self, tasks: Dict[str, TaskViewModel]) -> None:
        """Compute aggregated metrics for each task (modifies in-place).

        IMPORTANT: Only sum root-level wrapper spans to avoid double-counting.
        Root wrappers have durations from MLflow trace execution_time_ms.
        """
        for task in tasks.values():
            # Only sum root wrapper spans (agent-level like atomizer, planner, etc.)
            # These have correct durations from MLflow trace.info.execution_time_ms
            root_traces = [t for t in task.traces if not t.parent_trace_id]

            # Duration: sum root wrapper spans (they have trace-level durations from MLflow)
            task.total_duration = sum(t.duration for t in root_traces)

            # Tokens: sum ALL spans (tokens are only on LM call spans, not duplicated)
            task.total_tokens = sum(t.tokens for t in task.traces)

            # Cost: sum ALL spans
            task.total_cost = sum(t.cost for t in task.traces)

    # ════════════════════════════════════════════════════════════
    # Step 5: Find Root Tasks
    # ════════════════════════════════════════════════════════════

    def _find_root_tasks(self, tasks: Dict[str, TaskViewModel]) -> List[str]:
        """Find root tasks (tasks with no parent or parent not in tasks)."""
        roots = [
            task_id
            for task_id, task in tasks.items()
            if not task.parent_task_id or task.parent_task_id not in tasks
        ]

        # Sort by depth and goal for consistent ordering
        roots.sort(key=lambda tid: (tasks[tid].depth, tasks[tid].goal))

        return roots

    # ════════════════════════════════════════════════════════════
    # Step 6: Build Checkpoints View Models
    # ════════════════════════════════════════════════════════════

    def _build_checkpoints(self, checkpoint_data: Dict[str, Any]) -> List[CheckpointViewModel]:
        """Build checkpoint view models."""
        checkpoints: List[CheckpointViewModel] = []

        # Checkpoints might be in a separate list or in the snapshot
        checkpoint_list = checkpoint_data.get("checkpoints", [])

        for cp in checkpoint_list:
            if not isinstance(cp, dict):
                continue

            checkpoints.append(
                CheckpointViewModel(
                    checkpoint_id=cp.get("checkpoint_id", ""),
                    created_at=cp.get("created_at"),
                    trigger=cp.get("trigger", ""),
                    state=cp.get("state", ""),
                    total_tasks=cp.get("total_tasks", 0),
                    completed_tasks=cp.get("completed_tasks", 0),
                    file_size_bytes=cp.get("file_size_bytes"),
                )
            )

        return checkpoints

    # ════════════════════════════════════════════════════════════
    # Step 7: Build Metrics Summary
    # ════════════════════════════════════════════════════════════

    def _build_metrics_summary(
        self,
        metrics: Dict[str, Any],
        traces: List[TraceViewModel],
        tasks: Dict[str, TaskViewModel],
    ) -> MetricsSummary:
        """Build aggregated metrics summary."""
        # Use provided metrics if available, otherwise compute from traces
        if metrics and isinstance(metrics, dict):
            return MetricsSummary(
                total_calls=metrics.get("total_calls", len(traces)),
                total_tokens=metrics.get("total_tokens", sum(t.tokens for t in traces)),
                total_cost=metrics.get("total_cost_usd", sum(t.cost for t in traces)),
                total_duration=self._safe_float(metrics.get("total_duration", 0.0), 0.0),
                avg_latency_ms=self._safe_float(metrics.get("average_latency_ms"), 0.0),
                by_module=metrics.get("by_module", {}),
            )

        # Compute from traces
        total_calls = len(traces)
        total_tokens = sum(t.tokens for t in traces)
        total_cost = sum(t.cost for t in traces)
        total_duration = sum(t.duration for t in traces)
        avg_latency = (
            sum(t.duration * 1000 for t in traces) / total_calls if total_calls > 0 else 0.0
        )

        # By module
        by_module: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"calls": 0, "tokens": 0, "cost": 0.0, "durations": []}
        )

        for trace in traces:
            module = trace.module or "unknown"
            by_module[module]["calls"] += 1
            by_module[module]["tokens"] += trace.tokens
            by_module[module]["cost"] += trace.cost
            by_module[module]["durations"].append(trace.duration)

        # Compute averages
        for stats in by_module.values():
            durations = stats.pop("durations")
            stats["avg_latency_ms"] = (
                sum(d * 1000 for d in durations) / len(durations) if durations else 0.0
            )

        return MetricsSummary(
            total_calls=total_calls,
            total_tokens=total_tokens,
            total_cost=total_cost,
            total_duration=total_duration,
            avg_latency_ms=avg_latency,
            by_module=dict(by_module),
        )

    # ════════════════════════════════════════════════════════════
    # Utilities
    # ════════════════════════════════════════════════════════════

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Safely convert value to float."""
        if value in (None, ""):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        """Safely convert value to int."""
        if value in (None, ""):
            return default
        try:
            if isinstance(value, str):
                cleaned = value.replace(",", "").strip()
                if not cleaned:
                    return default
                return int(cleaned)
            if isinstance(value, float):
                return int(value)
            return int(value)
        except (TypeError, ValueError):
            return default
