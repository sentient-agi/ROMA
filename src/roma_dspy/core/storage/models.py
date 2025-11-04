"""SQLAlchemy models for PostgreSQL persistence."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Float,
    Integer,
    Numeric,
    String,
    Text,
    Index,
    ForeignKey,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models with async support."""
    pass


class Execution(Base):
    """
    Top-level execution tracking.

    Records metadata for each solver execution, including configuration,
    task statistics, and overall status.
    """
    __tablename__ = "executions"

    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # running, completed, failed
    initial_goal: Mapped[str] = mapped_column(Text, nullable=False)
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False)
    profile: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    experiment_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    failed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    config: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    execution_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    dag_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    final_result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Relationships
    checkpoints: Mapped[List["Checkpoint"]] = relationship(
        "Checkpoint",
        back_populates="execution",
        cascade="all, delete-orphan"
    )
    task_traces: Mapped[List["TaskTrace"]] = relationship(
        "TaskTrace",
        back_populates="execution",
        cascade="all, delete-orphan"
    )
    lm_traces: Mapped[List["LMTrace"]] = relationship(
        "LMTrace",
        back_populates="execution",
        cascade="all, delete-orphan"
    )
    circuit_breakers: Mapped[List["CircuitBreaker"]] = relationship(
        "CircuitBreaker",
        back_populates="execution",
        cascade="all, delete-orphan"
    )
    event_traces: Mapped[List["EventTrace"]] = relationship(
        "EventTrace",
        back_populates="execution",
        cascade="all, delete-orphan"
    )
    toolkit_traces: Mapped[List["ToolkitTrace"]] = relationship(
        "ToolkitTrace",
        back_populates="execution",
        cascade="all, delete-orphan"
    )
    tool_invocation_traces: Mapped[List["ToolInvocationTrace"]] = relationship(
        "ToolInvocationTrace",
        back_populates="execution",
        cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_executions_status", "status"),
        Index("idx_executions_created_at", "created_at", postgresql_using="btree"),
    )


class Checkpoint(Base):
    """
    Checkpoint metadata and DAG snapshots.

    Stores compressed DAG state snapshots for recovery, along with
    preserved results and module states.
    """
    __tablename__ = "checkpoints"

    checkpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    execution_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("executions.execution_id", ondelete="CASCADE"),
        nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    trigger: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)  # valid, expired, corrupted
    dag_snapshot: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    preserved_results: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    module_states: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    failed_task_ids: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    compressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    execution: Mapped["Execution"] = relationship("Execution", back_populates="checkpoints")
    task_traces: Mapped[List["TaskTrace"]] = relationship(
        "TaskTrace",
        back_populates="checkpoint",
        foreign_keys="TaskTrace.checkpoint_id"
    )

    __table_args__ = (
        Index("idx_checkpoints_execution", "execution_id", "created_at", postgresql_using="btree"),
        Index("idx_checkpoints_trigger", "trigger"),
        Index("idx_checkpoints_state", "state"),
    )


class TaskTrace(Base):
    """
    Individual task execution history.

    Tracks each task's lifecycle, including status changes, retries,
    dependencies, and results.
    """
    __tablename__ = "task_traces"

    trace_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("executions.execution_id", ondelete="CASCADE"),
        nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    parent_task_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    checkpoint_id: Mapped[Optional[str]] = mapped_column(
        String(128),
        ForeignKey("checkpoints.checkpoint_id", ondelete="SET NULL"),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    # Task metadata
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)
    node_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    # Execution data
    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dependencies: Mapped[List[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    subgraph_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Metadata
    task_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationships
    execution: Mapped["Execution"] = relationship("Execution", back_populates="task_traces")
    checkpoint: Mapped[Optional["Checkpoint"]] = relationship(
        "Checkpoint",
        back_populates="task_traces",
        foreign_keys=[checkpoint_id]
    )

    __table_args__ = (
        Index("idx_task_traces_execution", "execution_id", "created_at", postgresql_using="btree"),
        Index("idx_task_traces_task_id", "execution_id", "task_id"),
        Index("idx_task_traces_status", "status"),
        Index("idx_task_traces_parent", "parent_task_id"),
    )


class LMTrace(Base):
    """
    LM call traces with token metrics.

    Records every language model invocation with full request/response data,
    token usage, costs, and latency metrics.
    """
    __tablename__ = "lm_traces"

    trace_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("executions.execution_id", ondelete="CASCADE"),
        nullable=False
    )
    task_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    module_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # LM metadata
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    temperature: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    prediction_strategy: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # Token metrics
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    cost_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 6), nullable=True)

    # Request/Response
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Metadata
    lm_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationships
    execution: Mapped["Execution"] = relationship("Execution", back_populates="lm_traces")

    __table_args__ = (
        Index("idx_lm_traces_execution", "execution_id", "created_at", postgresql_using="btree"),
        Index("idx_lm_traces_task", "task_id"),
        Index("idx_lm_traces_model", "model"),
        Index("idx_lm_traces_module", "module_name"),
    )


