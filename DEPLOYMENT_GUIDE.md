# Pantheon COO OS — deployment guide

Choose how you run the COO backend and dashboard. All paths assume you have an **Anthropic API key** and (for production) **JWT_SECRET** and strong auth settings.

## Options at a glance

| Option | Best for | Ops burden | Notes |
|--------|-----------|------------|--------|
| **Local installer** (`install.sh`) | Developers, single machine | Low | macOS/Linux; uses `run_all.sh` for API + static dashboard |
| **Docker** (`docker-start.sh` / Compose) | Teams with Docker already | Low | Image `pantheonai/coo-os:latest` + local build fallback in `docker-compose.yml` |
| **Railway** | Fast HTTPS deploy, Git push | Low | See `railway.json`, `RAILWAY_DEPLOY.md`, `.railway.env.example` |
| **VPS** (Ubuntu 22.04) | Full control, custom domain, compliance | Medium | `vps_setup.sh`, nginx, systemd, certbot — `VPS_DEPLOY.md` |

## Cost comparison (indicative)

| Item | Rough range |
|------|-------------|
| **Anthropic API** | Usage-based (main variable cost) |
| **Railway Hobby** | ~$5/mo + egress |
| **VPS (Hetzner / DO / AWS)** | ~€5–25/mo for a small VM |
| **Docker locally** | No hosting fee; only API usage |

## What to configure everywhere

- `ANTHROPIC_API_KEY` (required)
- `AUTH_MODE=jwt` in production
- `JWT_SECRET` (strong random)
- Optional: `RAZORPAY_*`, `STRIPE_*`, WhatsApp, email, etc. (see `.env.example`)

## Links

- [INSTALL.md](INSTALL.md) — `install.sh` / `uninstall.sh`
- [DOCKER.md](DOCKER.md) — Compose + `docker-start.sh`
- [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md)
- [VPS_DEPLOY.md](VPS_DEPLOY.md)

After deploy, open `/app` or `/` for the dashboard and `/docs` for the OpenAPI UI.
