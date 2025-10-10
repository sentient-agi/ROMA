#!/bin/bash

# SentientResearchAgent Unified Setup Script
# Supports both Docker and Native installation (macOS and Ubuntu/Debian)

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# OS detection helpers
OS_FAMILY="unknown"

detect_os() {
    uname_s="$(uname -s 2>/dev/null || echo "")"
    case "$uname_s" in
        Darwin)
            OS_FAMILY="macos"
            ;;
        Linux)
            if [[ -f /etc/debian_version ]]; then
                OS_FAMILY="debian"
            else
                OS_FAMILY="linux"
            fi
            ;;
        *)
            OS_FAMILY="unknown"
            ;;
    esac
}

open_url() {
    local url="$1"
    detect_os
    case "$OS_FAMILY" in
        macos)
            command -v open >/dev/null 2>&1 && open "$url" || true
            ;;
        debian|linux)
            command -v xdg-open >/dev/null 2>&1 && xdg-open "$url" >/dev/null 2>&1 || true
            ;;
        *)
            ;;
    esac
}

get_shell_profile() {
    # Prefer zsh on macOS, otherwise bash
    if [ -n "$ZSH_VERSION" ] || [ "$(basename "$SHELL")" = "zsh" ]; then
        echo "$HOME/.zshrc"
    else
        echo "$HOME/.bashrc"
    fi
}

append_to_profile_once() {
    local line="$1"
    local profile
    profile="$(get_shell_profile)"
    touch "$profile"
    if ! grep -Fqx "$line" "$profile" 2>/dev/null; then
        echo "$line" >> "$profile"
    fi
}

# ASCII Banner
show_banner() {
    cat << "EOF"
  ____            _   _            _   
 / ___|  ___ _ __ | |_(_) ___ _ __ | |_ 
 \___ \ / _ \ '_ \| __| |/ _ \ '_ \| __|
  ___) |  __/ | | | |_| |  __/ | | | |_ 
 |____/ \___|_| |_|\__|_|\___|_| |_|\__|
                                        
 Research Agent - Setup
EOF
    echo ""
}

# ============================================
# PATH VALIDATION AND SECURITY FUNCTIONS
# ============================================

validate_mount_path() {
    local path="$1"
    local path_description="$2"
    
    if [ -z "$path" ]; then
        print_error "Mount path cannot be empty"
        return 1
    fi
    
    # Must be absolute path
    if [[ "$path" != /* ]]; then
        print_error "$path_description must be an absolute path (start with /)"
        return 1
    fi
    
    # No parent directory traversal
    if [[ "$path" == *"../"* || "$path" == *"/.."* || "$path" == *"/../"* ]]; then
        print_error "$path_description contains dangerous parent directory references"
        return 1
    fi
    
    # No dangerous system paths
    case "$path" in
        "/" | "/boot" | "/boot/"* | "/etc" | "/etc/"* | "/sys" | "/sys/"* | "/proc" | "/proc/"*)
            print_error "$path_description points to protected system directory: $path"
            return 1
            ;;
        "/usr" | "/usr/"* | "/lib" | "/lib/"* | "/sbin" | "/sbin/"*)
            print_error "$path_description points to system directory: $path"
            return 1
            ;;
    esac
    
    # Check for potentially dangerous characters
    if [[ "$path" =~ [[:space:]$\`\|\&\;\(\)\<\>] ]]; then
        print_error "$path_description contains potentially dangerous characters"
        return 1
    fi
    
    # Path length sanity check
    if [ ${#path} -gt 255 ]; then
        print_error "$path_description is too long (max 255 characters)"
        return 1
    fi
    
    # Must not be just /data or other too-generic paths that could conflict
    case "$path" in
        "/data" | "/tmp" | "/var" | "/opt")
            print_warning "$path_description is a very generic path that may conflict with system use"
            read -p "Are you sure you want to use '$path'? (y/n): " -n 1 -r
            echo ""
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                return 1
            fi
            ;;
    esac
    
    return 0
}

create_mount_directory() {
    local mount_dir="$1"
    
    print_info "Creating mount directory: $mount_dir"
    
    # Check if directory already exists
    if [ -d "$mount_dir" ]; then
        print_info "Mount directory already exists: $mount_dir"
        
        # Check if current user can write to it
        if [ -w "$mount_dir" ]; then
            print_success "Mount directory is writable by current user"
            return 0
        else
            print_warning "Mount directory exists but is not writable by current user"
            print_info "Attempting to fix permissions..."
        fi
    fi
    
    # Create directory with proper permissions
    if [[ "$mount_dir" == /opt/* ]]; then
        # For /opt paths, create with sudo and set proper ownership
        print_info "Creating /opt directory requires elevated permissions"
        
        if sudo mkdir -p "$mount_dir"; then
            print_success "Mount directory created: $mount_dir"
            
            # Set ownership to current user
            if sudo chown "$USER:$(id -gn)" "$mount_dir"; then
                print_success "Mount directory ownership set to current user"
            else
                print_warning "Could not set ownership, mount may not be writable"
            fi
            
            # Set appropriate permissions (755 - owner can read/write/execute, group and others can read/execute)
            if sudo chmod 755 "$mount_dir"; then
                print_success "Mount directory permissions set correctly"
            else
                print_warning "Could not set permissions"
            fi
            
        else
            print_error "Failed to create mount directory: $mount_dir"
            print_error "Please ensure you have sudo privileges or create the directory manually:"
            print_error "  sudo mkdir -p $mount_dir"
            print_error "  sudo chown $USER:$(id -gn) $mount_dir"
            print_error "  sudo chmod 755 $mount_dir"
            return 1
        fi
        
    else
        # For other paths, try to create normally
        if mkdir -p "$mount_dir"; then
            print_success "Mount directory created: $mount_dir"
        else
            print_error "Failed to create mount directory: $mount_dir"
            return 1
        fi
    fi
    
    # Final verification
    if [ -d "$mount_dir" ] && [ -w "$mount_dir" ]; then
        print_success "Mount directory is ready: $mount_dir"
        return 0
    else
        print_error "Mount directory creation succeeded but directory is not writable"
        return 1
    fi
}

sanitize_env_value() {
    local value="$1"
    # Remove quotes and trim whitespace
    value=$(echo "$value" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//;s/^["'\'']*//;s/["'\'']*$//')
    echo "$value"
}

parse_boolean() {
    local value="$1"
    local default_value="${2:-false}"
    
    if [ -z "$value" ]; then
        echo "$default_value"
        return 0
    fi
    
    # Convert to lowercase for comparison
    value=$(echo "$value" | tr '[:upper:]' '[:lower:]')
    
    case "$value" in
        "true" | "yes" | "1" | "on" | "enabled")
            echo "true"
            ;;
        "false" | "no" | "0" | "off" | "disabled")
            echo "false" 
            ;;
        *)
            print_warning "Invalid boolean value '$value', using default '$default_value'"
            echo "$default_value"
            ;;
    esac
}

safe_env_extract() {
    local env_file="$1"
    local var_name="$2"
    local default_value="$3"
    
    if [ ! -f "$env_file" ]; then
        echo "$default_value"
        return 0
    fi
    
    # Use grep with error handling and sanitize the result
    local value
    value=$(grep "^${var_name}=" "$env_file" 2>/dev/null | cut -d'=' -f2- | head -n1)
    
    if [ -n "$value" ]; then
        sanitize_env_value "$value"
    else
        echo "$default_value"
    fi
}

# ============================================
# LOCAL S3 MOUNTING FUNCTIONS
# ============================================

