#!/bin/bash

# setup_local.sh - Local development setup for ROMA-DSPy with S3 storage
#
# This script sets up the local development environment with S3 storage mounted via goofys.
# It creates a symlink from the mount point to the configured storage path for consistency
# across local, Docker, and E2B environments.
#
# Requirements:
#   - goofys installed (brew install goofys on macOS)
#   - AWS credentials configured (~/.aws/credentials)
#   - STORAGE_BASE_PATH set in .env file
#
# Usage:
#   ./scripts/setup_local.sh

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper function for yes/no prompts
prompt_yes_no() {
    local prompt="$1"
    local default="${2:-y}"
    local response

    if [[ "$default" == "y" ]]; then
        echo -ne "${prompt} [Y/n]: "
    else
        echo -ne "${prompt} [y/N]: "
    fi

    read -r response
    response=${response:-$default}
    [[ "$response" =~ ^[Yy]$ ]]
}

echo -e "${GREEN}ROMA-DSPy Local Setup${NC}"
echo "========================================"

# Load environment variables
if [ -f .env ]; then
    echo -e "${GREEN}Loading .env file...${NC}"
    export $(grep -v '^#' .env | xargs)
else
    echo -e "${YELLOW}Warning: .env file not found. Using defaults.${NC}"
fi

# Configuration
STORAGE_BASE_PATH="${STORAGE_BASE_PATH:-/opt/sentient}"
S3_BUCKET="${ROMA_S3_BUCKET:-roma-storage}"
S3_MOUNT_POINT="${HOME}/.roma/s3_mount"
AWS_REGION="${AWS_REGION:-us-east-1}"

echo ""
echo "Configuration:"
echo "  Storage Base Path: ${STORAGE_BASE_PATH}"
echo "  S3 Bucket: ${S3_BUCKET}"
echo "  S3 Mount Point: ${S3_MOUNT_POINT}"
echo "  AWS Region: ${AWS_REGION}"
echo ""

# Check goofys installation - try multiple locations
# Prefer $HOME/go/bin for ARM64-compatible builds
GOOFYS_BIN=""
for goofys_path in "$HOME/go/bin/goofys" "/usr/local/bin/goofys" "$(command -v goofys 2>/dev/null)"; do
    if [ -n "$goofys_path" ] && [ -x "$goofys_path" ]; then
        # Test if binary is actually executable (correct architecture)
        if "$goofys_path" --version >/dev/null 2>&1; then
            GOOFYS_BIN="$goofys_path"
            echo -e "${GREEN}Found goofys at: ${GOOFYS_BIN}${NC}"
            break
        else
            echo -e "${YELLOW}Warning: Found goofys at ${goofys_path} but it's not executable (wrong architecture?)${NC}"
        fi
    fi
done

if [ -z "$GOOFYS_BIN" ]; then
    echo -e "${RED}Error: No working goofys installation found${NC}"
    echo "Run the main setup script to install goofys:"
    echo "  ./setup.sh"
    exit 1
fi

# Check AWS credentials (either from ~/.aws/credentials or environment variables)
if [ ! -f ~/.aws/credentials ] && [ -z "$AWS_ACCESS_KEY_ID" ]; then
    echo -e "${RED}Error: AWS credentials not found${NC}"
    echo "Configure with either:"
    echo "  1. aws configure (creates ~/.aws/credentials)"
    echo "  2. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env"
    exit 1
fi

# If credentials are in environment variables, goofys will use them automatically
if [ -n "$AWS_ACCESS_KEY_ID" ]; then
    echo -e "${GREEN}Using AWS credentials from environment variables${NC}"
elif [ -f ~/.aws/credentials ]; then
    echo -e "${GREEN}Using AWS credentials from ~/.aws/credentials${NC}"
fi

# Create mount point
echo -e "${GREEN}Creating mount point at ${S3_MOUNT_POINT}...${NC}"
mkdir -p "${S3_MOUNT_POINT}"

# Determine actual mount point
# If STORAGE_BASE_PATH already exists and is suitable, use it directly
ACTUAL_MOUNT_POINT="${S3_MOUNT_POINT}"
NEEDS_SYMLINK=false

