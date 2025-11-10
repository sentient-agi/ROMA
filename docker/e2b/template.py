import os
from e2b import AsyncTemplate

# Read environment variables from host at build time
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET_NAME = os.getenv("ROMA_S3_BUCKET", "")
STORAGE_BASE_PATH = os.getenv("STORAGE_BASE_PATH", "/opt/sentient")

# Extend the official code-interpreter template instead of building from scratch
# This preserves Jupyter server configuration and functionality
template = (
    AsyncTemplate()
    .from_template("code-interpreter-v1")
    .set_user("root")
    # Set environment variables from host
    .set_envs({
        "AWS_REGION": AWS_REGION,
        "S3_MOUNT_DIR": STORAGE_BASE_PATH,
        "S3_BUCKET_NAME": S3_BUCKET_NAME,
        "AWS_ACCESS_KEY_ID": AWS_ACCESS_KEY_ID,
        "AWS_SECRET_ACCESS_KEY": AWS_SECRET_ACCESS_KEY,
        "STORAGE_BASE_PATH": STORAGE_BASE_PATH,
    })
    # Install system packages
    .run_cmd("apt-get update")
    .run_cmd("apt-get install -y curl wget fuse ca-certificates jq && apt-get clean && rm -rf /var/lib/apt/lists/* && rm -rf /tmp/* && rm -rf /var/tmp/*")
    # Install goofys for S3 mounting
    .run_cmd("curl -L https://github.com/kahing/goofys/releases/latest/download/goofys -o /usr/local/bin/goofys && chmod +x /usr/local/bin/goofys")
    # Configure FUSE
    .run_cmd('echo "user_allow_other" >> /etc/fuse.conf')
    # Setup AWS credentials directories
    # Note: Environment variables set above are accessible in shell commands via $VAR
    .run_cmd('mkdir -p /root/.aws /home/user/.aws && if [ -n "$AWS_ACCESS_KEY_ID" ] && [ -n "$AWS_SECRET_ACCESS_KEY" ]; then echo "[default]" > /root/.aws/credentials && echo "aws_access_key_id = $AWS_ACCESS_KEY_ID" >> /root/.aws/credentials && echo "aws_secret_access_key = $AWS_SECRET_ACCESS_KEY" >> /root/.aws/credentials && echo "[default]" > /root/.aws/config && echo "region = $AWS_REGION" >> /root/.aws/config && echo "output = json" >> /root/.aws/config && cp /root/.aws/credentials /home/user/.aws/credentials && cp /root/.aws/config /home/user/.aws/config && chmod 600 /root/.aws/credentials /home/user/.aws/credentials && echo "AWS credentials configured from environment"; else echo "No AWS credentials provided - S3 mounting will be skipped"; fi')
    # Install Python requirements
    .copy("requirements.txt", "/tmp/requirements.txt")
    .run_cmd("pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt")
    # Create directories using environment variable
    .run_cmd(f'mkdir -p /workspace "${{STORAGE_BASE_PATH}}"')
    # Copy S3 mount script
    .copy("mount_s3.sh", "/usr/local/bin/mount_s3.sh")
    .run_cmd("chmod +x /usr/local/bin/mount_s3.sh")
    # Copy runtime startup script
    .copy("start_jupyter.sh", "/root/start_jupyter.sh")
    .run_cmd("chmod +x /root/start_jupyter.sh")
    # Set working directory
    .set_workdir("/workspace")
)

# Set start command to mount S3 at runtime and start Jupyter
# FUSE mounts don't persist in snapshots, so we must mount at RUNTIME
if S3_BUCKET_NAME:
    # ready_cmd checks BOTH Jupyter health AND S3 mount (parallel initialization)
    # Sandbox reports ready only when both are available
    # Graceful: if S3_BUCKET_NAME is empty, skip S3 check
    template = template.set_start_cmd(
        start_cmd="/root/start_jupyter.sh",
        ready_cmd='curl -s http://localhost:49999/health > /dev/null && ([ -f /opt/sentient/.e2b_ready ] || [ -z "$S3_BUCKET_NAME" ])'
    )
