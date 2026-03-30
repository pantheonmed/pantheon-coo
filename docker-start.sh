#!/usr/bin/env bash
# Pantheon COO OS — Docker Quick Start
# Requirements: Docker (Compose v2) installed
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Pantheon COO OS — Docker Setup"
echo ""

if ! command -v docker &> /dev/null; then
  echo "ERROR: Docker not found. Install Docker Desktop or engine + compose plugin."
  exit 1
fi

read -r -p "Anthropic API Key: " API_KEY
read -r -p "Admin Email: " ADMIN_EMAIL
read -r -p "Admin Password: " ADMIN_PASSWORD

JWT_SECRET=$(openssl rand -base64 32 2>/dev/null || python3 -c "import secrets; print(secrets.token_urlsafe(32))")

cat > .env << EOF
ANTHROPIC_API_KEY=$API_KEY
JWT_SECRET=$JWT_SECRET
AUTH_MODE=jwt
ADMIN_EMAIL=$ADMIN_EMAIL
ADMIN_PASSWORD=$ADMIN_PASSWORD
PORT=8002
EOF

docker compose up -d --build

echo ""
echo "✅ Started!"
echo "   Dashboard / API: http://localhost:8002"
echo "   Static UI: http://localhost:8002/app"
echo "   Stop: docker compose down"
