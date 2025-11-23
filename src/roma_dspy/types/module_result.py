"""
Module execution result tracking for comprehensive node history.
"""

from datetime import datetime, timezone
from typing import Any, Optional, Dict, List
from pydantic import BaseModel, Field
from dataclasses import dataclass, field


class TokenMetrics(BaseModel):
    """Token usage metrics for a module execution."""

    prompt_tokens: int = Field(default=0, description="Number of prompt tokens used")
    completion_tokens: int = Field(
        default=0, description="Number of completion tokens used"
    )
    total_tokens: int = Field(default=0, description="Total tokens used")
    cost: float = Field(default=0.0, description="Cost in USD")
    model: Optional[str] = Field(
        default=None, description="Model used for this execution"
    )

    @classmethod
    def from_usage_dict(
        cls,
        usage: Dict[str, Any],
        model: Optional[str] = None,
        cost: Optional[float] = None,
    ) -> "TokenMetrics":
        """Create TokenMetrics from DSPy usage dictionary."""
        # Handle empty usage dict but with cost available
        if not usage or not any(usage.values()):
            # If we have cost but no token counts, just use the cost
            return cls(
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                cost=cost or 0.0,
                model=model,
            )

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        # Use the cost from DSPy history if provided
        if cost is None:
            # Fall back to calculating if needed
            cost = cls.calculate_cost(prompt_tokens, completion_tokens, model)

        return cls(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost or 0.0,
            model=model,
        )

    @staticmethod
    def calculate_cost(
        prompt_tokens: int, completion_tokens: int, model: Optional[str] = None
    ) -> float:
        """Calculate cost based on token usage and model."""
        # Default pricing per 1K tokens (can be made configurable)
        pricing = {
            "gpt-4": {"prompt": 0.03, "completion": 0.06},
            "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
            "gpt-3.5-turbo": {"prompt": 0.0005, "completion": 0.0015},
            "gpt-4o": {"prompt": 0.005, "completion": 0.015},
            "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
            "claude-3-opus": {"prompt": 0.015, "completion": 0.075},
            "claude-3-sonnet": {"prompt": 0.003, "completion": 0.015},
            "claude-3-haiku": {"prompt": 0.00025, "completion": 0.00125},
        }

        # Extract base model name if it contains provider prefix
        if model and "/" in model:
            model = model.split("/")[-1]

        # Find matching pricing - check more specific models first
        model_pricing = None
        if model:
            model_lower = model.lower()
            # Check in order from most specific to least specific
            check_order = [
                "gpt-4o-mini",
                "gpt-4o",
                "gpt-4-turbo",
                "gpt-4",
                "gpt-3.5-turbo",
                "claude-3-opus",
                "claude-3-sonnet",
                "claude-3-haiku",
            ]
            for key in check_order:
                if key in model_lower:
                    model_pricing = pricing[key]
                    break

        # Default to GPT-4o-mini pricing if model not found
        if not model_pricing:
            model_pricing = pricing["gpt-4o-mini"]

        # Calculate cost
        prompt_cost = (prompt_tokens / 1000) * model_pricing["prompt"]
        completion_cost = (completion_tokens / 1000) * model_pricing["completion"]

        return round(prompt_cost + completion_cost, 6)

    def __add__(self, other: "TokenMetrics") -> "TokenMetrics":
        """Add two TokenMetrics together."""
        return TokenMetrics(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost=self.cost + other.cost,
            model=self.model or other.model,
        )


class ModuleResult(BaseModel):
    """
    Result of a module execution (atomizer, planner, executor, aggregator).
    Tracks all inputs, outputs, token usage, and metadata for complete observability.
    """

    module_name: str = Field(
        description="Name of the module (atomizer, planner, executor, aggregator)"
    )
    input: Any = Field(description="Input provided to the module")
    output: Any = Field(description="Output produced by the module")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Execution timestamp",
    )
    duration: float = Field(default=0.0, description="Execution duration in seconds")
    error: Optional[str] = Field(
        default=None, description="Error message if execution failed"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    # Token tracking
    token_metrics: Optional[TokenMetrics] = Field(
        default=None, description="Token usage metrics"
    )
    messages: Optional[List[Dict[str, Any]]] = Field(
        default=None, description="Full prompt/response messages"
    )

    class Config:
        arbitrary_types_allowed = True


class StateTransition(BaseModel):
    """Record of a state transition in the task lifecycle."""

    from_state: str = Field(description="Previous state")
    to_state: str = Field(description="New state")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: Optional[str] = Field(default=None, description="Reason for transition")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NodeMetrics(BaseModel):
    """Performance and execution metrics for a task node."""

    atomizer_duration: Optional[float] = Field(
        default=None, description="Atomizer execution time"
    )
    planner_duration: Optional[float] = Field(
        default=None, description="Planner execution time"
    )
    executor_duration: Optional[float] = Field(
        default=None, description="Executor execution time"
    )
    aggregator_duration: Optional[float] = Field(
        default=None, description="Aggregator execution time"
    )
    total_duration: Optional[float] = Field(
        default=None, description="Total execution time"
    )
    retry_count: int = Field(default=0, description="Number of retries")
    max_retries: int = Field(default=3, description="Maximum allowed retries")
    subtasks_created: int = Field(default=0, description="Number of subtasks created")
    max_depth_reached: int = Field(
        default=0, description="Maximum recursion depth reached"
    )

    def calculate_total_duration(self) -> float:
        """Calculate total duration from component durations."""
        durations = [
            self.atomizer_duration or 0,
            self.planner_duration or 0,
            self.executor_duration or 0,
            self.aggregator_duration or 0,
        ]
        return sum(durations)


class ExecutionEvent(BaseModel):
    """Event in the execution timeline for tracking and visualization."""

    node_id: str = Field(description="ID of the task node")
    module_name: str = Field(description="Module that was executed")
    event_type: str = Field(description="Type of event (start, complete, error)")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration: Optional[float] = Field(
        default=None, description="Duration if event is complete"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True