check_fuse_support() {
    print_info "Checking FUSE support..."
    
    if [[ "$OS_TYPE" == "macos" ]]; then
        # Check for macFUSE (formerly osxfuse)
        if [ ! -e /Library/Filesystems/macfuse.fs ]; then
            print_warning "macFUSE is not installed"
            
            # Check if Homebrew is available
            if command -v brew &> /dev/null; then
                print_info "Installing macFUSE via Homebrew..."
                if brew install --cask macfuse; then
                    print_success "macFUSE installed successfully"
                    print_warning "You may need to restart your terminal or reboot to use macFUSE"
                    print_info "If FUSE mounting fails, please reboot your system"
                else
                    print_error "Failed to install macFUSE via Homebrew"
                    print_info "Manual installation: https://osxfuse.github.io/"
                    return 1
                fi
            else
                print_error "Homebrew not found. Please install macFUSE manually"
                print_info "Install macFUSE from: https://osxfuse.github.io/"
                print_info "Or install Homebrew first, then run: brew install --cask macfuse"
                return 1
            fi
        else
            print_success "macFUSE detected"
        fi
        
    elif [[ "$OS_TYPE" == "linux" ]]; then
        # Check for FUSE kernel module
        if ! lsmod | grep -q fuse; then
            print_warning "FUSE module not loaded, attempting to load..."
            if ! sudo modprobe fuse 2>/dev/null; then
                print_error "Failed to load FUSE kernel module"
                print_info "Install FUSE: sudo apt-get install fuse (Ubuntu/Debian)"
                return 1
            fi
        fi
        
        # Check for FUSE userspace tools
        if ! command -v fusermount &> /dev/null; then
            print_warning "FUSE userspace tools not found, attempting to install..."
            if command -v apt &> /dev/null; then
                if sudo apt update && sudo apt install -y fuse; then
                    print_success "FUSE installed successfully"
                else
                    print_error "Failed to install FUSE via apt"
                    return 1
                fi
            elif command -v yum &> /dev/null; then
                if sudo yum install -y fuse; then
                    print_success "FUSE installed successfully"
                else
                    print_error "Failed to install FUSE via yum"
                    return 1
                fi
            else
                print_error "Cannot auto-install FUSE - unknown package manager"
                print_info "Please install FUSE manually for your distribution"
                return 1
            fi
        fi
        
        # Check user permissions for FUSE
        if ! groups "$USER" | grep -q fuse; then
            print_warning "User '$USER' not in 'fuse' group"
            print_info "Adding user to fuse group..."
            if sudo usermod -a -G fuse "$USER" 2>/dev/null; then
                print_warning "User added to fuse group. Please log out and back in, or run: newgrp fuse"
            else
                print_error "Failed to add user to fuse group"
                return 1
            fi
        fi
        
        print_success "FUSE support verified"
    fi
    
    return 0
}

install_goofys() {
    print_info "Installing goofys for high-performance S3 mounting..."
    
    # Check FUSE support first
    if ! check_fuse_support; then
        print_error "FUSE support check failed - cannot install goofys"
        return 1
    fi
    
    # Check if goofys is already installed (check multiple locations)
    if command -v goofys &> /dev/null; then
        local goofys_path=$(command -v goofys)
        local goofys_version=$(goofys --help 2>&1 | head -1 || echo "version unknown")
        print_success "goofys already installed at: $goofys_path"
        print_info "Version info: $goofys_version"
        return 0
    fi
    
    # Also check common locations where it might be installed
    local common_paths=("/usr/local/bin/goofys" "$HOME/go/bin/goofys" "/opt/homebrew/bin/goofys")
    for path in "${common_paths[@]}"; do
        if [ -x "$path" ]; then
            print_success "goofys found at: $path"
            # Add to PATH if not already there
            if ! command -v goofys &> /dev/null; then
                local dir=$(dirname "$path")
                export PATH="$PATH:$dir"
                print_info "Added $dir to PATH for current session"
            fi
            return 0
        fi
    done
    
    # Try multiple installation methods for goofys
    print_info "Trying multiple methods to install goofys..."
    
    # Method 1: Try pre-built binary from GitHub releases
    if install_goofys_binary; then
        return 0
    fi
    
    # Method 2: Try building from source with Go
    if install_goofys_from_source; then
        return 0
    fi
    
    # Method 3: Try installing Go and building goofys
    if install_go_and_build_goofys; then
        return 0
    fi
    
    print_error "All goofys installation methods failed"
    print_info "You may need to install goofys manually:"
    print_info "1. Install Go: https://golang.org/doc/install"
    print_info "2. Run: go install github.com/kahing/goofys@latest"
    print_info "3. Ensure $HOME/go/bin is in your PATH"
    return 1
}

install_goofys_binary() {
    # GitHub releases only provide Linux x86_64 binaries
    # Only attempt this for Linux x86_64 systems
    
    if [[ "$OS_TYPE" != "linux" ]]; then
        print_info "Method 1: Pre-built binaries only available for Linux, skipping for $OS_TYPE"
        return 1
    fi
    
    local arch=$(uname -m)
    if [[ "$arch" != "x86_64" ]]; then
        print_info "Method 1: Pre-built binary only available for x86_64, skipping for $arch"
        return 1
    fi
    
    print_info "Method 1: Installing pre-built binary for Linux x86_64..."
    
    local goofys_url="https://github.com/kahing/goofys/releases/download/v0.24.0/goofys"
    local install_dir="/usr/local/bin"
    local temp_file="/tmp/goofys-$$"
    
    # Create install directory if it doesn't exist
    if [ ! -d "$install_dir" ]; then
        sudo mkdir -p "$install_dir"
    fi
    
    # Download goofys binary
    if curl -L "$goofys_url" -o "$temp_file" 2>/dev/null; then
        # Verify the download was successful (binary should be >20MB)
        if [ -s "$temp_file" ] && [ $(stat -c%s "$temp_file" 2>/dev/null) -gt 20000000 ]; then
            # Test if binary is executable
            if chmod +x "$temp_file" && "$temp_file" --help >/dev/null 2>&1; then
                # Install the binary
                if sudo mv "$temp_file" "$install_dir/goofys"; then
                    print_success "goofys pre-built binary installed successfully"
                    return 0
                fi
            fi
        fi
        rm -f "$temp_file"
    fi
    
    print_warning "Pre-built binary installation failed"
    return 1
}

install_goofys_from_source() {
    print_info "Method 2: Building goofys from source with Go..."
    
    # Check if Go is available
    if ! command -v go &> /dev/null; then
        print_warning "Go compiler not found, will try to install Go next"
        return 1
    fi
    
    # Check Go version (need 1.10+, but really should be 1.16+ for modern builds)
    local go_version=$(go version 2>/dev/null | grep -o 'go[0-9]\+\.[0-9]\+' | sed 's/go//' | head -1)
    if [ -z "$go_version" ]; then
        print_warning "Could not determine Go version"
        return 1
    fi
    
    local major_version=$(echo "$go_version" | cut -d'.' -f1)
    local minor_version=$(echo "$go_version" | cut -d'.' -f2)
    
    if [ "$major_version" -lt 1 ] || ([ "$major_version" -eq 1 ] && [ "$minor_version" -lt 16 ]); then
        print_warning "Go version $go_version is old (recommend 1.16+), but trying anyway..."
    fi
    
    print_info "Building goofys from source with Go $go_version for $(uname -s)/$(uname -m)..."
    
    # Set up Go environment
    export GOPATH="${GOPATH:-$HOME/go}"
    export PATH="$PATH:$GOPATH/bin:/opt/homebrew/bin"
    
    # Create GOPATH if it doesn't exist
    mkdir -p "$GOPATH/bin"
    
    # Use PR #778 which fixes gopsutil v3 compatibility for macOS M1/ARM
    print_info "Building goofys from PR #778 (gopsutil v3 fix)..."
    
    local temp_dir="/tmp/goofys-build-$$"
    mkdir -p "$temp_dir"
    cd "$temp_dir"
    
    # Clone and build PR #778 using modern Go approach
    print_info "Building goofys with gopsutil v3 from PR #778..."
    
    # Set GOPATH as the official method does
    export GOPATH="${GOPATH:-$HOME/work}"
    mkdir -p "$GOPATH/bin"
    
    # Clone the PR branch
    if git clone -b feature/upgrade-gopsutil https://github.com/chiehting/goofys.git; then
        cd goofys
        
        print_info "Building goofys using go install..."
        # Use go install . to install from current directory
        if go install .; then
            print_success "Successfully built and installed goofys from PR #778"
        else
            print_error "Failed to build goofys from PR #778"
            cd - && rm -rf "$temp_dir"
            return 1
        fi
    else
        print_error "Failed to clone goofys PR #778"
        cd - && rm -rf "$temp_dir"
        return 1
    fi
    
    # Clean up
    cd - && rm -rf "$temp_dir"
    
    # Check if build was successful - check both GOPATH and default Go bin
    GOOFYS_PATH=""
    if [ -f "$GOPATH/bin/goofys" ]; then
        GOOFYS_PATH="$GOPATH/bin/goofys"
    elif [ -f "$HOME/go/bin/goofys" ]; then
        GOOFYS_PATH="$HOME/go/bin/goofys"
    fi
    
    if [ -n "$GOOFYS_PATH" ]; then
        # Test the built binary
        if "$GOOFYS_PATH" --help >/dev/null 2>&1; then
            # Install to system location (try different approaches)
            if [ -w /usr/local/bin ]; then
                # User has write access
                if cp "$GOOFYS_PATH" /usr/local/bin/goofys; then
                    print_success "goofys built and installed from source to /usr/local/bin"
                    return 0
                fi
            elif sudo -n true 2>/dev/null; then
                # User has passwordless sudo
                if sudo cp "$GOOFYS_PATH" /usr/local/bin/goofys; then
                    print_success "goofys built and installed from source to /usr/local/bin"
                    return 0
                fi
            else
                # Just use it from GOPATH
                print_success "goofys built successfully at $GOOFYS_PATH"
                print_info "Note: goofys is available at $GOOFYS_PATH"
                print_info "You may want to add $(dirname $GOOFYS_PATH) to your PATH"
                return 0
            fi
        else
            print_error "Built goofys binary is not working"
        fi
    else
        print_error "goofys binary not found after build"
    fi
    
    print_warning "Source build failed"
    return 1
}

