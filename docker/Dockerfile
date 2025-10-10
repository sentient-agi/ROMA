# Dockerfile for SentientResearchAgent with UV for faster builds

# Backend base image
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS backend

# Install system dependencies
RUN apt-get update && apt-get install -y \
    awscli \
    s3fs \
    curl \
    fuse \
    jq \
    util-linux \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml pdm.lock* ./
COPY README.md ./

# Convert PDM lock to requirements and install with UV
# This provides compatibility with PDM while using UV's speed
RUN if [ -f pdm.lock ]; then \
        pip install pdm && \
        pdm export -f requirements --without-hashes > requirements.txt && \
        uv pip install --system -r requirements.txt; \
    else \
        uv pip install --system -e .; \
    fi

# Copy source code
COPY src/ ./src/
COPY sentient.yaml ./
COPY emergency_backups/ ./emergency_backups/
COPY project_results/ ./project_results/

# Install goofys for high-performance S3 mounting
RUN curl -L https://github.com/kahing/goofys/releases/latest/download/goofys -o /usr/local/bin/goofys \
    && chmod +x /usr/local/bin/goofys

# Copy startup script and make it executable
COPY docker/startup.sh /usr/local/bin/startup.sh
RUN chmod +x /usr/local/bin/startup.sh

# Set Python path
ENV PYTHONPATH=/app/src
ENV FLASK_APP=sentientresearchagent.server.main

# Expose backend port
EXPOSE ${FLASK_PORT:-8000}

# Command to run the backend
CMD ["/usr/local/bin/startup.sh", "uv", "run", "python", "-m", "sentientresearchagent"]