#!/bin/bash

# ROMA-DSPy Dynamic Setup Script
# Fully dynamic configuration discovery and setup

set -e  # Exit on error

# =============================================================================
# Configuration Discovery
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Dynamic configuration paths
CONFIG_DIR="config"
PROFILES_DIR="$CONFIG_DIR/profiles"
EXAMPLES_DIR="$CONFIG_DIR/examples"
DEFAULTS_DIR="$CONFIG_DIR/defaults"

# =============================================================================
# Helper Functions
# =============================================================================

print_banner() {
    echo -e "${CYAN}"
    cat << "EOF"
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║             ROMA-DSPy Dynamic Setup                          ║
║             Hierarchical Multi-Agent Framework               ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
EOF
    echo -e "${NC}"
}

success() { echo -e "${GREEN}✓ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
error() { echo -e "${RED}✗ $1${NC}"; }
info() { echo -e "${CYAN}ℹ $1${NC}"; }
step() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BOLD}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

detect_os() {
    case "$(uname -s)" in
        Darwin) OS_TYPE="macos" ;;
        Linux)
            if [[ -f /etc/debian_version ]]; then
                OS_TYPE="debian"
            else
                OS_TYPE="linux"
            fi
            ;;
        *) OS_TYPE="unknown" ;;
    esac
}

check_command() {
    command -v "$1" &> /dev/null
}

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

prompt_input() {
    local prompt="$1"
    local default="$2"
    local response

    if [[ -n "$default" ]]; then
        echo -ne "${prompt} [${default}]: " >&2
    else
        echo -ne "${prompt}: " >&2
    fi

    read -r response
    echo "${response:-$default}"
}

prompt_password() {
    local prompt="$1"
    local password
    echo -ne "${prompt}: "
    read -rs password
    echo
    echo "$password"
}

# Safely set or update a key=value in .env without duplicates
ensure_env_var() {
    local key="$1"
    local value="$2"
    if [ ! -f .env ]; then
        echo "${key}=${value}" > .env
        return 0
    fi
    # Remove any existing entries for the key, then append once
    if grep -q "^${key}=" .env; then
        sed -i.bak "/^${key}=.*/d" .env && rm -f .env.bak
    fi
    echo "${key}=${value}" >> .env
}

# =============================================================================
# Dynamic Discovery Functions
# =============================================================================

discover_profiles() {
    local profiles=()

    if [ -d "$PROFILES_DIR" ]; then
        for profile_file in "$PROFILES_DIR"/*.yaml "$PROFILES_DIR"/*.yml; do
            if [ -f "$profile_file" ]; then
                local profile_name=$(basename "$profile_file" .yaml)
                profile_name=$(basename "$profile_name" .yml)
                profiles+=("$profile_name")
            fi
        done
    fi

    echo "${profiles[@]}"
}

discover_examples() {
    local examples=()

    if [ -d "$EXAMPLES_DIR" ]; then
        for example_file in "$EXAMPLES_DIR"/*.yaml "$EXAMPLES_DIR"/*.yml; do
            if [ -f "$example_file" ]; then
                local example_name=$(basename "$example_file" .yaml)
                example_name=$(basename "$example_name" .yml)
                examples+=("$example_name")
            fi
        done
    fi

    echo "${examples[@]}"
}

get_profile_description() {
    local profile_file="$1"

    # Try to extract description from YAML comments or metadata
    if [ -f "$profile_file" ]; then
        # Look for description comment or field
        local desc=$(grep -E "^#\s*description:|^description:" "$profile_file" | head -1 | sed 's/.*description:\s*//' | sed 's/#//')
        if [ -z "$desc" ]; then
            # Try to get first comment line as description
            desc=$(grep -E "^#" "$profile_file" | head -1 | sed 's/^#\s*//')
        fi
        echo "${desc:-No description available}"
    fi
}

