"""Async event scheduler orchestrating TaskDAG execution."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, Optional

from loguru import logger

from roma_dspy.core.engine.dag import TaskDAG
from roma_dspy.core.engine.events import EventType, TaskEvent
from roma_dspy.core.signatures.base_models.task_node import TaskNode


EventHandler = Callable[[TaskEvent], Awaitable[Optional[TaskEvent]]]


class EventScheduler:
    """Thin orchestration layer built on top of TaskDAG and events."""

    def __init__(
        self,
        dag: TaskDAG,
        priority_fn: Optional[Callable[[TaskNode], int]] = None,
        max_queue_size: int = 1000,
        on_event_dropped: Optional[Callable[[TaskEvent], None]] = None,
        postgres_storage: Optional[Any] = None,
    ) -> None:
        self.dag = dag
        self._priority_fn = priority_fn or (lambda node: node.depth)
        self.max_queue_size = max_queue_size
        self.event_queue: asyncio.PriorityQueue[TaskEvent] = asyncio.PriorityQueue(
            maxsize=max_queue_size
        )
        self.processors: Dict[EventType, EventHandler] = {}
        self._metrics = defaultdict(int)
        self._stop_requested = False
        self._completion_event = asyncio.Event()
        self._on_event_dropped = on_event_dropped
        self._postgres_storage = postgres_storage

        # Queue overflow tracking
        self._overflow_count = 0
        self._last_overflow_time = None

    def register_processor(self, event_type: EventType, handler: EventHandler) -> None:
        """Register a coroutine handler for a particular event type."""

        self.processors[event_type] = handler

    async def emit_event(self, event: TaskEvent) -> None:
        """Push an event onto the internal queue with overflow protection."""

        if self._stop_requested and event.event_type != EventType.STOP:
            return

        # Persist event to database with retry
        persist_success = await self._persist_event(event, dropped=False)
        if not persist_success:
            self._metrics[f"persist_failed::{event.event_type.name.lower()}"] += 1
            logger.error(
                f"Event {event.event_type.name} queued but persistence FAILED after retries"
            )

        try:
            # Try to add event without blocking
            self.event_queue.put_nowait(event)
            self._metrics[f"queued::{event.event_type.name.lower()}"] += 1
        except asyncio.QueueFull:
            # Handle queue overflow
            await self._handle_queue_overflow(event)

    async def _handle_queue_overflow(self, event: TaskEvent) -> None:
        """Handle queue overflow with priority-based dropping strategy."""
        import time

        self._overflow_count += 1
        self._last_overflow_time = time.time()
        self._metrics["queue_overflows"] += 1

        # For critical events (STOP), force them in by dropping lowest priority events
        if event.event_type == EventType.STOP:
            try:
                # Extract all events from queue to find lowest priority
                events = []
                while not self.event_queue.empty():
                    try:
                        events.append(self.event_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break

                if not events:
                    # Queue became empty, just add STOP
                    self.event_queue.put_nowait(event)
                    self._metrics[f"queued::{event.event_type.name.lower()}"] += 1
                    return

                # Find and remove the lowest priority (highest priority value) non-STOP event
                # Priority queue uses min-heap, so lower priority value = higher priority
                # We want to drop the LOWEST priority = HIGHEST priority value
                # Use task creation time as tiebreaker for same-priority events (older = drop first)
                non_stop_events = [e for e in events if e.event_type != EventType.STOP]

                if non_stop_events:
                    # Find event with highest priority value (lowest priority)
                    # For ties, prefer dropping older events by checking task creation time
                    def drop_priority(event):
                        # Primary: priority value (higher = lower priority = drop first)
                        # Secondary: task age (older = drop first)
                        if event.task_id and event.dag_id:
                            try:
                                dag = self.dag.find_dag(event.dag_id)
                                if dag:
                                    task = dag.get_node(event.task_id)
                                    # Return tuple: (priority, -timestamp) for sorting
                                    # Negative timestamp so older (smaller timestamp) sorts higher
                                    return (
                                        event.priority,
                                        -task.created_at.timestamp(),
                                    )
                            except (ValueError, AttributeError):
                                pass
                        # Fallback: just use priority
                        return (event.priority, 0)

                    lowest_priority_event = max(non_stop_events, key=drop_priority)
                    events.remove(lowest_priority_event)

                    logger.warning(
                        "Queue overflow: forcing STOP event by dropping lowest-priority %s event (priority=%d)",
                        lowest_priority_event.event_type.name,
                        lowest_priority_event.priority,
                    )

                    self._metrics[
                        f"dropped::{lowest_priority_event.event_type.name.lower()}"
                    ] += 1
                    # Persist dropped event
                    await self._persist_event(lowest_priority_event, dropped=True)
                    if self._on_event_dropped:
                        self._on_event_dropped(lowest_priority_event)
                else:
                    # All events are STOP, just drop oldest
                    dropped = events.pop(0)
                    self._metrics[f"dropped::{dropped.event_type.name.lower()}"] += 1
                    # Persist dropped event
                    await self._persist_event(dropped, dropped=True)
                    if self._on_event_dropped:
                        self._on_event_dropped(dropped)

                # Re-add all remaining events plus the new STOP event
                for e in events:
                    self.event_queue.put_nowait(e)
                self.event_queue.put_nowait(event)
                self._metrics[f"queued::{event.event_type.name.lower()}"] += 1

            except Exception as e:
                logger.error(f"Error handling STOP overflow: {e}")
                # Fallback: try to add STOP anyway
                try:
                    self.event_queue.put_nowait(event)
                except asyncio.QueueFull:
                    pass
        else:
            # Drop non-critical events
            logger.error(
                f"Event queue full (size: {self.max_queue_size}), "
                f"dropping {event.event_type.name} event for task {event.task_id}. "
                f"Total overflows: {self._overflow_count}"
            )
            self._metrics[f"dropped::{event.event_type.name.lower()}"] += 1
            # Persist dropped event
            await self._persist_event(event, dropped=True)
            # Notify controller that event was dropped so it can be re-enqueued
            if self._on_event_dropped:
                self._on_event_dropped(event)

    async def schedule(self, max_concurrency: int = 1) -> None:
        """Consume events until the DAG marks itself complete."""

        if max_concurrency < 1:
            raise ValueError("max_concurrency must be >= 1")

        self._completion_event.clear()
        workers = [asyncio.create_task(self._worker()) for _ in range(max_concurrency)]

        try:
            await self._completion_event.wait()
        finally:
            self.force_stop()
            stop_event = TaskEvent(priority=0, event_type=EventType.STOP)
            for _ in workers:
                await self.event_queue.put(stop_event)
            await asyncio.gather(*workers, return_exceptions=False)

    async def _process_event(self, event: TaskEvent) -> None:
        """Dispatch an event to its registered processor."""

        handler = self.processors.get(event.event_type)
        if handler is None:
            return

        follow_up = await handler(event)
        self._metrics[f"handled::{event.event_type.name.lower()}"] += 1

        if follow_up is not None:
            await self.emit_event(follow_up)

    async def _worker(self) -> None:
        """Continuously consume events until stop requested."""

        while True:
            event = await self.event_queue.get()
            if event.event_type == EventType.STOP:
                break

            try:
                await self._process_event(event)
            except Exception as e:
                # Handler failed even after resilience retries/circuit breaker
                logger.error(
                    "Handler failed for event %s (task=%s, dag=%s) after exhausting resilience retries: %s",
                    event.event_type.name,
                    event.task_id,
                    event.dag_id,
                    str(e),
                )
                self._metrics["handler_failures"] += 1

                # Emit FAILED event if this was a task operation that failed
                if (
                    event.task_id
                    and event.dag_id
                    and event.event_type not in (EventType.FAILED, EventType.STOP)
                ):
                    failed_event = TaskEvent(
                        priority=event.priority,
                        event_type=EventType.FAILED,
                        task_id=event.task_id,
                        dag_id=event.dag_id,
                        data=str(e),
                    )
                    try:
                        await self.emit_event(failed_event)
                    except Exception as emit_error:
                        logger.error("Failed to emit FAILED event: %s", emit_error)

            if (
                not self._stop_requested
                and self.dag.is_dag_complete()
                and self.event_queue.empty()
            ):
                self._completion_event.set()

    def force_stop(self) -> None:
        """Signal the scheduler to stop processing new events."""

        if not self._stop_requested:
            self._stop_requested = True
            self._completion_event.set()

    def priority_for(self, node: TaskNode) -> int:
        """Evaluate current priority for a task node."""

        return self._priority_fn(node)

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status for monitoring."""
        import time

        return {
            "current_size": self.event_queue.qsize(),
            "max_size": self.max_queue_size,
            "is_full": self.event_queue.full(),
            "overflow_count": self._overflow_count,
            "last_overflow_time": self._last_overflow_time,
            "time_since_last_overflow": (
                time.time() - self._last_overflow_time
                if self._last_overflow_time
                else None
            ),
        }

    @property
    def metrics(self) -> Dict[str, int]:
        """Expose basic counters for observability."""

        # Include queue status in metrics
        queue_status = self.get_queue_status()
        metrics = dict(self._metrics)
        metrics.update(
            {
                "queue_current_size": queue_status["current_size"],
                "queue_max_size": queue_status["max_size"],
                "queue_overflow_count": queue_status["overflow_count"],
            }
        )

        return metrics

    def get_scheduler_state(self) -> Dict[str, Any]:
        """Get current scheduler state for checkpointing."""
        # NOTE: We don't capture queued events to avoid race conditions
        # Events will be regenerated by the event loop based on DAG state during recovery

        return {
            "max_queue_size": self.max_queue_size,
            "stop_requested": self._stop_requested,
            "metrics": dict(self._metrics),
            "overflow_count": self._overflow_count,
            "last_overflow_time": self._last_overflow_time,
            "queue_current_size": self.event_queue.qsize(),  # Safe to call
            "queue_status": self.get_queue_status(),
        }

    def restore_scheduler_state(self, state: Dict[str, Any]) -> None:
        """Restore scheduler state from checkpoint."""
        try:
            # Restore basic state
            self._stop_requested = state.get("stop_requested", False)
            self._metrics.update(state.get("metrics", {}))
            self._overflow_count = state.get("overflow_count", 0)
            self._last_overflow_time = state.get("last_overflow_time")

            # Note: We don't restore queued events as they should be regenerated
            # by the event loop based on the DAG state

            logger.info("Scheduler state restored from checkpoint")

        except Exception as e:
            logger.error(f"Failed to restore scheduler state: {e}")
            raise

    async def _persist_event(self, event: TaskEvent, dropped: bool = False) -> bool:
        """Persist event to PostgreSQL storage with retry logic.

        Args:
            event: TaskEvent to persist
            dropped: Whether this event was dropped due to queue overflow

        Returns:
            True if persistence succeeded, False otherwise
        """
        if not self._postgres_storage:
            return True  # No storage configured, consider success

        # Get execution_id from DAG
        execution_id = self.dag.execution_id

        # Serialize event data once
        event_data = None
        if event.data is not None:
            try:
                # Convert data to JSON-serializable format
                if isinstance(event.data, dict):
                    event_data = event.data
                elif isinstance(event.data, str):
                    event_data = {"message": event.data}
                else:
                    event_data = {"value": str(event.data)}
            except Exception as e:
                logger.warning(f"Failed to serialize event data: {e}")
                event_data = {"error": "serialization_failed"}

        # Retry persistence with exponential backoff
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self._postgres_storage.save_event_trace(
                    execution_id=execution_id,
                    event_type=event.event_type.name,
                    priority=event.priority,
                    task_id=event.task_id,
                    dag_id=event.dag_id,
                    event_data=event_data,
                    dropped=dropped,
                )
                # Success!
                if attempt > 0:
                    logger.info(f"Event persistence succeeded on attempt {attempt + 1}")
                return True

            except Exception as e:
                if attempt < max_retries - 1:
                    # Exponential backoff: 0.1s, 0.2s, 0.4s
                    backoff = 0.1 * (2**attempt)
                    logger.warning(
                        f"Event persistence attempt {attempt + 1}/{max_retries} failed: {e}. "
                        f"Retrying in {backoff}s..."
                    )
                    await asyncio.sleep(backoff)
                else:
                    # Final attempt failed
                    logger.error(
                        f"Event persistence failed after {max_retries} attempts: {e}. "
                        f"Event: {event.event_type.name} for task {event.task_id}"
                    )
                    return False

        return False
