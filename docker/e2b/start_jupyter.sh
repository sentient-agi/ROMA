#!/bin/bash
# Wrapper script to mount S3 and start Jupyter in parallel
# This runs at RUNTIME when sandbox starts

echo "[Startup] Starting E2B sandbox with S3 support..."

# Mount S3 in background if configured (non-blocking, parallel with Jupyter)
if [ -n "$S3_BUCKET_NAME" ]; then
    echo "[Startup] Mounting S3 bucket: $S3_BUCKET_NAME to $STORAGE_BASE_PATH (async)"
    /usr/local/bin/mount_s3.sh &
else
    echo "[Startup] No S3 bucket configured, skipping mount"
fi

# Start Jupyter server immediately (doesn't wait for S3)
echo "[Startup] Starting Jupyter server..."
# Execute the base template's startup script
exec sudo /root/.jupyter/start-up.sh