discover_required_env_vars() {
    local profile="$1"
    local profile_file="$PROFILES_DIR/${profile}.yaml"

    if [ ! -f "$profile_file" ]; then
        profile_file="$PROFILES_DIR/${profile}.yml"
    fi

    local required_vars=()

    if [ -f "$profile_file" ]; then
        # Parse profile for model providers and toolkits
        local content=$(cat "$profile_file")

        # Check for OpenRouter first
        local uses_openrouter=false
        if echo "$content" | grep -q "openrouter"; then
            required_vars+=("OPENROUTER_API_KEY")
            uses_openrouter=true
        fi

        # Only check for individual provider keys if NOT using OpenRouter
        # (OpenRouter routes to all providers with one key)
        if [ "$uses_openrouter" = false ]; then
            # Check for OpenAI
            if echo "$content" | grep -q "openai\|gpt"; then
                required_vars+=("OPENAI_API_KEY")
            fi

            # Check for Anthropic
            if echo "$content" | grep -q "anthropic\|claude"; then
                required_vars+=("ANTHROPIC_API_KEY")
            fi

            # Check for Google
            if echo "$content" | grep -q "google\|gemini"; then
                required_vars+=("GOOGLE_API_KEY")
            fi
        fi

        # Check for E2B toolkit
        if echo "$content" | grep -q "e2b_toolkit\|E2BToolkit"; then
            required_vars+=("E2B_API_KEY")
        fi

        # Check for AWS/S3
        if echo "$content" | grep -q "s3\|aws\|file_toolkit"; then
            required_vars+=("AWS_ACCESS_KEY_ID" "AWS_SECRET_ACCESS_KEY" "AWS_REGION")
        fi

        # Check for web search (Serper)
        if echo "$content" | grep -q "web_search\|serper\|search_toolkit"; then
            required_vars+=("SERPER_API_KEY")
        fi

        # Check for crypto toolkits
        if echo "$content" | grep -q "arkham_toolkit"; then
            required_vars+=("ARKHAM_API_KEY")
        fi

        if echo "$content" | grep -q "defillama_toolkit"; then
            required_vars+=("DEFILLAMA_API_KEY")
        fi

        if echo "$content" | grep -q "binance_toolkit"; then
            required_vars+=("BINANCE_API_KEY" "BINANCE_API_SECRET")
        fi

        if echo "$content" | grep -q "coingecko_toolkit"; then
            required_vars+=("COINGECKO_API_KEY")
        fi
    fi

    # Always include database vars
    required_vars+=("POSTGRES_PASSWORD")

    echo "${required_vars[@]}"
}

discover_docker_compose_files() {
    local compose_files=("-f docker-compose.yaml")

    # Check for override files
    if [ -f "docker-compose.override.yaml" ]; then
        compose_files+=("-f docker-compose.override.yaml")
    elif [ -f "docker-compose.override.yml" ]; then
        compose_files+=("-f docker-compose.override.yml")
    fi

    # Check for environment-specific files
    local env_type="${ROMA_ENV:-development}"
    if [ -f "docker-compose.${env_type}.yaml" ]; then
        compose_files+=("-f docker-compose.${env_type}.yaml")
    elif [ -f "docker-compose.${env_type}.yml" ]; then
        compose_files+=("-f docker-compose.${env_type}.yml")
    fi

    echo "${compose_files[@]}"
}

# =============================================================================
# Prerequisites Check
# =============================================================================

check_prerequisites() {
    step "Checking Prerequisites"

    local missing=()
    local optional=()

    # Core requirements
    local requirements=(
        "docker:Docker:https://docs.docker.com/get-docker/"
        "python3:Python 3:https://www.python.org/downloads/"
    )

    # Optional tools
    local optional_tools=(
        "goofys:goofys (S3 mounting):github.com/kahing/goofys"
        "aws:AWS CLI:https://aws.amazon.com/cli/"
        "e2b:E2B CLI:npm install -g @e2b/cli"
        "jq:jq (JSON processor):https://jqlang.github.io/jq/download/"
        "yq:yq (YAML processor):https://github.com/mikefarah/yq"
    )

    # Check for FUSE (required for goofys)
    if [[ "$OS_TYPE" == "macos" ]]; then
        if [ ! -d "/Library/Filesystems/macfuse.fs" ] && [ ! -d "/Library/Filesystems/osxfuse.fs" ]; then
            optional+=("macFUSE (required for S3 mounting)")
            warning "macFUSE not installed (required for goofys)"
            info "  Install from: https://osxfuse.github.io/"
        else
            success "macFUSE installed"
        fi
    elif [[ "$OS_TYPE" == "debian" || "$OS_TYPE" == "linux" ]]; then
        if ! dpkg -l | grep -q fuse3 && ! command -v fusermount3 &>/dev/null; then
            optional+=("FUSE3 (required for S3 mounting)")
            warning "FUSE3 not installed (required for goofys)"
        else
            success "FUSE3 installed"
        fi
    fi

    # Check required tools
    for req in "${requirements[@]}"; do
        IFS=':' read -r cmd name url <<< "$req"
        if ! check_command "$cmd"; then
            missing+=("$name")
            info "  Install $name: $url"
        else
            success "$name installed"
        fi
    done

    # Check Docker Compose
    if ! check_command docker-compose && ! docker compose version &>/dev/null; then
        missing+=("Docker Compose")
        info "  Install: https://docs.docker.com/compose/install/"
    else
        success "Docker Compose installed"
    fi

    # Check optional tools
    echo ""
    for opt in "${optional_tools[@]}"; do
        IFS=':' read -r cmd name install <<< "$opt"
        if ! check_command "$cmd"; then
            optional+=("$name")
            warning "$name not installed (optional)"
            info "  Purpose: $install"
        else
            success "$name installed"
        fi
    done

    # Offer to install missing optional tools
    if [ ${#optional[@]} -gt 0 ]; then
        echo ""
        if prompt_yes_no "Would you like to install optional tools now?" "n"; then
            install_optional_tools
        else
            info "Optional tools can be installed later manually"
        fi
    fi

    # Check Python version
    if check_command python3; then
        local py_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
        if (( $(echo "$py_version < 3.10" | bc -l 2>/dev/null || echo 0) )); then
            warning "Python $py_version found. Python 3.10+ recommended"
        fi
    fi

    # Verify Docker daemon
    if ! docker info &>/dev/null; then
        error "Docker daemon is not running"
        echo "Please start Docker and run this script again"
        exit 1
    fi

    if [ ${#missing[@]} -gt 0 ]; then
        error "Missing required tools: ${missing[*]}"
        if ! prompt_yes_no "Continue anyway? (not recommended)" "n"; then
            exit 1
        fi
    else
        success "All required prerequisites installed"
    fi
}

# =============================================================================
# Optional Tools Installation
# =============================================================================

install_fuse() {
    info "Installing FUSE for filesystem mounting..."

    case "$OS_TYPE" in
        macos)
            if [ -d "/Library/Filesystems/macfuse.fs" ] || [ -d "/Library/Filesystems/osxfuse.fs" ]; then
                success "macFUSE already installed"
                return 0
            fi

            info "macFUSE requires manual installation on macOS"
            info "Opening download page in browser..."
            open "https://osxfuse.github.io/" 2>/dev/null || true
            echo ""
            warning "Please install macFUSE from the opened page, then re-run this script"
            info "Direct download: https://github.com/osxfuse/osxfuse/releases"
            return 1
            ;;
        debian)
            info "Installing FUSE3 via apt..."
            if sudo apt-get update && sudo apt-get install -y fuse3 libfuse3-dev 2>/dev/null; then
                success "FUSE3 installed successfully"
                return 0
            else
                error "Failed to install FUSE3"
                return 1
            fi
            ;;
        linux)
            info "Installing FUSE via package manager..."
            if command -v yum &>/dev/null; then
                sudo yum install -y fuse3 fuse3-devel
            elif command -v apt-get &>/dev/null; then
                sudo apt-get update && sudo apt-get install -y fuse3 libfuse3-dev
            else
                error "Unsupported package manager"
                return 1
            fi
            success "FUSE installed successfully"
            return 0
            ;;
        *)
            error "Unsupported OS for automatic FUSE installation"
            return 1
            ;;
    esac
}

