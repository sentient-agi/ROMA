"""Resilience configuration schemas for ROMA-DSPy."""

from typing import Optional, Any
from pydantic.dataclasses import dataclass
from pydantic import field_validator

# Import for type checking only (avoid OmegaConf issues with nested Pydantic models)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from roma_dspy.types.checkpoint_models import CheckpointConfig


@dataclass
class ResilienceConfig:
    """Configuration for resilience features (retry, circuit breaker, checkpointing)."""

    # Retry configuration
    retry_strategy: str = "exponential_backoff"
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter_factor: float = 0.1

    # Circuit breaker configuration
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 2
    evaluation_window: float = 300.0

    # Checkpoint configuration (stored as dict for OmegaConf compatibility)
    checkpoint: Optional[Any] = (
        None  # Will be converted to CheckpointConfig in __post_init__
    )

    def __post_init__(self):
        """Initialize checkpoint config with defaults if not provided."""
        from roma_dspy.types.checkpoint_models import CheckpointConfig

        if self.checkpoint is None:
            self.checkpoint = CheckpointConfig()
        elif isinstance(self.checkpoint, dict):
            # Convert dict to CheckpointConfig (from YAML/OmegaConf)
            try:
                self.checkpoint = CheckpointConfig(**self.checkpoint)
            except Exception as e:
                raise ValueError(f"Invalid checkpoint configuration: {e}") from e
        elif not isinstance(self.checkpoint, CheckpointConfig):
            raise TypeError(
                f"Checkpoint must be CheckpointConfig or dict, got {type(self.checkpoint).__name__}"
            )

    @field_validator("retry_strategy")
    @classmethod
    def validate_retry_strategy(cls, v: str) -> str:
        """Validate retry strategy is one of the allowed values."""
        allowed_strategies = {"exponential_backoff", "fixed_delay", "linear_backoff"}
        if v not in allowed_strategies:
            raise ValueError(
                f"Retry strategy must be one of {allowed_strategies}, got: {v}"
            )
        return v

    @field_validator("max_retries")
    @classmethod
    def validate_max_retries(cls, v: int) -> int:
        """Validate max_retries is within valid range."""
        if not (0 <= v <= 10):
            raise ValueError(f"Max retries must be between 0 and 10, got {v}")
        return v

    @field_validator("base_delay")
    @classmethod
    def validate_base_delay(cls, v: float) -> float:
        """Validate base_delay is within valid range."""
        if not (0.1 <= v <= 60.0):
            raise ValueError(
                f"Base delay must be between 0.1 and 60.0 seconds, got {v}"
            )
        return v

    @field_validator("max_delay")
    @classmethod
    def validate_max_delay(cls, v: float) -> float:
        """Validate max_delay is within valid range."""
        if not (1.0 <= v <= 3600.0):
            raise ValueError(
                f"Max delay must be between 1.0 and 3600.0 seconds, got {v}"
            )
        return v

    @field_validator("jitter_factor")
    @classmethod
    def validate_jitter_factor(cls, v: float) -> float:
        """Validate jitter_factor is within valid range."""
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"Jitter factor must be between 0.0 and 1.0, got {v}")
        return v

    @field_validator("failure_threshold")
    @classmethod
    def validate_failure_threshold(cls, v: int) -> int:
        """Validate failure_threshold is within valid range."""
        if not (1 <= v <= 100):
            raise ValueError(f"Failure threshold must be between 1 and 100, got {v}")
        return v

    @field_validator("recovery_timeout")
    @classmethod
    def validate_recovery_timeout(cls, v: float) -> float:
        """Validate recovery_timeout is within valid range."""
        if not (1.0 <= v <= 3600.0):
            raise ValueError(
                f"Recovery timeout must be between 1.0 and 3600.0 seconds, got {v}"
            )
        return v

    @field_validator("success_threshold")
    @classmethod
    def validate_success_threshold(cls, v: int) -> int:
        """Validate success_threshold is within valid range."""
        if not (1 <= v <= 20):
            raise ValueError(f"Success threshold must be between 1 and 20, got {v}")
        return v

    @field_validator("evaluation_window")
    @classmethod
    def validate_evaluation_window(cls, v: float) -> float:
        """Validate evaluation_window is within valid range."""
        if not (1.0 <= v <= 7200.0):
            raise ValueError(
                f"Evaluation window must be between 1.0 and 7200.0 seconds, got {v}"
            )
        return v
