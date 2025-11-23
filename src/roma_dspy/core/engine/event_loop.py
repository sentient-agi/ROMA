"""Event-driven controller wiring the scheduler to module runtime."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Callable, Optional, Set, Tuple, Dict, Any

from loguru import logger

from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.core.engine.events import EventType, TaskEvent
from roma_dspy.core.engine.runtime import ModuleRuntime
from roma_dspy.core.engine.scheduler import EventScheduler
from roma_dspy.core.signatures import TaskNode
from roma_dspy.types import TaskStatus, FailureContext
from roma_dspy.types.checkpoint_types import CheckpointTrigger, RecoveryStrategy
from roma_dspy.resilience import create_default_retry_policy
from roma_dspy.resilience.checkpoint_manager import CheckpointManager
from roma_dspy.types.checkpoint_models import CheckpointConfig


class EventLoopController:
    """Coordinates event scheduling and module execution."""

    def __init__(
        self,
        dag: TaskDAG,
        runtime: ModuleRuntime,
        priority_fn: Optional[Callable[[TaskNode], int]] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
        max_queue_size: int = 1000,
        postgres_storage: Optional[Any] = None,
    ) -> None:
        self.dag = dag
        self.runtime = runtime
        self.max_queue_size = max_queue_size
        self.postgres_storage = postgres_storage
        self._queued: Set[Tuple[str, str]] = set()  # (dag_id, task_id)
        self.scheduler = EventScheduler(
            dag,
            priority_fn=priority_fn,
            max_queue_size=max_queue_size,
            on_event_dropped=self._handle_event_dropped,
            postgres_storage=postgres_storage,
        )
        self.scheduler.register_processor(EventType.READY, self._handle_ready)
        self.scheduler.register_processor(EventType.COMPLETED, self._handle_completed)
        self.scheduler.register_processor(
            EventType.SUBGRAPH_COMPLETE, self._handle_subgraph_complete
        )
        self.scheduler.register_processor(EventType.FAILED, self._handle_failed)

        # Initialize checkpoint manager for recovery - respect disabled state
        self.checkpoint_manager = checkpoint_manager  # Don't create if None (disabled)
        self._failure_count = 0
        self._max_recovery_attempts = 3
        self._max_queued_tasks = max_queue_size  # Use same limit for event loop queue
        self._failed_task_ids: Set[str] = (
            set()
        )  # Track failed tasks for checkpoint recovery

        # Event loop health tracking
        self._event_stats = {
            "events_processed": 0,
            "events_failed": 0,
            "last_failure_time": None,
            "handler_failures": {
                "ready": 0,
                "completed": 0,
                "subgraph": 0,
                "failed": 0,
            },
        }

        # Event checkpointing state
        self._last_checkpoint_time = None
        self._events_since_checkpoint = 0
        self._checkpoint_interval = 50  # Checkpoint every N events

    async def _maybe_checkpoint(
        self, trigger: CheckpointTrigger, event: Optional[TaskEvent] = None
    ) -> None:
        """Conditionally create checkpoint based on configuration and trigger."""
        if not self.checkpoint_manager or not self.checkpoint_manager.config.enabled:
            return

        should_checkpoint = False

        # Check if this trigger is enabled
        if trigger in self.checkpoint_manager.config.auto_checkpoint_triggers:
            should_checkpoint = True

        # Check periodic checkpoint interval
        if (
            trigger == CheckpointTrigger.PERIODIC
            and self._events_since_checkpoint >= self._checkpoint_interval
        ):
            should_checkpoint = True

        # Always checkpoint on failures
        if trigger == CheckpointTrigger.ON_FAILURE:
            should_checkpoint = True

        if should_checkpoint:
            await self._create_event_checkpoint(trigger, event)

    async def apply_pending_restorations(self) -> bool:
        """Apply any pending state restorations from checkpoint manager."""
        if not self.checkpoint_manager:
            return True  # No restoration needed if checkpoints disabled

        try:
            success = True

            # Restore scheduler state if pending
            scheduler_state = self.checkpoint_manager.get_pending_scheduler_state()
            if scheduler_state:
                # Increment recovery attempt counter
                self._failure_count += 1
                logger.info(
                    "Attempting checkpoint recovery (attempt %d/%d)",
                    self._failure_count,
                    self._max_recovery_attempts,
                )

                # Check if max recovery attempts exceeded
                if self._failure_count > self._max_recovery_attempts:
                    logger.error(
                        "Max recovery attempts (%d) exceeded, aborting restoration",
                        self._max_recovery_attempts,
                    )
                    return False

                self.scheduler.restore_scheduler_state(scheduler_state)
                logger.info("Applied scheduler state restoration")

            # Restore event loop state if pending
            event_loop_state = self.checkpoint_manager.get_pending_event_loop_state()
            if event_loop_state:
                self._events_since_checkpoint = event_loop_state.get(
                    "events_processed", 0
                )
                # Don't restore failure_count from checkpoint - it's a runtime counter
                self._last_checkpoint_time = event_loop_state.get(
                    "last_checkpoint_time"
                )

                # DON'T restore queued_tasks - they should be regenerated based on DAG state
                # This prevents dropped events from being incorrectly marked as queued
                self._queued.clear()
                # Let enqueue_ready_tasks() repopulate based on current DAG state

                logger.info("Applied event loop state restoration")

            # Clear pending states after successful restoration
            if scheduler_state or event_loop_state:
                self.checkpoint_manager.clear_pending_states()

            return success

        except Exception as e:
            logger.error(f"Failed to apply pending restorations: {e}")
            self._failure_count += 1
            return False

    async def _create_event_checkpoint(
        self, trigger: CheckpointTrigger, event: Optional[TaskEvent] = None
    ) -> Optional[str]:
        """Create a checkpoint using the CheckpointManager."""
        if not self.checkpoint_manager:
            return None

        try:
            import time

            # Create checkpoint using the existing CheckpointManager
            checkpoint_id = await self.checkpoint_manager.create_checkpoint(
                checkpoint_id=None,  # Let manager generate ID
                dag=self.dag,
                trigger=trigger,
                current_depth=0,  # Event loop doesn't track depth
                solver_config={
                    "max_queue_size": self.max_queue_size,
                    "checkpoint_interval": self._checkpoint_interval,
                    "events_processed": self._event_stats["events_processed"],
                    "failure_count": self._failure_count,
                },
                failed_task_ids=self._failed_task_ids.copy(),  # Use tracked failures
                # Pass scheduler state in module_states for proper restoration
                module_states={
                    "scheduler": self.scheduler.get_scheduler_state(),
                    "event_loop": {
                        "queued_tasks": list(self._queued),
                        "events_processed": self._event_stats["events_processed"],
                        "failure_count": self._failure_count,
                        "last_checkpoint_time": self._last_checkpoint_time,
                    },
                },
            )

            # Update tracking
            self._last_checkpoint_time = time.time()
            self._events_since_checkpoint = 0

            logger.info(
                f"Created event checkpoint {checkpoint_id} for trigger {trigger}"
            )
            return checkpoint_id

        except Exception as e:
            logger.error(f"Failed to create event checkpoint: {e}")
            return None

    async def run(self, max_concurrency: int = 1) -> None:
        """Seed initial tasks and process events until completion."""

        await self.enqueue_ready_tasks()
        await self.scheduler.schedule(max_concurrency=max_concurrency)

    async def enqueue_ready_tasks(self) -> None:
        """Inspect DAG hierarchy and queue tasks whose dependencies cleared."""
        # Prevent unbounded queue growth
        if len(self._queued) >= self._max_queued_tasks:
            logger.warning(
                f"Queue limit reached ({self._max_queued_tasks}), skipping new task enqueue"
            )
            return

        for task, owning_dag in self.dag.iter_ready_nodes():
            key = (owning_dag.dag_id, task.task_id)
            if key in self._queued:
                continue

            await self.scheduler.emit_event(self._make_ready_event(task, owning_dag))
            self._queued.add(key)

    def _make_ready_event(self, task: TaskNode, dag: TaskDAG) -> TaskEvent:
        return TaskEvent(
            priority=self.scheduler.priority_for(task),
            event_type=EventType.READY,
            task_id=task.task_id,
            dag_id=dag.dag_id,
        )

    def _make_completed_event(self, task: TaskNode, dag: TaskDAG) -> TaskEvent:
        return TaskEvent(
            priority=self.scheduler.priority_for(task),
            event_type=EventType.COMPLETED,
            task_id=task.task_id,
            dag_id=dag.dag_id,
        )

    def _make_subgraph_event(self, task: TaskNode, dag: TaskDAG) -> TaskEvent:
        return TaskEvent(
            priority=self.scheduler.priority_for(task),
            event_type=EventType.SUBGRAPH_COMPLETE,
            task_id=task.task_id,
            dag_id=dag.dag_id,
        )

    async def _handle_ready(self, event: TaskEvent) -> Optional[TaskEvent]:
        # Track event processing stats
        self._event_stats["events_processed"] += 1

        # Track checkpoint interval and maybe checkpoint (atomic operation)
        events_count = self._events_since_checkpoint + 1
        self._events_since_checkpoint = events_count

        # Check for periodic checkpoint with current count
        if (
            self.checkpoint_manager
            and self.checkpoint_manager.config.enabled
            and CheckpointTrigger.PERIODIC
            in self.checkpoint_manager.config.auto_checkpoint_triggers
            and events_count >= self._checkpoint_interval
        ):
            await self._create_event_checkpoint(CheckpointTrigger.PERIODIC, event)

        if not event.task_id or not event.dag_id:
            return None

        owning_dag = self._resolve_dag(event.dag_id)
        if owning_dag is None:
            logger.warning("Received READY event for unknown dag_id=%s", event.dag_id)
            return None

        try:
            task = owning_dag.get_node(event.task_id)
        except ValueError:
            logger.warning(
                "Task %s not found in dag %s", event.task_id, owning_dag.dag_id
            )
            return None

        self._queued.discard((owning_dag.dag_id, task.task_id))

        if task.should_force_execute():
            updated = await self.runtime.force_execute_async(task, owning_dag)
            return self._make_completed_event(updated, owning_dag)

        if task.status == TaskStatus.PENDING:
            task = await self.runtime.atomize_async(task, owning_dag)
            task = self.runtime.transition_from_atomizing(task, owning_dag)
            key = (owning_dag.dag_id, task.task_id)
            self._queued.add(key)
            return self._make_ready_event(task, owning_dag)

        if task.status == TaskStatus.PLANNING:
            # Checkpoint before planning as it's a critical operation
            await self._maybe_checkpoint(CheckpointTrigger.BEFORE_PLANNING, event)
            task = await self.runtime.plan_async(task, owning_dag)
            # Checkpoint after planning completes
            await self._maybe_checkpoint(CheckpointTrigger.AFTER_PLANNING, event)

            subgraph = (
                owning_dag.get_subgraph(task.subgraph_id) if task.subgraph_id else None
            )

            if subgraph and subgraph.graph.nodes():
                await self.enqueue_ready_tasks()
                return None

            # No subtasks -> treat as completed subgraph
            return self._make_subgraph_event(task, owning_dag)

        if task.status == TaskStatus.EXECUTING:
            task = await self.runtime.execute_async(task, owning_dag)
            return self._make_completed_event(task, owning_dag)

        if task.status == TaskStatus.AGGREGATING:
            # Checkpoint before aggregation as it's a critical operation
            await self._maybe_checkpoint(CheckpointTrigger.BEFORE_AGGREGATION, event)
            subgraph = (
                owning_dag.get_subgraph(task.subgraph_id) if task.subgraph_id else None
            )
            task = await self.runtime.aggregate_async(task, subgraph, owning_dag)
            return self._make_completed_event(task, owning_dag)

        return None

    async def _handle_completed(self, event: TaskEvent) -> Optional[TaskEvent]:
        # Track event processing stats
        self._event_stats["events_processed"] += 1
        # Track checkpoint interval
        self._events_since_checkpoint += 1

        if not event.task_id or not event.dag_id:
            return None

        owning_dag = self._resolve_dag(event.dag_id)
        if owning_dag is None:
            return None

        try:
            task = owning_dag.get_node(event.task_id)
        except ValueError:
            return None

        parent_info = await owning_dag.check_subgraph_complete(task.task_id)
        await self.enqueue_ready_tasks()

        if parent_info:
            parent_node, parent_dag = parent_info
            return self._make_subgraph_event(parent_node, parent_dag)

        return None

    async def _handle_subgraph_complete(self, event: TaskEvent) -> Optional[TaskEvent]:
        # Track event processing stats
        self._event_stats["events_processed"] += 1
        # Track checkpoint interval
        self._events_since_checkpoint += 1

        if not event.task_id or not event.dag_id:
            return None

        owning_dag = self._resolve_dag(event.dag_id)
        if owning_dag is None:
            return None

        try:
            task = owning_dag.get_node(event.task_id)
        except ValueError:
            return None

        if task.status != TaskStatus.PLAN_DONE:
            logger.debug(
                "Ignoring SUBGRAPH_COMPLETE for task %s in state %s",
                task.task_id,
                task.status,
            )
            return None

        subgraph = (
            owning_dag.get_subgraph(task.subgraph_id) if task.subgraph_id else None
        )
        task = await self.runtime.aggregate_async(task, subgraph, owning_dag)
        await self.enqueue_ready_tasks()
        return self._make_completed_event(task, owning_dag)

    async def _handle_failed(self, event: TaskEvent) -> Optional[TaskEvent]:
        # Track event processing stats
        self._event_stats["events_processed"] += 1
        self._event_stats["events_failed"] += 1
        self._event_stats["last_failure_time"] = datetime.now(timezone.utc)
        # Track checkpoint interval
        self._events_since_checkpoint += 1

        # Track failed task for checkpoint recovery
        if event.task_id:
            self._failed_task_ids.add(event.task_id)

        # Checkpoint on failure for recovery purposes
        await self._maybe_checkpoint(CheckpointTrigger.ON_FAILURE, event)

        if not event.task_id or not event.dag_id:
            return None

        owning_dag = self._resolve_dag(event.dag_id)
        if owning_dag is None:
            return None

        try:
            task = owning_dag.get_node(event.task_id)
        except ValueError:
            logger.warning(
                "Task %s not found in dag %s", event.task_id, owning_dag.dag_id
            )
            return None

        # Implement retry/backoff strategy
        retry_policy = create_default_retry_policy()

        # Check if retry is possible
        if task.can_retry:
            # Create failure context for retry calculation
            failure_context = FailureContext(
                error_type=type(event.data).__name__ if event.data else "Unknown",
                error_message=str(event.data) if event.data else "Task failed",
                task_type=task.task_type,
                metadata={
                    "task_id": task.task_id,
                    "depth": task.depth,
                    "retry_count": task.retry_count,
                },
            )

            # Calculate backoff delay
            delay = retry_policy.calculate_delay(
                task.retry_count, task.task_type, failure_context
            )

            logger.info(
                "Retrying task %s (attempt %d/%d) after %.2fs delay. Error: %s",
                task.task_id,
                task.retry_count + 1,
                task.max_retries,
                delay,
                event.data,
            )

            # Apply delay
            if delay > 0:
                await asyncio.sleep(delay)

            # Update task and transition to READY if needed
            try:
                updated_task = task.increment_retry()
                if updated_task.status != TaskStatus.READY:
                    updated_task = updated_task.transition_to(TaskStatus.READY)
                owning_dag.update_node(updated_task)

                # Remove from queued set and re-add with new state
                key = (owning_dag.dag_id, task.task_id)
                self._queued.discard(key)
                self._queued.add(key)

                return self._make_ready_event(updated_task, owning_dag)

            except ValueError as e:
                logger.error(
                    "Failed to increment retry for task %s: %s", task.task_id, str(e)
                )
                # Fall through to permanent failure handling

        # Task failed permanently - either can't retry or max retries exceeded
        logger.error(
            "Task %s in dag %s permanently failed after %d retries: %s",
            task.task_id,
            owning_dag.dag_id,
            task.retry_count,
            event.data,
        )
        await owning_dag.mark_failed(event.task_id, error=event.data)

        # Check if parent subgraph can still complete or should fail
        # This enables proper failure propagation up the task hierarchy
        parent_info = await owning_dag.check_subgraph_complete(task.task_id)

        if parent_info:
            parent_node, parent_dag = parent_info
            # Parent subgraph completed (possibly with some failures)
            return self._make_subgraph_event(parent_node, parent_dag)

        # Also check if this failure blocks any parent tasks
        # If the parent is waiting on this failed task, it should be notified
        await self.enqueue_ready_tasks()

        return None

    def _resolve_dag(self, dag_id: str) -> Optional[TaskDAG]:
        if not dag_id:
            return None
        return self.dag.find_dag(dag_id)

    def _handle_event_dropped(self, event: TaskEvent) -> None:
        """Handle dropped events by removing them from _queued so they can be re-enqueued."""
        if event.task_id and event.dag_id:
            key = (event.dag_id, event.task_id)
            self._queued.discard(key)
            logger.warning(
                "Event %s for task %s in dag %s was dropped due to queue overflow, removed from _queued",
                event.event_type.name,
                event.task_id,
                event.dag_id,
            )

    # ------------------------------------------------------------------
    # Event Loop Health and Monitoring
    # ------------------------------------------------------------------

    def get_event_loop_health(self) -> Dict[str, Any]:
        """Get comprehensive health status of the event loop."""
        scheduler_status = self.scheduler.get_queue_status()

        return {
            "event_stats": self._event_stats.copy(),
            "scheduler_health": {
                "queue_size": scheduler_status["current_size"],
                "queue_full": scheduler_status["is_full"],
                "overflow_count": scheduler_status["overflow_count"],
                "time_since_last_overflow": scheduler_status[
                    "time_since_last_overflow"
                ],
            },
            "queued_tasks_count": len(self._queued),
            "max_queued_tasks": self._max_queued_tasks,
            "queue_utilization": len(self._queued) / self._max_queued_tasks
            if self._max_queued_tasks > 0
            else 0,
            "failure_rate": (
                self._event_stats["events_failed"]
                / max(1, self._event_stats["events_processed"])
            ),
            "checkpoint_enabled": self.checkpoint_manager.config.enabled
            if self.checkpoint_manager
            else False,
            "recovery_attempts": self._failure_count,
            "max_recovery_attempts": self._max_recovery_attempts,
        }

    def reset_event_stats(self) -> None:
        """Reset event statistics for fresh monitoring."""
        self._event_stats = {
            "events_processed": 0,
            "events_failed": 0,
            "last_failure_time": None,
            "handler_failures": {
                "ready": 0,
                "completed": 0,
                "subgraph": 0,
                "failed": 0,
            },
        }
