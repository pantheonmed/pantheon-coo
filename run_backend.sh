#!/usr/bin/env bash
# run_backend.sh — Start Pantheon COO OS backend on port 8002
# Usage: ./run_backend.sh [--dev]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Load .env if present ──────────────────────────────────────────────────────
if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

PORT="${PORT:-8002}"
HOST="${HOST:-0.0.0.0}"
WORKERS="${WORKERS:-1}"
DEV_MODE=false

for arg in "$@"; do
  case $arg in
    --dev) DEV_MODE=true ;;
  esac
done

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ERROR: ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
  exit 1
fi

# Check port not already in use
if lsof -ti tcp:"$PORT" >/dev/null 2>&1; then
  echo "ERROR: Port $PORT is already in use. Set PORT= in .env to use a different port."
  exit 1
fi

# Create workspace
mkdir -p /tmp/pantheon_v2
mkdir -p /tmp/pantheon_v2/screenshots
mkdir -p tools/custom

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Pantheon COO OS — Backend"
echo "  Host : $HOST"
echo "  Port : $PORT"
echo "  Mode : $([ "$DEV_MODE" = true ] && echo 'development (reload)' || echo 'production')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$DEV_MODE" = true ]; then
  exec uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --reload \
    --reload-dir . \
    --log-level info
else
  exec uvicorn main:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level info
fi
