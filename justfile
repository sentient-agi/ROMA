# ROMA-DSPy Justfile
# Common development commands
# Default recipe
default:
    @just --list
# Install dependencies
install:
    pip install -e .
# Run all tests
test:
    pytest tests/
# Run specific test file
test-file file:
    pytest tests/{{file}}
# Run tests with coverage
test-coverage:
    pytest tests/ --cov=src/roma_dspy --cov-report=html --cov-report=term
# Run tests in verbose mode
test-verbose:
    pytest tests/ -v
# Run unit tests
test-unit:
    pytest tests/unit/ -v
# Run integration tests
test-integration:
    pytest tests/integration/ -v
# Run linting
lint:
    ruff check src/ tests/
# Format code
format:
    ruff format src/ tests/
# Type check
typecheck:
    mypy src/roma_dspy
# Clean cache and build artifacts
clean:
    rm -rf .pytest_cache/
    rm -rf htmlcov/
    rm -rf .coverage
    rm -rf dist/
    rm -rf build/
    rm -rf *.egg-info/
    find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
# Run the CLI
cli *args:
    python -m src.roma_dspy.cli {{args}}
# Start interactive Python session with imports
repl:
    python -c "from src.roma_dspy.engine.solve import solve, RecursiveSolver; from src.roma_dspy.modules import *; print('ROMA-DSPy modules loaded'); import IPython; IPython.start_ipython()"
# Run example notebooks
example name:
    jupyter nbconvert --to notebook --execute examples/{{name}}.ipynb --output {{name}}_executed.ipynb
# Start Jupyter notebook
notebook:
    jupyter notebook
# Build package
build:
    python -m build
# Run pre-commit checks
pre-commit:
    just format
    just lint
    just typecheck
    just test
# Setup complete environment (one-command setup)
setup profile="":
    @echo "Running complete ROMA-DSPy setup..."
    @if [ -n "{{profile}}" ]; then \
        ./setup.sh --profile {{profile}}; \
    else \
        ./setup.sh; \
    fi
# Setup development environment (Python only)
setup-dev:
    pip install -e .
    pip install pytest mypy ruff jupyter ipython coverage
    @echo "Development environment ready!"
# ==============================================================================
# CLI Commands (via Docker)
# ==============================================================================
# Solve a task using ROMA-DSPy CLI
# Usage: just solve <task> [profile] [max_depth] [verbose] [output]
# Example: just solve "your task" crypto_agent 3 false text
solve task profile="crypto_agent" max_depth="3" verbose="false" output="text":
    @if [ "{{verbose}}" = "true" ]; then \
        docker exec -it roma-dspy-api roma-dspy solve --profile {{profile}} --max-depth {{max_depth}} --output {{output}} --verbose "{{task}}"; \
    else \
        docker exec -it roma-dspy-api roma-dspy solve --profile {{profile}} --max-depth {{max_depth}} --output {{output}} "{{task}}"; \
    fi
# Run any CLI command in the container (Docker)
cli-docker *args:
    docker exec -it roma-dspy-api roma-dspy {{args}}
# Interactive TUI visualization
# Usage: just viz [execution_id] [experiment] [profile] [status]
# Examples:
#   just viz abc-123                          # View specific execution
#   just viz                                   # Browse all executions (browser mode)
#   just viz "" "ROMA-Crypto-Agent"          # Filter by experiment
#   just viz "" "" crypto_agent               # Filter by profile
#   just viz "" "" "" running                 # Filter by status
viz execution_id="" experiment="" profile="" status="":
    #!/usr/bin/env bash
    cmd="docker exec -it roma-dspy-api roma-dspy viz-interactive"
    [ -n "{{execution_id}}" ] && cmd="$cmd {{execution_id}}"
    [ -n "{{experiment}}" ] && cmd="$cmd --experiment '{{experiment}}'"
    [ -n "{{profile}}" ] && cmd="$cmd --profile {{profile}}"
    [ -n "{{status}}" ] && cmd="$cmd --status {{status}}"
    eval $cmd

