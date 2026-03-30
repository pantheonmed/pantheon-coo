#!/usr/bin/env bash
# run_all.sh — Start the complete Pantheon COO OS (backend + frontend)
#
# Usage:
#   ./run_all.sh            # production
#   ./run_all.sh --dev      # hot reload
#   ./run_all.sh --stop     # kill background processes
#   ./run_all.sh --status   # show running state
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
PID_DIR="/tmp/pantheon_v2/pids"
LOG_DIR="/tmp/pantheon_v2/logs"
mkdir -p "$PID_DIR" "$LOG_DIR"

if [ -f ".env" ]; then set -a; source .env; set +a; fi

PORT="${PORT:-8002}"
FRONTEND_PORT="${FRONTEND_PORT:-3002}"
HOST="${HOST:-0.0.0.0}"
AUTH_MODE="${AUTH_MODE:-none}"
COO_API_KEY="${COO_API_KEY:-}"
DEV_MODE=false

# ── Functions must be defined before they are called ──────────────────────────
_stop() {
  echo ""; echo "Stopping Pantheon COO OS..."; local stopped=0
  for pid_file in "$PID_DIR"/*.pid; do
    [ -f "$pid_file" ] || continue
    local pid; pid=$(cat "$pid_file"); local name; name=$(basename "$pid_file" .pid)
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null && echo "  Stopped $name (PID $pid)"; stopped=$((stopped+1))
    fi
    rm -f "$pid_file"
  done
  [ "$stopped" -eq 0 ] && echo "  No running processes found."; echo ""
}

_status() {
  echo ""; echo "Pantheon COO OS — Status"; echo "─────────────────────────"
  local any=false
  for pid_file in "$PID_DIR"/*.pid; do
    [ -f "$pid_file" ] || continue
    local pid; pid=$(cat "$pid_file"); local name; name=$(basename "$pid_file" .pid)
    if kill -0 "$pid" 2>/dev/null; then
      echo "  $name: RUNNING (PID $pid)"; any=true
    else
      echo "  $name: DEAD (stale)"; fi; done
  $any || echo "  No processes tracked."; echo ""
}

_check_port() {
  if lsof -ti tcp:"$1" >/dev/null 2>&1; then
    echo "ERROR: Port $1 ($2) already in use. Run --stop or change $2= in .env"; exit 1; fi
}

# ── Argument parsing ──────────────────────────────────────────────────────────
for arg in "$@"; do
  case $arg in
    --dev)    DEV_MODE=true ;;
    --stop)   _stop; exit 0 ;;
    --status) _status; exit 0 ;;
    --help|-h) echo "Usage: $0 [--dev|--stop|--status]"; exit 0 ;;
  esac
done

# ── Pre-flight ────────────────────────────────────────────────────────────────
[ -z "${ANTHROPIC_API_KEY:-}" ] && { echo "ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env"; exit 1; }
_check_port "$PORT" "PORT"
_check_port "$FRONTEND_PORT" "FRONTEND_PORT"
mkdir -p /tmp/pantheon_v2/screenshots /tmp/pantheon_v2/logs tools/custom

MODE_LABEL="PRODUCTION"; [ "$DEV_MODE" = true ] && MODE_LABEL="DEVELOPMENT (hot reload)"
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║         Pantheon COO OS v2 — Starting               ║"
echo "╠══════════════════════════════════════════════════════╣"
printf "║  Backend  : http://localhost:%-26s║\n" "$PORT"
printf "║  Dashboard: http://localhost:%-26s║\n" "$FRONTEND_PORT"
printf "║  Auth     : %-42s║\n" "$AUTH_MODE"
printf "║  Mode     : %-42s║\n" "$MODE_LABEL"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── Start backend ─────────────────────────────────────────────────────────────
echo "▶ Starting backend on port $PORT..."
if [ "$DEV_MODE" = true ]; then
  uvicorn main:app --host "$HOST" --port "$PORT" --reload >> "$LOG_DIR/backend.log" 2>&1 &
else
  uvicorn main:app --host "$HOST" --port "$PORT" >> "$LOG_DIR/backend.log" 2>&1 &
fi
BACKEND_PID=$!; echo "$BACKEND_PID" > "$PID_DIR/backend.pid"

printf "  Waiting for backend"
for i in $(seq 1 30); do
  if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    echo " ready (${i}s)"; break; fi
  printf "."; sleep 1
  if [ "$i" -eq 30 ]; then
    echo " TIMEOUT"; echo "Check: tail $LOG_DIR/backend.log"; kill "$BACKEND_PID" 2>/dev/null; exit 1; fi
done

# ── Start frontend ────────────────────────────────────────────────────────────
echo "▶ Starting dashboard on port $FRONTEND_PORT..."
SERVE_DIR=$(mktemp -d); cp -r static/* "$SERVE_DIR"/

CONFIG_JS="window.PANTHEON_CONFIG = { apiUrl: 'http://localhost:${PORT}'"
[ "$AUTH_MODE" = "apikey" ] && [ -n "$COO_API_KEY" ] && \
  CONFIG_JS="${CONFIG_JS}, apiKey: '${COO_API_KEY}'"
CONFIG_JS="${CONFIG_JS} };"

sed -i "s|</head>|<script>${CONFIG_JS}</script></head>|" "$SERVE_DIR/dashboard.html"
python3 -m http.server "$FRONTEND_PORT" --bind "$HOST" --directory "$SERVE_DIR" \
  >> "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!; echo "$FRONTEND_PID" > "$PID_DIR/frontend.pid"
sleep 1
kill -0 "$FRONTEND_PID" 2>/dev/null || { echo "ERROR: Frontend failed"; _stop; exit 1; }
echo "  Dashboard ready"

echo ""
echo "  Dashboard →  http://localhost:${FRONTEND_PORT}"
echo "  API       →  http://localhost:${PORT}"
echo "  Docs      →  http://localhost:${PORT}/docs"
echo "  Logs      →  tail -f $LOG_DIR/backend.log"
echo "  Stop      →  ./run_all.sh --stop"
echo ""

_cleanup() { _stop; rm -rf "$SERVE_DIR"; exit 0; }
trap '_cleanup' SIGINT SIGTERM

if [ -t 1 ]; then tail -f "$LOG_DIR/backend.log"; else wait "$BACKEND_PID"; fi
