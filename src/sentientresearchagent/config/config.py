"""
Configuration system for the Sentient Research Agent framework.

This module provides a flexible configuration system that can load settings from:
- Environment variables
- YAML files  
- Python dictionaries
- Programmatic configuration
"""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from pydantic import BaseModel, Field, validator, root_validator
from loguru import logger
import logging

from sentientresearchagent.hierarchical_agent_framework.types import TaskType
from .paths import RuntimePaths

class LLMConfig(BaseModel):
    """Configuration for LLM providers and models."""
    provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    api_key: Optional[str] = Field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    api_base: Optional[str] = None
    timeout: float = 30.0
    max_retries: int = 3
    
    @validator('temperature')
    def validate_temperature(cls, v):
        if not 0.0 <= v <= 2.0:
            raise ValueError('Temperature must be between 0.0 and 2.0')
        return v
    
    @validator('provider')
    def validate_provider(cls, v):
        valid_providers = ['openai', 'anthropic', 'azure', 'custom', 'openrouter']
        if v.lower() not in valid_providers:
            logger.warning(f"Provider '{v}' not in standard list: {valid_providers}")
        return v.lower()

class CacheConfig(BaseModel):
    """Configuration for caching system."""
    enabled: bool = True
    ttl_seconds: int = 3600  # 1 hour default
    max_size: int = 1000
    cache_type: str = "memory"  # memory, redis, file
    cache_dir: Optional[str] = None  # Will default to runtime/cache
    redis_url: Optional[str] = None
    
    @validator('cache_type')
    def validate_cache_type(cls, v):
        valid_types = ['memory', 'redis', 'file']
        if v.lower() not in valid_types:
            raise ValueError(f'Cache type must be one of: {valid_types}')
        return v.lower()

    @root_validator(pre=False, skip_on_failure=True)
    def check_redis_config(cls, values):
        enabled = values.get('enabled')
        cache_type = values.get('cache_type')
        redis_url = values.get('redis_url')
        if enabled and cache_type == "redis" and not redis_url:
            raise ValueError("Redis cache enabled but no redis_url provided")
        return values
    
    def get_cache_directory(self) -> Path:
        """Get the cache directory path."""
        if self.cache_dir:
            return Path(self.cache_dir)
        else:
            # Use centralized runtime paths
            paths = RuntimePaths.get_default()
            return paths.get_cache_path("agent")