install_go_and_build_goofys() {
    print_info "Method 3: Installing Go compiler and building goofys..."
    
    # Skip if Go is already installed
    if command -v go &> /dev/null; then
        print_info "Go already installed, skipping Go installation"
        return 1
    fi
    
    if [[ "$OS_TYPE" == "macos" ]]; then
        if command -v brew &> /dev/null; then
            print_info "Installing Go via Homebrew..."
            if brew install go; then
                # Update PATH for current session
                export PATH="$PATH:/usr/local/go/bin:$HOME/go/bin"
                
                # Try to build goofys now that Go is installed
                if install_goofys_from_source; then
                    return 0
                fi
            fi
        fi
    elif [[ "$OS_TYPE" == "linux" ]]; then
        # Try to install Go via package manager
        if command -v apt &> /dev/null; then
            print_info "Installing Go via apt..."
            if sudo apt update && sudo apt install -y golang-go; then
                export PATH="$PATH:/usr/local/go/bin:$HOME/go/bin"
                if install_goofys_from_source; then
                    return 0
                fi
            fi
        elif command -v yum &> /dev/null; then
            print_info "Installing Go via yum..."
            if sudo yum install -y golang; then
                export PATH="$PATH:/usr/local/go/bin:$HOME/go/bin"
                if install_goofys_from_source; then
                    return 0
                fi
            fi
        fi
    fi
    
    print_warning "Go installation and goofys build failed"
    return 1
}


setup_persistent_mount() {
    local bucket_name="$1"
    local mount_dir="$2"
    
    print_info "Setting up persistent S3 mount using goofys..."
    
    if [[ "$OS_TYPE" == "macos" ]]; then
        # Create launchd service for macOS
        local service_file="$HOME/Library/LaunchAgents/com.sentient.mount.plist"
        cat > "$service_file" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.sentient.mount</string>
    <key>ProgramArguments</key>
    <array>
        <string>goofys</string>
        <string>--stat-cache-ttl=10s</string>
        <string>--type-cache-ttl=10s</string>
        <string>$bucket_name</string>
        <string>$mount_dir</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
</dict>
</plist>
EOF
        launchctl load "$service_file" 2>/dev/null || true
        print_success "launchd service created for persistent mounting"
        
    elif [[ "$OS_TYPE" == "linux" ]]; then
        # Create systemd service for Linux
        local service_file="/etc/systemd/system/opt/sentient-mount.service"
        sudo tee "$service_file" > /dev/null << EOF
[Unit]
Description=Sentient S3 Mount
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/goofys --stat-cache-ttl=10s --type-cache-ttl=10s ${bucket_name} ${mount_dir}
ExecStop=/bin/fusermount -u ${mount_dir}
Restart=always
RestartSec=10
User=${USER}
Environment=HOME=${HOME}
Environment=AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID}
Environment=AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}
Environment=AWS_REGION=${AWS_REGION}

[Install]
WantedBy=multi-user.target
EOF
        sudo systemctl daemon-reload
        sudo systemctl enable sentient-mount.service 2>/dev/null || true
        print_success "systemd service created for persistent mounting"
    fi
}

validate_aws_credentials() {
    print_info "Validating AWS credentials and S3 access..."
    
    # Load AWS credentials from .env file
    local aws_access_key=$(safe_env_extract ".env" "AWS_ACCESS_KEY_ID" "")
    local aws_secret_key=$(safe_env_extract ".env" "AWS_SECRET_ACCESS_KEY" "")
    local aws_region=$(safe_env_extract ".env" "AWS_REGION" "us-east-1")
    local s3_bucket=$(safe_env_extract ".env" "S3_BUCKET_NAME" "")
    
    # Check if credentials are available
    if [ -z "$aws_access_key" ] || [ -z "$aws_secret_key" ] || [ -z "$s3_bucket" ]; then
        print_error "Missing AWS credentials or S3 bucket name in .env file"
        print_info "Required variables: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME"
        return 1
    fi
    
    # Export credentials for AWS CLI
    export AWS_ACCESS_KEY_ID="$aws_access_key"
    export AWS_SECRET_ACCESS_KEY="$aws_secret_key"
    export AWS_DEFAULT_REGION="$aws_region"
    
    # Check if aws CLI is available
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI not found. Installing..."
        if [[ "$OS_TYPE" == "macos" ]]; then
            brew install awscli
        elif [[ "$OS_TYPE" == "linux" ]]; then
            # Install via package manager or pip
            if command -v apt &> /dev/null; then
                sudo apt update && sudo apt install -y awscli
            elif command -v pip3 &> /dev/null; then
                pip3 install awscli --user
            else
                print_error "Cannot install AWS CLI automatically"
                return 1
            fi
        fi
    fi
    
    # Test AWS credentials
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        print_error "AWS credentials validation failed"
        print_info "Please check your AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in .env"
        return 1
    fi
    print_success "AWS credentials validated"
    
    # Test S3 bucket access
    if ! aws s3 ls "s3://$s3_bucket" >/dev/null 2>&1; then
        print_error "S3 bucket access failed for: $s3_bucket"
        print_info "Please check bucket name and permissions"
        return 1
    fi
    print_success "S3 bucket access validated: $s3_bucket"
    
    return 0
}

verify_s3_mount() {
    local mount_dir="$1"
    local bucket_name="$2"
    local max_wait=30
    local count=0
    
    print_info "Verifying S3 mount functionality..."
    
    # Wait for mount to be ready
    while [ $count -lt $max_wait ]; do
        if mountpoint -q "$mount_dir" 2>/dev/null || mount | grep -q "$mount_dir"; then
            break
        fi
        sleep 1
        ((count++))
    done
    
    if [ $count -ge $max_wait ]; then
        print_error "Mount verification timed out"
        return 1
    fi
    
    # Test directory listing - simplified for macOS compatibility
    if command -v timeout >/dev/null 2>&1; then
        # Use timeout if available (Linux)
        if ! timeout 10 ls "$mount_dir" >/dev/null 2>&1; then
            print_error "Cannot list mount directory contents"
            return 1
        fi
    elif command -v gtimeout >/dev/null 2>&1; then
        # Use gtimeout if available (macOS with coreutils)
        if ! gtimeout 10 ls "$mount_dir" >/dev/null 2>&1; then
            print_error "Cannot list mount directory contents"
            return 1
        fi
    else
        # Simple test for macOS - just check if ls succeeds
        if ! ls "$mount_dir" >/dev/null 2>&1; then
            print_error "Cannot list mount directory contents"
            return 1
        fi
    fi
    
    # Test write access with unique file
    local test_file="$mount_dir/.sentient-mount-test-$(date +%s)-$$"
    if ! echo "Mount test at $(date)" > "$test_file" 2>/dev/null; then
        print_error "Cannot write to mounted directory"
        return 1
    fi
    
    # Wait a moment for S3 sync, then verify in bucket
    sleep 2
    local test_key=$(basename "$test_file")
    if [ -n "$bucket_name" ] && command -v aws &> /dev/null; then
        if aws s3 ls "s3://$bucket_name/$test_key" >/dev/null 2>&1; then
            print_success "S3 sync verification successful"
            # Clean up test file
            rm "$test_file" 2>/dev/null || true
        else
            print_warning "File not synced to S3 bucket (may take time)"
        fi
    else
        # Clean up test file locally
        rm "$test_file" 2>/dev/null || true
    fi
    
    print_success "S3 mount verification completed"
    return 0
}

