#!/usr/bin/env bash
# Pantheon COO OS — VPS Setup Script
# Tested on Ubuntu 22.04 LTS
# Run as root or with sudo

set -euo pipefail

DOMAIN=""
EMAIL=""
PORT=8002

echo "Pantheon COO OS — VPS Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

read -r -p "Your domain (e.g. coo.yourcompany.com): " DOMAIN
read -r -p "Your email (for SSL certificate): " EMAIL
read -r -p "Anthropic API Key: " ANTHROPIC_KEY

# Update system
echo "Updating system..."
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get upgrade -y

# Install required packages
apt-get install -y \
  python3.11 python3.11-venv python3.11-dev python3-pip \
  nginx certbot python3-certbot-nginx \
  git curl wget ufw

# Configure firewall
ufw allow 22
ufw allow 80
ufw allow 443
ufw --force enable || true

# Clone repo
mkdir -p /opt
cd /opt
if [ ! -d pantheon-coo ]; then
  git clone https://github.com/yourusername/pantheon-coo pantheon-coo || {
    echo "ERROR: Clone failed. Set your fork URL inside vps_setup.sh"
    exit 1
  }
fi
APP_DIR="/opt/pantheon-coo/pantheon_v2"
if [ ! -d "$APP_DIR" ]; then
  APP_DIR="/opt/pantheon-coo"
fi
cd "$APP_DIR"

# Python setup
python3.11 -m venv venv
# shellcheck source=/dev/null
source venv/bin/activate
pip install -r requirements.txt --quiet
python3 -m playwright install chromium --with-deps

# Configure .env
cp -n .env.example .env 2>/dev/null || cp .env.example .env
JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
cat > .env << EOF
ANTHROPIC_API_KEY=$ANTHROPIC_KEY
JWT_SECRET=$JWT_SECRET
AUTH_MODE=jwt
PORT=$PORT
HOST=127.0.0.1
DEBUG=false
ALLOWED_ORIGINS=https://$DOMAIN
EOF

# Create systemd service
cat > /etc/systemd/system/pantheon-coo.service << EOF
[Unit]
Description=Pantheon COO OS
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR
Environment=PATH=$APP_DIR/venv/bin
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 127.0.0.1 --port $PORT --workers 2
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

chown -R www-data:www-data "$APP_DIR" /tmp/pantheon_v2 2>/dev/null || true
mkdir -p /tmp/pantheon_v2 && chown -R www-data:www-data /tmp/pantheon_v2

# Configure nginx
cat > /etc/nginx/sites-available/pantheon-coo << NGINX_EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_cache_bypass \$http_upgrade;

        proxy_buffering off;
        proxy_read_timeout 3600;
    }
}
NGINX_EOF

ln -sf /etc/nginx/sites-available/pantheon-coo /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

# SSL certificate
certbot --nginx -d "$DOMAIN" --non-interactive \
  --agree-tos --email "$EMAIL" || echo "WARN: certbot failed — configure SSL manually"

# Start service
systemctl daemon-reload
systemctl enable pantheon-coo
systemctl start pantheon-coo

echo ""
echo "✅ Pantheon COO OS deployed!"
echo "   URL: https://$DOMAIN"
echo "   Status: systemctl status pantheon-coo"
echo "   Logs: journalctl -u pantheon-coo -f"
