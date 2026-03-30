#!/usr/bin/env bash
# Pantheon COO OS — Universal Installer
# Usage: curl -sSL https://get.pantheon.ai | bash
# Or: ./install.sh

set -e

REPO_URL="${REPO_URL:-https://github.com/yourusername/pantheon-coo}"
INSTALL_DIR="${INSTALL_DIR:-$HOME/pantheon-coo}"
PORT=8002

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Pantheon COO OS — Installer        ║"
echo "╚══════════════════════════════════════╝"
echo ""

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "darwin"* ]]; then
  OS="mac"
elif [[ "$OSTYPE" == "linux-gnu"* ]] || [[ "$OSTYPE" == "linux"* ]]; then
  OS="linux"
fi
echo "Detected OS: $OS"

# Check Python 3.11+
if ! command -v python3 &> /dev/null; then
  echo "ERROR: Python 3 not found."
  if [ "$OS" == "mac" ]; then
    echo "Install from: https://python.org or run: brew install python@3.11"
  else
    echo "Run: sudo apt install python3.11 python3.11-venv python3-pip"
  fi
  exit 1
fi
if ! python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>/dev/null; then
  echo "ERROR: Python 3.11+ required (found: $(python3 --version 2>&1))"
  exit 1
fi
echo "✓ Python3 found ($(python3 --version 2>&1))"

# Check if git available
if ! command -v git &> /dev/null; then
  echo "ERROR: git not found."
  echo "Install git first: https://git-scm.com"
  exit 1
fi
echo "✓ git found"

# Clone or update repo
if [ -d "$INSTALL_DIR/.git" ] || [ -f "$INSTALL_DIR/pantheon_v2/requirements.txt" ]; then
  echo "Updating existing installation..."
  if [ -d "$INSTALL_DIR/.git" ]; then
    cd "$INSTALL_DIR"
    git pull || true
  fi
else
  echo "Downloading Pantheon COO OS..."
  git clone "$REPO_URL" "$INSTALL_DIR" || {
    echo "ERROR: git clone failed. Set REPO_URL to your fork."
    exit 1
  }
fi

# Resolve app directory (monorepo pantheon_v2/ or flat checkout)
APP_DIR="$INSTALL_DIR"
if [ -d "$INSTALL_DIR/pantheon_v2" ]; then
  APP_DIR="$INSTALL_DIR/pantheon_v2"
fi
cd "$APP_DIR"
if [ ! -f "requirements.txt" ]; then
  echo "ERROR: requirements.txt not found in $APP_DIR — check REPO_URL layout (expect pantheon_v2/ or repo root)."
  exit 1
fi

# Install Python dependencies
echo "Installing dependencies..."
PIP_FLAGS=(install -r requirements.txt --quiet)
if python3 -m pip install --help 2>/dev/null | grep -q break-system-packages; then
  PIP_FLAGS+=(--break-system-packages)
fi
python3 -m pip "${PIP_FLAGS[@]}"

# Install Playwright browsers
echo "Installing browser automation..."
python3 -m playwright install chromium --with-deps 2>/dev/null || \
python3 -m playwright install chromium

# Setup .env if not exists
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "SETUP REQUIRED"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo ""
  echo "Get your API key from:"
  echo "https://console.anthropic.com → API Keys"
  echo ""
  if [ -t 0 ]; then
    read -r -p "Paste your Anthropic API key: " api_key || true
    if [ -n "${api_key:-}" ]; then
      if [[ "$OS" == "mac" ]]; then
        sed -i.bak "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$api_key|" .env
      else
        sed -i.bak "s|^ANTHROPIC_API_KEY=.*|ANTHROPIC_API_KEY=$api_key|" .env
      fi
      echo "✓ API key saved"
    else
      echo "WARN: No key pasted. Edit $APP_DIR/.env and set ANTHROPIC_API_KEY."
    fi
  else
    echo "Non-interactive shell: edit .env and set ANTHROPIC_API_KEY."
  fi

  JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
  if [[ "$OS" == "mac" ]]; then
    sed -i.bak "s|^# JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" .env 2>/dev/null || true
    sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" .env 2>/dev/null || true
    sed -i.bak "s|^AUTH_MODE=none|AUTH_MODE=jwt|" .env 2>/dev/null || true
  else
    sed -i.bak "s|^# JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" .env 2>/dev/null || true
    sed -i.bak "s|^JWT_SECRET=.*|JWT_SECRET=$JWT_SECRET|" .env 2>/dev/null || true
    sed -i.bak "s|^AUTH_MODE=none|AUTH_MODE=jwt|" .env 2>/dev/null || true
  fi
  echo "✓ Security configured (JWT_SECRET, AUTH_MODE=jwt)"
fi

# Make scripts executable
chmod +x run_all.sh run_backend.sh run_frontend.sh 2>/dev/null || true

# Test the installation
echo ""
echo "Testing installation..."
python3 -c "import fastapi, anthropic, aiosqlite; print('✓ All dependencies OK')"

echo ""
echo "╔══════════════════════════════════════╗"
echo "║   Installation Complete!             ║"
echo "╠══════════════════════════════════════╣"
echo "║  Start:     ./run_all.sh             ║"
echo "║  Dashboard: http://localhost:${PORT} (API; use FRONTEND_PORT for static UI) ║"
echo "║  Docs:      http://localhost:${PORT}/docs ║"
echo "╚══════════════════════════════════════╝"
echo ""

if [ -t 0 ]; then
  read -r -p "To start now? (y/n) " start_now || true
  if [ "${start_now:-}" = "y" ] || [ "${start_now:-}" = "Y" ]; then
    ./run_all.sh
  fi
fi
