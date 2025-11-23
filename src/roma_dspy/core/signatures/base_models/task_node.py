from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Optional, Dict, Any, FrozenSet, List
from roma_dspy.types import (
    TaskType,
    NodeType,
    TaskStatus,
    ModuleResult,
    StateTransition,
    NodeMetrics,
    TokenMetrics,
)
from datetime import datetime, timezone
from uuid import uuid4


class TaskNode(BaseModel):
    """
    Immutable task node representing a unit of work in ROMA's execution graph.

    Key principles:
    - Completely immutable (frozen=True) for thread safety
    - State transitions return new instances
    - Typed relationships using frozensets

    Lifecycle:
    1. Created with PENDING status
    2. Atomizer determines PLAN or EXECUTE node_type
    3. State transitions through READY → EXECUTING → COMPLETED/FAILED
    4. Parent nodes AGGREGATE results from children
    """

    # Enforce true immutability at Pydantic level
    model_config = ConfigDict(
        frozen=True,  # Prevents all direct attribute assignment
        validate_assignment=False,  # Not needed with frozen
        arbitrary_types_allowed=True,  # Allow custom types
        extra="forbid",  # Reject unknown fields to catch errors early
    )

    # Identity and structure
    task_id: str = Field(
        default_factory=lambda: str(uuid4()), description="Unique task identifier"
    )

    def model_copy(
        self, *, update: Optional[Dict[str, Any]] = None, deep: bool = False
    ) -> "TaskNode":
        """
        Override model_copy to preserve task_id (which has default_factory that would regenerate it).

        CRITICAL BUG FIX: task_id has default_factory=uuid4, so Pydantic regenerates it
        unless explicitly included in the update dict. This caused "Task X not in DAG" errors
        when subtasks were created with model_copy calls.

        Args:
            update: Dict of fields to update
            deep: Whether to perform deep copy (passed to parent)

        Returns:
            New TaskNode instance with task_id preserved
        """
        from loguru import logger

        if update is None:
            update = {}

        # Always preserve task_id unless explicitly overridden
        if "task_id" not in update:
            logger.debug(
                f"[TaskNode.model_copy] Preserving task_id: {self.task_id[:8]}..."
            )
            update["task_id"] = self.task_id
        else:
            logger.debug(
                f"[TaskNode.model_copy] task_id explicitly set in update: {update['task_id'][:8]}..."
            )

        return super().model_copy(update=update, deep=deep)

    parent_id: Optional[str] = Field(default=None, description="Parent task ID")
    goal: str = Field(default="", min_length=1, description="Task objective")
    execution_id: str = Field(
        ..., description="Required unique identifier for execution run isolation"
    )

    # Recursion depth tracking
    depth: int = Field(default=0, description="Current recursion depth")
    max_depth: int = Field(default=2, description="Maximum allowed recursion depth")

    # MECE classification and atomizer decision
    task_type: TaskType = Field(
        default=TaskType.THINK, description="MECE task classification"
    )
    node_type: Optional[NodeType] = Field(
        default=None, description="Atomizer decision: PLAN or EXECUTE"
    )

    # State management
    status: TaskStatus = Field(
        default=TaskStatus.PENDING, description="Current task status"
    )

    # Execution results
    result: Optional[Any] = Field(default=None, description="Task execution result")
    error: Optional[str] = Field(
        default=None, description="Error message if task failed"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="Task metadata"
    )

    # Immutable relationships
    dependencies: FrozenSet[str] = Field(
        default_factory=frozenset, description="Task dependencies"
    )
    children: FrozenSet[str] = Field(
        default_factory=frozenset, description="Child tasks"
    )

    # Comprehensive tracking
    execution_history: Dict[str, ModuleResult] = Field(
        default_factory=dict, description="Complete history of module executions"
    )
    state_transitions: List[StateTransition] = Field(
        default_factory=list, description="State transition history"
    )
    metrics: NodeMetrics = Field(
        default_factory=NodeMetrics, description="Performance and execution metrics"
    )

    # Subgraph reference for planning nodes
    subgraph_id: Optional[str] = Field(
        default=None, description="ID of subgraph for PLAN nodes"
    )

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)

    # Version for optimistic locking
    version: int = Field(default=0)

    def transition_to(self, status: TaskStatus, **updates: Any) -> "TaskNode":
        """
        Create new instance with status transition and optional updates.

        Args:
            status: Target status to transition to
            **updates: Additional field updates

        Returns:
            New TaskNode instance with updated status

        Raises:
            ValueError: If status transition is invalid
        """
        if not self.status.can_transition_to_status(status):
            raise ValueError(
                f"Invalid transition from {self.status} to {status}. "
                f"Valid transitions: {self.status.can_transition_to}"
            )

        # Record state transition
        transition = StateTransition(
            from_state=self.status.value,
            to_state=status.value,
            timestamp=datetime.now(timezone.utc),
            metadata=updates.get("transition_metadata", {}),
        )

        new_transitions = list(self.state_transitions)
        new_transitions.append(transition)

        # Auto-update timestamps based on status
        timestamp_updates = {}
        if status == TaskStatus.EXECUTING and not self.started_at:
            timestamp_updates["started_at"] = datetime.now(timezone.utc)
        elif status.is_terminal and not self.completed_at:
            timestamp_updates["completed_at"] = datetime.now(timezone.utc)

        # Increment version for optimistic locking
        all_updates = {
            "status": status,
            "state_transitions": new_transitions,
            "version": self.version + 1,
            **timestamp_updates,
            **updates,
        }

        return self.model_copy(update=all_updates)

    def with_result(
        self, result: Any, metadata: Optional[Dict[str, Any]] = None
    ) -> "TaskNode":
        """
        Create new instance with successful completion.

        Args:
            result: The execution result
            metadata: Optional metadata to merge

        Returns:
            New TaskNode instance with COMPLETED status and result
        """
        updates: Dict[str, Any] = {"result": result}
        if metadata:
            updates["metadata"] = {**self.metadata, **metadata}

        return self.transition_to(TaskStatus.COMPLETED, **updates)

    def restore_state(
        self,
        result: Any = None,
        status: TaskStatus = None,
        error: str = None,
        **updates,
    ) -> "TaskNode":
        """
        Create new instance with restored state, bypassing transition validation.
        Used for checkpoint restoration where normal state transitions don't apply.

        Args:
            result: The execution result to restore
            status: The status to restore
            error: The error message to restore
            **updates: Additional field updates

        Returns:
            New TaskNode instance with restored state
        """
        restore_updates: Dict[str, Any] = {"version": self.version + 1, **updates}

        # Set timestamps based on restored status
        if status is not None:
            if status == TaskStatus.COMPLETED and not self.completed_at:
                restore_updates["completed_at"] = datetime.now(timezone.utc)
            if status == TaskStatus.EXECUTING and not self.started_at:
                restore_updates["started_at"] = datetime.now(timezone.utc)

            # Add transition entry for auditability
            from roma_dspy.types.module_result import StateTransition

            transition = StateTransition(
                from_state=self.status.value,
                to_state=status.value,
                timestamp=datetime.now(timezone.utc),
                metadata={"restored": True, "checkpoint_recovery": True},
            )
            new_transitions = list(self.state_transitions)
            new_transitions.append(transition)
            restore_updates["state_transitions"] = new_transitions

        if result is not None:
            restore_updates["result"] = result
        if status is not None:
            restore_updates["status"] = status
        if error is not None:
            restore_updates["error"] = error

        return self.model_copy(update=restore_updates)

    def add_child(self, child_id: str) -> "TaskNode":
        """
        Create new instance with additional child.

        Args:
            child_id: ID of child task to add

        Returns:
            New TaskNode instance with child added
        """
        if child_id in self.children:
            return self  # No change needed

        return self.model_copy(
            update={
                "children": self.children | {child_id},
            }
        )

    def remove_child(self, child_id: str) -> "TaskNode":
        """
        Create new instance with child removed.

        Args:
            child_id: ID of child task to remove

        Returns:
            New TaskNode instance with child removed
        """
        if child_id not in self.children:
            return self  # No change needed

        return self.model_copy(
            update={
                "children": self.children - {child_id},
            }
        )

    def add_dependency(self, dependency_id: str) -> "TaskNode":
        """
        Create new instance with additional dependency.

        Args:
            dependency_id: ID of dependency task to add

        Returns:
            New TaskNode instance with dependency added
        """
        if dependency_id in self.dependencies:
            return self  # No change needed

        return self.model_copy(
            update={
                "dependencies": self.dependencies | {dependency_id},
            }
        )

    def remove_dependency(self, dependency_id: str) -> "TaskNode":
        """
        Create new instance with dependency removed.

        Args:
            dependency_id: ID of dependency task to remove

        Returns:
            New TaskNode instance with dependency removed
        """
        if dependency_id not in self.dependencies:
            return self  # No change needed

        return self.model_copy(
            update={
                "dependencies": self.dependencies - {dependency_id},
            }
        )

    def update_metadata(self, **metadata: Any) -> "TaskNode":
        """
        Create new instance with updated metadata.

        Args:
            **metadata: Metadata fields to update

        Returns:
            New TaskNode instance with merged metadata
        """
        return self.model_copy(
            update={
                "metadata": {**self.metadata, **metadata},
                "version": self.version + 1,
            }
        )

    def set_node_type(self, node_type: NodeType) -> "TaskNode":
        """
        Create new instance with node type set (typically by atomizer).

        Args:
            node_type: NodeType determined by atomizer

        Returns:
            New TaskNode instance with node_type set

        Raises:
            ValueError: If node_type conflicts with task_type constraints
        """
        # All task types can be either PLAN or EXECUTE based on atomizer decision
        # No special constraints - the atomizer handles complexity evaluation

        return self.model_copy(
            update={"node_type": node_type, "version": self.version + 1}
        )

    # Properties for convenience
    @property
    def is_atomic(self) -> bool:
        """Check if task is atomic (EXECUTE node_type)."""
        return self.node_type == NodeType.EXECUTE

    @property
    def is_composite(self) -> bool:
        """Check if task needs decomposition (PLAN node_type)."""
        return self.node_type == NodeType.PLAN

    @property
    def is_root(self) -> bool:
        """Check if this is a root task (no parent)."""
        return self.parent_id is None

    @property
    def is_leaf(self) -> bool:
        """Check if this is a leaf task (no children)."""
        return len(self.children) == 0

    @property
    def has_dependencies(self) -> bool:
        """Check if task has dependencies."""
        return len(self.dependencies) > 0

    @property
    def execution_duration(self) -> Optional[float]:
        """
        Calculate execution duration in seconds if available.

        Returns:
            Duration in seconds, or None if not completed
        """
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def retry_count(self) -> int:
        """Get current retry count from metrics."""
        return self.metrics.retry_count

    @property
    def max_retries(self) -> int:
        """Get maximum retries from metrics."""
        return self.metrics.max_retries

    @property
    def can_retry(self) -> bool:
        """Check if task can be retried."""
        return self.retry_count < self.max_retries

    @property
    def retry_exhausted(self) -> bool:
        """Check if all retries have been exhausted."""
        return self.retry_count >= self.max_retries

    def increment_retry(self) -> "TaskNode":
        """
        Create new instance with incremented retry count.

        Returns:
            New TaskNode instance with incremented retry count

        Raises:
            ValueError: If maximum retries already reached
        """
        if self.retry_exhausted:
            raise ValueError(f"Maximum retries ({self.max_retries}) already reached")

        new_metrics = self.metrics.model_copy(
            update={"retry_count": self.metrics.retry_count + 1}
        )

        return self.model_copy(
            update={
                "metrics": new_metrics,
            }
        )

    def record_module_execution(
        self, module_name: str, result: ModuleResult
    ) -> "TaskNode":
        """
        Record module execution result in history.

        Args:
            module_name: Name of the module (atomizer, planner, executor, aggregator)
            result: Module execution result

        Returns:
            New TaskNode instance with updated execution history
        """
        new_history = dict(self.execution_history)
        new_history[module_name] = result

        # Update metrics based on module
        new_metrics = self.metrics.model_copy()
        if module_name == "atomizer":
            new_metrics.atomizer_duration = result.duration
        elif module_name == "planner":
            new_metrics.planner_duration = result.duration
        elif module_name == "executor":
            new_metrics.executor_duration = result.duration
        elif module_name == "aggregator":
            new_metrics.aggregator_duration = result.duration

        new_metrics.total_duration = new_metrics.calculate_total_duration()

        return self.model_copy(
            update={
                "execution_history": new_history,
                "metrics": new_metrics,
                "version": self.version + 1,
            }
        )

    def should_force_execute(self) -> bool:
        """
        Check if task should be forced to execute due to max depth.

        Returns:
            True if at or beyond max depth, False otherwise
        """
        return self.depth >= self.max_depth

    def with_incremented_depth(self, parent_depth: int) -> "TaskNode":
        """
        Create new instance with depth set based on parent.

        Args:
            parent_depth: Depth of parent node

        Returns:
            New TaskNode instance with updated depth
        """
        return self.model_copy(
            update={"depth": parent_depth + 1, "version": self.version + 1}
        )

    def set_subgraph(self, subgraph_id: str) -> "TaskNode":
        """
        Set subgraph ID for planning nodes.

        Args:
            subgraph_id: ID of the subgraph

        Returns:
            New TaskNode instance with subgraph ID set
        """
        return self.model_copy(
            update={"subgraph_id": subgraph_id, "version": self.version + 1}
        )

    def get_node_metrics(self) -> TokenMetrics:
        """
        Get token metrics for ONLY this node (not including subtasks).

        Returns:
            TokenMetrics object with aggregated metrics for this node
        """
        total_metrics = TokenMetrics()

        for module_result in self.execution_history.values():
            if module_result.token_metrics:
                total_metrics = total_metrics + module_result.token_metrics

        return total_metrics

    def get_tree_metrics(self, dag: Optional["TaskDAG"] = None) -> TokenMetrics:
        """
        Get token metrics for this node and ALL its subtasks recursively.

        Args:
            dag: The DAG containing the task relationships

        Returns:
            TokenMetrics object with aggregated metrics for entire tree
        """
        # Start with this node's metrics
        total_metrics = self.get_node_metrics()

        # If we have a DAG and subgraph, add metrics from all subtasks
        if dag and self.subgraph_id:
            subgraph = dag.get_subgraph(self.subgraph_id)
            if subgraph:
                for child_task in subgraph.get_all_tasks(include_subgraphs=True):
                    child_metrics = child_task.get_tree_metrics(subgraph)
                    total_metrics = total_metrics + child_metrics

        return total_metrics

    def get_node_summary(self) -> Dict[str, Any]:
        """
        Get summary of this node's execution with token metrics.

        Returns:
            Dictionary containing node execution details
        """
        node_metrics = self.get_node_metrics()

        return {
            "task_id": self.task_id[:8],
            "goal": self.goal,
            "depth": self.depth,
            "status": self.status.value,
            "node_type": self.node_type.value if self.node_type else None,
            "modules_executed": list(self.execution_history.keys()),
            "token_metrics": {
                "prompt_tokens": node_metrics.prompt_tokens,
                "completion_tokens": node_metrics.completion_tokens,
                "total_tokens": node_metrics.total_tokens,
                "cost": f"${node_metrics.cost:.6f}",
            },
            "duration": self.execution_duration,
            "children_count": len(self.children),
        }

    def log_node_completion(self) -> str:
        """
        Generate a formatted log string for node completion.

        Returns:
            Formatted string showing node execution details
        """
        lines = []
        lines.append(f"\n{'=' * 80}")
        lines.append(f"📋 Node Completed: {self.goal}")
        lines.append(f"{'=' * 80}")

        # Module breakdown
        if self.execution_history:
            lines.append("\nModule Execution Details:")
            lines.append("-" * 80)
            lines.append(
                f"{'Module':<12} | {'Tokens (P/C/T)':<20} | {'Cost':<10} | {'Duration':<8} | {'Input/Output Preview'}"
            )
            lines.append("-" * 80)

            total_metrics = TokenMetrics()

            for module_name, result in self.execution_history.items():
                # Get token metrics
                metrics = result.token_metrics or TokenMetrics()
                total_metrics = total_metrics + metrics

                # Format tokens
                token_str = f"{metrics.prompt_tokens}/{metrics.completion_tokens}/{metrics.total_tokens}"

                # Format cost
                cost_str = f"${metrics.cost:.6f}"

                # Format duration
                duration_str = f"{result.duration:.2f}s"

                # Get input/output preview
                input_str = str(result.input)[:30] if result.input else ""
                output_str = str(result.output)[:30] if result.output else ""

                lines.append(
                    f"{module_name:<12} | {token_str:<20} | {cost_str:<10} | {duration_str:<8} | "
                    f"IN: {input_str}... OUT: {output_str}..."
                )

            lines.append("-" * 80)
            lines.append(
                f"{'Node Total':<12} | "
                f"{total_metrics.prompt_tokens}/{total_metrics.completion_tokens}/{total_metrics.total_tokens:<20} | "
                f"${total_metrics.cost:.6f}"
            )

        lines.append(f"{'=' * 80}\n")
        return "\n".join(lines)

    def get_execution_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive execution summary.

        Returns:
            Dictionary containing all execution details
        """
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "depth": self.depth,
            "status": self.status.value,
            "node_type": self.node_type.value if self.node_type else None,
            "execution_history": {
                name: {
                    "input": str(result.input)[:100],
                    "output": str(result.output)[:100],
                    "duration": result.duration,
                    "error": result.error,
                }
                for name, result in self.execution_history.items()
            },
            "metrics": self.metrics.model_dump(),
            "state_transitions": [
                {
                    "from": t.from_state,
                    "to": t.to_state,
                    "timestamp": t.timestamp.isoformat(),
                }
                for t in self.state_transitions
            ],
            "children": list(self.children),
            "dependencies": list(self.dependencies),
        }

    def __str__(self) -> str:
        """Human-readable string representation."""
        node_type_str = f"({self.node_type.value})" if self.node_type else ""
        depth_str = f"[D{self.depth}]" if self.depth > 0 else ""
        return f"TaskNode{depth_str}[{self.task_id[:8]}]{node_type_str}: {self.goal[:50]}..."

    def pretty_print(
        self, show_result: bool = True, show_execution: bool = True, indent: int = 0
    ) -> str:
        """
        Generate a pretty-printed representation of the task node.

        Args:
            show_result: Whether to show the result content
            show_execution: Whether to show execution history details
            indent: Current indentation level

        Returns:
            Formatted string representation
        """
        lines = []
        prefix = "  " * indent

        # Header with task info
        lines.append(f"{prefix}{'=' * 60}")
        lines.append(f"{prefix}📋 TASK NODE")
        lines.append(f"{prefix}{'=' * 60}")

        # Basic info
        lines.append(f"{prefix}ID:        {self.task_id[:8]}...")
        lines.append(f"{prefix}Goal:      {self.goal}")  # Show full goal
        lines.append(f"{prefix}Depth:     {self.depth}/{self.max_depth}")

        # Status and type
        status_emoji = {
            "PENDING": "⏳",
            "ATOMIZING": "🔍",
            "PLANNING": "📝",
            "PLAN_DONE": "✅",
            "READY": "🟢",
            "EXECUTING": "⚙️",
            "AGGREGATING": "🔄",
            "COMPLETED": "✨",
            "FAILED": "❌",
            "NEEDS_REPLAN": "🔁",
        }.get(self.status.value, "❓")

        lines.append(f"{prefix}Status:    {status_emoji} {self.status.value}")

        if self.node_type:
            node_emoji = "📝" if self.node_type == NodeType.PLAN else "⚡"
            lines.append(f"{prefix}Node Type: {node_emoji} {self.node_type.value}")

        if self.task_type:
            lines.append(f"{prefix}Task Type: {self.task_type.value}")

        # Subgraph info
        if self.subgraph_id:
            lines.append(f"{prefix}Subgraph:  {self.subgraph_id[:20]}...")

        # Execution history
        if show_execution and self.execution_history:
            lines.append(f"{prefix}")
            lines.append(f"{prefix}📊 EXECUTION HISTORY:")
            lines.append(f"{prefix}{'-' * 40}")

            for module_name, result in self.execution_history.items():
                module_emoji = {
                    "atomizer": "🔍",
                    "planner": "📝",
                    "executor": "⚡",
                    "aggregator": "🔄",
                }.get(module_name, "📦")

                lines.append(f"{prefix}  {module_emoji} {module_name.upper()}")
                lines.append(f"{prefix}     Duration: {result.duration:.2f}s")

                if result.error:
                    lines.append(f"{prefix}     ❌ Error: {result.error}")
                else:
                    # Show output preview
                    output_str = str(result.output)
                    if len(output_str) > 100:
                        output_str = output_str[:100] + "..."
                    lines.append(f"{prefix}     Output: {output_str}")

        # Metrics
        if self.metrics and (
            self.metrics.total_duration or self.metrics.subtasks_created
        ):
            lines.append(f"{prefix}")
            lines.append(f"{prefix}📈 METRICS:")
            lines.append(f"{prefix}{'-' * 40}")
            if self.metrics.total_duration:
                lines.append(
                    f"{prefix}  Total Duration: {self.metrics.total_duration:.2f}s"
                )
            if self.metrics.subtasks_created:
                lines.append(
                    f"{prefix}  Subtasks Created: {self.metrics.subtasks_created}"
                )
            if self.metrics.retry_count:
                lines.append(f"{prefix}  Retries: {self.metrics.retry_count}")

        # Result
        if show_result and self.result:
            lines.append(f"{prefix}")
            lines.append(f"{prefix}📄 RESULT:")
            lines.append(f"{prefix}{'-' * 40}")
            result_str = str(self.result)

            # Format result based on length
            if len(result_str) <= 200:
                lines.append(f"{prefix}  {result_str}")
            else:
                # Show first and last parts for long results
                lines.append(f"{prefix}  {result_str[:150]}...")
                lines.append(
                    f"{prefix}  ... [truncated {len(result_str) - 200} chars] ..."
                )
                lines.append(f"{prefix}  ...{result_str[-50:]}")

        # State transitions summary
        if self.state_transitions:
            lines.append(f"{prefix}")
            lines.append(f"{prefix}🔄 STATE TRANSITIONS: {len(self.state_transitions)}")
            last_transition = self.state_transitions[-1]
            lines.append(
                f"{prefix}  Last: {last_transition.from_state} → {last_transition.to_state}"
            )

        lines.append(f"{prefix}{'=' * 60}")

        return "\n".join(lines)

    def print_tree(
        self,
        dag: Optional["TaskDAG"] = None,
        indent: int = 0,
        visited: Optional[set] = None,
    ) -> str:
        """
        Print the task tree structure with this node as root.

        Args:
            dag: The DAG containing the task relationships
            indent: Current indentation level
            visited: Set of visited task IDs to avoid cycles

        Returns:
            Tree representation as string
        """
        if visited is None:
            visited = set()

        if self.task_id in visited:
            return f"{'  ' * indent}↺ {self.task_id[:8]}... (circular reference)"

        visited.add(self.task_id)

        lines = []
        prefix = "  " * indent

        # Current node
        status_emoji = {
            "COMPLETED": "✅",
            "FAILED": "❌",
            "EXECUTING": "⚙️",
            "PENDING": "⏳",
            "PLANNING": "📝",
            "PLAN_DONE": "✔️",
        }.get(self.status.value, "❓")

        node_type_str = f"[{self.node_type.value}]" if self.node_type else ""
        lines.append(
            f"{prefix}{status_emoji} {self.goal} {node_type_str}"
        )  # Show full goal

        # If we have a DAG and subgraph, show children
        if dag and self.subgraph_id:
            subgraph = dag.get_subgraph(self.subgraph_id)
            if subgraph:
                for child_task in subgraph.get_all_tasks(include_subgraphs=False):
                    child_lines = child_task.print_tree(subgraph, indent + 1, visited)
                    if child_lines:
                        lines.append(child_lines)

        return "\n".join(lines)

    def get_execution_id(self) -> Optional[str]:
        """
        Get the execution ID for this task.

        Returns:
            Execution ID string or None if not set
        """
        return self.execution_id