install_goofys() {
    info "Installing goofys for S3 mounting..."

    # Check FUSE prerequisite
    local fuse_installed=false
    if [[ "$OS_TYPE" == "macos" ]]; then
        if [ -d "/Library/Filesystems/macfuse.fs" ] || [ -d "/Library/Filesystems/osxfuse.fs" ]; then
            fuse_installed=true
        fi
    elif [[ "$OS_TYPE" == "debian" || "$OS_TYPE" == "linux" ]]; then
        if command -v fusermount3 &>/dev/null || dpkg -l | grep -q fuse3; then
            fuse_installed=true
        fi
    fi

    if [ "$fuse_installed" = false ]; then
        warning "FUSE is not installed (required for goofys)"
        if prompt_yes_no "Install FUSE first?" "y"; then
            if ! install_fuse; then
                error "FUSE installation failed or requires manual steps"
                return 1
            fi
        else
            warning "Skipping goofys installation - FUSE is required"
            return 1
        fi
    fi

    # Check if already installed in common locations
    if check_command goofys; then
        local goofys_version=$(goofys --help 2>&1 | head -1 || echo "version unknown")
        success "goofys already installed at: $(command -v goofys)"
        info "Version info: $goofys_version"
        return 0
    fi

    local common_paths=("/usr/local/bin/goofys" "$HOME/go/bin/goofys" "/opt/homebrew/bin/goofys")
    for path in "${common_paths[@]}"; do
        if [ -x "$path" ]; then
            success "goofys found at: $path"
            if ! check_command goofys; then
                local dir=$(dirname "$path")
                export PATH="$PATH:$dir"
                info "Added $dir to PATH for current session"
            fi
            return 0
        fi
    done

    # Try multiple installation methods
    info "Trying multiple methods to install goofys..."

    # Method 1: Pre-built binary (Linux x86_64 only)
    local arch=$(uname -m)
    if [[ "$OS_TYPE" == "debian" || "$OS_TYPE" == "linux" ]] && [[ "$arch" == "x86_64" ]]; then
        info "Method 1: Installing pre-built binary for Linux x86_64..."
        local goofys_url="https://github.com/kahing/goofys/releases/download/v0.24.0/goofys"
        local temp_file="/tmp/goofys-$$"

        if curl -L "$goofys_url" -o "$temp_file" 2>/dev/null; then
            if [ -s "$temp_file" ] && [ $(stat -c%s "$temp_file" 2>/dev/null || echo 0) -gt 20000000 ]; then
                if chmod +x "$temp_file" && "$temp_file" --help >/dev/null 2>&1; then
                    if sudo mv "$temp_file" /usr/local/bin/goofys 2>/dev/null; then
                        success "goofys pre-built binary installed successfully"
                        return 0
                    fi
                fi
            fi
            rm -f "$temp_file"
        fi
        warning "Pre-built binary installation failed"
    else
        info "Skipping pre-built binary (only available for Linux x86_64)"
    fi

    # Method 2: Build from source with Go (works for all platforms including Apple Silicon)
    if check_command go; then
        info "Method 2: Building goofys from source with Go..."

        local go_version=$(go version 2>/dev/null | grep -o 'go[0-9]\+\.[0-9]\+' | sed 's/go//' | head -1)
        if [ -n "$go_version" ]; then
            info "Building with Go $go_version for $(uname -s)/$(uname -m)..."
        fi

        export GOPATH="${GOPATH:-$HOME/go}"
        mkdir -p "$GOPATH/bin"

        # Use PR #778 which fixes gopsutil v3 compatibility for macOS M1/ARM
        info "Building goofys from PR #778 (gopsutil v3 fix for Apple Silicon)..."
        local temp_dir="/tmp/goofys-build-$$"
        mkdir -p "$temp_dir"
        cd "$temp_dir"

        if git clone -b feature/upgrade-gopsutil https://github.com/chiehting/goofys.git 2>/dev/null; then
            cd goofys
            if go install . 2>/dev/null; then
                cd - && rm -rf "$temp_dir"

                # Check if build successful
                local goofys_path=""
                if [ -f "$GOPATH/bin/goofys" ]; then
                    goofys_path="$GOPATH/bin/goofys"
                elif [ -f "$HOME/go/bin/goofys" ]; then
                    goofys_path="$HOME/go/bin/goofys"
                fi

                if [ -n "$goofys_path" ] && "$goofys_path" --help >/dev/null 2>&1; then
                    # Try to install to system location
                    if sudo cp "$goofys_path" /usr/local/bin/goofys 2>/dev/null; then
                        success "goofys built and installed from source"
                        return 0
                    else
                        success "goofys built at $goofys_path"
                        export PATH="$PATH:$(dirname $goofys_path)"
                        info "Added $(dirname $goofys_path) to PATH for current session"
                        return 0
                    fi
                fi
            fi
        fi
        cd - && rm -rf "$temp_dir"
        warning "Build from source failed"
    else
        info "Go compiler not found, skipping source build"
    fi

    # Method 3: Install Go and build goofys
    if ! check_command go; then
        info "Method 3: Installing Go compiler and building goofys..."

        if [[ "$OS_TYPE" == "macos" ]] && check_command brew; then
            info "Installing Go via Homebrew..."
            if brew install go 2>/dev/null; then
                export PATH="$PATH:/usr/local/go/bin:$HOME/go/bin:/opt/homebrew/bin"
                # Retry build now that Go is installed
                return $(install_goofys)
            fi
        elif [[ "$OS_TYPE" == "debian" ]] && check_command apt; then
            info "Installing Go via apt..."
            if sudo apt update && sudo apt install -y golang-go 2>/dev/null; then
                export PATH="$PATH:/usr/local/go/bin:$HOME/go/bin"
                # Retry build now that Go is installed
                return $(install_goofys)
            fi
        fi
        warning "Go installation and goofys build failed"
    fi

    error "All goofys installation methods failed"
    info "goofys is optional and only needed for S3 mounting"
    info "You can install it manually later if needed"
    return 1
}

