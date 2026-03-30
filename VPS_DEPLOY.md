# Pantheon COO OS — VPS deployment (Ubuntu 22.04)

## Prerequisites

- **Ubuntu 22.04 LTS** (or compatible) cloud VM
- **DNS A record** pointing your domain to the server public IP
- **Ports 22, 80, 443** reachable (22 for SSH; 80/443 for HTTP/S)
- **Anthropic API key**
- **Git** access to your fork of the repo (update clone URL in `vps_setup.sh`)

## Step-by-step

1. **SSH** into the server as root or a sudo user.
2. Copy `vps_setup.sh` to the server (or clone the repo and run from project root).
3. **Edit** `vps_setup.sh` — set `git clone` URL to your fork if needed.
4. Run: `sudo bash vps_setup.sh`
5. Enter **domain**, **email** (Let's Encrypt), and **Anthropic API key** when prompted.
6. After completion, open `https://your-domain` and register / log in.

## Cost breakdown (indicative)

| Provider | Example droplet | ~Monthly |
|----------|------------------|----------|
| **DigitalOcean** | Basic 2 GB | ~$12–24 |
| **AWS** | t3.small + egress | varies by region |
| **Hetzner** | CX22 | ~€5–10 |

Add **Anthropic API** usage on top (usage-based).

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| **502 Bad Gateway** | `systemctl status pantheon-coo` — is uvicorn running? `journalctl -u pantheon-coo -n 100` |
| **SSL fails** | DNS must resolve to this server before certbot. Port 80 open? |
| **Permission errors** | `www-data` must own `WorkingDirectory` and `/tmp/pantheon_v2` |
| **Playwright / browser** | Run `sudo -u www-data ./venv/bin/python -m playwright install chromium` from app dir |

## Manual nginx / systemd

- Site file: `/etc/nginx/sites-available/pantheon-coo`
- Unit file: `/etc/systemd/system/pantheon-coo.service`
- Reload nginx: `sudo nginx -t && sudo systemctl reload nginx`
