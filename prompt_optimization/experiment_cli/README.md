# GEPA Optimization Experiment CLI

CLI tool for running configurable GEPA optimization experiments with MLflow tracking.

## Features

- **YAML-based configuration**: All experiment settings in YAML files
- **MLflow autolog integration**: Automatic tracking of params, metrics, datasets, traces
- **OmegaConf support**: Type-safe config loading with defaults and overrides
- **Minimal CLI overrides**: Quick tweaks without editing config files
- **GEPA observability**: Full support for track_stats, log_dir, checkpointing
- **Leverages ROMA profiles**: Agent configurations come from existing ROMA profile YAMLs

## Quick Start

### Recommended: Using Just Commands

The easiest way to run experiments is using the `just` task runner from the project root:

```bash
# Start services (MLflow, MinIO, PostgreSQL)
just docker-up-full

# Run optimization with default config (quick_test)
just optimize

# Run with specific config and name
just optimize balanced my-experiment

# Run with specific profile and verbose logging
just optimize balanced my-experiment default true

# Run without MLflow tracking
just optimize-no-mlflow quick_test test-run

# List available configs
just list-optimize-configs

# Open MLflow UI in browser
just mlflow-ui
```

**Just Command Arguments:**
```bash
just optimize [config] [name] [profile] [verbose]
  config  - Config name from configs/ (without .yaml, default: quick_test)
  name    - Experiment name (default: auto-generated timestamp)
  profile - ROMA profile to use (default: test)
  verbose - Enable verbose logging (default: false)
```

**Why use Just commands?**
- ✅ Runs inside Docker with all dependencies configured
- ✅ MLflow tracking pre-configured (`http://mlflow:5000`)
- ✅ MinIO S3 artifact storage pre-configured
- ✅ Simple, memorable commands from project root

### Alternative: Direct Docker Commands

If you prefer to run Docker commands directly:

```bash
# Start services
docker compose --profile observability up -d

# Run experiment inside container (using uv)
docker exec -it roma-dspy-api bash -c "cd /app/prompt_optimization/experiment_cli && uv run python run_experiment.py --config configs/quick_test.yaml"

# Or enter container interactively
docker exec -it roma-dspy-api bash
cd /app/prompt_optimization/experiment_cli
uv run python run_experiment.py --config configs/balanced.yaml
```

**Note:** The container has `uv` installed for fast Python package management. Always use `uv run python` for consistency.

### For Local Development (Outside Docker)

For local development, use `uv` as well:

```bash
# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Run experiment locally
cd prompt_optimization/experiment_cli
uv run python run_experiment.py --config configs/quick_test.yaml
```

Ensure your `.env` has the correct endpoints:

```bash
MLFLOW_TRACKING_URI=http://mlflow:5000  # For Docker, or http://localhost:5000 for local
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
```

### Example Configs

- **`configs/quick_test.yaml`**: Fast iteration (8 train, 10 metric calls)
- **`configs/balanced.yaml`**: Good balance (32 train, 48 metric calls)
- **`configs/thorough.yaml`**: Maximum quality (64 train, 100 metric calls)
- **`configs/custom_lms.yaml`**: Custom LM configuration example

## Configuration

### YAML Structure

The config YAML maps directly to `OptimizationConfig` dataclass:

```yaml
# Dataset configs
train_size: 32
val_size: 8
test_size: 12
dataset_seed: 0

# GEPA configs
max_metric_calls: 48
num_threads: 8
reflection_minibatch_size: 8
component_selector: "round_robin"  # or planner_only, atomizer_only, etc.

# GEPA observability
track_stats: true
track_best_outputs: true
log_dir: "logs/my_experiment"
use_mlflow: true

# Solver configs
max_depth: 1
enable_logging: false

# Execution
max_parallel: 12

# Output
output_path: "outputs/my_experiment"
```

### Custom LM Configurations

Override LM configs for specific components:

```yaml
# Judge LM (for component feedback)
judge_lm:
  model: "openrouter/anthropic/claude-sonnet-4.5"
  temperature: 0.75
  max_tokens: 64000
  cache: true

# Reflection LM (for GEPA optimization)
reflection_lm:
  model: "openrouter/anthropic/claude-sonnet-4.5"
  temperature: 1.0
  max_tokens: 64000
  cache: true
```

**Note**: Agent LMs (atomizer, planner, executor, aggregator) come from ROMA profile YAMLs, not optimization config.

## CLI Options

### Required
None (uses defaults if no config specified)

### Optional

