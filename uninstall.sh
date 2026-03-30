#!/usr/bin/env bash
# Pantheon COO OS — Remove local installation cloned by install.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/pantheon-coo}"

echo "Pantheon COO OS — Uninstall"
echo "Target directory: $INSTALL_DIR"
echo ""

# Stop tracked processes if run_all.sh exists
if [ -f "$INSTALL_DIR/pantheon_v2/run_all.sh" ]; then
  (cd "$INSTALL_DIR/pantheon_v2" && ./run_all.sh --stop) 2>/dev/null || true
elif [ -f "$INSTALL_DIR/run_all.sh" ]; then
  (cd "$INSTALL_DIR" && ./run_all.sh --stop) 2>/dev/null || true
fi

# Best-effort: stop uvicorn for this app
pkill -f "uvicorn main:app" 2>/dev/null || true

read -r -p "Permanently delete $INSTALL_DIR? Type 'yes' to confirm: " ok
if [ "$ok" != "yes" ]; then
  echo "Aborted."
  exit 0
fi

rm -rf "$INSTALL_DIR"
echo "Removed $INSTALL_DIR"
