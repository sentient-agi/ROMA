#!/bin/bash

# start-up.sh - E2B sandbox startup script for ROMA-DSPy
#
# IMPORTANT: This script runs during TEMPLATE BUILD TIME (via start_cmd in e2b.toml)
#
# E2B Execution Model:
# 1. Template build: This script executes via start_cmd in e2b.toml
# 2. AWS credentials are created by Dockerfile from build args and stored in ~/.aws/credentials
# 3. This script mounts S3 bucket using goofys with those credentials during the build
# 4. Template is snapshotted with S3 mounted and accessible
# 5. Runtime: Sandbox instances restore from snapshot with S3 already available
#
# Build-time Environment Variables (from Dockerfile build args):
#   - AWS_ACCESS_KEY_ID: AWS credentials (from build args, stored in ~/.aws/credentials)
#   - AWS_SECRET_ACCESS_KEY: AWS credentials (from build args, stored in ~/.aws/credentials)
#   - AWS_REGION: AWS region (from build arg, default: us-east-1)
#   - S3_BUCKET_NAME: S3 bucket name (from build arg)
#   - STORAGE_BASE_PATH: Storage mount path (from build arg, default: /opt/sentient)
#
# Note: Don't use 'set -e' as it can interfere with E2B's process management

# Configuration from environment
STORAGE_BASE_PATH="${STORAGE_BASE_PATH:-/opt/sentient}"
S3_BUCKET="${S3_BUCKET_NAME}"  # Set via Dockerfile ENV from build arg
AWS_REGION="${AWS_REGION:-us-east-1}"

# Logging function
log() {
    echo "[E2B-SETUP] $1"
}

# Start Jupyter Server (required for E2B code interpreter)
start_jupyter_server() {
	counter=0
	response=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8888/api/status")
	while [[ ${response} -ne 200 ]]; do
		let counter++
		if ((counter % 20 == 0)); then
			log "Waiting for Jupyter Server to start..."
			sleep 0.1
		fi

		response=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8888/api/status")
	done

	cd /root/.server/
	/root/.server/.venv/bin/uvicorn main:app --host 0.0.0.0 --port 49999 --workers 1 --no-access-log --no-use-colors --timeout-keep-alive 640
}

log "🚀 Starting ROMA-DSPy E2B Sandbox setup..."
log "Storage path: ${STORAGE_BASE_PATH}"
log "S3 bucket: ${S3_BUCKET:-<not configured>}"

# Check AWS credentials availability
check_aws_credentials() {
    # First check if credentials files already exist (created by Dockerfile from build args)
    if [ -f "$HOME/.aws/credentials" ] || [ -f "/root/.aws/credentials" ]; then
        log "✅ AWS credentials files found (configured from build args)"
        return 0
    fi

    # If not, try to create from environment variables (fallback)
    if [ ! -z "$AWS_ACCESS_KEY_ID" ] && [ ! -z "$AWS_SECRET_ACCESS_KEY" ]; then
        log "Setting up AWS credentials from environment variables..."

        # Create AWS CLI credentials directory
        mkdir -p $HOME/.aws
        mkdir -p /root/.aws

        # Write credentials file
        cat > $HOME/.aws/credentials << EOF
[default]
aws_access_key_id = $AWS_ACCESS_KEY_ID
aws_secret_access_key = $AWS_SECRET_ACCESS_KEY
EOF

        cat > /root/.aws/credentials << EOF
[default]
aws_access_key_id = $AWS_ACCESS_KEY_ID
aws_secret_access_key = $AWS_SECRET_ACCESS_KEY
EOF

        # Write config file with region
        if [ ! -z "$AWS_REGION" ]; then
            cat > $HOME/.aws/config << EOF
[default]
region = $AWS_REGION
output = json
EOF
            cat > /root/.aws/config << EOF
[default]
region = $AWS_REGION
output = json
EOF
        fi

        log "✅ AWS credentials configured from environment"
        return 0
    else
        log "⚠️  No AWS credentials found - S3 mounting will be skipped"
        return 1
    fi
}

# Mount S3 bucket using goofys
mount_s3_bucket() {
    if [ -z "$S3_BUCKET" ]; then
        log "⚠️  S3 bucket name not configured - skipping mount"
        return 1
    fi

    log "Mounting S3 bucket: $S3_BUCKET to $STORAGE_BASE_PATH"

    # Create mount point
    mkdir -p "$STORAGE_BASE_PATH"

    # Check if goofys is available
    if ! command -v goofys &> /dev/null; then
        log "⚠️  goofys not found - cannot mount S3"
        return 1
    fi

    # Check if already mounted
    if mountpoint -q "$STORAGE_BASE_PATH" 2>/dev/null || mount | grep -q "$STORAGE_BASE_PATH"; then
        log "✅ S3 already mounted at $STORAGE_BASE_PATH"
        return 0
    fi

    # Mount with goofys (using Sentient's working configuration)
    log "Attempting goofys mount..."
    log "AWS Region: ${AWS_REGION}"
    # Note: -o allow_other is critical for FUSE mounts in containers
    # Reduced cache TTL to 1s for faster cross-mount synchronization (HOST <-> E2B)
    if goofys \
        --stat-cache-ttl=1s \
        --type-cache-ttl=1s \
        --dir-mode=0777 \
        --file-mode=0666 \
        -o allow_other \
        "$S3_BUCKET" \
        "$STORAGE_BASE_PATH"; then

        log "✅ S3 bucket mounted successfully with goofys"

        # Verify mount
        if timeout 5 ls "$STORAGE_BASE_PATH" >/dev/null 2>&1; then
            log "✅ S3 mount verified"

            # Create executions directory structure
            mkdir -p "$STORAGE_BASE_PATH/executions" 2>/dev/null || true

            # Test write access
            test_file="$STORAGE_BASE_PATH/executions/.e2b_test_$(date +%s)"
            if echo "e2b_test" > "$test_file" 2>/dev/null; then
                rm "$test_file" 2>/dev/null || true
                log "✅ Write access confirmed"
            else
                log "⚠️  Write access test failed"
            fi
        else
            log "⚠️  S3 mount verification failed"
        fi

        return 0
    else
        log "❌ goofys mount failed - S3 not available"
        return 1
    fi
}

# Main startup sequence
main() {
    log "Initializing E2B sandbox..."

    # Check AWS credentials and mount S3 bucket (both optional)
    if check_aws_credentials; then
        mount_s3_bucket
    fi

    # Create workspace directory (always)
    mkdir -p /workspace 2>/dev/null || true

    # Set up Python path if needed
    export PYTHONPATH="/code/src:${PYTHONPATH}"

    log "✅ Startup script completed successfully"
    log "Sandbox ready for code execution"
}

# Run main function
main "$@"

# Start Code Interpreter server (required for E2B code execution)
log "Starting Code Interpreter server..."
start_jupyter_server &
MATPLOTLIBRC=/root/.config/matplotlib/.matplotlibrc jupyter server --IdentityProvider.token="" >/dev/null 2>&1