class ExecutionConfig(BaseModel):
    """Configuration for task execution."""
    max_concurrent_nodes: int = 10  # Increased for better parallelization
    max_parallel_nodes: int = 8     # Maximum nodes to process in parallel batches
    max_retries: int = 3
    retry_delay_seconds: float = 5.0
    rate_limit_rpm: int = 30  # Updated to match YAML default  
    max_execution_steps: int = 500  # Updated to match YAML default
    max_recursion_depth: int = 5  # NEW: Maximum recursion depth for task decomposition
    node_execution_timeout_seconds: float = 2400.0  # Updated to match YAML default (40 minutes)
    
    # State management optimization
    state_batch_size: int = 50      # Batch size for state updates
    state_batch_timeout_ms: int = 100  # Max time before flushing state batch
    enable_state_compression: bool = True  # Compress large state objects
    
    # WebSocket optimization  
    ws_batch_size: int = 50         # Batch size for WebSocket messages
    ws_batch_timeout_ms: int = 100  # Max time before sending WebSocket batch
    enable_ws_compression: bool = True  # Compress WebSocket payloads
    enable_diff_updates: bool = True    # Send differential updates only
    
    # Immediate slot filling for better concurrency
    enable_immediate_slot_fill: bool = True  # Fill slots as soon as they become available
    
    # HITL (Human-in-the-Loop) Configuration - Centralized
    enable_hitl: bool = True  # Master HITL switch
    hitl_timeout_seconds: float = 1200.0  # 20 minutes - Updated to match YAML
    
    # CHANGED: Default to root plan only - review only the initial high-level plan
    hitl_root_plan_only: bool = True  # Only review root node's initial plan
    
    # NEW: Force root nodes to always plan (skip atomizer)
    force_root_node_planning: bool = True  # Ensures complex top-level questions get decomposed
    
    # NEW: Skip atomization entirely - forces hierarchy/depth-based execution decisions
    skip_atomization: bool = False  # When True, bypasses atomizer and uses max_depth rules
    
    # Specific HITL Checkpoints (when enable_hitl is True and hitl_root_plan_only is False)
    hitl_after_plan_generation: bool = True   # Review plans after generation
    hitl_after_modified_plan: bool = True     # Review modified plans
    hitl_after_atomizer: bool = False         # Review atomizer decisions (usually off)
    hitl_before_execute: bool = False         # Review before execution (usually off)
    
    # NEW: Execution optimization settings
    optimization_level: str = "balanced"  # "conservative" | "balanced" | "aggressive"
    execution_strategy: str = "standard"  # "standard" | "realtime" | "deferred"
    knowledge_store_batch_size: int = 10  # Number of updates to batch
    broadcast_mode: str = "full"  # "full" | "batch" | "none"
    enable_update_coalescing: bool = True  # Combine rapid updates
    update_coalescing_window_ms: int = 50  # Window for combining updates
    
    @validator('max_concurrent_nodes')
    def validate_concurrency(cls, v):
        if v < 1:
            raise ValueError('max_concurrent_nodes must be at least 1')
        if v > 20:
            logger.warning(f'High concurrency ({v}) may overwhelm LLM APIs')
        return v
    
    @classmethod
    def create_with_overrides(cls, overrides: dict = None, base_config: 'ExecutionConfig' = None) -> 'ExecutionConfig':
        """
        Create ExecutionConfig with consistent defaults and optional overrides.
        
        This ensures all ExecutionConfig instances have the same baseline values
        regardless of where they're created in the codebase.
        
        Args:
            overrides: Dict of values to override defaults
            base_config: Existing config to use as base (optional)
            
        Returns:
            ExecutionConfig with consistent defaults
        """
        # Start with either base config or class defaults
        if base_config:
            base_values = base_config.dict()
        else:
            base_values = {
                'max_concurrent_nodes': 10,
                'max_parallel_nodes': 8,
                'max_retries': 3,
                'retry_delay_seconds': 5.0,
                'rate_limit_rpm': 30,
                'max_execution_steps': 500,
                'max_recursion_depth': 5,
                'node_execution_timeout_seconds': 2400.0,
                'state_batch_size': 50,
                'state_batch_timeout_ms': 100,
                'enable_state_compression': True,
                'ws_batch_size': 50,
                'ws_batch_timeout_ms': 100,
                'enable_ws_compression': True,
                'enable_diff_updates': True,
                'enable_immediate_slot_fill': True,
                'enable_hitl': True,
                'hitl_timeout_seconds': 1200.0,  # 20 minutes
                'hitl_root_plan_only': True,
                'force_root_node_planning': True,
                'skip_atomization': False,
                'hitl_after_plan_generation': True,
                'hitl_after_modified_plan': True,
                'hitl_after_atomizer': False,
                'hitl_before_execute': False,
                'optimization_level': 'balanced',
                'execution_strategy': 'standard',
                'knowledge_store_batch_size': 10,
                'broadcast_mode': 'full',
                'enable_update_coalescing': True,
                'update_coalescing_window_ms': 50
            }
        
        # Apply overrides
        if overrides:
            base_values.update(overrides)
            
        return cls(**base_values)
    
    def to_frontend_dict(self) -> dict:
        """
        Convert ExecutionConfig to frontend-friendly dictionary.
        
        This ensures the frontend receives all configuration options
        in a consistent format regardless of how they were set.
        """
        return {
            'max_concurrent_nodes': self.max_concurrent_nodes,
            'max_parallel_nodes': self.max_parallel_nodes,
            'max_execution_steps': self.max_execution_steps,
            'max_recursion_depth': self.max_recursion_depth,
            'node_execution_timeout_seconds': self.node_execution_timeout_seconds,
            'rate_limit_rpm': self.rate_limit_rpm,
            'state_batch_size': self.state_batch_size,
            'state_batch_timeout_ms': self.state_batch_timeout_ms,
            'enable_state_compression': self.enable_state_compression,
            'ws_batch_size': self.ws_batch_size,
            'ws_batch_timeout_ms': self.ws_batch_timeout_ms,
            'enable_ws_compression': self.enable_ws_compression,
            'enable_diff_updates': self.enable_diff_updates,
            'enable_hitl': self.enable_hitl,
            'hitl_timeout_seconds': self.hitl_timeout_seconds,
            'hitl_root_plan_only': self.hitl_root_plan_only,
            'force_root_node_planning': self.force_root_node_planning,
            'skip_atomization': self.skip_atomization,
            'hitl_after_plan_generation': self.hitl_after_plan_generation,
            'hitl_after_modified_plan': self.hitl_after_modified_plan,
            'hitl_after_atomizer': self.hitl_after_atomizer,
            'hitl_before_execute': self.hitl_before_execute,
            'optimization_level': self.optimization_level,
            'execution_strategy': self.execution_strategy,
            'broadcast_mode': self.broadcast_mode,
            'enable_update_coalescing': self.enable_update_coalescing
        }
    
    @validator('max_recursion_depth')
    def validate_recursion_depth(cls, v):
        if v < 1:
            raise ValueError('max_recursion_depth must be at least 1')
        if v > 10:
            logger.warning(f'High recursion depth ({v}) may cause very deep task hierarchies')
        return v
    
    @validator('hitl_after_plan_generation', 'hitl_after_modified_plan', 'hitl_after_atomizer', 'hitl_before_execute')
    def validate_hitl_checkpoints(cls, v, values):
        """HITL checkpoints only matter if master HITL is enabled and root_plan_only is False"""
        if not values.get('enable_hitl', True) and v:
            logger.info("HITL checkpoint disabled due to master enable_hitl=False")
            return False  # Auto-disable instead of just warning
        if values.get('hitl_root_plan_only', False) and v:
            logger.info("HITL checkpoint will be ignored due to hitl_root_plan_only=True")
        return v
    
    @validator('hitl_root_plan_only')
    def validate_root_plan_only(cls, v, values):
        """Root plan only requires master HITL to be enabled"""
        if v and not values.get('enable_hitl', True):
            logger.info("hitl_root_plan_only disabled due to master enable_hitl=False")
            return False  # Auto-disable instead of just warning
        return v

    @validator('rate_limit_rpm')
    def validate_rate_limit_rpm(cls, v):
        if v > 100:
            logger.warning(f"High rate limit ({v} RPM) may cause API errors or rate limiting from providers.")
        if v < 1:
            raise ValueError("rate_limit_rpm must be at least 1.")
        return v
    
    @validator('optimization_level')
    def validate_optimization_level(cls, v):
        valid_levels = ['conservative', 'balanced', 'aggressive']
        if v not in valid_levels:
            raise ValueError(f'optimization_level must be one of: {valid_levels}')
        return v
    
    @validator('execution_strategy')
    def validate_execution_strategy(cls, v):
        valid_strategies = ['standard', 'realtime', 'deferred']
        if v not in valid_strategies:
            raise ValueError(f'execution_strategy must be one of: {valid_strategies}')
        return v
    
    @validator('broadcast_mode')
    def validate_broadcast_mode(cls, v):
        valid_modes = ['full', 'batch', 'none']
        if v not in valid_modes:
            raise ValueError(f'broadcast_mode must be one of: {valid_modes}')
        return v

