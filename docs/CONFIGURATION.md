# ⚙️ Configuration Guide

This guide covers all configuration options in SentientResearchAgent, helping you tune the system for your specific needs.

## 📋 Table of Contents

- [Configuration Overview](#-configuration-overview)
- [Configuration File Structure](#-configuration-file-structure)
- [LLM Configuration](#-llm-configuration)
- [Execution Configuration](#-execution-configuration)
- [Cache Configuration](#-cache-configuration)
- [Logging Configuration](#-logging-configuration)
- [HITL Configuration](#-hitl-configuration)
- [Agent Profiles](#-agent-profiles)
- [Environment Variables](#-environment-variables)
- [Advanced Configuration](#-advanced-configuration)
- [Configuration Examples](#-configuration-examples)

## 🌐 Configuration Overview

SentientResearchAgent uses a hierarchical configuration system:

1. **Default Configuration** - Built-in defaults
2. **YAML Configuration** - `sentient.yaml` file
3. **Environment Variables** - Override specific values
4. **Runtime Configuration** - Programmatic overrides

### Configuration Priority

```
Runtime Config > Environment Variables > YAML File > Defaults
```

### Main Configuration File

The primary configuration file is `sentient.yaml` in the project root:

```yaml
# sentient.yaml - Main configuration file
llm:
  provider: "openrouter"
  api_key: "${OPENROUTER_API_KEY}"  # Environment variable reference

execution:
  max_concurrent_nodes: 10
  enable_hitl: true

# ... more configuration
```

## 📁 Configuration File Structure

### Complete Configuration Schema

```yaml
# LLM Infrastructure
llm:
  provider: string              # LLM provider
  api_key: string              # API key (can use env vars)
  timeout: float               # Request timeout in seconds
  max_retries: integer         # Retry attempts
  base_url: string             # Optional custom endpoint

# Cache System
cache:
  enabled: boolean             # Enable/disable caching
  cache_type: string           # "file" or "memory"
  ttl_seconds: integer         # Cache time-to-live
  max_size: integer            # Maximum cache entries

# Execution Framework
execution:
  max_concurrent_nodes: integer # Parallel execution limit
  max_parallel_nodes: integer   # Batch processing size
  max_execution_steps: integer  # Maximum execution steps
  rate_limit_rpm: integer       # Rate limit (requests/minute)
  enable_hitl: boolean          # Enable human-in-the-loop
  # ... more execution options

# Logging
logging:
  level: string                # Log level
  enable_console: boolean      # Console output
  enable_file: boolean         # File logging
  console_style: string        # Output style

# Experiment Configuration
experiment:
  base_dir: string             # Experiment directory
  retention_days: integer      # Data retention period

# Environment
environment: string            # "development", "production", etc.

# Default Agent Profile
default_profile: string        # Default agent profile to use
```

## 🤖 LLM Configuration

### Basic LLM Settings

```yaml
llm:
  provider: "openrouter"       # Options: openrouter, openai, anthropic, google
  api_key: "${OPENROUTER_API_KEY}"  # Use environment variable
  timeout: 300.0               # 5 minutes timeout
  max_retries: 3               # Retry failed requests
```

### Provider-Specific Configuration

#### OpenRouter
```yaml
llm:
  provider: "openrouter"
  api_key: "${OPENROUTER_API_KEY}"
  base_url: "https://openrouter.ai/api/v1"
  default_model: "anthropic/claude-3-opus"
  headers:
    HTTP-Referer: "https://yourapp.com"
    X-Title: "SentientResearchAgent"
```

#### OpenAI
```yaml
llm:
  provider: "openai"
  api_key: "${OPENAI_API_KEY}"
  organization: "${OPENAI_ORG_ID}"  # Optional
  default_model: "gpt-4-turbo-preview"
```

#### Anthropic
```yaml
llm:
  provider: "anthropic"
  api_key: "${ANTHROPIC_API_KEY}"
  default_model: "claude-3-opus-20240229"
  max_tokens: 4096
```

#### Google (Gemini)
```yaml
llm:
  provider: "google"
  api_key: "${GOOGLE_GENAI_API_KEY}"
  default_model: "gemini-pro"
  safety_settings:
    harassment: "BLOCK_NONE"
    hate_speech: "BLOCK_NONE"
```

### Model Selection Strategy

```yaml
llm:
  model_selection:
    # Use different models for different tasks
    simple_tasks: "gpt-3.5-turbo"
    complex_tasks: "gpt-4"
    creative_tasks: "claude-3-opus"
    
  # Fallback configuration
  fallback_models:
    - "gpt-4"
    - "claude-3-sonnet"
    - "gpt-3.5-turbo"
```

## ⚡ Execution Configuration

### Core Execution Settings

```yaml
execution:
  # Concurrency Control
  max_concurrent_nodes: 10      # Maximum parallel tasks
  max_parallel_nodes: 8         # Batch processing size
  enable_immediate_slot_fill: true  # Dynamic task scheduling
  
  # Execution Limits
  max_execution_steps: 500      # Maximum total steps
  max_recursion_depth: 5        # Maximum task depth
  node_execution_timeout_seconds: 2400.0  # 40 minutes
  max_stuck_duration: 300  # 5 minutes
  
  # Rate Limiting
  rate_limit_rpm: 30            # Requests per minute
  rate_limit_strategy: "adaptive"  # or "fixed"
```

### Timeout Configuration

```yaml
execution:
  timeout_strategy:
    warning_threshold_seconds: 60.0    # Warn about slow tasks
    soft_timeout_seconds: 180.0        # Attempt graceful stop
    hard_timeout_seconds: 300.0        # Force termination
    max_recovery_attempts: 3           # Recovery attempts
    enable_aggressive_recovery: true   # Aggressive deadlock recovery
```

### State Management

```yaml
execution:
  # State Update Optimization
  state_batch_size: 50          # Batch state updates
  state_batch_timeout_ms: 100   # Flush timeout
  enable_state_compression: true # Compress large states
  
  # WebSocket Optimization
  ws_batch_size: 50             # WebSocket batch size
  ws_batch_timeout_ms: 100      # WebSocket flush timeout
  enable_ws_compression: true   # Compress payloads
  enable_diff_updates: true     # Send only changes
```

### Task Processing Rules

```yaml
execution:
  # Planning Control
  force_root_node_planning: true  # Root always plans
  skip_atomization: false         # Skip atomizer checks
  atomization_threshold: 0.7      # Complexity threshold
  
  # Execution Strategy
  execution_strategy: "balanced"  # Options: aggressive, balanced, conservative
  optimization_level: "balanced"  # Options: none, balanced, aggressive
```

## 💾 Cache Configuration

### Basic Cache Settings

```yaml
cache:
  enabled: true
  cache_type: "file"            # Options: file, memory, redis
  ttl_seconds: 7200             # 2 hours cache lifetime
  max_size: 500                 # Maximum cache entries
```

### Advanced Cache Configuration

```yaml
cache:
  # File Cache Settings
  cache_dir: "runtime/cache/agent"  # Cache directory
  
  # Cache Strategy
  eviction_policy: "lru"        # Options: lru, lfu, fifo
  
  # Selective Caching
  cache_filters:
    min_execution_time: 5.0     # Only cache slow operations
    min_token_count: 100        # Only cache substantial responses
    
  # Cache Warming
  warm_cache_on_startup: true
  cache_warming_profile: "common_queries"
```

### Cache Key Configuration

```yaml
cache:
  key_generation:
    include_model: true         # Include model in cache key
    include_temperature: true   # Include temperature
    include_profile: true       # Include agent profile
    normalize_whitespace: true  # Normalize query whitespace
```

## 📝 Logging Configuration

### Basic Logging

```yaml
logging:
  level: "INFO"                 # Options: DEBUG, INFO, WARNING, ERROR
  enable_console: true
  enable_file: true
  file_rotation: "10 MB"        # Rotate by size
  file_retention: 3             # Keep 3 log files
```

### Console Output Styles

```yaml
logging:
  console_style: "clean"        # Options: clean, timestamp, detailed
  
  # Style definitions:
  # clean: Just messages with colors
  # timestamp: Include timestamps
  # detailed: Full details (time, level, module)
```

### Module-Specific Logging

```yaml
logging:
  # Reduce noise from specific modules
  module_levels:
    "sentientresearchagent.server.services.broadcast_service": "WARNING"
    "sentientresearchagent.server.services.project_service": "WARNING"
    "sentientresearchagent.core.project_manager": "WARNING"
    "sentientresearchagent.hierarchical_agent_framework.graph": "INFO"
    "sentientresearchagent.hierarchical_agent_framework.node": "DEBUG"
```

### Structured Logging

```yaml
logging:
  # Structured logging for analysis
  structured:
    enabled: true
    format: "json"              # Options: json, logfmt
    include_context: true       # Include execution context
    include_metrics: true       # Include performance metrics
```


## 👥 Agent Profiles

### Profile Configuration

```yaml
# Default profile selection
default_profile: "general_agent"

# Profile-specific overrides
profiles:
  deep_research_agent:
    execution:
      max_concurrent_nodes: 20  # More parallelism
      max_recursion_depth: 7    # Deeper research
    cache:
      ttl_seconds: 14400        # Longer cache (4 hours)
      
  quick_response_agent:
    execution:
      max_concurrent_nodes: 3   # Less parallelism
      max_execution_steps: 50   # Fewer steps
    llm:
      timeout: 30.0             # Faster timeout
```

## 🔐 Environment Variables

### Supported Environment Variables

```bash
# API Keys
OPENROUTER_API_KEY=sk-...
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_GENAI_API_KEY=...
EXA_API_KEY=...

# Configuration Overrides
SENTIENT_CONFIG_PATH=/path/to/custom/config.yaml
SENTIENT_PROFILE=deep_research_agent
SENTIENT_LOG_LEVEL=DEBUG
SENTIENT_CACHE_ENABLED=true

# Server Configuration
SENTIENT_HOST=0.0.0.0
SENTIENT_PORT=5000
SENTIENT_DEBUG=false

# Feature Flags
SENTIENT_ENABLE_HITL=true
SENTIENT_ENABLE_CACHE=true
SENTIENT_ENABLE_METRICS=true
```

### Using Environment Variables in Config

```yaml
# Reference environment variables
llm:
  api_key: "${OPENROUTER_API_KEY}"
  
# With defaults
cache:
  enabled: "${SENTIENT_CACHE_ENABLED:true}"  # Default to true
  
# Conditional configuration
execution:
  enable_hitl: "${SENTIENT_ENABLE_HITL:false}"
```
