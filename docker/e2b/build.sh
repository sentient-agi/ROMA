#!/bin/bash
# E2B Template Build Script for ROMA-DSPy
# This script builds the E2B template using the Python SDK (v2 approach)
# It reads AWS credentials from environment and passes them to the template

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if E2B_API_KEY is set
if [ -z "$E2B_API_KEY" ]; then
    log_error "E2B_API_KEY is not set"
    log_info "Please set E2B_API_KEY in your environment or .env file"
    exit 1
fi

# Check required environment variables for S3 (optional)
if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ] || [ -z "$ROMA_S3_BUCKET" ]; then
    log_warn "AWS credentials or S3 bucket not configured"
    log_warn "Template will build without S3 mounting capability"
    log_info "To enable S3: Set AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, and ROMA_S3_BUCKET"
else
    log_info "AWS credentials found - S3 mounting will be configured"
    log_info "S3 Bucket: $ROMA_S3_BUCKET"
fi

# Default to production build unless specified
BUILD_TYPE="${1:-prod}"

if [ "$BUILD_TYPE" = "dev" ]; then
    log_info "Building development template: roma-dspy-sandbox-dev"
    BUILD_SCRIPT="build_dev.py"
elif [ "$BUILD_TYPE" = "prod" ]; then
    log_info "Building production template: roma-dspy-sandbox"
    BUILD_SCRIPT="build_prod.py"
else
    log_error "Invalid build type: $BUILD_TYPE"
    log_info "Usage: $0 [dev|prod]"
    exit 1
fi

# Export environment variables for the Python build script
export AWS_REGION="${AWS_REGION:-us-east-1}"
export STORAGE_BASE_PATH="${STORAGE_BASE_PATH:-/opt/sentient}"
export E2B_API_KEY="$E2B_API_KEY"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-}"
export ROMA_S3_BUCKET="${ROMA_S3_BUCKET:-}"

log_info "Starting E2B template build..."
log_info "Environment:"
log_info "  - AWS_REGION: $AWS_REGION"
log_info "  - STORAGE_BASE_PATH: $STORAGE_BASE_PATH"
log_info "  - E2B_API_KEY: ${E2B_API_KEY:0:10}..."

# Run the Python build script
if python3 "$BUILD_SCRIPT"; then
    log_info "✅ E2B template built successfully!"

    if [ "$BUILD_TYPE" = "prod" ]; then
        log_info "Template name: roma-dspy-sandbox"
        log_info "Usage: Sandbox('roma-dspy-sandbox')"
    else
        log_info "Template name: roma-dspy-sandbox-dev"
        log_info "Usage: Sandbox('roma-dspy-sandbox-dev')"
    fi
else
    log_error "❌ E2B template build failed"
    log_info "Check the output above for errors"
    exit 1
fi
