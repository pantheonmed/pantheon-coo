# Pantheon COO OS — Operator Guide

For teams **deploying and running** COO in production.

## System requirements

- **Python 3.11+** for bare-metal installs; or **Docker** / **Railway** per `DEPLOYMENT_GUIDE.md`.
- **Anthropic API key** (required for core agents).
- **Disk** for SQLite DB and workspace (`WORKSPACE_DIR`, `DB_PATH`).
- Optional: **Redis** for distributed rate limits and HTTP caching; **PostgreSQL** when `POSTGRES_STORE_ENABLED` is adopted.

## Security checklist

- Set `AUTH_MODE=jwt` and a strong `JWT_SECRET`.
- Never commit `.env`; rotate keys if leaked.
- Use HTTPS in production (Railway/VPS/nginx terminate TLS).
- Restrict **admin** accounts; admin routes include `/admin/*`.
- Configure `ALLOWED_ORIGINS` / reverse proxy headers if exposing the API publicly.

## Backups

- **SQLite:** stop or use `VACUUM`/`sqlite3 .backup` during low traffic; copy `DB_PATH` and workspace regularly.
- **Docker:** persist the `pantheon_data` volume and snapshot it.
- Test restores on a staging instance quarterly.

## Monitoring

- **Liveness:** `GET /health` (includes `queue_depth`, `error_count_last_hour`, `alert_count_today` when error tracking is active).
- **Product metrics:** `GET /admin/analytics` (admin JWT).
- **Founder snapshot:** `GET /admin/dashboard-stats` (admin JWT).
- Wire external APM (OpenTelemetry flags in `.env`) for deeper traces.

## User management

- Registration: `POST /auth/register` (disable with `ALLOW_REGISTRATION=false`).
- Plans: stored on `users.plan`; billing via Razorpay/Stripe when configured.
- Password resets: implement via your policy (custom flow or support).

## Custom branding

- `WHITE_LABEL_*` settings and `GET/PATCH /admin/branding` for name, colors, logo.

## API keys

- Per-user keys: `POST /auth/reset-api-key` (JWT).
- Legacy static key: `AUTH_MODE=apikey` + `COO_API_KEY` (single-tenant only).

## Cost optimization

- Use **smaller Claude models** for fast paths (`CLAUDE_MODEL_FAST`).
- Enable **Redis** caching to cut repeat load on `/report`, analytics, and billing catalog.
- Cap **`MAX_LOOP_ITERATIONS`** and tune **`MIN_EVAL_SCORE`** for your risk tolerance.
- Archive old tasks from SQLite if the DB grows large (after backup).

## Support escalation

- Application logs: stdout / container logs.
- Error buffer: `GET /admin/errors` (admin).
- Security: `SECURITY.md`.