# Interactive TUI visualization (v2 - testing)
# Usage: just viz-v2 <execution_id> [live]
# Example: just viz-v2 abc-123-def-456
# Example: just viz-v2 abc-123-def-456 true
viz-v2 execution_id live="false":
    @if [ "{{live}}" = "true" ]; then \
        docker exec -it roma-dspy-api roma-dspy viz-v2 {{execution_id}} --live; \
    else \
        docker exec -it roma-dspy-api roma-dspy viz-v2 {{execution_id}}; \
    fi

# ==============================================================================
# Prompt Optimization (GEPA)
# ==============================================================================

# Run GEPA prompt optimization experiment inside Docker container
# Usage: just optimize [config] [name] [profile] [verbose]
# Example: just optimize quick_test my-experiment test false
# Example: just optimize balanced prod-run default true
#
# Arguments:
#   config  - Config file name from prompt_optimization/experiment_cli/configs/ (without .yaml)
#   name    - Experiment name (default: auto-generated timestamp)
#   profile - ROMA profile to use (default: test)
#   verbose - Enable verbose logging (default: false)
#
# The experiment runs inside the roma-dspy-api container where:
#   - MLflow tracking is pre-configured (http://mlflow:5000)
#   - MinIO S3 artifact storage is pre-configured
#   - All environment variables are automatically set
#
# Results are tracked in MLflow at http://localhost:5000
# Optimized programs are saved to prompt_optimization/experiment_cli/outputs/
optimize config="quick_test" name="" profile="test" verbose="false":
    #!/usr/bin/env bash
    set -e

    # Build the command
    cmd="cd /app/prompt_optimization/experiment_cli && uv run python run_experiment.py --config configs/{{config}}.yaml --profile {{profile}}"

    # Add optional name parameter
    if [ -n "{{name}}" ]; then
        cmd="$cmd --name {{name}}"
    fi

    # Add verbose flag if requested
    if [ "{{verbose}}" = "true" ]; then
        cmd="$cmd --verbose"
    fi

    # Run in container with uv
    echo "Running GEPA optimization experiment..."
    echo "Config: {{config}}.yaml | Profile: {{profile}} | Name: {{name}}"
    echo "MLflow tracking: http://localhost:5000"
    echo "----------------------------------------"
    docker exec -it roma-dspy-api bash -c "$cmd"

# Run optimization experiment without MLflow tracking
# Usage: just optimize-no-mlflow [config] [name] [profile]
optimize-no-mlflow config="quick_test" name="" profile="test":
    #!/usr/bin/env bash
    set -e

    cmd="cd /app/prompt_optimization/experiment_cli && uv run python run_experiment.py --config configs/{{config}}.yaml --profile {{profile}} --no-mlflow"

    if [ -n "{{name}}" ]; then
        cmd="$cmd --name {{name}}"
    fi

    echo "Running optimization without MLflow tracking..."
    docker exec -it roma-dspy-api bash -c "$cmd"

