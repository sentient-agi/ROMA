# syntax=docker/dockerfile:1.4
# ROMA-DSPy Application Dockerfile - OPTIMIZED
# Using BuildKit for cache mounts and faster builds
# Multi-stage build with uv for minimal size and maximum speed

# ============================================================================
# Builder stage - Install Python dependencies
# ============================================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

# Install build dependencies in single layer
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only dependency files first (better layer caching)
COPY pyproject.toml README.md ./
COPY src/roma_dspy/__init__.py src/roma_dspy/

# Install dependencies with uv cache mount (much faster on rebuilds)
# --prerelease=allow is needed for mlflow 3.5.0rc0
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --prerelease=allow -e ".[e2b,api,wandb]" boto3

# Copy rest of source for final install
COPY src/ ./src/
RUN uv pip install --system --no-deps -e .

# ============================================================================
# Final stage - Minimal runtime image
# ============================================================================
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install all runtime dependencies in single layer, clean up in same layer
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    fuse \
    ca-certificates \
    postgresql-client \
    wget \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/* \
    # Download and install goofys
    && wget -q -O /usr/local/bin/goofys https://github.com/kahing/goofys/releases/latest/download/goofys \
    && chmod +x /usr/local/bin/goofys \
    # Enable FUSE for non-root users
    && echo "user_allow_other" >> /etc/fuse.conf \
    # Create user and all directories in one command
    && useradd -m -u 1000 roma \
    && mkdir -p /opt/sentient /app/.checkpoints /app/.cache /app/logs /app/executions /mlflow/artifacts \
    && chown -R roma:roma /opt/sentient /mlflow

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code (with proper ownership)
COPY --chown=roma:roma . .

# Final ownership fix
RUN chown -R roma:roma /app

# Switch to non-root user
USER roma

# Set environment variables (combined for fewer layers)
ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1

# Expose API port
EXPOSE 8000

# Optimized health check (less frequent, faster timeout)
HEALTHCHECK --interval=60s --timeout=5s --start-period=40s --retries=2 \
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["roma-dspy", "server", "start", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]