class CircuitBreaker(Base):
    """
    Circuit breaker state tracking.

    Monitors failure rates and manages circuit breaker states
    for resilience management.
    """
    __tablename__ = "circuit_breakers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    circuit_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    execution_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("executions.execution_id", ondelete="CASCADE"),
        nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    state: Mapped[str] = mapped_column(String(32), nullable=False)  # closed, open, half_open
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_failure_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    config: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    breaker_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationships
    execution: Mapped[Optional["Execution"]] = relationship(
        "Execution",
        back_populates="circuit_breakers"
    )

    __table_args__ = (
        Index("idx_circuit_breakers_execution", "execution_id"),
        Index("idx_circuit_breakers_state", "state"),
    )


class EventTrace(Base):
    """
    Event execution traces for event-driven scheduler.

    Records all events emitted during task execution, including
    event type, priority, processing status, and any errors.
    Enables execution flow reconstruction and event system debugging.
    """
    __tablename__ = "event_traces"

    event_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("executions.execution_id", ondelete="CASCADE"),
        nullable=False
    )
    task_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    dag_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Event metadata
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    handler_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Event data and status
    event_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    processing_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    dropped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    execution: Mapped["Execution"] = relationship("Execution", back_populates="event_traces")

    __table_args__ = (
        Index("idx_event_traces_execution", "execution_id", "created_at", postgresql_using="btree"),
        Index("idx_event_traces_type", "event_type"),
        Index("idx_event_traces_task", "task_id"),
    )


class ToolkitTrace(Base):
    """
    Toolkit lifecycle event traces.

    Records toolkit creation, caching, cleanup operations with timing and outcomes.
    Enables toolkit performance analysis and reliability monitoring.
    """
    __tablename__ = "toolkit_traces"

    trace_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("executions.execution_id", ondelete="CASCADE"),
        nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Operation details
    operation: Mapped[str] = mapped_column(String(32), nullable=False)  # create, cache_hit, cache_miss, cleanup
    toolkit_class: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)

    # Outcome
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Additional context
    context_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationships
    execution: Mapped["Execution"] = relationship("Execution", back_populates="toolkit_traces")

    __table_args__ = (
        Index("idx_toolkit_traces_execution", "execution_id", "timestamp", postgresql_using="btree"),
        Index("idx_toolkit_traces_operation", "operation"),
        Index("idx_toolkit_traces_class", "toolkit_class"),
        Index("idx_toolkit_traces_success", "success"),
    )


class ToolInvocationTrace(Base):
    """
    Individual tool invocation traces.

    Records every tool call with timing, input/output sizes, and outcomes.
    Provides granular visibility into tool usage patterns and performance.
    """
    __tablename__ = "tool_invocation_traces"

    trace_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    execution_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("executions.execution_id", ondelete="CASCADE"),
        nullable=False
    )
    invoked_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    # Tool identification
    toolkit_class: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Performance metrics
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    input_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Outcome
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Additional context
    context_metadata: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    # Relationships
    execution: Mapped["Execution"] = relationship("Execution", back_populates="tool_invocation_traces")

    __table_args__ = (
        Index("idx_tool_invocation_execution", "execution_id", "invoked_at", postgresql_using="btree"),
        Index("idx_tool_invocation_toolkit", "toolkit_class"),
        Index("idx_tool_invocation_tool", "tool_name"),
        Index("idx_tool_invocation_success", "success"),
        Index("idx_tool_invocation_composite", "toolkit_class", "tool_name", "success"),
    )
