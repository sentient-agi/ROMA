"""WebSocket streaming support for PTC service.

Provides real-time progress updates during code generation and validation.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
from uuid import uuid4

from loguru import logger
from pydantic import BaseModel, Field


class StreamEventType(str, Enum):
    """Types of streaming events."""

    # Connection lifecycle
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"

    # Execution lifecycle
    EXECUTION_STARTED = "execution_started"
    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"

    # Progress events
    PROGRESS = "progress"
    STAGE_STARTED = "stage_started"
    STAGE_COMPLETED = "stage_completed"

    # Validation events
    VALIDATION_STARTED = "validation_started"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    VALIDATION_WARNING = "validation_warning"

    # Code generation events
    CODE_GENERATING = "code_generating"
    CODE_GENERATED = "code_generated"
    CODE_BLOCK_READY = "code_block_ready"

    # Test events
    TEST_STARTED = "test_started"
    TEST_PASSED = "test_passed"
    TEST_FAILED = "test_failed"

    # Error events
    ERROR = "error"
    WARNING = "warning"


class StreamMessage(BaseModel):
    """A streaming message sent to clients."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: StreamEventType
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    execution_id: Optional[str] = None
    stage: Optional[str] = None
    progress: Optional[float] = None  # 0.0 to 1.0
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return self.model_dump_json()

    @classmethod
    def connected(cls, execution_id: str) -> "StreamMessage":
        """Create a connected message."""
        return cls(
            event_type=StreamEventType.CONNECTED,
            execution_id=execution_id,
            message="Connected to execution stream",
        )

    @classmethod
    def progress_update(
        cls,
        execution_id: str,
        progress: float,
        message: str,
        stage: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> "StreamMessage":
        """Create a progress update message."""
        return cls(
            event_type=StreamEventType.PROGRESS,
            execution_id=execution_id,
            progress=progress,
            message=message,
            stage=stage,
            data=data,
        )

    @classmethod
    def stage_started(
        cls, execution_id: str, stage: str, message: Optional[str] = None
    ) -> "StreamMessage":
        """Create a stage started message."""
        return cls(
            event_type=StreamEventType.STAGE_STARTED,
            execution_id=execution_id,
            stage=stage,
            message=message or f"Stage '{stage}' started",
        )

    @classmethod
    def stage_completed(
        cls,
        execution_id: str,
        stage: str,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> "StreamMessage":
        """Create a stage completed message."""
        return cls(
            event_type=StreamEventType.STAGE_COMPLETED,
            execution_id=execution_id,
            stage=stage,
            message=message or f"Stage '{stage}' completed",
            data=data,
        )

    @classmethod
    def validation_result(
        cls,
        execution_id: str,
        passed: bool,
        stage: str,
        message: str,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
    ) -> "StreamMessage":
        """Create a validation result message."""
        event_type = StreamEventType.VALIDATION_PASSED if passed else StreamEventType.VALIDATION_FAILED
        return cls(
            event_type=event_type,
            execution_id=execution_id,
            stage=stage,
            message=message,
            data={
                "passed": passed,
                "errors": errors or [],
                "warnings": warnings or [],
            },
        )

    @classmethod
    def error(
        cls, execution_id: str, error: str, stage: Optional[str] = None
    ) -> "StreamMessage":
        """Create an error message."""
        return cls(
            event_type=StreamEventType.ERROR,
            execution_id=execution_id,
            stage=stage,
            error=error,
            message=f"Error: {error}",
        )


@dataclass
class StreamContext:
    """Context for managing a streaming execution."""

    execution_id: str
    started_at: float = field(default_factory=time.time)
    current_stage: Optional[str] = None
    progress: float = 0.0
    messages: List[StreamMessage] = field(default_factory=list)
    _subscribers: List[asyncio.Queue] = field(default_factory=list)

    async def emit(self, message: StreamMessage) -> None:
        """Emit a message to all subscribers."""
        message.execution_id = self.execution_id
        self.messages.append(message)

        for queue in self._subscribers:
            try:
                await queue.put(message)
            except asyncio.QueueFull:
                logger.warning(f"Queue full for execution {self.execution_id}, dropping message")

    async def emit_progress(
        self,
        progress: float,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit a progress update."""
        self.progress = progress
        await self.emit(
            StreamMessage.progress_update(
                execution_id=self.execution_id,
                progress=progress,
                message=message,
                stage=self.current_stage,
                data=data,
            )
        )

    async def start_stage(self, stage: str, message: Optional[str] = None) -> None:
        """Start a new stage."""
        self.current_stage = stage
        await self.emit(
            StreamMessage.stage_started(self.execution_id, stage, message)
        )

    async def complete_stage(
        self,
        stage: str,
        message: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Complete a stage."""
        await self.emit(
            StreamMessage.stage_completed(self.execution_id, stage, message, data)
        )
        if self.current_stage == stage:
            self.current_stage = None

    async def emit_validation(
        self,
        passed: bool,
        stage: str,
        message: str,
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
    ) -> None:
        """Emit a validation result."""
        await self.emit(
            StreamMessage.validation_result(
                execution_id=self.execution_id,
                passed=passed,
                stage=stage,
                message=message,
                errors=errors,
                warnings=warnings,
            )
        )

    async def emit_error(self, error: str) -> None:
        """Emit an error."""
        await self.emit(
            StreamMessage.error(self.execution_id, error, self.current_stage)
        )

    def subscribe(self) -> asyncio.Queue:
        """Subscribe to messages."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from messages."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)

    @property
    def elapsed_seconds(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.started_at


class StreamManager:
    """Manages streaming contexts for multiple executions."""

    def __init__(self):
        self._contexts: Dict[str, StreamContext] = {}
        self._lock = asyncio.Lock()

    async def create_context(self, execution_id: Optional[str] = None) -> StreamContext:
        """Create a new streaming context."""
        execution_id = execution_id or str(uuid4())
        async with self._lock:
            if execution_id in self._contexts:
                return self._contexts[execution_id]

            context = StreamContext(execution_id=execution_id)
            self._contexts[execution_id] = context
            logger.debug(f"Created stream context for execution {execution_id}")
            return context

    async def get_context(self, execution_id: str) -> Optional[StreamContext]:
        """Get an existing context."""
        return self._contexts.get(execution_id)

    async def remove_context(self, execution_id: str) -> None:
        """Remove a context."""
        async with self._lock:
            if execution_id in self._contexts:
                del self._contexts[execution_id]
                logger.debug(f"Removed stream context for execution {execution_id}")

    async def subscribe(self, execution_id: str) -> Optional[asyncio.Queue]:
        """Subscribe to an execution's messages."""
        context = await self.get_context(execution_id)
        if context:
            return context.subscribe()
        return None

    def get_active_executions(self) -> List[str]:
        """Get list of active execution IDs."""
        return list(self._contexts.keys())


# Global stream manager instance
_stream_manager: Optional[StreamManager] = None


def get_stream_manager() -> StreamManager:
    """Get or create the global stream manager."""
    global _stream_manager
    if _stream_manager is None:
        _stream_manager = StreamManager()
    return _stream_manager


async def stream_generator(
    execution_id: str,
    timeout: float = 300.0,
) -> AsyncGenerator[str, None]:
    """Generate streaming messages for an execution.

    Args:
        execution_id: Execution ID to stream
        timeout: Maximum time to wait for messages

    Yields:
        JSON-encoded StreamMessage strings
    """
    manager = get_stream_manager()
    queue = await manager.subscribe(execution_id)

    if not queue:
        yield StreamMessage.error(execution_id, "Execution not found").to_json()
        return

    # Send connected message
    yield StreamMessage.connected(execution_id).to_json()

    start_time = time.time()
    try:
        while True:
            remaining = timeout - (time.time() - start_time)
            if remaining <= 0:
                yield StreamMessage.error(execution_id, "Stream timeout").to_json()
                break

            try:
                message = await asyncio.wait_for(queue.get(), timeout=min(remaining, 30.0))
                yield message.to_json()

                # Check for terminal events
                if message.event_type in (
                    StreamEventType.EXECUTION_COMPLETED,
                    StreamEventType.EXECUTION_FAILED,
                ):
                    break

            except asyncio.TimeoutError:
                # Send keepalive
                yield StreamMessage(
                    event_type=StreamEventType.PROGRESS,
                    execution_id=execution_id,
                    message="Waiting for updates...",
                ).to_json()

    finally:
        context = await manager.get_context(execution_id)
        if context:
            context.unsubscribe(queue)