class AgentConfig(BaseModel):
    """Configuration for a specific agent."""
    name: str
    agent_type: str  # "planner", "executor", "aggregator", "custom"
    model_override: Optional[str] = None
    temperature_override: Optional[float] = None
    system_prompt: Optional[str] = None
    supported_task_types: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    enabled: bool = True

class LoggingConfig(BaseModel):
    """Configuration for logging."""
    level: str = "INFO"
    # Much cleaner format - shorter timestamps, no module paths
    format: str = "<green>{time:HH:mm:ss}</green> | <level>{level: <5}</level> | <level>{message}</level>"
    file_path: Optional[str] = None  # Will default to runtime/logs/sentient.log
    file_rotation: str = "10 MB"  # Rotate by size instead of time
    file_retention: int = 3  # Keep only 3 files (must be int, not string)
    enable_console: bool = True
    enable_file: bool = True
    module_levels: Optional[Dict[str, str]] = None  # Module-specific log levels
    console_style: str = "clean"  # "clean", "timestamp", or "detailed"
    
    @validator('level')
    def validate_level(cls, v):
        valid_levels = ['TRACE', 'DEBUG', 'INFO', 'SUCCESS', 'WARNING', 'ERROR', 'CRITICAL']
        if v.upper() not in valid_levels:
            raise ValueError(f'Log level must be one of: {valid_levels}')
        return v.upper()
    
    def get_log_file_path(self) -> Optional[Path]:
        """Get the log file path."""
        if self.file_path:
            return Path(self.file_path)
        else:
            # Use centralized runtime paths
            paths = RuntimePaths.get_default()
            return paths.get_log_path("sentient")

