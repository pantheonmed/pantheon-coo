#!/bin/sh
# docker/entrypoint.sh
# Injects window.PANTHEON_CONFIG into dashboard.html at container startup.
# This runs as part of nginx's /docker-entrypoint.d/ pipeline.

BACKEND_URL="${BACKEND_URL:-http://localhost:8002}"
HTML="/usr/share/nginx/html/dashboard.html"
INJECT="<script>window.PANTHEON_CONFIG = { apiUrl: '' };</script>"

# When served via nginx proxy (same origin), apiUrl can be empty.
# When accessed cross-origin, inject the actual backend URL.
if grep -q "PANTHEON_CONFIG" "$HTML"; then
  echo "[entrypoint] window.PANTHEON_CONFIG already present in dashboard.html"
else
  sed -i "s|</head>|${INJECT}</head>|" "$HTML"
  echo "[entrypoint] Injected PANTHEON_CONFIG into dashboard.html"
fi

# Also substitute BACKEND_URL in nginx.conf (for proxy_pass)
envsubst '${BACKEND_URL}' < /etc/nginx/conf.d/default.conf > /tmp/default.conf.tmp
mv /tmp/default.conf.tmp /etc/nginx/conf.d/default.conf
echo "[entrypoint] nginx.conf configured with BACKEND_URL=${BACKEND_URL}"
