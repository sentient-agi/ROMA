# SentientResearchAgent Setup Guide

This guide provides detailed instructions for setting up ROMA using either Docker or native installation (recommended for development).

## Prerequisites

### For Docker Setup
- Docker and Docker Compose installed
- Git

### For Native Setup (Ubuntu/Debian)
- Ubuntu 20.04+ or Debian 11+
- sudo privileges
- Git

## Quick Start

```bash
# Clone the repository
git clone https://github.com/sentient-agi/ROMA.git
cd ROMA

# Run the setup script
./setup.sh
```

The setup script will prompt you to choose between:
1. **Docker setup** - Containerized environment, best for production
2. **Native setup** - Direct installation, best for development

## Docker Setup

### Quick Setup
```bash
./setup.sh --docker
# or
make setup-docker
```

### What It Does
1. Checks Docker and Docker Compose installation
2. Creates `.env` file from template
3. Builds optimized Docker images using UV for fast dependency installation
4. Starts all services (backend and frontend)
5. Verifies health of services

### Docker Commands
```bash
# View logs
cd docker && docker compose logs -f

# Stop services
cd docker && docker compose down

# Restart services
cd docker && docker compose restart

# View status
cd docker && docker compose ps

# Rebuild after changes
cd docker && docker compose build
```

### Docker Architecture
- **Backend**: Python 3.12 with UV package manager
- **Frontend**: Node.js 23.11.0 with npm 10.9.2
- **Volumes**: Mounted for live development
- **Ports**: Backend (5000), Frontend (5173)

## Native Setup (Ubuntu/Debian)

### Quick Setup
```bash
./setup.sh --native
# or
make setup-native
```

### What It Does
1. Installs Python 3.12 from deadsnakes PPA
2. Installs PDM and UV package managers
3. Installs NVM, Node.js 23.11.0, and npm 10.9.2
4. Initializes PDM project with UV backend
5. Creates virtual environment and installs dependencies
6. Installs frontend dependencies
7. Creates necessary directories

### Manual Steps

#### 1. Install Python 3.12
```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.12 python3.12-venv python3.12-dev
```

#### 2. Install PDM and UV
```bash
# Install PDM
curl -sSL https://pdm-project.org/install-pdm.py | python3 -

# Install UV
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add to PATH (add to ~/.bashrc)
export PATH="$HOME/.local/bin:$PATH"
source "$HOME/.cargo/env"
```

#### 3. Install Node.js
```bash
# Install NVM
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.7/install.sh | bash
source ~/.bashrc

# Install Node.js and npm
nvm install 23.11.0
nvm use 23.11.0
npm install -g npm@10.9.2
```

#### 4. Setup Project
```bash
# Initialize PDM
pdm init --non-interactive --python 3.12 --dist
pdm config use_uv true

# Install dependencies
eval "$(pdm venv activate)"
pdm install

# Install frontend
cd frontend && npm install
```

### Configuration
1. Copy `.env.example` to `.env`
2. Add your LLM API keys
3. **Optional**: Configure comprehensive S3 mounting:
   ```bash
   # ===== S3 Mounting Configuration =====
   # Enable S3 mounting (accepts: true/yes/1/on/enabled)
   S3_MOUNT_ENABLED=true
   
   # Universal mount directory (identical across all platforms)
   S3_MOUNT_DIR=/opt/sentient
   
   # AWS S3 Configuration
   S3_BUCKET_NAME=your-s3-bucket
   AWS_ACCESS_KEY_ID=your_aws_key
   AWS_SECRET_ACCESS_KEY=your_aws_secret
   AWS_REGION=us-east-1
   
   # ===== E2B Integration (Optional) =====
   E2B_API_KEY=your_e2b_api_key_here
   ```
4. Customize `sentient.yaml` as needed

**🔒 Security Features in Configuration:**
- **Path validation**: Mount directories are validated against injection attacks
- **AWS verification**: Credentials are tested before mounting attempts
- **FUSE checking**: System dependencies verified automatically
- **Mount verification**: Comprehensive functionality testing before proceeding
- **Flexible booleans**: `S3_MOUNT_ENABLED` accepts multiple true/false formats

### 💾 S3 Data Persistence

SentientResearchAgent includes a comprehensive S3 mounting solution for seamless data persistence across all environments:

```bash
# During setup, you'll be asked:
# "Setup S3 mounting for data persistence? (y/n)"

# Universal mount directory: /opt/sentient (identical across all platforms)
```

**🔒 Enterprise-Grade Security Features:**
- 🛡️ **Path Injection Protection** - Validated mount directories prevent security vulnerabilities
- 🔐 **AWS Credentials Validation** - Pre-flight checks ensure S3 bucket access before mounting
- 📁 **Safe Environment Parsing** - Secure handling of configuration files and environment variables
- 🔍 **Mount Verification** - Comprehensive testing of mount functionality before proceeding
- ⚡ **FUSE Dependency Checking** - Automatic verification of macFUSE/FUSE requirements

**🚀 Advanced Mounting Capabilities:**
- 🔄 **Exact Path Matching** - Identical mount paths across local, Docker, and E2B environments
- ⚡ **Zero-Sync Latency** - Live filesystem access via high-performance goofys mounting
- 📁 **Dynamic Project Isolation** - Runtime project-based folders with configurable structures
- 🛠 **Cross-Platform Support** - Seamless operation on macOS and Linux with auto-installation
- 🔐 **Persistent Services** - Auto-mount on boot via systemd/launchd with proper configuration
- 🔧 **Flexible Configuration** - Boolean values accept multiple formats (true/yes/1/on/enabled)

