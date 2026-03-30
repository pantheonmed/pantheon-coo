#!/usr/bin/env bash
# run_frontend.sh — Serve Pantheon COO OS dashboard on port 3002
# Injects the backend API URL into the page so the dashboard knows where to call.
# Usage: ./run_frontend.sh [--backend-url http://localhost:8002]
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

FRONTEND_PORT="${FRONTEND_PORT:-3002}"
FRONTEND_HOST="${FRONTEND_HOST:-0.0.0.0}"
BACKEND_PORT="${PORT:-8002}"
BACKEND_URL="http://localhost:${BACKEND_PORT}"

# Allow --backend-url override
for i in "$@"; do
  case $i in
    --backend-url=*) BACKEND_URL="${i#*=}" ;;
    --backend-url)   shift; BACKEND_URL="$1" ;;
  esac
done

# ── Port check ────────────────────────────────────────────────────────────────
if lsof -ti tcp:"$FRONTEND_PORT" >/dev/null 2>&1; then
  echo "ERROR: Port $FRONTEND_PORT is already in use. Set FRONTEND_PORT= in .env."
  exit 1
fi

# ── Build served HTML with injected config ────────────────────────────────────
# Creates a temporary served directory so the original dashboard.html is untouched.
SERVE_DIR="$(mktemp -d)"
trap 'rm -rf "$SERVE_DIR"' EXIT

# Copy static assets
cp -r static/* "$SERVE_DIR"/

# Inject window.PANTHEON_CONFIG before </head> so the dashboard uses the right API URL
INJECT="<script>window.PANTHEON_CONFIG = { apiUrl: '${BACKEND_URL}' };</script>"
sed -i "s|</head>|${INJECT}</head>|" "$SERVE_DIR/dashboard.html"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Pantheon COO OS — Dashboard"
echo "  Frontend : http://localhost:${FRONTEND_PORT}"
echo "  Backend  : ${BACKEND_URL}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Serve ─────────────────────────────────────────────────────────────────────
# Use Python's built-in HTTP server — no extra dependencies needed.
# For production, swap with nginx pointing at static/ with proxy_pass to backend.
exec python3 -m http.server "$FRONTEND_PORT" \
  --bind "$FRONTEND_HOST" \
  --directory "$SERVE_DIR"
