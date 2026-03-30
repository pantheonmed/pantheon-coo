## Run with Docker (easiest for technical users)

### Requirements

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine + Compose v2 plugin)

### One-command start

```bash
bash docker-start.sh
```

Follow prompts for API key and admin account.

### Manual start

```bash
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY, JWT_SECRET, AUTH_MODE=jwt, etc.
docker compose up -d --build
```

The first run builds the image locally if `pantheonai/coo-os:latest` is not pulled yet (`build` is defined alongside `image` in `docker-compose.yml`).

### Useful commands

| Command | Purpose |
|---------|---------|
| `docker compose logs -f` | Follow logs |
| `docker compose down` | Stop containers |
| `docker compose restart` | Restart services |
| `docker compose pull` | Pull published image (when using registry only) |

### Optional services

```bash
docker compose --profile postgres up -d postgres
docker compose --profile redis up -d redis
```