```
--config, -c          Path to YAML config file
--name                Experiment name (default: auto-generated timestamp)
--dataset             Dataset type: aimo, frames, simpleqa, simpleqa_verified, seal0
--profile             ROMA config profile (default: test)
--num-threads         GEPA num_threads override
--selector            Component selector override
--mlflow-uri          MLflow tracking URI (default: http://localhost:5000)
--mlflow-experiment   MLflow experiment name (default: roma-optimization)
--no-mlflow           Disable MLflow tracking
--output-dir          Output directory override
--save-config         Save effective config to path (useful for debugging)
--verbose             Enable verbose logging
```

## MLflow Integration

### Setup

1. **Start MLflow server** (one-time):
   ```bash
   mlflow server --backend-store-uri sqlite:///mlflow.db --host 0.0.0.0 --port 5000
   ```

2. **Run experiment** (MLflow autolog handles tracking automatically):
   ```bash
   python run_experiment.py --config configs/balanced.yaml
   ```

3. **View results**:
   Open http://localhost:5000 in browser

### What Gets Tracked Automatically

MLflow's `dspy.autolog()` captures:
- ✅ All GEPA optimizer parameters
- ✅ Training/validation metrics over time
- ✅ Optimized program states (JSON artifacts)
- ✅ Datasets used
- ✅ Full execution traces
- ✅ Intermediate program versions

### Manual Logging

Only a few things need manual logging:
- Experiment metadata (name, dataset type)
- Test set evaluation results
- Custom metrics/tags

The CLI handles these automatically.

## Example Workflows

### Quick Iteration
```bash
# Fast test with minimal budget
python run_experiment.py \
  --config configs/quick_test.yaml \
  --name quick_test_001 \
  --dataset aimo
```

### Production Run
```bash
# Thorough optimization with full tracking
python run_experiment.py \
  --config configs/thorough.yaml \
  --name prod_frames_experiment \
  --dataset frames \
  --profile default
```

### Experiment Sweep
```bash
# Test different selectors
for selector in planner_only round_robin; do
  python run_experiment.py \
    --config configs/balanced.yaml \
    --selector $selector \
    --name "balanced_${selector}"
done
```

### Custom Configuration
```bash
# Create custom config
cat > configs/my_experiment.yaml <<EOF
train_size: 16
val_size: 4
test_size: 8
max_metric_calls: 30
num_threads: 12
component_selector: "planner_only"
track_stats: true
use_mlflow: true
EOF

# Run it
python run_experiment.py --config configs/my_experiment.yaml --name my_exp
```

## GEPA Observability Features

### Checkpointing & Resume

GEPA automatically saves checkpoints to `log_dir`:

```yaml
log_dir: "logs/my_experiment"
```

If interrupted, rerun with same `log_dir` to resume.

### Detailed Results

Access optimization statistics:

```yaml
track_stats: true
track_best_outputs: true
```

After optimization:
```python
# Access via detailed_results attribute
pareto_scores = optimized.detailed_results.val_aggregate_scores
best_outputs = optimized.detailed_results.best_outputs_valset
```

### Multithreading

GEPA uses Python multithreading for parallel evaluation:

```yaml
num_threads: 16  # Increase for faster optimization
```

**Note**: Higher values = faster but more API rate limit risk

## Troubleshooting

### MLflow not tracking
```bash
# Check if MLflow server is running
curl http://localhost:5000

# Start server if needed
mlflow server --backend-store-uri sqlite:///mlflow.db --host 0.0.0.0 --port 5000
```

### Config not loading
```bash
# Check config syntax
python -c "from omegaconf import OmegaConf; print(OmegaConf.load('configs/my_config.yaml'))"

# Save and inspect effective config
python run_experiment.py --config configs/my_config.yaml --save-config debug_config.yaml
```

### Import errors
```bash
# Make sure you're in the right directory
cd prompt_optimization/experiment_cli
python run_experiment.py --config configs/quick_test.yaml
```

## Architecture

- **Config Loading**: OmegaConf with type-safe dataclass schema
- **Agent Configs**: Come from ROMA profile YAMLs (not optimization config)
- **Optimizer Creation**: Reuses existing `create_optimizer()` factory
- **Solver Creation**: Reuses existing `create_solver_module()` factory
- **MLflow Tracking**: Autolog handles 90% automatically
- **Dataset Loading**: Reuses existing loader functions

## See Also

- `GEPA_OBSERVABILITY.md`: Full GEPA observability features documentation
- `MLFLOW_INTEGRATION.md`: Detailed MLflow integration guide
- `../README.md`: Main prompt optimization documentation