class WebServerConfig(BaseModel):
    """Configuration for the Flask/SocketIO web server."""
    host: str = Field(default_factory=lambda: os.getenv("FLASK_HOST", "0.0.0.0"))
    port: int = Field(default_factory=lambda: int(os.getenv("FLASK_PORT", 8000)))
    debug: bool = Field(default_factory=lambda: os.getenv("FLASK_DEBUG", "false").lower() == "true")
    secret_key: str = Field(default_factory=lambda: os.getenv("FLASK_SECRET_KEY", "a-secure-default-secret-key-please-change"))

    @validator('port')
    def validate_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v
    
    @validator('secret_key')
    def validate_secret_key(cls, v):
        if v == "a-secure-default-secret-key-please-change" and os.getenv("SENTIENT_ENV", "development").lower() == "production":
            logger.warning("Using default FLASK_SECRET_KEY in production. Please set a strong, unique key.")
        if not v:
            raise ValueError("FLASK_SECRET_KEY cannot be empty.")
        return v

class ExperimentConfig(BaseModel):
    """Configuration for experiment management and output organization."""
    base_dir: str = Field(default_factory=lambda: os.getenv("EXPERIMENTS_DIR", "experiments"))
    results_dir: str = "results"  # Subdirectory for results
    emergency_backup_dir: str = "emergency_backups"  # Subdirectory for emergency backups
    configs_dir: str = "configs"  # Subdirectory for experiment configs
    retention_days: int = Field(default_factory=lambda: int(os.getenv("EXPERIMENT_RETENTION_DAYS", "30")))
    auto_cleanup: bool = True
    timestamp_format: str = "%Y%m%d_%H%M%S"
    
    @validator('retention_days')
    def validate_retention(cls, v):
        if v < 1:
            raise ValueError('Retention days must be at least 1')
        return v
    
    def get_results_path(self) -> Path:
        """Get full path to results directory."""
        return Path(self.base_dir) / self.results_dir
    
    def get_emergency_backup_path(self) -> Path:
        """Get full path to emergency backups directory."""
        return Path(self.base_dir) / self.emergency_backup_dir
    
    def get_configs_path(self) -> Path:
        """Get full path to configs directory."""
        return Path(self.base_dir) / self.configs_dir