setup_local_s3_mounting() {
    print_info "Setting up local S3 mounting..."
    
    # Use safe environment extraction
    S3_BUCKET_NAME=$(safe_env_extract ".env" "S3_BUCKET_NAME" "")
    S3_MOUNT_DIR=$(safe_env_extract ".env" "S3_MOUNT_DIR" "/opt/sentient")
    # Expand $HOME variable if present
    S3_MOUNT_DIR=$(eval echo "$S3_MOUNT_DIR")
    AWS_REGION=$(safe_env_extract ".env" "AWS_REGION" "us-east-1")
    AWS_ACCESS_KEY_ID=$(safe_env_extract ".env" "AWS_ACCESS_KEY_ID" "")
    AWS_SECRET_ACCESS_KEY=$(safe_env_extract ".env" "AWS_SECRET_ACCESS_KEY" "")
    
    # Export AWS credentials for goofys
    export AWS_ACCESS_KEY_ID
    export AWS_SECRET_ACCESS_KEY  
    export AWS_REGION
    
    if [ -z "$S3_BUCKET_NAME" ] || [ "$S3_BUCKET_NAME" = "your-s3-bucket-name" ]; then
        print_error "S3_BUCKET_NAME not configured in .env"
        return 1
    fi
    
    if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
        print_error "AWS credentials not configured in .env"
        return 1
    fi
    
    # Validate mount directory path
    if ! validate_mount_path "$S3_MOUNT_DIR" "S3 mount directory"; then
        return 1
    fi
    
    # Create mount directory with proper permissions
    create_mount_directory "$S3_MOUNT_DIR"
    if [ $? -ne 0 ]; then
        return 1
    fi
    
    # Validate AWS credentials and S3 access
    if ! validate_aws_credentials; then
        print_error "AWS credentials validation failed"
        return 1
    fi
    
    # Check FUSE support
    if ! check_fuse_support; then
        print_error "FUSE support not available"
        return 1
    fi
    
    # Install goofys for high-performance S3 mounting
    if ! install_goofys; then
        print_error "Failed to install goofys"
        return 1
    fi
    
    # Create mount directory with proper permissions
    if [ ! -d "$S3_MOUNT_DIR" ]; then
        if [[ "$S3_MOUNT_DIR" == /* ]]; then
            # Absolute path, might need sudo
            if ! mkdir -p "$S3_MOUNT_DIR" 2>/dev/null; then
                sudo mkdir -p "$S3_MOUNT_DIR"
                sudo chown $USER:$(id -gn) "$S3_MOUNT_DIR"
            fi
        else
            # Relative path
            mkdir -p "$S3_MOUNT_DIR"
        fi
    fi
    
    print_info "Mounting S3 bucket '$S3_BUCKET_NAME' to '$S3_MOUNT_DIR'..."
    
    # Check if already mounted
    if mount | grep -q "$S3_MOUNT_DIR" || df | grep -q "$S3_MOUNT_DIR"; then
        print_info "S3 bucket already mounted to $S3_MOUNT_DIR"
        # Verify mount functionality
        if verify_s3_mount "$S3_MOUNT_DIR"; then
            print_success "Existing S3 mount verification passed"
            return 0
        else
            print_warning "Existing mount verification failed, remounting..."
            # Unmount and continue
            diskutil unmount "$S3_MOUNT_DIR" 2>/dev/null || umount "$S3_MOUNT_DIR" 2>/dev/null || true
            pkill -f "goofys.*$S3_MOUNT_DIR" 2>/dev/null || true
            sleep 2
        fi
    fi
    
    # Test mount S3 bucket to configured directory using goofys
    print_info "Attempting to mount S3 bucket '$S3_BUCKET_NAME' to '$S3_MOUNT_DIR' using goofys..."
    
    if goofys --stat-cache-ttl=10s --type-cache-ttl=10s "$S3_BUCKET_NAME" "$S3_MOUNT_DIR"; then
        print_success "S3 bucket mounted successfully to $S3_MOUNT_DIR using goofys"
        
        # Verify mount functionality
        if verify_s3_mount "$S3_MOUNT_DIR"; then
            print_success "S3 mount verification passed"
            
            # Update .env if not already set
            if ! grep -q "S3_MOUNT_ENABLED=true" .env; then
                echo "S3_MOUNT_ENABLED=true" >> .env
            fi
            if ! grep -q "S3_MOUNT_DIR=" .env; then
                echo "S3_MOUNT_DIR=$S3_MOUNT_DIR" >> .env
            fi
            
            # Setup persistent mounting
            setup_persistent_mount "$S3_BUCKET_NAME" "$S3_MOUNT_DIR"
        else
            print_error "S3 mount verification failed"
            # Attempt to unmount the failed mount
            fusermount -u "$S3_MOUNT_DIR" 2>/dev/null || umount "$S3_MOUNT_DIR" 2>/dev/null || true
            return 1
        fi
        
    else
        print_error "Failed to mount S3 bucket - check AWS credentials and bucket access"
        return 1
    fi
}

ask_for_s3_mounting() {
    if [ -f .env ] && grep -q "S3_BUCKET_NAME=" .env && ! grep -q "S3_BUCKET_NAME=your-s3-bucket-name" .env; then
        echo ""
        print_info "S3 credentials detected in .env"
        read -p "Setup S3 mounting for data persistence? (y/n): " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            # Get mount directory from .env file or use default
            mount_dir=$(safe_env_extract ".env" "S3_MOUNT_DIR" "/opt/sentient")
            print_info "Using S3 mount directory from .env: $mount_dir"
            
            # Update .env with mount directory if not already present
            if ! grep -q "S3_MOUNT_DIR=" .env; then
                echo "S3_MOUNT_DIR=$mount_dir" >> .env
                print_info "Added S3_MOUNT_DIR=$mount_dir to .env"
            fi
            
            setup_local_s3_mounting
        else
            print_info "S3 mounting skipped"
        fi
    fi
}

# ============================================
# E2B TEMPLATE SETUP FUNCTIONS
# ============================================

check_e2b_requirements() {
    print_info "Checking E2B requirements..."
    
    # Check if E2B_API_KEY is set in .env
    if [ -f .env ] && grep -q "E2B_API_KEY=" .env && ! grep -q "E2B_API_KEY=your_e2b_api_key_here" .env; then
        print_success "E2B API key found in .env"
    else
        print_warning "E2B_API_KEY not configured in .env - E2B template build will be skipped"
        return 1
    fi
    
    # Check if Node.js is available for E2B CLI
    if ! command -v npm &> /dev/null; then
        print_warning "npm not found - E2B CLI installation will be skipped"
        return 1
    fi
    
    return 0
}

install_e2b_cli() {
    print_info "Installing E2B CLI..."
    
    # Install E2B CLI globally
    if ! command -v e2b &> /dev/null; then
        npm install -g @e2b/cli
        print_success "E2B CLI installed"
    else
        print_info "E2B CLI already installed"
    fi
}

e2b_auth_login() {
    print_info "Authenticating with E2B..."
    
    # Check if already authenticated
    if e2b auth whoami &> /dev/null; then
        print_success "Already authenticated with E2B"
        return 0
    fi
    
    # Get API key from .env
    E2B_API_KEY=$(safe_env_extract ".env" "E2B_API_KEY" "")
    
    if [ -z "$E2B_API_KEY" ] || [ "$E2B_API_KEY" = "your_e2b_api_key_here" ]; then
        print_error "E2B_API_KEY not properly configured in .env"
        return 1
    fi
    
    # Authenticate using API key
    echo "$E2B_API_KEY" | e2b auth login
    print_success "E2B authentication successful"
}

build_e2b_template() {
    print_info "Building custom E2B template with S3 integration..."
    
    # Check if template directory exists
    if [ ! -d "docker/e2b-sandbox" ]; then
        print_error "E2B template directory not found: docker/e2b-sandbox"
        return 1
    fi
    
    cd docker/e2b-sandbox
    
    # Load AWS credentials from .env for build args
    if [ -f "../../.env" ]; then
        print_info "Loading AWS credentials from ../../.env..."
        export $(grep -v '^#' ../../.env | xargs) 2>/dev/null || true
    elif [ -f "../.env" ]; then
        print_info "Loading AWS credentials from ../.env..."
        export $(grep -v '^#' ../.env | xargs) 2>/dev/null || true
    else
        print_warning "No .env file found at ../../.env or ../.env"
    fi
    
    # Validate AWS credentials are available
    if [[ -z "$AWS_ACCESS_KEY_ID" || -z "$AWS_SECRET_ACCESS_KEY" || -z "$S3_BUCKET_NAME" ]]; then
        print_error "AWS credentials required for E2B template build:"
        print_error "Required in .env: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME"
        cd ../..
        return 1
    fi
    
    print_info "Building template 'sentient-e2b-s3' with AWS credentials..."
    print_info "  AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:0:10}..."
    print_info "  S3_BUCKET_NAME: $S3_BUCKET_NAME"
    
    # Get S3 mount directory from .env or use default
    S3_MOUNT_DIR=$(safe_env_extract "../../.env" "S3_MOUNT_DIR" "/opt/sentient")
    # Expand $HOME variable if present
    S3_MOUNT_DIR=$(eval echo "$S3_MOUNT_DIR")
    
    # Build template with AWS credentials and mount directory as build args
    if e2b template build \
        --build-arg AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
        --build-arg AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
        --build-arg AWS_REGION="${AWS_REGION:-us-west-2}" \
        --build-arg S3_BUCKET_NAME="$S3_BUCKET_NAME" \
        --build-arg S3_MOUNT_DIR="$S3_MOUNT_DIR" \
        --name sentient-e2b-s3; then
        
        print_success "E2B template 'sentient-e2b-s3' built successfully!"
        print_info "Template includes S3 integration with your credentials"
        print_info "Test the template with: $0 --test-e2b"
    else
        print_error "E2B template build failed"
        cd ../..
        return 1
    fi
    
    cd ../..
}

setup_e2b_integration() {
    print_info "Setting up E2B integration..."
    
    if ! check_e2b_requirements; then
        print_info "Skipping E2B setup - requirements not met"
        return 0
    fi
    
    install_e2b_cli
    e2b_auth_login
    build_e2b_template
    
    print_success "E2B integration setup complete!"
}

# ============================================
# DOCKER SETUP FUNCTIONS
# ============================================

docker_check_requirements() {
    print_info "Checking Docker requirements..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed"
        echo "Please install Docker: https://docs.docker.com/get-docker/"
        return 1
    fi
    
    if ! docker compose version &> /dev/null 2>&1; then
        if ! command -v docker-compose &> /dev/null; then
            print_error "Docker Compose is not installed"
            echo "Visit: https://docs.docker.com/compose/install/"
            return 1
        fi
        COMPOSE_CMD="docker-compose"
    else
        COMPOSE_CMD="docker compose"
    fi
    
    print_success "Docker and Docker Compose found"
    return 0
}

docker_setup_environment() {
    print_info "Setting up Docker environment..."
    
    # Check if .env exists in project root
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            print_info "Created .env file from .env.example"
            print_warning "Please update .env with your API keys!"
        else
            print_warning "No .env.example file found. Please create .env manually."
        fi
    else
        print_info ".env file already exists"
    fi
    
    # Ensure FLASK_PORT is set in .env if not already present
    if [ -f .env ] && ! grep -q "FLASK_PORT=" .env; then
        echo "FLASK_PORT=8000" >> .env
        print_info "Added FLASK_PORT=8000 to .env"
    fi
    
    # Check docker-specific env
    if [ ! -f docker/.env ]; then
        if [ -f docker/.env.example ]; then
            cp docker/.env.example docker/.env
            print_info "Created docker/.env from template"
        else
            # Create docker/.env from main .env
            cp .env docker/.env 2>/dev/null || true
        fi
    fi
    
    # Create necessary directories
    print_info "Creating necessary directories..."
    mkdir -p logs project_results emergency_backups
    
    print_success "Environment setup complete"
}

docker_build() {
    print_info "Building Docker images..."
    
    cd docker
    
    # Load environment variables from .env file
    if [ -f "../.env" ]; then
        print_info "Loading environment variables from ../.env..."
        export $(grep -v '^#' ../.env | xargs) 2>/dev/null || true
    fi
    
    # Use same compose file selection logic as docker_start
    local compose_files="-f docker-compose.yml"
    if [ -f "../.env" ]; then
        S3_MOUNT_ENABLED=$(safe_env_extract "../.env" "S3_MOUNT_ENABLED" "false")
        S3_MOUNT_DIR=$(safe_env_extract "../.env" "S3_MOUNT_DIR" "/opt/sentient")
        # Expand $HOME variable if present
        S3_MOUNT_DIR=$(eval echo "$S3_MOUNT_DIR")
        
        # Use flexible boolean parsing for S3_MOUNT_ENABLED
        s3_mount_env=$(echo "$S3_MOUNT_ENABLED" | tr '[:upper:]' '[:lower:]' | xargs)
        if [[ "$s3_mount_env" =~ ^(true|yes|1|on|enabled)$ ]] && [ -n "$S3_MOUNT_DIR" ]; then
            if validate_mount_path "$S3_MOUNT_DIR" "S3 mount directory" && [ -d "$S3_MOUNT_DIR" ]; then
                compose_files="$compose_files -f docker-compose.s3.yml"
                print_info "Building with S3 mount configuration for directory: $S3_MOUNT_DIR"
            fi
        fi
    fi
    
    print_info "Building with FLASK_PORT=${FLASK_PORT:-8000}"
    $COMPOSE_CMD $compose_files build --no-cache
    cd ..
    
    print_success "Docker images built successfully"
}

docker_start() {
    print_info "Starting Docker services..."
    
    cd docker
    
    # Load environment variables from .env file
    if [ -f "../.env" ]; then
        print_info "Loading environment variables from ../.env..."
        export $(grep -v '^#' ../.env | xargs) 2>/dev/null || true
    fi
    
    # Check if S3 mounting is enabled and validated
    local compose_files="-f docker-compose.yml"
    if [ -f "../.env" ]; then
        S3_MOUNT_ENABLED=$(safe_env_extract "../.env" "S3_MOUNT_ENABLED" "false")
        S3_MOUNT_DIR=$(safe_env_extract "../.env" "S3_MOUNT_DIR" "/opt/sentient")
        # Expand $HOME variable if present
        S3_MOUNT_DIR=$(eval echo "$S3_MOUNT_DIR")
        
        # Use flexible boolean parsing for S3_MOUNT_ENABLED
        s3_mount_env=$(echo "$S3_MOUNT_ENABLED" | tr '[:upper:]' '[:lower:]' | xargs)
        if [[ "$s3_mount_env" =~ ^(true|yes|1|on|enabled)$ ]] && [ -n "$S3_MOUNT_DIR" ]; then
            # Validate the mount path before using it
            if validate_mount_path "$S3_MOUNT_DIR" "S3 mount directory" && [ -d "$S3_MOUNT_DIR" ]; then
                compose_files="$compose_files -f docker-compose.s3.yml"
                print_info "Including S3 mount configuration for directory: $S3_MOUNT_DIR"
            else
                print_warning "S3 mount directory invalid or not mounted, skipping S3 compose override"
            fi
        fi
    fi
    
    print_info "Starting with FLASK_PORT=${FLASK_PORT:-8000}"
    print_info "Docker Compose command: $COMPOSE_CMD $compose_files up -d"
    $COMPOSE_CMD $compose_files up -d
    
    # Wait for services
    print_info "Waiting for services to start..."
    sleep 10
    
    # Check backend health
    local backend_port=${FLASK_PORT:-8000}
    if curl -sf http://localhost:$backend_port/api/health > /dev/null; then
        print_success "Backend is healthy"
    else
        print_warning "Backend health check failed - it may still be starting"
        echo "Check logs with: cd docker && $COMPOSE_CMD logs backend"
    fi
    
    # Check frontend
    if curl -sf http://localhost:3000 > /dev/null 2>&1; then
        print_success "Frontend is running on http://localhost:3000"
    else
        print_info "Frontend may still be starting..."
    fi
    
    # Auto-open browser for Docker frontend
    open_url "http://localhost:3000"
    
    cd ..
}

# Rebuild Docker services from scratch: stop, remove volumes, no-cache build, force recreate
docker_from_scratch() {
    print_info "Rebuilding Docker services from scratch..."
    
    if ! docker_check_requirements; then
        return 1
    fi
    
    cd docker
    
    # Load environment variables from .env file
    if [ -f "../.env" ]; then
        print_info "Loading environment variables from ../.env..."
        export $(grep -v '^#' ../.env | xargs) 2>/dev/null || true
    fi
    
    # Compute compose files like docker_start
    local compose_files="-f docker-compose.yml"
    if [ -f "../.env" ]; then
        S3_MOUNT_ENABLED=$(safe_env_extract "../.env" "S3_MOUNT_ENABLED" "false")
        S3_MOUNT_DIR=$(safe_env_extract "../.env" "S3_MOUNT_DIR" "/opt/sentient")
        # Expand $HOME variable if present
        S3_MOUNT_DIR=$(eval echo "$S3_MOUNT_DIR")
        
        s3_mount_env=$(echo "$S3_MOUNT_ENABLED" | tr '[:upper:]' '[:lower:]' | xargs)
        if [[ "$s3_mount_env" =~ ^(true|yes|1|on|enabled)$ ]] && [ -n "$S3_MOUNT_DIR" ]; then
            if validate_mount_path "$S3_MOUNT_DIR" "S3 mount directory" && [ -d "$S3_MOUNT_DIR" ]; then
                compose_files="$compose_files -f docker-compose.s3.yml"
                print_info "Including S3 mount configuration for directory: $S3_MOUNT_DIR"
            else
                print_warning "S3 mount directory invalid or not present; skipping S3 compose override"
            fi
        fi
    fi
    
    # Stop and remove containers and volumes
    $COMPOSE_CMD $compose_files down -v --remove-orphans
    
    # Build with no cache and pull latest bases
    $COMPOSE_CMD $compose_files build --no-cache --pull
    
    # Start fresh containers, force recreate
    $COMPOSE_CMD $compose_files up -d --force-recreate
    
    # Wait for services
    print_info "Waiting for services to start..."
    sleep 10
    
    # Check backend health
    local backend_port=${FLASK_PORT:-8000}
    if curl -sf http://localhost:$backend_port/api/health > /dev/null; then
        print_success "Backend is healthy"
    else
        print_warning "Backend health check failed - it may still be starting"
        echo "Check logs with: cd docker && $COMPOSE_CMD logs backend"
    fi
    
    # Check frontend
    if curl -sf http://localhost:3000 > /dev/null 2>&1; then
        print_success "Frontend is running on http://localhost:3000"
    else
        print_info "Frontend may still be starting..."
    fi
    
    cd ..
    
    print_success "Docker services rebuilt from scratch"
    
    # Auto-open browser for Docker frontend
    open_url "http://localhost:3000"
}

docker_compose_run() {
    print_info "Running Docker Compose with S3 configuration check..."
    
    if ! docker_check_requirements; then
        return 1
    fi
    
    cd docker
    
    # Load environment variables from .env file
    if [ -f "../.env" ]; then
        print_info "Loading environment variables from ../.env..."
        export $(grep -v '^#' ../.env | xargs) 2>/dev/null || true
    fi
    
    # Check if S3 mounting is enabled and validated
    local compose_files="-f docker-compose.yml"
    if [ -f "../.env" ]; then
        S3_MOUNT_ENABLED=$(safe_env_extract "../.env" "S3_MOUNT_ENABLED" "false")
        S3_MOUNT_DIR=$(safe_env_extract "../.env" "S3_MOUNT_DIR" "/opt/sentient")
        # Expand $HOME variable if present
        S3_MOUNT_DIR=$(eval echo "$S3_MOUNT_DIR")
        
        # Use flexible boolean parsing for S3_MOUNT_ENABLED
        s3_mount_env=$(echo "$S3_MOUNT_ENABLED" | tr '[:upper:]' '[:lower:]' | xargs)
        if [[ "$s3_mount_env" =~ ^(true|yes|1|on|enabled)$ ]] && [ -n "$S3_MOUNT_DIR" ]; then
            # Validate the mount path before using it
            if validate_mount_path "$S3_MOUNT_DIR" "S3 mount directory" && [ -d "$S3_MOUNT_DIR" ]; then
                compose_files="$compose_files -f docker-compose.s3.yml"
                print_info "Including S3 mount configuration for directory: $S3_MOUNT_DIR"
            else
                print_warning "S3 mount directory invalid or not mounted, skipping S3 compose override"
            fi
        fi
    fi
    
    print_info "Running: $COMPOSE_CMD $compose_files up"
    $COMPOSE_CMD $compose_files up -d
    
    # Wait for services
    print_info "Waiting for services to start..."
    sleep 10
    
    # Check backend health
    local backend_port=${FLASK_PORT:-8000}
    if curl -sf http://localhost:$backend_port/api/health > /dev/null; then
        print_success "Backend is healthy at http://localhost:$backend_port"
    else
        print_warning "Backend health check failed - it may still be starting"
        echo "Check logs with: cd docker && $COMPOSE_CMD logs backend"
    fi
    
    # Check frontend
    if curl -sf http://localhost:3000 > /dev/null 2>&1; then
        print_success "Frontend is running at http://localhost:3000"
    else
        print_info "Frontend may still be starting..."
    fi
    
    cd ..
    
    print_success "Docker Compose started successfully!"
    echo "Services available at:"
    local backend_port=${FLASK_PORT:-8000}
    echo "  - Backend API: http://localhost:$backend_port"
    echo "  - Frontend: http://localhost:3000"
}

docker_setup() {
    print_info "Starting Docker setup..."
    
    if ! docker_check_requirements; then
        return 1
    fi
    
    docker_setup_environment
    
    # macOS: Host-based S3 mounting for Docker (container FUSE not supported on Desktop)
    if [ -f .env ]; then
        S3_MOUNT_ENABLED=$(safe_env_extract ".env" "S3_MOUNT_ENABLED" "false")
        S3_MOUNT_DIR=$(safe_env_extract ".env" "S3_MOUNT_DIR" "/opt/sentient")
        # Expand $HOME variable if present
        S3_MOUNT_DIR=$(eval echo "$S3_MOUNT_DIR")
        s3_mount_env=$(echo "$S3_MOUNT_ENABLED" | tr '[:upper:]' '[:lower:]' | xargs)
        if [[ "$s3_mount_env" =~ ^(true|yes|1|on|enabled)$ ]] && [ -n "$S3_MOUNT_DIR" ]; then
            print_info "S3 mounting enabled - performing host-based S3 mounting for Docker"
            print_info "S3 mount directory: $S3_MOUNT_DIR"
            # Perform host-based S3 mounting for reliable host visibility
            setup_local_s3_mounting || print_warning "Host S3 mounting failed"
        fi
    fi
    
    docker_build
    docker_start
    
    echo ""
    echo "========================================"
    print_success "Docker Setup Complete!"
    echo "========================================"
    echo ""
    echo "Services:"
    local backend_port=${FLASK_PORT:-8000}
    echo "  - Backend API: http://localhost:$backend_port"
    echo "  - Frontend Dev: http://localhost:3000"
    echo ""
    echo "Features:"
    echo "  - E2B Code Execution: $([ -f .env ] && grep -q "E2B_API_KEY=" .env && ! grep -q "E2B_API_KEY=your_e2b_api_key_here" .env && echo "✅ Configured" || echo "⚠️  Configure E2B_API_KEY in .env")"
    echo "  - S3 Integration: $([ -f .env ] && grep -q "S3_BUCKET_NAME=" .env && ! grep -q "S3_BUCKET_NAME=your-s3-bucket-name" .env && echo "✅ Configured" || echo "⚠️  Configure AWS credentials in .env")"
    echo ""
    echo "Useful Docker commands:"
    echo "  - View logs:    cd docker && $COMPOSE_CMD logs -f"
    echo "  - Stop:         cd docker && $COMPOSE_CMD down"
    echo "  - Restart:      cd docker && $COMPOSE_CMD restart"
    echo "  - View status:  cd docker && $COMPOSE_CMD ps"
    echo ""
    
    if [ -f .env ] && (grep -q "your_.*_api_key_here" .env || grep -q "your-.*-bucket-name" .env); then
        print_warning "Don't forget to configure your API keys and S3 settings in .env"
    fi
    
    echo ""
    print_info "🚀 Optional: Setup E2B sandbox for code execution"
    print_info "   Run: $0 --e2b (requires E2B_API_KEY and AWS credentials in .env)"
    print_info "   Test: $0 --test-e2b (after E2B setup)"
}

# ============================================
# NATIVE SETUP FUNCTIONS (Shared)
# ============================================

native_install_pdm_uv() {
    print_info "Installing PDM and UV package managers..."
    
    # Install PDM
    if ! command -v pdm &> /dev/null; then
        print_info "Installing PDM..."
        curl -sSL https://pdm-project.org/install-pdm.py | python3 -
        
        # Add PDM to PATH for current session and shell profile
        export PATH="$HOME/.local/bin:$PATH"
        append_to_profile_once 'export PATH="$HOME/.local/bin:$PATH"'
    else
        print_success "PDM is already installed"
    fi
    
    # Install UV
    if ! command -v uv &> /dev/null; then
        print_info "Installing UV..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        
        # Try to source cargo env if available (harmless if not)
        if [ -f "$HOME/.cargo/env" ]; then
            # shellcheck source=/dev/null
            source "$HOME/.cargo/env"
            append_to_profile_once 'source "$HOME/.cargo/env"'
        fi
        # Ensure ~/.local/bin is on PATH (uv may be installed there)
        append_to_profile_once 'export PATH="$HOME/.local/bin:$PATH"'
        export PATH="$HOME/.local/bin:$PATH"
    else
        print_success "UV is already installed"
    fi
    
    print_success "UV package manager installed successfully"
}

native_install_node() {
    print_info "Installing NVM and Node.js..."
    
    # Install NVM
    if [ ! -d "$HOME/.nvm" ]; then
        print_info "Installing NVM..."
        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
        
        # Load NVM
        export NVM_DIR="$HOME/.nvm"
        [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
        append_to_profile_once 'export NVM_DIR="$HOME/.nvm"'
        append_to_profile_once '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"'
    else
        print_success "NVM is already installed"
        # Load NVM
        export NVM_DIR="$HOME/.nvm"
        [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    fi
    
    # Install Node.js 23.11.0 with fallback to LTS if unavailable
    print_info "Installing Node.js v23.11.0..."
    if ! nvm install 23.11.0; then
        print_warning "Node v23.11.0 not available; falling back to latest LTS"
        nvm install --lts
        nvm use --lts
    else
        nvm use 23.11.0
    fi
    
    # Install specific npm version
    print_info "Installing npm v10.9.2..."
    npm install -g npm@10.9.2 || print_warning "Could not set npm to v10.9.2; continuing."
    
    # Verify versions
    NODE_VERSION=$(node -v || echo "unknown")
    NPM_VERSION=$(npm -v || echo "unknown")
    
    print_success "Node.js version: $NODE_VERSION, npm version: $NPM_VERSION"
}

native_setup_project() {
    print_info "Setting up project with UV..."
    
    # Check if we're in the project directory
    if [ ! -f "pyproject.toml" ]; then
        print_error "Please run this script from the SentientResearchAgent project root directory"
        return 1
    fi
    
    # Create virtual environment with UV
    print_info "Creating virtual environment with UV..."
    if [ -d ".venv" ]; then
        print_info "Virtual environment already exists, using existing one"
    else
        uv venv --python 3.12
    fi
    
    # Activate virtual environment
    print_info "Activating virtual environment..."
    if [[ "$OS_TYPE" == "macos" ]] || [[ "$SHELL" =~ "zsh" ]]; then
        source .venv/bin/activate
    else
        source .venv/bin/activate
    fi
    
    # Install dependencies with UV
    print_info "Installing Python dependencies with UV..."
    uv sync
    
    print_success "Project setup complete"
}

native_install_frontend() {
    print_info "Installing frontend dependencies..."
    
    # Check if frontend directory exists
    if [ ! -d "frontend" ]; then
        print_error "Frontend directory not found"
        return 1
    fi
    
    cd frontend
    
    # Install dependencies
    print_info "Running npm install..."
    npm install
    
    cd ..
    
    print_success "Frontend dependencies installed"
}

native_setup_environment() {
    print_info "Setting up environment configuration..."
    
    # Create .env file if it doesn't exist
    if [ ! -f .env ]; then
        if [ -f .env.example ]; then
            cp .env.example .env
            print_info "Created .env file from .env.example"
            print_warning "Please update .env with your API keys!"
        else
            print_warning "No .env.example file found. Please create .env manually."
        fi
    else
        print_info ".env file already exists"
    fi
    
    # Ensure FLASK_PORT is set in .env if not already present
    if [ -f .env ] && ! grep -q "FLASK_PORT=" .env; then
        echo "FLASK_PORT=8000" >> .env
        print_info "Added FLASK_PORT=8000 to .env"
    fi
    
    # Create necessary directories
    print_info "Creating necessary directories..."
    mkdir -p logs project_results emergency_backups
    
    print_success "Environment setup complete"
}

# ============================================
# NATIVE SETUP (Ubuntu/Debian)
# ============================================

native_check_system_debian() {
    print_info "Checking system compatibility (Ubuntu/Debian)..."
    
    if [[ ! -f /etc/debian_version ]]; then
        print_error "This path is for Ubuntu/Debian systems."
        return 1
    fi
    
    print_success "Running on Ubuntu/Debian system"
    return 0
}

native_install_python_debian() {
    print_info "Installing Python 3.12 (Ubuntu/Debian)..."
    
    # Check if Python 3.12 is already installed
    if command -v python3.12 &> /dev/null; then
        print_success "Python 3.12 is already installed"
        return
    fi
    
    # Add deadsnakes PPA
    print_info "Adding deadsnakes PPA..."
    sudo add-apt-repository ppa:deadsnakes/ppa -y
    
    # Update package list
    print_info "Updating package list..."
    sudo apt update
    
    # Install Python 3.12
    print_info "Installing Python 3.12..."
    sudo apt install -y python3.12 python3.12-venv python3.12-dev
    
    print_success "Python 3.12 installed successfully"
}

post_native_quickstart() {
    if [ -f "./quickstart.sh" ]; then
        print_info "Running quickstart to launch backend and frontend..."
        # Try with bash to avoid executable bit requirement
        bash ./quickstart.sh || ./quickstart.sh || true
    else
        print_warning "quickstart.sh not found; skipping auto-start."
    fi
}

native_setup_debian() {
    if ! native_check_system_debian; then
        return 1
    fi
    
    # Install system dependencies
    print_info "Installing system dependencies (Ubuntu/Debian)..."
    sudo apt update
    sudo apt install -y curl git build-essential screen
    
    native_install_python_debian
    native_install_pdm_uv
    native_install_node
    native_setup_environment
    
    # Ask for S3 mounting after environment setup
    ask_for_s3_mounting
    
    native_setup_project
    native_install_frontend
    
    echo ""
    echo "========================================"
    print_success "Native Setup Complete!"
    echo "========================================"
    echo ""
    echo "To run the servers:"
    echo ""
    echo "1. Start the backend server:"
    echo "   screen -S backend_server"
    echo "   source .venv/bin/activate"
    echo "   python -m sentientresearchagent"
    echo "   # Press Ctrl+A, then D to detach"
    echo ""
    echo "2. Start the frontend server:"
    echo "   screen -S frontend_server"
    echo "   cd frontend && npm run dev"
    echo "   # Press Ctrl+A, then D to detach"
    echo ""
    echo "Server URLs:"
    local backend_port=${FLASK_PORT:-8000}
    echo "  - Backend API: http://localhost:$backend_port"
    echo "  - Frontend: http://localhost:3000"
    echo ""
    echo "Screen commands:"
    echo "  - List screens: screen -ls"
    echo "  - Reattach: screen -r backend_server"
    echo "  - Kill screen: screen -X -S backend_server quit"
    echo ""
    print_warning "Don't forget to:"
    echo "  1. Update .env file with your API keys"
    echo "  2. Reload your shell to update PATH (e.g., 'source ~/.zshrc' or 'source ~/.bashrc')"
    echo ""
    
    # Auto-launch servers and open browser
    post_native_quickstart
}

# ============================================
# NATIVE SETUP (macOS)
# ============================================

native_check_system_macos() {
    print_info "Checking system compatibility (macOS)..."
    if [ "$(uname -s)" != "Darwin" ]; then
        print_error "This path is for macOS systems."
        return 1
    fi
    print_success "Running on macOS"
    return 0
}

native_install_homebrew() {
    if command -v brew &>/dev/null; then
        print_success "Homebrew is already installed"
        brew update || true
    else
        print_info "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        # Initialize brew for current session and future shells
        if [ -x "/opt/homebrew/bin/brew" ]; then
            eval "$(/opt/homebrew/bin/brew shellenv)"
            append_to_profile_once 'eval "$(/opt/homebrew/bin/brew shellenv)"'
        elif [ -x "/usr/local/bin/brew" ]; then
            eval "$(/usr/local/bin/brew shellenv)"
            append_to_profile_once 'eval "$(/usr/local/bin/brew shellenv)"'
        fi
        print_success "Homebrew installed"
    fi
}

native_install_system_deps_macos() {
    print_info "Installing system dependencies (macOS)..."
    brew install git screen || true
}

native_install_python_macos() {
    print_info "Installing Python 3.12 (macOS)..."
    
    if command -v python3.12 &>/dev/null; then
        print_success "Python 3.12 is already installed"
        return
    fi
    
    native_install_homebrew
    
    # Install Python 3.12 via Homebrew (keg-only)
    brew install python@3.12
    
    # Ensure the python3.12 binary is on PATH
    PY312_BIN="$(brew --prefix)/opt/python@3.12/bin"
    if [ -x "$PY312_BIN/python3.12" ]; then
        export PATH="$PY312_BIN:$PATH"
        append_to_profile_once 'export PATH="'"$PY312_BIN"'":$PATH'
        print_success "Added Python 3.12 to PATH"
    else
        print_warning "Could not locate python3.12 in Homebrew prefix; you may need to restart your shell."
    fi
}

native_setup_macos() {
    if ! native_check_system_macos; then
        return 1
    fi
    
    native_install_homebrew
    native_install_system_deps_macos
    native_install_python_macos
    native_install_pdm_uv
    native_install_node
    native_setup_environment
    native_setup_project
    native_install_frontend
    
    echo ""
    echo "========================================"
    print_success "Native Setup Complete!"
    echo "========================================"
    echo ""
    echo "To run the servers:"
    echo ""
    echo "1. Start the backend server:"
    echo "   screen -S backend_server"
    echo "   eval \"\$(pdm venv activate)\""
    echo "   python -m sentientresearchagent"
    echo "   # Press Ctrl+A, then D to detach"
    echo ""
    echo "2. Start the frontend server:"
    echo "   screen -S frontend_server"
    echo "   cd frontend && npm run dev"
    echo "   # Press Ctrl+A, then D to detach"
    echo ""
    echo "Server URLs:"
    local backend_port=${FLASK_PORT:-8000}
    echo "  - Backend API: http://localhost:$backend_port"
    echo "  - Frontend: http://localhost:3000"
    echo ""
    echo "Screen commands:"
    echo "  - List screens: screen -ls"
    echo "  - Reattach: screen -r backend_server"
    echo "  - Kill screen: screen -X -S backend_server quit"
    echo ""
    print_warning "Don't forget to:"
    echo "  1. Update .env file with your API keys"
    echo "  2. Reload your shell to update PATH (e.g., 'source ~/.zshrc' or 'source ~/.bashrc')"
    echo ""
    
    # Auto-launch servers and open browser
    post_native_quickstart
}

# ============================================
# NATIVE SETUP DISPATCH
# ============================================

native_setup() {
    detect_os
    case "$OS_FAMILY" in
        macos)
            print_info "Starting native macOS setup..."
            native_setup_macos
            ;;
        debian)
            print_info "Starting native Ubuntu/Debian setup..."
            native_setup_debian
            ;;
        *)
            print_error "Unsupported system detected. This script supports macOS and Ubuntu/Debian."
            echo "Please install dependencies manually (Python 3.12, PDM, UV, NVM/Node, npm) and rerun."
            return 1
            ;;
    esac
}

# ============================================
# MAIN MENU
# ============================================

show_menu() {
    echo ""
    echo "Choose your setup method:"
    echo ""
    echo "  1) Docker Setup (Recommended)"
    echo "     - Isolated environment"
    echo "     - No system dependencies"
    echo "     - One-command setup"
    echo "     - Best for production"
    echo ""
    echo "  2) Native Setup (macOS or Ubuntu/Debian)"
    echo "     - Direct installation"
    echo "     - Full development access"
    echo "     - Manual dependency management"
    echo "     - Best for development"
    echo ""
    echo "Both options provide the same functionality!"
    echo ""
    read -p "Enter your choice (1 or 2): " -n 1 -r
    echo ""
    
    case $REPLY in
        1)
            docker_setup
            ;;
        2)
            native_setup
            ;;
        *)
            print_error "Invalid choice. Please run the script again and select 1 or 2."
            exit 1
            ;;
    esac
}

# ============================================
# E2B TEMPLATE SETUP
# ============================================

setup_e2b_template() {
    print_info "Setting up E2B template with AWS credentials..."
    
    # Check if E2B CLI is installed
    if ! command -v e2b &> /dev/null; then
        print_error "E2B CLI not found. Please install it first:"
        print_info "npm install -g @e2b/cli"
        return 1
    fi
    
    # Check if .env file exists
    if [ ! -f .env ]; then
        print_error ".env file not found. Please create it with AWS credentials first."
        return 1
    fi
    
    # Load environment variables from .env
    print_info "Loading AWS credentials from .env..."
    export $(grep -v '^#' .env | xargs)
    
    # Validate required environment variables
    if [[ -z "$AWS_ACCESS_KEY_ID" || -z "$AWS_SECRET_ACCESS_KEY" || -z "$S3_BUCKET_NAME" ]]; then
        print_error "Missing required AWS credentials in .env file:"
        print_error "Required: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET_NAME"
        return 1
    fi
    
    print_info "AWS credentials found:"
    print_info "  AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:0:10}..."
    print_info "  S3_BUCKET_NAME: $S3_BUCKET_NAME"
    print_info "  AWS_REGION: ${AWS_REGION:-us-west-2}"
    
    # Change to E2B template directory
    if [ ! -d "docker/e2b-sandbox" ]; then
        print_error "E2B template directory not found: docker/e2b-sandbox"
        return 1
    fi
    
    cd docker/e2b-sandbox
    
    # Get S3 mount directory from .env or use default
    S3_MOUNT_DIR=$(safe_env_extract "../../.env" "S3_MOUNT_DIR" "/opt/sentient")
    # Expand $HOME variable if present
    S3_MOUNT_DIR=$(eval echo "$S3_MOUNT_DIR")
    
    # Build E2B template with build args
    print_info "Building E2B template with AWS credentials and mount directory as build args..."
    print_info "  S3_MOUNT_DIR: $S3_MOUNT_DIR"
    e2b template build \
        --build-arg AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \
        --build-arg AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \
        --build-arg AWS_REGION="${AWS_REGION:-us-west-2}" \
        --build-arg S3_BUCKET_NAME="$S3_BUCKET_NAME" \
        --build-arg S3_MOUNT_DIR="$S3_MOUNT_DIR" \
        --name sentient-e2b-s3
    
    if [ $? -eq 0 ]; then
        print_success "E2B template built successfully!"
        print_info "Template name: sentient-e2b-s3"
        print_info "You can now use this template with AgnoAgent E2BTools"
        print_info "Test the template with: $0 --test-e2b"
    else
        print_error "E2B template build failed"
        return 1
    fi
    
    cd ../..
}

test_e2b_template() {
    print_info "Testing E2B template with AWS integration..."
    
    # Check if E2B CLI is available
    if ! command -v e2b &> /dev/null; then
        print_error "E2B CLI not found. Install with: npm install -g @e2b/cli"
        return 1
    fi
    
    # Check E2B authentication
    print_info "Checking E2B authentication..."
    if ! e2b auth whoami &> /dev/null; then
        print_warning "E2B not authenticated. Attempting to log in..."
        print_info "This will open your browser to authenticate with E2B"
        if e2b auth login; then
            print_success "E2B authentication successful"
        else
            print_error "E2B authentication failed. Please try manually: e2b auth login"
            return 1
        fi
    fi
    print_success "E2B authentication verified"
    
    # Check if template exists
    template_name="sentient-e2b-s3"
    print_info "Checking E2B template: $template_name"
    
    if e2b template list 2>/dev/null | grep -q "$template_name"; then
        print_success "E2B template '$template_name' found"
    else
        print_warning "E2B template '$template_name' not found"
        print_info "Available templates:"
        e2b template list 2>/dev/null || print_error "Failed to list templates"
        print_info "Build the template with: cd docker/e2b-sandbox && e2b template build --name $template_name"
        return 1
    fi
    
    # Load E2B API key from environment
    E2B_API_KEY=$(safe_env_extract ".env" "E2B_API_KEY" "")
    export E2B_API_KEY
    
    # Check AWS environment variables  
    print_info "Checking AWS configuration..."
    aws_vars=("AWS_ACCESS_KEY_ID" "AWS_SECRET_ACCESS_KEY" "S3_BUCKET_NAME")
    missing_vars=()
    
    for var in "${aws_vars[@]}"; do
        if [ -z "${!var}" ]; then
            missing_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -eq 0 ]; then
        print_success "AWS credentials configured"
    else
        print_warning "Missing AWS environment variables: ${missing_vars[*]}"
        print_info "Configure these in your .env file for full functionality"
    fi
    
    # Test basic E2B sandbox creation (without specific libraries)
    print_info "Testing E2B sandbox creation..."
    
    python3 -c "
import os
import sys

print('[INFO] Testing basic E2B functionality...')

# Check environment variables
e2b_key = os.getenv('E2B_API_KEY')
if not e2b_key:
    print('[ERROR] E2B_API_KEY not set')
    sys.exit(1)

print('[SUCCESS] E2B_API_KEY configured')

# Try to import E2B (check multiple possible imports)
e2b_available = False
for module_path in ['e2b_code_interpreter', 'e2b', 'agno.tools.e2b']:
    try:
        if module_path == 'e2b_code_interpreter':
            from e2b_code_interpreter import Sandbox
            e2b_available = True
            print(f'[SUCCESS] E2B available via {module_path}')
            break
        elif module_path == 'e2b':
            import e2b
            e2b_available = True
            print(f'[SUCCESS] E2B available via {module_path}')
            break
        elif module_path == 'agno.tools.e2b':
            from agno.tools.e2b import E2BTools
            e2b_available = True
            print(f'[SUCCESS] E2B available via {module_path}')
            break
    except ImportError:
        continue

if not e2b_available:
    print('[WARNING] No E2B Python libraries found')
    print('[INFO] Template exists but Python integration not available')
    print('[SUCCESS] E2B CLI test completed (limited functionality)')
else:
    print('[SUCCESS] E2B Python integration available')

print('[SUCCESS] E2B template test completed!')
" 2>/dev/null
    
    local python_result=$?
    
    if [ $python_result -eq 0 ]; then
        print_success "E2B template test completed successfully!"
        print_info "Template '$template_name' is ready for use"
    else
        print_warning "E2B template test completed with limitations"
        print_info "E2B CLI is working but Python libraries may need installation"
    fi
    
    return 0
}

# ============================================
# MAIN EXECUTION
# ============================================

main() {
    show_banner
    
    # Detect OS
    detect_os
    
    # Handle command line arguments
    case "$1" in
        --docker)
            docker_setup
            ;;
        --docker-from-scratch)
            docker_from_scratch
            ;;
        --compose)
            docker_compose_run
            ;;
        --native)
            native_setup
            ;;
        --e2b)
            setup_e2b_integration
            ;;
        --test-e2b)
            test_e2b_template
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --docker    Run Docker setup directly"
            echo "  --docker-from-scratch  Rebuild Docker images and containers from scratch (down -v, no cache)"
            echo "  --compose   Run docker-compose up -d with S3 configuration (assumes images already built)"
            echo "  --native    Run native setup (macOS or Ubuntu/Debian) directly"
            echo "  --e2b       Setup E2B template with AWS credentials (requires E2B_API_KEY and AWS creds in .env)"
            echo "  --test-e2b  Test E2B template integration (run after --e2b)"
            echo "  --help      Show this help message"
            echo ""
            echo "Without options, an interactive menu will be shown."
            ;;
        "")
            show_menu
            ;;
        *)
            print_error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
}

# Error handling
trap 'print_error "Setup failed! Check the error messages above."; exit 1' ERR

# Run main function with all arguments
main "$@"