# List available optimization configs
list-optimize-configs:
    @echo "Available optimization configs:"
    @ls -1 prompt_optimization/experiment_cli/configs/*.yaml 2>/dev/null | xargs -n1 basename | sed 's/\.yaml$//' | sed 's/^/  - /'

# Open MLflow UI to view optimization results
mlflow-ui:
    @echo "MLflow UI: http://localhost:5000"
    @command -v open >/dev/null 2>&1 && open http://localhost:5000 || xdg-open http://localhost:5000 2>/dev/null || echo "Please open http://localhost:5000 in your browser"

# ==============================================================================
# Quick Setup Commands
# ==============================================================================
# One-command setup with everything
quick-start:
    @echo "Starting quick setup..."
    ./setup.sh
# Setup with specific profile
setup-profile profile:
    ./setup.sh --profile {{profile}}
# Setup without optional components
setup-minimal:
    ./setup.sh --skip-e2b --skip-s3
# List available profiles
list-profiles:
    @echo "Available configuration profiles:"
    @cd config/profiles && ls -1 *.yaml 2>/dev/null | sed 's/\.yaml$//' | sed 's/^/  - /'
# ==============================================================================
# Docker Commands
# ==============================================================================
# Build Docker image (with BuildKit for faster builds and cache mounts)
docker-build:
    DOCKER_BUILDKIT=1 docker compose build
# Build Docker image with no cache
docker-build-clean:
    DOCKER_BUILDKIT=1 docker compose build --no-cache
# Rebuild and restart all services (full cycle)
docker-rebuild:
    @echo "Stopping containers..."
    docker compose down
    @echo "Rebuilding images with BuildKit..."
    DOCKER_BUILDKIT=1 docker compose build
    @echo "Starting services with observability..."
    docker compose --profile observability up -d
    @echo "✓ Rebuild complete! Containers are running."
# Start all services with docker-compose
docker-up:
    docker compose up -d
# Start services with observability (MLflow)
docker-up-full:
    docker compose --profile observability up -d
# Stop all services
docker-down:
    docker compose down
# Stop and remove volumes
docker-down-clean:
    docker compose down -v
# View logs for all services
docker-logs:
    docker compose logs -f
# View logs for specific service
docker-logs-service service:
    docker compose logs -f {{service}}
# Restart all services
docker-restart:
    docker compose restart
# Check service status
docker-ps:
    docker compose ps
# Execute command in roma-api container
docker-exec *args:
    docker compose exec roma-api {{args}}
# Open shell in roma-api container
docker-shell:
    docker compose exec roma-api bash
# Run database migrations
docker-migrate:
    docker compose exec roma-api alembic upgrade head
# ==============================================================================
# S3 Storage Setup
# ==============================================================================
# Mount S3 bucket locally (requires goofys and AWS credentials)
s3-mount:
    @echo "Mounting S3 bucket for local development..."
    bash scripts/setup_local.sh
# Unmount S3 bucket
s3-unmount:
    @echo "Unmounting S3 bucket..."
    umount ${STORAGE_BASE_PATH:-${HOME}/.roma/s3_mount} || true
# Check S3 mount status
s3-status:
    @echo "Checking S3 mount status..."
    @mount | grep ${STORAGE_BASE_PATH:-${HOME}/.roma/s3_mount} || echo "S3 not mounted"
# ==============================================================================
# E2B Template Management
# ==============================================================================
# Build E2B sandbox template
e2b-build:
    @echo "Building E2B sandbox template..."
    cd docker/e2b && e2b template build
# List E2B templates
e2b-list:
    e2b template list
# Delete E2B template (use with caution)
e2b-delete template_id:
    e2b template delete {{template_id}}
# Test E2B sandbox connection (quick check)
e2b-test:
    @echo "Testing E2B sandbox creation..."
    python -c "from e2b_code_interpreter import Sandbox; s = Sandbox(); print(f'Sandbox created: {s.id}'); s.kill(); print('Test successful!')"
# Validate E2B template (comprehensive integration test)
e2b-validate:
    @echo "Running E2B template validation tests..."
    pytest tests/integration/test_e2b_template_validation.py -v
# ==============================================================================
# Production Deployment
# ==============================================================================
# Deploy to production (build and start all services)
deploy:
    @echo "Deploying ROMA-DSPy to production..."
    just docker-build
    just s3-mount
    just docker-up
    @echo "Deployment complete!"
# Full production deployment with observability
deploy-full:
    @echo "Deploying ROMA-DSPy with full observability stack..."
    just docker-build
    just s3-mount
    just docker-up-full
    @echo "Deployment complete!"
# Health check
health-check:
    @echo "Checking service health..."
    curl -f http://localhost:8000/health || echo "API not responding"
    docker compose ps