class SentientConfig(BaseModel):
    """Main configuration class for the Sentient Research Agent framework."""
    
    # Core configurations
    llm: LLMConfig = Field(default_factory=LLMConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    web_server: WebServerConfig = Field(default_factory=WebServerConfig)
    experiment: ExperimentConfig = Field(default_factory=ExperimentConfig)
    
    # Agent configurations
    agents: Dict[str, AgentConfig] = Field(default_factory=dict)
    
    # Active Profile
    active_profile_name: Optional[str] = None
    default_profile: str = "deep_research_agent"

    # Custom configurations for extensions
    custom: Dict[str, Any] = Field(default_factory=dict)
    
    # Metadata
    config_version: str = "1.0.0"
    environment: str = Field(default_factory=lambda: os.getenv("SENTIENT_ENV", "development"))

    class Config:
        extra = "allow"
        validate_assignment = True

    @classmethod
    def from_yaml(cls, path: Union[str, Path]) -> "SentientConfig":
        """
        Load configuration from a YAML file.
        
        Args:
            path: Path to the YAML configuration file
            
        Returns:
            SentientConfig instance
            
        Raises:
            FileNotFoundError: If the config file doesn't exist
            yaml.YAMLError: If the YAML is invalid
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if data is None:
                data = {}
                
            logger.info(f"Loaded configuration from {path}")
            # DEBUG: Log timeout value being loaded
            if 'execution' in data and 'node_execution_timeout_seconds' in data['execution']:
                logger.debug(f"🔧 CONFIG DEBUG: Loading node_execution_timeout_seconds = {data['execution']['node_execution_timeout_seconds']}")
            return cls(**data)
        except yaml.YAMLError as e:
            logger.error(f"Invalid YAML in configuration file {path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error loading configuration from {path}: {e}")
            raise

    @classmethod 
    def from_env(cls, prefix: str = "SENTIENT_") -> "SentientConfig":
        """
        Load configuration from environment variables.
        
        Args:
            prefix: Prefix for environment variables (default: "SENTIENT_")
            
        Returns:
            SentientConfig instance with values from environment
        """
        config = cls()
        
        # Map environment variables to config fields
        env_mappings = {
            f"{prefix}LLM_PROVIDER": ("llm", "provider"),
            f"{prefix}LLM_MODEL": ("llm", "model"),
            f"{prefix}LLM_TEMPERATURE": ("llm", "temperature"),
            f"{prefix}LLM_API_KEY": ("llm", "api_key"),
            f"{prefix}LLM_API_BASE": ("llm", "api_base"),
            f"{prefix}CACHE_ENABLED": ("cache", "enabled"),
            f"{prefix}CACHE_TTL": ("cache", "ttl_seconds"),
            f"{prefix}MAX_CONCURRENT": ("execution", "max_concurrent_nodes"),
            f"{prefix}MAX_STEPS": ("execution", "max_execution_steps"),
            f"{prefix}EXECUTION_TIMEOUT": ("execution", "node_execution_timeout_seconds"),
            f"{prefix}HITL_TIMEOUT": ("execution", "hitl_timeout_seconds"),
            f"{prefix}ENABLE_HITL": ("execution", "enable_hitl"),
            f"{prefix}LOG_LEVEL": ("logging", "level"),
            f"{prefix}LOG_FILE": ("logging", "file_path"),
            f"{prefix}ENVIRONMENT": ("environment",),
        }
        
        for env_var, config_path in env_mappings.items():
            value = os.getenv(env_var)
            if value is not None:
                try:
                    # Convert string values to appropriate types
                    if env_var.endswith(('_ENABLED', '_HITL')):
                        value = value.lower() in ('true', '1', 'yes', 'on')
                    elif env_var.endswith(('_TTL', '_CONCURRENT', '_STEPS')):
                        value = int(value)
                    elif env_var.endswith('_TEMPERATURE'):
                        value = float(value)
                    
                    # Set the configuration value
                    if len(config_path) == 1:
                        setattr(config, config_path[0], value)
                    else:
                        section = getattr(config, config_path[0])
                        setattr(section, config_path[1], value)
                        
                    logger.debug(f"Set config from {env_var}: {config_path} = {value}")
                except (ValueError, AttributeError) as e:
                    logger.warning(f"Failed to set config from {env_var}: {e}")
        
        logger.info("Configuration loaded from environment variables")
        return config

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SentientConfig":
        """
        Create configuration from a dictionary.
        
        Args:
            data: Dictionary containing configuration data
            
        Returns:
            SentientConfig instance
        """
        return cls(**data)

    def to_yaml(self, path: Union[str, Path]) -> None:
        """
        Save configuration to a YAML file.
        
        Args:
            path: Path where to save the configuration
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Convert to dictionary and clean up None values
        data = self.dict(exclude_none=True)
        
        with open(path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, indent=2, sort_keys=True)
        
        logger.info(f"Configuration saved to {path}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return self.dict(exclude_none=True)

    def merge_with(self, other: "SentientConfig") -> "SentientConfig":
        """
        Merge this configuration with another, with other taking precedence.
        
        Args:
            other: Another SentientConfig to merge with
            
        Returns:
            New SentientConfig with merged values
        """
        self_dict = self.to_dict()
        other_dict = other.to_dict()
        
        def deep_merge(base: dict, overlay: dict) -> dict:
            """Recursively merge dictionaries."""
            result = base.copy()
            for key, value in overlay.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result
        
        merged_dict = deep_merge(self_dict, other_dict)
        return SentientConfig.from_dict(merged_dict)

    def validate_api_keys(self) -> List[str]:
        """
        Validate that required API keys are present.
        
        Returns:
            List of missing API key names
        """
        missing_keys = []
        
        if self.llm.provider == "openai" and not self.llm.api_key:
            missing_keys.append("OpenAI API key")
        
        # Add validation for other providers as needed
        
        return missing_keys

    def setup_logging(self) -> None:
        """Configure logging based on the current settings."""
        from ..core.logging_config import setup_logging, create_module_filter
        
        # Create module filter if module_levels is specified
        console_filter = None
        if hasattr(self, 'logging') and hasattr(self.logging, 'module_levels') and self.logging.module_levels:
            console_filter = create_module_filter(self.logging.module_levels)
        
        # Use the enhanced logging setup
        setup_logging(self.logging, console_filter)

# Default configuration instance
default_config = SentientConfig()

# Convenience functions
def load_config(
    config_file: Optional[Union[str, Path]] = None,
    use_env: bool = True,
    env_prefix: str = "SENTIENT_"
) -> SentientConfig:
    """
    Load configuration using the standard precedence:
    1. Default configuration
    2. Environment variables (if use_env=True)
    3. Configuration file (if provided)
    
    Args:
        config_file: Optional path to YAML configuration file
        use_env: Whether to load from environment variables
        env_prefix: Prefix for environment variables
        
    Returns:
        SentientConfig instance
    """
    # Start with default config
    config = SentientConfig()
    
    # Merge with environment variables
    if use_env:
        env_config = SentientConfig.from_env(env_prefix)
        config = config.merge_with(env_config)
    
    # Merge with file config
    if config_file:
        file_config = SentientConfig.from_yaml(config_file)
        logger.debug(f"🔧 CONFIG DEBUG: Before merge - timeout = {config.execution.node_execution_timeout_seconds}")
        logger.debug(f"🔧 CONFIG DEBUG: File config - timeout = {file_config.execution.node_execution_timeout_seconds}")
        config = config.merge_with(file_config)
        logger.debug(f"🔧 CONFIG DEBUG: After merge - timeout = {config.execution.node_execution_timeout_seconds}")
    
    # Validate and setup
    missing_keys = config.validate_api_keys()
    if missing_keys:
        logger.warning(f"Missing API keys: {', '.join(missing_keys)}")
    
    config.setup_logging()
    return config

def create_sample_config(path: Union[str, Path]) -> None:
    """
    Create a sample configuration file.
    
    Args:
        path: Where to save the sample configuration
    """
    sample_config = SentientConfig(
        llm=LLMConfig(
            provider="openai",
            model="gpt-4",
            temperature=0.7,
            api_key="your-api-key-here"
        ),
        cache=CacheConfig(
            enabled=True,
            ttl_seconds=3600,
            max_size=1000
        ),
        execution=ExecutionConfig(
            max_concurrent_nodes=3,
            max_execution_steps=100,
            enable_hitl=True
        ),
        agents={
            "custom_researcher": AgentConfig(
                name="custom_researcher",
                agent_type="executor",
                system_prompt="You are a specialized research assistant...",
                supported_task_types=["SEARCH", "THINK"],
                tools=["web_search", "file_reader"]
            )
        }
    )
    
    sample_config.to_yaml(path)
    logger.info(f"Sample configuration created at {path}") 