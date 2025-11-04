"""Base configuration schemas for ROMA-DSPy."""

from pydantic.dataclasses import dataclass
from pydantic import field_validator
from typing import Optional, Dict, Any
from loguru import logger
import json

from roma_dspy.types import AdapterType


@dataclass
class CacheConfig:
    """DSPy cache system configuration."""
    enabled: bool = True  # Master toggle for cache system

    # Cache layer controls
    enable_disk_cache: bool = True
    enable_memory_cache: bool = True

    # Storage configuration
    disk_cache_dir: str = ".cache/dspy"
    disk_size_limit_bytes: int = 30_000_000_000  # 30GB (DSPy default)
    memory_max_entries: int = 1_000_000  # 1M entries (DSPy default)

    @field_validator("disk_cache_dir")
    @classmethod
    def validate_cache_dir(cls, v: str) -> str:
        """Validate cache directory is not empty."""
        if not v or not v.strip():
            raise ValueError("Cache directory cannot be empty")
        return v.strip()

    @field_validator("disk_size_limit_bytes")
    @classmethod
    def validate_size_limit(cls, v: int) -> int:
        """Validate disk size limit is positive."""
        if v <= 0:
            raise ValueError("Disk size limit must be positive")
        return v

    @field_validator("memory_max_entries")
    @classmethod
    def validate_max_entries(cls, v: int) -> int:
        """Validate memory max entries is positive."""
        if v <= 0:
            raise ValueError("Memory max entries must be positive")
        return v


@dataclass
class LLMConfig:
    """Language model configuration."""

    model: str = "gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 2000
    timeout: int = 30
    api_key: Optional[str] = None
    base_url: Optional[str] = None

    # DSPy-native retry and caching
    num_retries: int = 3
    cache: bool = True
    rollout_id: Optional[int] = None

    # Adapter configuration (DSPy)
    adapter_type: AdapterType = AdapterType.CHAT  # JSON or CHAT adapter
    use_native_function_calling: bool = False  # Enable native tool calling

    # Provider-specific parameters (passed to LiteLLM via extra_body)
    # See: https://openrouter.ai/docs for OpenRouter features (web search, routing, etc.)
    extra_body: Optional[Dict[str, Any]] = None

    @field_validator("extra_body")
    @classmethod
    def validate_extra_body(cls, v: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """
        Validate extra_body structure with lenient validation.

        Performs security checks and warns about cost-impacting settings.
        Allows flexibility while preventing common mistakes.

        Raises:
            ValueError: If sensitive keys detected or size limit exceeded

        Returns:
            Validated extra_body dict or None
        """
        if v is None:
            return None

        # Security check: reject sensitive keys
        sensitive_patterns = ["api_key", "secret", "password", "token", "credential"]
        for key in v.keys():
            if any(pattern in key.lower() for pattern in sensitive_patterns):
                raise ValueError(
                    f"Sensitive key '{key}' detected in extra_body. "
                    f"Use LLMConfig.api_key field instead for security."
                )

        # Size check: prevent abuse
        json_str = json.dumps(v)
        if len(json_str) > 50_000:  # 50KB limit
            raise ValueError(
                f"extra_body too large ({len(json_str)} bytes). "
                f"Maximum size is 50KB to prevent abuse."
            )

        # Cost warning: OpenRouter web search
        if "plugins" in v and isinstance(v["plugins"], list):
            if "web_search" in v["plugins"]:
                logger.warning(
                    "OpenRouter web_search plugin enabled via extra_body. "
                    "This may significantly increase API costs per request."
                )

        # Helpful warning: common typo
        if "plugin" in v and "plugins" not in v:
            logger.warning(
                "Found 'plugin' in extra_body. Did you mean 'plugins' (plural)?"
            )

        return v

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        """Validate temperature is within valid range."""
        if not (0.0 <= v <= 2.0):
            raise ValueError(f"Temperature must be between 0.0 and 2.0, got {v}")
        return v

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, v: int) -> int:
        """Validate max_tokens is within valid range."""
        if not (0 < v <= 200000):
            raise ValueError(f"Max tokens must be between 1 and 200000, got {v}")
        return v

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate timeout is positive."""
        if v <= 0:
            raise ValueError(f"Timeout must be positive, got {v}")
        return v

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """Validate model name is not empty."""
        if not v or not v.strip():
            raise ValueError("Model name cannot be empty")
        return v.strip()

    @field_validator("num_retries")
    @classmethod
    def validate_num_retries(cls, v: int) -> int:
        """Validate num_retries is within valid range."""
        if not (0 <= v <= 10):
            raise ValueError(f"num_retries must be between 0 and 10, got {v}")
        return v

    @field_validator("adapter_type", mode="before")
    @classmethod
    def validate_adapter_type(cls, v) -> AdapterType:
        """Validate and convert adapter_type to AdapterType enum."""
        if isinstance(v, AdapterType):
            return v
        if isinstance(v, str):
            return AdapterType.from_string(v)
        raise ValueError(
            f"adapter_type must be AdapterType enum or string ('json'/'chat'), got {type(v)}"
        )


@dataclass
class RuntimeConfig:
    """Runtime system configuration."""

    max_concurrency: int = 5
    timeout: int = 30
    verbose: bool = False
    max_depth: int = 5  # For recursive solver depth control
    enable_logging: bool = False  # Separate logging control from verbose
    log_level: str = "INFO"  # Logging level control

    # Cache configuration
    cache: Optional[CacheConfig] = None

    def __post_init__(self):
        """Initialize cache config with defaults if not provided."""
        if self.cache is None:
            self.cache = CacheConfig()

    @property
    def cache_dir(self) -> str:
        """Backward compatibility property for cache_dir."""
        return self.cache.disk_cache_dir if self.cache else ".cache/dspy"

    @field_validator("max_concurrency")
    @classmethod
    def validate_max_concurrency(cls, v: int) -> int:
        """Validate max_concurrency is within valid range."""
        if not (1 <= v <= 50):
            raise ValueError(f"Max concurrency must be between 1 and 50, got {v}")
        return v

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: int) -> int:
        """Validate timeout is within valid range."""
        if not (1 <= v <= 300):
            raise ValueError(f"Timeout must be between 1 and 300 seconds, got {v}")
        return v

    @field_validator("cache_dir")
    @classmethod
    def validate_cache_dir(cls, v: str) -> str:
        """Validate cache directory path."""
        if not v or not v.strip():
            raise ValueError("Cache directory cannot be empty")
        return v.strip()

    @field_validator("max_depth")
    @classmethod
    def validate_max_depth(cls, v: int) -> int:
        """Validate max_depth is within valid range."""
        if not (1 <= v <= 20):
            raise ValueError(f"Max depth must be between 1 and 20, got {v}")
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log_level is a valid logging level."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of {valid_levels}, got {v}")
        return v.upper()