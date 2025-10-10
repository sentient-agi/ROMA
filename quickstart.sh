#!/bin/bash
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

detect_os() {
  case "$(uname -s 2>/dev/null || echo "")" in
    Darwin) echo "macos" ;;
    Linux)
      if [[ -f /etc/debian_version ]]; then echo "debian"; else echo "linux"; fi
      ;;
    *) echo "unknown" ;;
  esac
}

open_url() {
  local url="$1"
  case "$(detect_os)" in
    macos) command -v open >/dev/null 2>&1 && open "$url" || true ;;
    debian|linux) command -v xdg-open >/dev/null 2>&1 && xdg-open "$url" >/dev/null 2>&1 || true ;;
    *) ;;
  esac
}

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

# Ensure screen is available
if ! command -v screen >/dev/null 2>&1; then
  print_warning "screen not found; please install it (brew install screen or sudo apt install screen)."
fi

# Kill existing sessions if any
screen -S backend_server -X quit >/dev/null 2>&1 || true
screen -S frontend_server -X quit >/dev/null 2>&1 || true

# Start backend in a detached screen
print_info "Starting backend in screen session 'backend_server'..."
screen -dmS backend_server bash -lc 'eval "$(pdm venv activate)" && python -m sentientresearchagent'

# Start frontend in a detached screen
print_info "Starting frontend in screen session 'frontend_server'..."
screen -dmS frontend_server bash -lc 'cd frontend && npm run dev'

# Wait for ports
backend_port=${FLASK_PORT:-8000}
print_info "Waiting for backend (http://localhost:$backend_port/api/health)..."
for i in {1..60}; do
  if curl -sf http://localhost:$backend_port/api/health >/dev/null 2>&1; then
    print_success "Backend is up."
    break
  fi
  sleep 1
  if [ "$i" -eq 60 ]; then print_warning "Backend still not responding; continuing."; fi
done

print_info "Waiting for frontend (http://localhost:3000)..."
for i in {1..60}; do
  if curl -sf http://localhost:3000 >/dev/null 2>&1; then
    print_success "Frontend is up."
    break
  fi
  sleep 1
  if [ "$i" -eq 60 ]; then print_warning "Frontend still not responding; continuing."; fi
done

# Open browser
open_url "http://localhost:3000"

echo ""
echo "========================================"
print_success "Quickstart complete!"
echo "========================================"
echo ""
echo "Screen commands:"
echo "  - List sessions: screen -ls"
echo "  - Reattach backend: screen -r backend_server"
echo "  - Reattach frontend: screen -r frontend_server"
echo "  - Kill session: screen -X -S <name> quit"
echo ""