install_optional_tool() {
    local tool="$1"
    local os_type="$2"

    info "Installing ${tool}..."

    case "$tool" in
        fuse|macfuse|FUSE3)
            install_fuse
            return $?
            ;;
        goofys)
            install_goofys
            return $?
            ;;
        aws)
            case "$os_type" in
                macos)
                    if check_command brew; then
                        brew install awscli
                    else
                        error "Homebrew required to install AWS CLI on macOS"
                        return 1
                    fi
                    ;;
                debian)
                    sudo apt-get update && sudo apt-get install -y awscli
                    ;;
                linux)
                    curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip" && \
                    unzip awscliv2.zip && \
                    sudo ./aws/install && \
                    rm -rf awscliv2.zip aws
                    ;;
            esac
            ;;
        jq)
            case "$os_type" in
                macos)
                    if check_command brew; then
                        brew install jq
                    else
                        error "Homebrew required to install jq on macOS"
                        return 1
                    fi
                    ;;
                debian)
                    sudo apt-get update && sudo apt-get install -y jq
                    ;;
                linux)
                    sudo yum install -y jq || sudo apt-get install -y jq
                    ;;
            esac
            ;;
        yq)
            case "$os_type" in
                macos)
                    if check_command brew; then
                        brew install yq
                    else
                        error "Homebrew required to install yq on macOS"
                        return 1
                    fi
                    ;;
                debian|linux)
                    sudo wget -qO /usr/local/bin/yq https://github.com/mikefarah/yq/releases/latest/download/yq_linux_amd64 && \
                    sudo chmod +x /usr/local/bin/yq
                    ;;
            esac
            ;;
        e2b)
            # Install E2B CLI (Node-based)
            if check_command npm; then
                npm install -g @e2b/cli || return 1
            elif check_command yarn; then
                yarn global add @e2b/cli || return 1
            else
                error "Node.js not found (npm/yarn). Install Node.js to get the E2B CLI."
                info "Install Node: https://nodejs.org/"
                info "Then run: npm install -g @e2b/cli"
                return 1
            fi
            ;;
        *)
            error "Unknown tool: $tool"
            return 1
            ;;
    esac
}

