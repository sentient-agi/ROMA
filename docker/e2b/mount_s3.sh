#!/bin/bash
# Simple S3 mounting script for E2B v2 start command
# This runs in the background and mounts S3 bucket

STORAGE_BASE_PATH="${STORAGE_BASE_PATH:-/opt/sentient}"
S3_BUCKET="${S3_BUCKET_NAME}"

# Only mount if bucket is configured
if [ -z "$S3_BUCKET" ]; then
    echo "[S3] No bucket configured - skipping mount"
    exit 0
fi

# Create mount point
mkdir -p "$STORAGE_BASE_PATH"

# Mount with goofys
echo "[S3] Mounting bucket: $S3_BUCKET to $STORAGE_BASE_PATH"
goofys \
    --stat-cache-ttl=1s \
    --type-cache-ttl=1s \
    --dir-mode=0777 \
    --file-mode=0666 \
    -o allow_other \
    "$S3_BUCKET" \
    "$STORAGE_BASE_PATH"

# Create marker file to signal mount is ready
if [ $? -eq 0 ]; then
    mkdir -p "$STORAGE_BASE_PATH/executions"
    echo "mounted" > "$STORAGE_BASE_PATH/.e2b_ready"
    echo "[S3] Mount successful"
else
    echo "[S3] Mount failed"
    exit 1
fi