# Installing Pantheon COO OS

## Universal installer (macOS / Linux)

From the project root (this repo):

```bash
chmod +x install.sh uninstall.sh
./install.sh
```

Or pipe from a hosted URL (after you publish `install.sh`):

```bash
curl -sSL https://get.pantheon.ai | bash
```

**Before running:** set `REPO_URL` in `install.sh` (or in the environment) to your GitHub fork if the default placeholder is not your repo.

The script:

- Requires **Python 3.11+**, **git**, and **pip**
- Clones or updates `~/pantheon-coo` (override with `INSTALL_DIR`)
- Installs `requirements.txt`, Chromium for Playwright, and seeds `.env` on first run

**Remove** an install:

```bash
chmod +x uninstall.sh
./uninstall.sh
```

## Other options

| Method | Doc |
|--------|-----|
| Docker | [DOCKER.md](DOCKER.md) |
| Railway | [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md) |
| VPS (Ubuntu 22.04) | [VPS_DEPLOY.md](VPS_DEPLOY.md) |
| Full comparison | [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) |