install_optional_tools() {
    step "Installing Optional Tools"

    detect_os

    # Check each optional tool
    local tools_to_install=()

    if ! check_command goofys; then
        tools_to_install+=("goofys")
    fi

    if ! check_command aws; then
        tools_to_install+=("aws")
    fi

    if ! check_command jq; then
        tools_to_install+=("jq")
    fi

    if ! check_command yq; then
        tools_to_install+=("yq")
    fi

    if ! check_command e2b; then
        tools_to_install+=("e2b")
    fi

    if [ ${#tools_to_install[@]} -eq 0 ]; then
        success "All optional tools are already installed"
        return 0
    fi

    echo ""
    info "Missing optional tools: ${tools_to_install[*]}"
    echo ""

    # Install each tool
    local installed_tools=()
    local failed_tools=()

    for tool in "${tools_to_install[@]}"; do
        echo ""
        if ! prompt_yes_no "Install ${tool}?" "y"; then
            info "Skipping ${tool}"
            continue
        fi

        if install_optional_tool "$tool" "$OS_TYPE"; then
            installed_tools+=("$tool")
        else
            failed_tools+=("$tool")
            warning "You may need to install it manually"
        fi
    done

    # Validate installation
    echo ""
    step "Validating Installed Tools"

    for tool in "${installed_tools[@]}"; do
        if check_command "$tool"; then
            success "${tool} verified and working"
        else
            error "${tool} installation reported success but command not found"
            failed_tools+=("$tool")
        fi
    done

    # Summary
    echo ""
    if [ ${#installed_tools[@]} -gt 0 ]; then
        success "Successfully installed: ${installed_tools[*]}"
    fi

    if [ ${#failed_tools[@]} -gt 0 ]; then
        warning "Failed to install: ${failed_tools[*]}"
        info "These tools are optional and can be installed manually later"
    fi

    echo ""
    success "Optional tools setup complete"
}

# =============================================================================
# Profile Selection
# =============================================================================

select_profile() {
    step "Select Configuration Profile"

    local profiles=($(discover_profiles))

    if [ ${#profiles[@]} -eq 0 ]; then
        error "No profiles found in $PROFILES_DIR"
        exit 1
    fi

    echo ""
    info "Available profiles:"
    echo ""

    local i=1
    for profile in "${profiles[@]}"; do
        local profile_file="$PROFILES_DIR/${profile}.yaml"
        [ ! -f "$profile_file" ] && profile_file="$PROFILES_DIR/${profile}.yml"

        local desc=$(get_profile_description "$profile_file")
        printf "  ${BOLD}%2d.${NC} %-20s - %s\n" "$i" "$profile" "$desc"
        ((i++))
    done

    echo ""
    local choice=$(prompt_input "Select profile (1-${#profiles[@]} or name)" "1")

    # Handle numeric or name input
    if [[ "$choice" =~ ^[0-9]+$ ]]; then
        if [ "$choice" -ge 1 ] && [ "$choice" -le ${#profiles[@]} ]; then
            SELECTED_PROFILE="${profiles[$((choice-1))]}"
        else
            error "Invalid selection"
            exit 1
        fi
    else
        # Check if profile exists
        if [[ " ${profiles[@]} " =~ " ${choice} " ]]; then
            SELECTED_PROFILE="$choice"
        else
            error "Profile '$choice' not found"
            exit 1
        fi
    fi

    success "Selected profile: $SELECTED_PROFILE"

    # Show what this profile requires
    local required_vars=($(discover_required_env_vars "$SELECTED_PROFILE"))
    if [ ${#required_vars[@]} -gt 0 ]; then
        info "This profile may require:"
        for var in "${required_vars[@]}"; do
            echo "  - $var"
        done
    fi
}

# =============================================================================
# Environment Configuration
# =============================================================================

configure_environment() {
    step "Configuring Environment"

    # Handle existing .env
    if [ -f .env ]; then
        info ".env file already exists"
        echo ""
        info "Options:"
        info "  [Y]es - Backup current .env and create new one (re-enter all settings)"
        info "  [N]o  - Keep existing .env and skip configuration (recommended for re-runs)"
        echo ""

        if prompt_yes_no "Backup and reconfigure?" "n"; then
            local backup_file=".env.backup.$(date +%Y%m%d_%H%M%S)"
            mv .env "$backup_file"
            info "Backed up to $backup_file"
        else
            info "Keeping existing .env file"
            return 0
        fi
    fi

    # Create from template if exists
    if [ -f .env.example ]; then
        cp .env.example .env
        success "Created .env from template"
    else
        # Create minimal .env
        cat > .env << EOF
# ROMA-DSPy Environment Configuration
# Generated: $(date)
# Profile: ${SELECTED_PROFILE}

# Environment
ROMA_ENV=development
ROMA_CONFIG_PROFILE=${SELECTED_PROFILE}

# Database
POSTGRES_DB=roma_dspy
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
API_WORKERS=4

# Logging
LOG_LEVEL=INFO
LOG_CONSOLE_FORMAT=default

EOF
        success "Created new .env file"
    fi

    # Dynamic configuration based on discovered requirements
    local required_vars=($(discover_required_env_vars "$SELECTED_PROFILE"))

    if [ ${#required_vars[@]} -gt 0 ]; then
        echo ""
        info "Profile '$SELECTED_PROFILE' may use the following API keys:"
        info "(The application will validate these when needed)"
        echo ""

        for var in "${required_vars[@]}"; do
            # Skip if already configured (not checking validity)
            if grep -q "^${var}=" .env && ! grep -q "^${var}=your_" .env && ! grep -q "^${var}=$" .env; then
                success "$var already set in .env"
                continue
            fi

            # Determine input type
            case "$var" in
                *PASSWORD*|*SECRET*|*KEY*)
                    local value=$(prompt_password "Enter $var (or skip)")
                    ;;
                *)
                    local value=$(prompt_input "Enter $var (or skip)" "")
                    ;;
            esac

            if [ -n "$value" ]; then
                # Update or add to .env (no validation)
                if grep -q "^${var}=" .env; then
                    sed -i.bak "s|^${var}=.*|${var}=${value}|" .env
                else
                    echo "${var}=${value}" >> .env
                fi
                success "$var added to .env"
            else
                warning "$var skipped - can be configured later if needed"
            fi
        done

        # Clean up backup
        rm -f .env.bak
    fi

    # Discover and configure additional services
    echo ""
    if prompt_yes_no "Configure optional services?" "n"; then
        configure_optional_services
    fi

    success "Environment configuration complete (validation will happen at runtime)"
}

configure_optional_services() {
    info "Configuring optional services..."

    # S3 Storage
    if prompt_yes_no "Configure S3 storage?" "n"; then
        local bucket=$(prompt_input "S3 bucket name" "")
        [ -n "$bucket" ] && echo "ROMA_S3_BUCKET=$bucket" >> .env

        local region=$(prompt_input "AWS region" "us-east-1")
        echo "AWS_REGION=$region" >> .env

        local storage_path=$(prompt_input "Storage mount path" "/opt/sentient")
        echo "STORAGE_BASE_PATH=$storage_path" >> .env
    fi

    # MLflow
    if prompt_yes_no "Enable MLflow observability?" "n"; then
        ensure_env_var "MLFLOW_ENABLED" "true"
        local mlflow_port=$(prompt_input "MLflow port" "5000")
        ensure_env_var "MLFLOW_PORT" "$mlflow_port"

        # Let user specify full tracking URI (single variable)
        local default_uri="http://127.0.0.1:${mlflow_port}"
        local current_uri=$(grep -E "^MLFLOW_TRACKING_URI=" .env | sed 's/^MLFLOW_TRACKING_URI=//')
        if [ -n "$current_uri" ]; then
            default_uri="$current_uri"
        fi
        local tracking_uri=$(prompt_input "MLflow Tracking URI (single variable)" "$default_uri")
        ensure_env_var "MLFLOW_TRACKING_URI" "$tracking_uri"
    fi

    # Custom configurations
    if prompt_yes_no "Add custom environment variables?" "n"; then
        while true; do
            local var_name=$(prompt_input "Variable name (or 'done')" "done")
            [ "$var_name" = "done" ] && break

            local var_value=$(prompt_input "Value for $var_name" "")
            echo "${var_name}=${var_value}" >> .env
        done
    fi
}

# =============================================================================
# Dynamic Service Setup
# =============================================================================

setup_s3_mount() {
    step "Setting up S3 Storage Mount (Optional)"

    # Check if S3 bucket is configured
    if ! grep -q "^ROMA_S3_BUCKET=" .env || grep -q "^ROMA_S3_BUCKET=$" .env; then
        info "S3 bucket not configured, skipping mount setup"
        info "S3 can be configured later if needed"
        return 0
    fi

    # Check if goofys is available for mounting
    if ! check_command goofys; then
        warning "goofys not installed - needed for S3 mounting"
        info "Install later with: brew install goofys (macOS) or see github.com/kahing/goofys"
        return 0
    fi

    # Check for mount script
    local mount_scripts=(
        "scripts/setup_local.sh"
        "scripts/s3_mount.sh"
        "scripts/mount.sh"
    )

    local mount_script=""
    for script in "${mount_scripts[@]}"; do
        if [ -f "$script" ]; then
            mount_script="$script"
            break
        fi
    done

    if [ -n "$mount_script" ]; then
        info "Running S3 mount script: $mount_script"

        # Load .env file to make AWS credentials available
        if [ -f .env ]; then
            info "Loading environment variables from .env"
            set -a  # Mark variables for export
            source .env
            set +a  # Unmark
        fi

        # Check if AWS credentials are available
        if [ -z "$AWS_ACCESS_KEY_ID" ] || [ -z "$AWS_SECRET_ACCESS_KEY" ]; then
            warning "AWS credentials not found in .env file"
            info "S3 mounting requires AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY"
            info "Skipping S3 mount - will be configured at runtime if needed"
            return 0
        fi

        info "AWS credentials loaded, attempting mount..."
        if bash "$mount_script" 2>&1; then
            success "S3 mount setup completed successfully"
        else
            warning "S3 mount setup failed - will retry at runtime if needed"
            info "This is usually fine - Docker will handle S3 mounting at startup"
        fi
    else
        warning "No S3 mount script found - S3 will be configured by Docker if needed"
    fi
}

setup_build_venv() {
    if prompt_yes_no "Create local virtual environment for build dependencies?" "y"; then
        info "Setting up virtual environment..."

        if check_command uv; then
            info "Using uv for fast setup..."
            if uv venv .venv && uv pip install e2b; then
                success "Virtual environment created with uv"
            else
                warning "Failed to create venv with uv, falling back to standard venv"
                if python3 -m venv .venv && .venv/bin/pip install e2b; then
                    success "Virtual environment created"
                else
                    error "Failed to create venv"
                    return 1
                fi
            fi
        else
            info "Using standard python venv..."
            if python3 -m venv .venv && .venv/bin/pip install e2b; then
                success "Virtual environment created"
            else
                error "Failed to create venv"
                return 1
            fi
        fi

        info "Activating virtual environment..."
        source .venv/bin/activate
    fi
}

build_e2b_template() {
    step "Building E2B v2 Template (Optional)"

    # Check if E2B CLI is available
    if ! check_command e2b; then
        info "E2B CLI not installed, skipping template build"
        info "Install later with: npm install -g @e2b/cli"
        return 0
    fi

    # Check if E2B key is in env (not validating it)
    if ! grep -q "^E2B_API_KEY=" .env || grep -q "^E2B_API_KEY=$" .env || grep -q "^E2B_API_KEY=your_" .env; then
        info "E2B API key not configured, skipping template build"
        info "Template can be built later when E2B is configured"
        return 0
    fi

    # Find E2B template directory (E2B v2 uses template.py)
    local e2b_dirs=(
        "docker/e2b"
        "docker/e2b-sandbox"
        "e2b"
        "templates/e2b"
    )

    local e2b_dir=""
    for dir in "${e2b_dirs[@]}"; do
        if [ -d "$dir" ] && [ -f "$dir/template.py" ]; then
            e2b_dir="$dir"
            break
        fi
    done

    if [ -n "$e2b_dir" ]; then
        info "Found E2B v2 template directory: $e2b_dir"

        # Load .env file to make E2B API key available
        if [ -f "$SCRIPT_DIR/.env" ]; then
            info "Loading environment variables from .env"
            set -a  # Mark variables for export
            source "$SCRIPT_DIR/.env"
            set +a  # Unmark
        fi

        # Check if E2B API key is available
        if [ -z "$E2B_API_KEY" ]; then
            warning "E2B_API_KEY not found in environment"
            info "E2B template build requires E2B_API_KEY to be set"
            info "Skipping E2B build - can be built later when configured"
            return 0
        fi

        info "E2B API key loaded, building dev template..."
        cd "$e2b_dir"

        # Setup virtual environment if requested
        setup_build_venv

        # E2B v2 approach: Use Python SDK with environment variables
        info "Building template using E2B v2 Python SDK..."
        info "Template features: Runtime S3 mounting, parallel initialization"

        if ./build.sh dev; then
            success "E2B v2 template built successfully!"
            info "Template name: roma-dspy-sandbox-dev"
            info "Features: Runtime S3 mounting, dynamic paths, parallel init"

            # Run validation test if available
            if [ -f "test_e2b_runtime_s3.py" ]; then
                info "Running validation tests..."
                if python3 test_e2b_runtime_s3.py; then
                    success "E2B v2 validation tests passed!"
                else
                    warning "Validation tests failed - but template is built"
                    info "Run tests manually: cd $e2b_dir && python3 test_e2b_runtime_s3.py"
                fi
            fi
        else
            warning "E2B template build failed - check E2B API key and AWS credentials"
            info "Template can be built later with: cd $e2b_dir && ./build.sh dev"
        fi

        cd "$SCRIPT_DIR"
    else
        info "No E2B v2 template directory found - not required for base functionality"
    fi
}

# =============================================================================
# Docker Operations
# =============================================================================

build_docker_images() {
    step "Building Docker Images"

    # Find Dockerfile
    local dockerfiles=(
        "Dockerfile"
        "docker/Dockerfile"
        "build/Dockerfile"
    )

    local dockerfile=""
    for df in "${dockerfiles[@]}"; do
        if [ -f "$df" ]; then
            dockerfile="$df"
            break
        fi
    done

    if [ -z "$dockerfile" ]; then
        error "No Dockerfile found"
        exit 1
    fi

    info "Building from: $dockerfile"

    # Build with dynamic tag
    local image_name="${DOCKER_IMAGE_NAME:-roma-dspy}"
    local image_tag="${DOCKER_IMAGE_TAG:-latest}"

    if docker build -t "${image_name}:${image_tag}" -f "$dockerfile" .; then
        success "Docker image built: ${image_name}:${image_tag}"
    else
        error "Docker build failed"
        exit 1
    fi
}

start_services() {
    step "Starting Services"

    # Discover compose files
    local compose_files=($(discover_docker_compose_files))

    info "Using compose files: ${compose_files[*]}"

    # Set profile in environment
    export ROMA_CONFIG_PROFILE="${SELECTED_PROFILE}"

    # Check for profiles in docker-compose
    local compose_profiles=()

    if grep -q "^MLFLOW_ENABLED=true" .env; then
        compose_profiles+=("--profile" "observability")
    fi

    # Start services
    if docker compose ${compose_files[@]} ${compose_profiles[@]} up -d; then
        success "Services started"
    else
        error "Failed to start services"
        exit 1
    fi

    # Wait for services
    info "Waiting for services to be ready..."
    sleep 10
}

# =============================================================================
# Validation
# =============================================================================

validate_deployment() {
    step "Validating Deployment"

    local validation_passed=true

    # Dynamic service discovery from docker-compose
    local services=$(docker compose ps --services 2>/dev/null || docker-compose ps --services 2>/dev/null)

    for service in $services; do
        if docker compose ps | grep -q "${service}.*Up"; then
            success "$service is running"
        else
            error "$service is not running"
            validation_passed=false
        fi
    done

    # API health check
    local api_port="${API_PORT:-8000}"
    if curl -sf "http://localhost:${api_port}/health" &>/dev/null; then
        success "API is healthy"
    else
        error "API health check failed"
        validation_passed=false
    fi

    # Check for API documentation
    if curl -sf "http://localhost:${api_port}/docs" &>/dev/null; then
        success "API documentation available"
    else
        warning "API documentation not accessible"
    fi

    if $validation_passed; then
        success "All validations passed!"
        info "Note: API key validation happens at runtime by config/tool managers"
    else
        warning "Some validations failed"
        info "Check logs: docker compose logs"
    fi
}

# =============================================================================
# Finalization
# =============================================================================

create_shortcuts() {
    step "Creating Shortcuts"

    # Create dynamic CLI wrapper
    cat > cli << EOF
#!/bin/bash
# ROMA-DSPy CLI wrapper
docker exec -it roma-dspy-api roma-dspy "\$@"
EOF
    chmod +x cli

    # Create run script
    cat > run << EOF
#!/bin/bash
# Quick run script
profile="\${1:-${SELECTED_PROFILE}}"
task="\${2:-Analyze market trends}"
docker exec -it roma-dspy-api roma-dspy solve --profile "\$profile" "\$task"
EOF
    chmod +x run

    success "Created CLI shortcuts: ./cli and ./run"
}

show_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║                    Setup Complete! 🎉                        ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Configuration:"
    echo "  Profile: ${SELECTED_PROFILE}"
    echo "  Environment: ${ROMA_ENV:-development}"
    echo ""
    echo "Quick Commands:"
    echo "  ${BOLD}./cli solve \"Your task\"${NC}      - Run a task"
    echo "  ${BOLD}./run \"Your task\"${NC}            - Quick run with default profile"
    echo "  ${BOLD}docker compose logs -f${NC}       - View logs"
    echo "  ${BOLD}docker compose ps${NC}            - Check status"
    echo ""
    echo "API Endpoints:"
    echo "  REST API: http://localhost:${API_PORT:-8000}/api/v1/"
    echo "  API Docs: http://localhost:${API_PORT:-8000}/docs"
    echo "  Health:   http://localhost:${API_PORT:-8000}/health"
    echo ""

    # Show profile-specific information
    if [ -f "$PROFILES_DIR/${SELECTED_PROFILE}.yaml" ]; then
        info "Profile: ${SELECTED_PROFILE}"
        local desc=$(get_profile_description "$PROFILES_DIR/${SELECTED_PROFILE}.yaml")
        [ -n "$desc" ] && echo "  $desc"
    fi
}

# =============================================================================
# Main Execution
# =============================================================================

main() {
    print_banner
    detect_os

    # Parse arguments dynamically
    while [[ $# -gt 0 ]]; do
        case $1 in
            --profile)
                SELECTED_PROFILE="$2"
                shift 2
                ;;
            --env)
                ROMA_ENV="$2"
                shift 2
                ;;
            --help|-h)
                echo "ROMA-DSPy Dynamic Setup"
                echo ""
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --profile NAME    Use specific profile"
                echo "  --env ENV         Set environment (development, production)"
                echo "  --help           Show this help"
                echo ""
                echo "Available profiles:"
                for p in $(discover_profiles); do
                    echo "  - $p"
                done
                exit 0
                ;;
            *)
                error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    # Run setup steps
    check_prerequisites

    # Select profile if not specified
    [ -z "$SELECTED_PROFILE" ] && select_profile

    configure_environment

    # Optional components (prompt user)
    echo ""
    if prompt_yes_no "Setup S3 storage mount?" "n"; then
        setup_s3_mount
    else
        info "Skipping S3 setup - can be configured later if needed"
    fi

    echo ""
    if prompt_yes_no "Build E2B code execution template?" "n"; then
        build_e2b_template
    else
        info "Skipping E2B template build - can be built later if needed"
    fi

    # Docker operations
    build_docker_images
    start_services
    validate_deployment

    # Finalization
    create_shortcuts
    show_summary
}

# Error handling
trap 'error "Setup failed at line $LINENO"; exit 1' ERR

# Run main
main "$@"