**🏗️ Architecture Benefits:**
1. **Unified Data Layer**: All environments access the exact same S3-mounted directory
2. **No Path Translation**: Eliminates complexity with consistent `${S3_MOUNT_DIR}` across all systems
3. **Instant Availability**: Files written by data toolkits appear immediately in E2B sandboxes
4. **Secure Docker Integration**: Dynamic compose file selection with validated mount paths
5. **Production-Ready**: Enterprise security validation with comprehensive error handling

**How It Works:**
```bash
# Local System: Data toolkit saves to
${S3_MOUNT_DIR}/project_123/binance/price_data_1642567890.parquet

# Docker Container: Exact same path
${S3_MOUNT_DIR}/project_123/binance/price_data_1642567890.parquet  

# E2B Sandbox: Identical path structure
${S3_MOUNT_DIR}/project_123/binance/price_data_1642567890.parquet
```

Make sure that S3_MOUNT_DIR is universal across all platform as absolute path so the path of the files would be consistent.

**Perfect data consistency with zero configuration overhead!**

### 🐳 Docker S3 mounting with goofys (setup.sh pipeline)

When you run `./setup.sh` and choose Docker, the script:

1. Validates `S3_MOUNT_ENABLED` and `S3_MOUNT_DIR` from your `.env`.
2. If enabled and valid, starts Compose with `docker/docker-compose.yml` plus the S3 override `docker/docker-compose.s3.yml`.
3. The override grants FUSE permissions (`/dev/fuse`, `SYS_ADMIN`, apparmor unconfined) required for `goofys` inside the container.
4. The backend container entrypoint runs `/usr/local/bin/startup.sh`, which mounts S3 using `goofys` before launching the app.

macOS note (Docker mode): Docker Desktop does not support FUSE mounts inside containers. Our setup mounts S3 on the host at the universal path (`/opt/sentient`) and bind-mounts it into the container. The container startup detects the existing mount and verifies it maps to the intended bucket, skipping in-container goofys. On Linux Docker engines, the container can mount directly.

Pass additional `goofys` flags via the environment variable `GOOFYS_EXTRA_ARGS` in your `.env`:

```bash
# .env
S3_MOUNT_ENABLED=true
S3_MOUNT_DIR=/opt/sentient
S3_BUCKET_NAME=your-s3-bucket
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
AWS_REGION=us-east-1

# Optional: extra goofys flags
GOOFYS_EXTRA_ARGS="--allow-other --stat-cache-ttl=10s --type-cache-ttl=10s"
```

Notes:
- All variables from `.env` are injected into the backend container by Compose and read by `startup.sh`.
- The command specified in the image (`uv run python -m sentientresearchagent`) is forwarded unchanged by `startup.sh` via `exec "$@"`.

### Running the Application

#### Using Screen (Recommended)
```bash
# Start backend
screen -S backend_server
eval "$(pdm venv activate)"
python -m sentientresearchagent
# Press Ctrl+A, then D to detach

# Start frontend
screen -S frontend_server
cd frontend && npm run dev
# Press Ctrl+A, then D to detach

# View screens
screen -ls

# Reattach to screen
screen -r backend_server
```

#### Direct Run
```bash
# Terminal 1 - Backend
eval "$(pdm venv activate)"
python -m sentientresearchagent

# Terminal 2 - Frontend
cd frontend && npm run dev
```

## Environment Configuration

### API Keys
Both setup methods require API keys in the `.env` file:

```bash
# OpenRouter API Key (required)
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Optional API Keys
EXA_API_KEY=your_exa_api_key_here
GOOGLE_GENAI_API_KEY=your_google_genai_api_key_here
```

### Configuration Files
- **Main config**: `sentient.yaml`
- **Environment**: `.env` (created from `.env.example`)
- **Agent profiles**: `src/sentientresearchagent/hierarchical_agent_framework/agent_configs/profiles/`

## Troubleshooting

### Common Issues

#### Docker Issues
- **Port conflicts**: Ensure ports 5000 and 5173 are free
- **Permission denied**: Run Docker commands with sudo or add user to docker group
- **Build failures**: Clear Docker cache with `docker system prune`

#### Native Setup Issues
- **Python version**: Ensure Python 3.12 is active
- **PDM not found**: Add `~/.local/bin` to PATH
- **UV not found**: Source `~/.cargo/env`
- **Node version**: Use `nvm use 23.11.0` to switch versions

### Health Checks
```bash
# Check backend
curl http://localhost:5000/api/health

# Check frontend
curl http://localhost:3000
```

### Logs
- **Docker logs**: `cd docker && docker compose logs -f`
- **Native logs**: Check `logs/` directory in project root

## Development Workflow

### Making Changes
1. **Backend**: Changes in `src/` are auto-reloaded
2. **Frontend**: Vite HMR provides instant updates
3. **Config**: Restart services after changing `sentient.yaml`

### Using Different Agent Profiles
```bash
# With specific config
python -m sentientresearchagent --config sentient.yaml

# With different profile
python -m sentientresearchagent --profile deep_research_agent
```