if [ "${STORAGE_BASE_PATH}" != "${S3_MOUNT_POINT}" ]; then
    # Check if STORAGE_BASE_PATH is already mounted with our S3 bucket
    if mount | grep -q "^${S3_BUCKET} on ${STORAGE_BASE_PATH}"; then
        echo -e "${GREEN}S3 bucket already mounted at ${STORAGE_BASE_PATH}${NC}"
        ACTUAL_MOUNT_POINT="${STORAGE_BASE_PATH}"
    elif [ -L "${STORAGE_BASE_PATH}" ]; then
        # It's a symlink, we'll recreate it
        NEEDS_SYMLINK=true
    elif [ ! -e "${STORAGE_BASE_PATH}" ]; then
        # Doesn't exist, we'll create symlink
        NEEDS_SYMLINK=true
    elif [ -d "${STORAGE_BASE_PATH}" ]; then
        # It's a directory - check if it's empty or a mount point
        if mountpoint -q "${STORAGE_BASE_PATH}" 2>/dev/null; then
            echo -e "${GREEN}${STORAGE_BASE_PATH} is already a mount point${NC}"
            ACTUAL_MOUNT_POINT="${STORAGE_BASE_PATH}"
        elif [ -z "$(ls -A "${STORAGE_BASE_PATH}" 2>/dev/null)" ]; then
            # Empty directory, we can mount directly here
            echo -e "${GREEN}Using existing empty directory ${STORAGE_BASE_PATH}${NC}"
            ACTUAL_MOUNT_POINT="${STORAGE_BASE_PATH}"
        else
            echo -e "${YELLOW}Warning: ${STORAGE_BASE_PATH} exists with contents${NC}"
            if prompt_yes_no "Mount to ${S3_MOUNT_POINT} and create symlink instead?" "y"; then
                NEEDS_SYMLINK=true
            else
                echo -e "${YELLOW}Mounting directly to ${STORAGE_BASE_PATH} (existing contents will be hidden)${NC}"
                ACTUAL_MOUNT_POINT="${STORAGE_BASE_PATH}"
            fi
        fi
    fi
fi

# Check if already mounted at the target location
if mountpoint -q "${ACTUAL_MOUNT_POINT}" 2>/dev/null || mount | grep -q "${S3_BUCKET} on ${ACTUAL_MOUNT_POINT}"; then
    echo -e "${YELLOW}S3 already mounted at ${ACTUAL_MOUNT_POINT}${NC}"
else
    # Create mount point directory
    echo -e "${GREEN}Creating mount point at ${ACTUAL_MOUNT_POINT}...${NC}"
    mkdir -p "${ACTUAL_MOUNT_POINT}"

    # Mount S3 bucket with goofys (optimized settings)
    # Note: Region auto-detected from AWS credentials/config, explicit --region flag causes issues
    # Reduced cache TTL to 1s for faster cross-mount synchronization (HOST <-> E2B)
    echo -e "${GREEN}Mounting S3 bucket ${S3_BUCKET} to ${ACTUAL_MOUNT_POINT}...${NC}"
    "$GOOFYS_BIN" \
        --stat-cache-ttl 1s \
        --type-cache-ttl 1s \
        --dir-mode 0755 \
        --file-mode 0644 \
        "${S3_BUCKET}" \
        "${ACTUAL_MOUNT_POINT}"

    echo -e "${GREEN}Successfully mounted S3 bucket${NC}"
fi

# Create symlink if needed
if [ "$NEEDS_SYMLINK" = true ]; then
    echo -e "${GREEN}Creating symlink: ${STORAGE_BASE_PATH} -> ${ACTUAL_MOUNT_POINT}${NC}"

    # Remove existing symlink
    if [ -L "${STORAGE_BASE_PATH}" ]; then
        rm "${STORAGE_BASE_PATH}"
    fi

    # Create parent directory if needed
    PARENT_DIR=$(dirname "${STORAGE_BASE_PATH}")
    if [ ! -d "${PARENT_DIR}" ]; then
        echo -e "${GREEN}Creating parent directory ${PARENT_DIR}...${NC}"
        sudo mkdir -p "${PARENT_DIR}"
        sudo chown "${USER}:$(id -gn)" "${PARENT_DIR}"
    fi

    # Create symlink
    ln -s "${ACTUAL_MOUNT_POINT}" "${STORAGE_BASE_PATH}"
    echo -e "${GREEN}Symlink created successfully${NC}"
fi

# Verify setup
echo ""
echo -e "${GREEN}Verifying setup...${NC}"
if [ -d "${STORAGE_BASE_PATH}" ]; then
    echo -e "${GREEN}✓ Storage path accessible: ${STORAGE_BASE_PATH}${NC}"
else
    echo -e "${RED}✗ Storage path not accessible${NC}"
    exit 1
fi

# Create executions directory
EXECUTIONS_DIR="${STORAGE_BASE_PATH}/executions"
mkdir -p "${EXECUTIONS_DIR}"
echo -e "${GREEN}✓ Executions directory created: ${EXECUTIONS_DIR}${NC}"

# Test write access
TEST_FILE="${EXECUTIONS_DIR}/.test_$(date +%s)"
if echo "test" > "${TEST_FILE}" 2>/dev/null; then
    rm "${TEST_FILE}"
    echo -e "${GREEN}✓ Write access confirmed${NC}"
else
    echo -e "${RED}✗ No write access to storage${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup complete!${NC}"
echo ""
echo "Storage is ready at: ${STORAGE_BASE_PATH}"
echo "S3 bucket '${S3_BUCKET}' mounted via goofys"
echo ""
echo "To unmount:"
echo "  umount ${S3_MOUNT_POINT}"
echo ""
echo "To mount on startup, add to crontab:"
echo "  @reboot $(pwd)/scripts/setup_local.sh"
echo ""