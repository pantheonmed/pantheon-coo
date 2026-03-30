# Pantheon COO OS

[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-CI-2088FF?logo=githubactions&logoColor=white)](.github/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/pytest-550%2B-passing-brightgreen)](CONTRIBUTING.md#running-tests)

**Autonomous AI Chief Operating Officer** — a multi-agent execution system that thinks, plans, executes, evaluates, and continuously improves.

After you publish the repo, add a live workflow badge: `https://github.com/<owner>/<repo>/actions/workflows/ci.yml/badge.svg` in this README and **[star the repo](https://github.com/pantheonai/pantheon-coo-os)** once it exists (update the link to your canonical URL).

## What it is

Not a chatbot. Not a script runner. A system that accepts a natural-language goal and drives it to completion through a 6-agent autonomous loop — retrying on failure, learning from every execution, building new tools for repeated patterns, and monitoring its own performance.

```
Goal → Reason → Plan → Execute → Evaluate → Learn → Repeat
```

## Quick start

```bash
git clone <repo>
cd pantheon_v2
make setup                   # install deps + copy .env template
# edit .env — set ANTHROPIC_API_KEY
make dev                     # start backend:8002 + dashboard:3002
```

Open `http://localhost:3002` — type a command — watch it execute.

## Installation options

| Method | When to use | Doc |
|--------|----------------|-----|
| **Make / local** | Day-to-day development | [Quick start](#quick-start) above |
| **`install.sh`** | macOS/Linux one-shot clone + deps | [INSTALL.md](INSTALL.md) |
| **Docker** | Any machine with Docker | [DOCKER.md](DOCKER.md), `docker-start.sh` |
| **Railway** | Managed HTTPS, Git deploy | [RAILWAY_DEPLOY.md](RAILWAY_DEPLOY.md) |
| **VPS** | Your own domain + full control | [VPS_DEPLOY.md](VPS_DEPLOY.md) |

See **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** for a full comparison and rough costs.

**Kubernetes:** see **[k8s/README.md](k8s/README.md)** — `Deployment` + `Service` (LoadBalancer) + `HorizontalPodAutoscaler`; readiness probe hits **`GET /ready`** on port 8002.

**Teams & marketplace:** `POST /teams` + invite codes; shared task board via `GET /teams/{id}/tasks`. **`GET /marketplace`** lists approved tools; authors publish with `POST /marketplace/publish` (admin approves). Revenue share **70% author / 30% platform** on paid purchases.

**ML pipeline:** `ml/README.md` — export high-scoring tasks to JSONL via **`GET /admin/ml/stats`** and **`POST /admin/ml/export`** (admin JWT).

**Onboarding:** public `GET /onboarding/samples?industry=medical|retail|tech|finance|other`, `GET /tutorials`; welcome email template `templates/emails/welcome.html`; dashboard first-login tour. **Pricing:** `GET /landing` — Free / Starter / Pro with multi-currency toggle; in-app usage bar and upgrade modal when monthly task limits are reached. **Team plans** `team_5` / `team_25` appear in **`GET /billing/plans`**.

## Agents

| Agent | Role |
|---|---|
| **Reasoning** | Understands intent, defines success criteria, flags risk |
| **Planning** | Converts reasoning into typed, ordered execution steps |
| **Execution** | Runs tools concurrently, respects dependencies, retries with backoff |
| **Evaluator** | Scores 0–1, decides done vs. loop again |
| **Memory** | Distills learnings, stores by goal type, recalls before each task |
| **Tool Builder** | Detects repeated patterns, writes new Python tool modules |
| **Decomposer** | Breaks high-level goals into parallel sub-tasks |
| **Briefing** | Generates daily COO reports, distributes via email + WhatsApp |

## Tools

| Tool | Phase | Capabilities |
|---|---|---|
| Filesystem | 1 | read, write, list, mkdir, delete |
| Terminal | 1 | safe subprocess (command allowlist) |
| Browser | 2 | Playwright: navigate, click, fill_form, screenshot |
| HTTP | 2 | GET, POST, PUT, DELETE, webhooks |
| Email | 3 | SMTP + Resend, HTML reports |
| Custom | 3 | Tool Builder generates and hot-loads these |

## API

```bash
# Execute a command
curl -X POST http://localhost:8002/execute \
  -H "Content-Type: application/json" \
  -d '{"command": "Check disk space and write a report to workspace"}'

# Poll for result
curl http://localhost:8002/tasks/{task_id}

# Real-time log stream
curl -N http://localhost:8002/tasks/{task_id}/stream

# Retry a failed task
curl -X POST http://localhost:8002/tasks/{task_id}/retry

# Create a project (multi-task goal)
curl -X POST http://localhost:8002/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "Competitor analysis", "goal": "Research 3 competitors and write a comparison report"}'

# Daily briefing
curl -X POST http://localhost:8002/briefing \
  -d '{"recipients": ["you@example.com"]}'
```

Full API docs: `http://localhost:8002/docs`

## Configuration

Copy `.env.example` to `.env`:

```bash
ANTHROPIC_API_KEY=sk-ant-...     # required
PORT=8002                         # backend port
FRONTEND_PORT=3002                # dashboard port
AUTH_MODE=none                    # none | apikey | jwt
COO_API_KEY=                      # run: make key
MAX_LOOP_ITERATIONS=5             # max retry loops per task
MIN_EVAL_SCORE=0.75               # score threshold for DONE
```

## Make commands

```bash
make dev          # start with hot reload
make test         # run full pytest suite (~460+ tests)
make coverage     # tests + HTML coverage report
make lint         # ruff linter
make fmt          # ruff formatter
make migrate      # run DB migrations
make docker-up    # start via Docker Compose
make key          # generate new API key
make help         # all targets
```

## Multi-language (12 locales)

- **API:** `GET /i18n/languages` (flags + RTL), `GET /i18n/translations/{code}` for dashboard copy.
- **Detection:** `?lang=` query, `Accept-Language`, or saved user preference (`PATCH /auth/me/language` with JWT).
- **Agents:** Reasoning and planning prompts include “respond in the user’s language” so JSON text fields match the UI locale.
- **Dashboard:** header language selector, RTL layout for Arabic (`static/dashboard.html`). Marketing sample: `GET /landing`.

## Global pricing & payments

- **Currencies:** `INR`, `USD`, `GBP`, `EUR`, `AED`, `JPY`, `BRL`, `IDR`, `SGD`, `NGN` (config `supported_currencies` + `GLOBAL_PRICING` for major regions).
- **Gateways:** **Razorpay** for INR checkouts; **Stripe** `PaymentIntent` for other currencies when `STRIPE_*` keys are set.
- **Registration:** optional `country_code` sets default `currency`, `timezone`, and `locale` (`TIMEZONE_BY_COUNTRY`, `COUNTRY_TO_CURRENCY`, `LOCALE_BY_COUNTRY`).
- **Catalog:** `GET /billing/plans?currency=USD` returns localized starter/pro/enterprise labels.

## Amazon & Meesho (seller tools)

- **`AMAZON_SELLER`:** `get_orders`, `get_inventory`, `get_sales_report`, `update_price`, `get_reviews` against Selling Partner API–style HTTP (configure `AMAZON_*` keys; default marketplace India `A21TJRUUN4KGV`).
- **`MEESHO`:** orders, catalog, payments, inventory sync (`MEESHO_API_KEY`, `MEESHO_SUPPLIER_ID`).
- Templates: `amazon_daily_report`, `amazon_inventory_alert`, `amazon_review_monitor`, `meesho_orders`, `biovital_meesho`.

## Timezone & locale formatting

- User fields `timezone`, `locale`; `PATCH /auth/me/timezone` returns `current_time_for_user`.
- **`utils/timezone.py`:** `now_for_user`, `utc_to_user_tz` (pytz).
- **`utils/locale_format.py`:** `format_currency`, `format_number`, `format_date` for en-IN, en-US, de-DE, ja-JP, ar-AE, etc.
- **Scheduler:** each schedule stores `timezone`; cron “9:00” is evaluated in that zone, `next_run_at` stored in UTC.

## Integrations

### Voice (WhatsApp / Telegram / API)

1. Set `OPENAI_API_KEY` (Whisper + TTS use the same key as other OpenAI features).
2. Set `VOICE_ENABLED=true` so inbound WhatsApp audio and Telegram voice/audio messages are transcribed and executed (otherwise users get a short setup hint).
3. **HTTP API:** `POST /voice/transcribe` with multipart file (optional query `auto_execute=true` to queue a COO task); `GET /voice/speak?text=...` returns MP3 for playback.
4. **WhatsApp:** Incoming audio messages are transcribed; after the task finishes, a short spoken summary is sent back as audio when voice mode is active.

### Google Sheets

1. Create a Google Cloud project and enable the **Google Sheets API**.
2. Create a **service account**, download the JSON key, and share your spreadsheet with the service account email (Editor).
3. Set `GOOGLE_SERVICE_ACCOUNT_JSON` to the key file path **or** paste the JSON string into `.env` (see `.env.example`).
4. Use the built-in tool `GOOGLE_SHEETS` (read/write/append/clear/create) or the **Templates** tab entries for export/analysis flows.

### Telegram bot

1. Create a bot with [@BotFather](https://t.me/BotFather), copy the token into `TELEGRAM_BOT_TOKEN`.
2. Optionally set `TELEGRAM_WEBHOOK_SECRET` and register it as Telegram’s `secret_token` when calling `setWebhook`.
3. Expose `POST /webhook/telegram` over HTTPS; call `GET /webhook/telegram/setup` once to register the webhook URL with Telegram (requires the token).
4. Users who submit tasks via Telegram receive completion messages via the Bot API (`notifications.send_telegram`).

### Outbound webhooks (HTTPS)

1. With `AUTH_MODE=jwt`, authenticate and `POST /webhooks` with `{ "url": "https://your.app/hooks/pantheon", "events": ["task.completed","task.failed"] }`.
2. The response returns `webhook_id` and a **secret** (shown once). Your endpoint must use HTTPS.
3. Deliveries are `POST`ed with JSON `{"event","data","ts"}` and header `X-Pantheon-Signature: sha256=<hmac>` over the raw body. Verify with the secret before trusting payloads.
4. List subscriptions with `GET /webhooks` (only the last 4 characters of the secret are shown), inspect `GET /webhooks/{id}/logs`, and `DELETE /webhooks/{id}` to deactivate.

### PWA / mobile dashboard

- Open `/app` or `/` for the dashboard. On small screens, a **+** floating action button opens a quick command sheet.
- `GET /static/manifest.json` and `/static/icon.svg` support “Add to Home Screen” (manifest `start_url`: `/app`, theme color aligned with the UI).

### Native mobile app (Expo)

- Folder: **`mobile_app/`** — React Native (Expo ~51) + TypeScript, dark theme aligned with the web dashboard.
- **Install:** `cd mobile_app && npm install`
- **Run:** `npx expo start` (scan QR in Expo Go or run iOS/Android simulators).
- **API URL:** open **Settings** in the app and set the backend base URL (default `http://localhost:8002`; use your machine’s LAN IP for a physical device).
- **Screens:** Login (`POST /auth/login`, token in AsyncStorage), Dashboard (execute + task list, pull-to-refresh + 5s poll), Task detail (logs / plan / evaluation tabs), Voice (`POST /voice/transcribe` → execute), Settings (plan/usage, logout, app version).
- **Tabs:** Home, History, Voice, Settings.

### Chrome extension

- Folder: **`chrome_extension/`** — Manifest V3: popup command runner, optional login, last tasks, **Send page content to COO**, context menu on selected text, background notifications when tasks complete.
- **Install:** Chrome → Extensions → Developer mode → Load unpacked → select `chrome_extension/`.
- Set the **API URL** in the popup (default `http://localhost:8002`). Match `host_permissions` in `manifest.json` if you use a different origin.

### Real-time collaboration & shared tasks

- **Multi-viewer SSE:** `GET /tasks/{id}/stream` supports multiple simultaneous subscribers (each client gets its own queue; events broadcast to all).
- **Share link (24h):** Authenticated `POST /tasks/{task_id}/share` returns `{ share_url, expires_at }`. Public **`GET /shared/{token}`** returns read-only task + logs; **`GET /shared/{token}/stream`** is the public SSE stream.
- **Dashboard:** each task row has **Share** (copies URL) and a live **watching** count from `GET /tasks/{id}/watchers`.

### Zapier

- **Inbound (Zap → COO):** `POST /webhook/zapier` with JSON `{ "command": "...", "user_email": "...", "data": {} }` and header **`X-Zapier-Secret`** matching **`ZAPIER_WEBHOOK_SECRET`** in `.env`. Response includes `task_id` and status URL for follow-up Zaps.
- **Tool `ZAPIER`:** `send_to_webhook` / `trigger_zap` for outbound HTTP to Zapier catch hooks (sandbox blocks disallowed URLs such as localhost).

### HubSpot CRM

- Set **`HUBSPOT_API_KEY`** (private app token with CRM scopes).
- Tool **`HUBSPOT`:** contacts, deals, pipeline queries, transactional-style email helper — HubSpot API v3 at `https://api.hubapi.com`.
- Templates: `hubspot_lead`, `hubspot_pipeline`.

### WordPress & Shopify

- **WordPress:** `WORDPRESS_SITE_URL`, `WORDPRESS_USERNAME`, `WORDPRESS_APP_PASSWORD` (application password). Tool **`WORDPRESS`** uses `{site}/wp-json/wp/v2` for posts and pages.
- **Shopify:** `SHOPIFY_STORE_DOMAIN` (e.g. `your-shop.myshopify.com`), `SHOPIFY_ACCESS_TOKEN`. Tool **`SHOPIFY`** uses Admin REST `2024-01`.
- Templates: `wp_blog_post`, `shopify_daily_report`.

### Trading analysis (educational only)

- Tool **`MARKET_DATA`**: Yahoo Finance chart + quoteSummary — quotes, history, news, indices (NIFTY/SENSEX/BANKNIFTY), a small filtered screener.
- Agent **`trading_analyst`**: structured JSON commentary with a mandatory non-advice disclaimer (not trade execution).
- Templates: `stock_analysis`, `portfolio_report`, `market_screener`. Symbols are sandbox-validated (`[A-Z0-9.^\\-]{1,20}`).

### Website builder

- Tool **`WEBSITE_BUILDER`**: Claude-generated single-file HTML (landing, portfolio, product pages), `optimize_seo` meta injection, `add_section` for structured blocks under `workspace/websites/`.
- Templates: `business_website`, `medical_website`.

### Content & CFO tools

- **`CONTENT_CREATOR`**: blog, social, email, ad copy, 30-day calendars → `workspace/content/*.md`.
- **`FINANCE`**: GST (0/5/12/18/28%), GST invoices (HTML), P&L, cashflow, expense categorization — deterministic Python (no LLM).
- Templates include `linkedin_post`, `blog_post`, `product_description`, `biovital_content`, `gst_report`, `invoice_create`, `pnl_monthly`, `pantheon_med_invoice`.

### CTO / code scaffolding

- **`CODE_BUILDER`**: FastAPI + Telegram bot skeletons under `workspace/projects/`, `run_code_review` (JSON issues/suggestions/score), `generate_tests`, `add_docstrings` (Claude).
- **`code_agent`**: shared codegen/review persona.
- Templates: `build_api`, `generate_tests_template`.

### Personal brand API

- Authenticated JSON endpoints: `POST /brand/strategy`, `POST /brand/viral-ideas`, `POST /brand/content-pack` (powered by **`brand_agent`**, India-aware strategy copy).
- Templates: `personal_brand_audit`, `viral_post_generator`, `nishant_brand`.

### Phone & SMS (Twilio)

1. Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_PHONE_NUMBER` (E.164, e.g. `+91…`) in `.env`.
2. Tool **`PHONE`**: `make_call` (outbound voice with TwiML `Say` + Polly), `send_sms`, `get_call_status`.
3. Sandbox requires `+` and 10–15 digits; blocks numbers whose digits after `+` start with `000` or `999`.

### Database connector

- Tool **`DATABASE`**: `connect_and_query` (parameterized `params`), `execute_statement`, `get_schema`, `backup_sqlite`.
- **SQLite:** `sqlite:///` paths must resolve under the workspace (`WORKSPACE_DIR`).
- **PostgreSQL / MySQL:** only if the host appears in `DATABASE_WHITELIST` (comma-separated); internal/private hosts are rejected. Optional drivers: `psycopg2-binary`, `pymysql`.

### PDF generation

- Tool **`PDF_GENERATOR`** (`reportlab`): `create_invoice_pdf` (same-style data as finance invoices), `create_report_pdf`, `create_letter_pdf`, `markdown_to_pdf` (markdown file under workspace → PDF in `workspace/pdfs/`).

### Image analysis

- Tool **`IMAGE_ANALYZER`**: Claude vision for `analyze_image`, `extract_text_from_image`, `compare_images`, `analyze_document_image`.
- Allowed extensions: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`; max **10MB**; paths must stay in the workspace.

### Security scanner

- Tool **`SECURITY_SCANNER`**: `scan_website` (SSL + headers + score), `check_ssl`, `check_security_headers`, `check_password_strength` (password is scored in memory only — never logged), `generate_security_report` (markdown under `workspace/security/`).
- Sandbox blocks `localhost`, private IPs, and URLs with embedded credentials (`user:pass@`).

### Compliance & legal templates

- Tool **`COMPLIANCE`**: GSTIN/PAN validation (`validate_gstin`, `validate_pan`, `gst_compliance_check`), `generate_compliance_doc` (CDSCO / ISO13485 / MDR2017 / GDPR / SOC2 checklists), `create_nda`, `create_mou`.
- All generated legal content includes a **template disclaimer** — not a substitute for counsel.

### Auto-deployment

- Tool **`DEPLOYER`**: `deploy_to_railway` / `deploy_to_vercel` (CLI in `project_path` under workspace), `create_github_repo` + optional `push_path`, `push_to_github`, `check_deployment` (HTTP GET + timing).
- Configure `GITHUB_TOKEN`, `GITHUB_USERNAME`, `RAILWAY_TOKEN`, `VERCEL_TOKEN` in `.env`. Sandbox enforces workspace paths and safe `repo_name` characters.

### Video generation

- Tool **`VIDEO_GENERATOR`**: `text_to_video`, `images_to_slideshow` (tries **ffmpeg**, else HTML), `create_product_demo`, `create_social_video` (scripts under `workspace/video/`).
- Optional: `DID_API_KEY`, `SYNTHESIA_API_KEY`, `VIDEO_GENERATION_ENABLED=true` for API-backed renders; otherwise HTML + text fallbacks.

### PostgreSQL (optional)

- Set `DATABASE_URL` (e.g. `postgresql+asyncpg://pantheon:PASSWORD@localhost:5433/pantheon_coo`). `DBPool.backend` reflects Postgres when the URL contains `postgresql`.
- **Store layer** still uses SQLite file (`db_path`) in `acquire()` unless **`POSTGRES_STORE_ENABLED=true`** (enable only after migrating SQL to Postgres — see `migrations/versions/0012_postgres_compat.sql`).
- Local DB: `docker compose --profile postgres up -d postgres` (image `postgres:16-alpine`, host port **5433**). Volume `pantheon_coo_postgres`.

### Notion

- Tool **`NOTION`**: pages, search, database rows, append — `NOTION_API_KEY`, header `Notion-Version: 2022-06-28`. Sandbox: Notion page/database IDs must be UUIDs.

### Zoho CRM (India)

- Tool **`ZOHO_CRM`**: REST v2 on **`https://www.zohoapis.in/crm/v2`** — leads, contacts, deals, search. Set `ZOHO_ACCESS_TOKEN` (and refresh/client secrets for token renewal outside the tool).

### Google Calendar

- Tool **`GOOGLE_CALENDAR`**: same **`GOOGLE_SERVICE_ACCOUNT_JSON`** as Sheets; scope `GOOGLE_CALENDAR_SCOPE` (default Calendar API scope). Actions: create/list/update/delete events, `find_free_slot` heuristic. Service accounts often need domain-wide delegation or a shared calendar for user mailboxes.

## Docker

```bash
cp .env.example .env   # set ANTHROPIC_API_KEY
make docker-up         # backend:8002, dashboard:3002
make docker-logs       # follow logs
make docker-down       # stop
```

Optional **Redis** (cache + distributed rate limits): `docker compose --profile redis up -d redis` — server on host port **6380** (`REDIS_URL=redis://localhost:6380/0`, `REDIS_ENABLED=true`).

## Redis caching & rate limits

1. Start Redis (see Docker above) or point `REDIS_URL` at any Redis 7 instance.
2. Set `REDIS_ENABLED=true` in `.env`. The API uses Redis for sliding-window rate limits when enabled; otherwise it keeps the in-memory limiter.
3. Expensive reads are cached when Redis is on: performance `GET /report`, admin `GET /admin/analytics`, and `GET /templates`. Completed tasks invalidate per-user report cache keys.

## OpenTelemetry tracing

1. Set `OTEL_ENABLED=true` and optionally `OTEL_EXPORTER_OTLP_ENDPOINT` (gRPC, default port 4317) or rely on console export when unset.
2. `OTEL_SERVICE_NAME` defaults to `pantheon-coo`. Spans cover the orchestrator loop phases and `POST /execute`.

## White-label branding

1. Set `WHITE_LABEL_ENABLED=true` and optional `WHITE_LABEL_NAME`, logo URL, primary color, support email, domain (see `.env.example`).
2. Public `GET /config/branding` drives the dashboard (`loadBranding()` in `static/dashboard.html`).
3. Admins can `GET`/`PATCH /admin/branding`; overrides persist to `branding.json` in the workspace.

## Affiliate program

1. Authenticated users `POST /affiliate/join` for an 8-character referral code; dashboard at `GET /affiliate/dashboard`.
2. `GET /affiliate/link?code=...` is public (tracks clicks, redirects to `/` or `WHITE_LABEL_DOMAIN`).
3. Registrations may include `ref_code` on `POST /auth/register`. After Razorpay payment verification (or webhook), referred users trigger commission credit (`DEFAULT_AFFILIATE_COMMISSION`, default 20%).
4. `GET /admin/affiliates` lists affiliates (admin JWT).

## Tally Prime (India accounting)

1. Configure `TALLY_HOST`, `TALLY_PORT` (default XML/HTTP bridge on 9000), and `TALLY_COMPANY` in `.env`.
2. Tool **`TALLY`**: ledgers, balances, vouchers, trial balance, invoice JSON sync from a workspace folder.
3. Templates: `tally_sync`, `tally_balance`, `pantheon_med_tally`.

## Architecture

```
pantheon_v2/
├── main.py                  FastAPI app (50+ endpoints)
├── orchestrator.py          Autonomous agent loop
├── config.py                Settings (env-driven)
├── models.py                All Pydantic contracts
├── agents/                  Core + support agents (voice, trading, web, brand, code, …)
├── memory/store.py          SQLite — 11+ tables
├── security/                Sandbox + auth + rate limiter
├── tools/                   Built-ins (filesystem, market, web, finance, code, …) + custom
├── migrations/              Versioned SQL schema files
├── tests/                   ~460+ tests, 0 failures
├── mobile_app/              Expo React Native client
├── chrome_extension/        Chrome MV3 extension
├── static/dashboard.html    Dark-mode control panel
├── docker-compose.yml       Isolated ports 8002/3002
└── Makefile                 25 developer targets
```

## Security

- **API auth**: `AUTH_MODE=apikey` requires `X-COO-API-Key` header
- **Rate limiting**: plan-based RPM (free/starter/pro/enterprise) on global routes and `/execute`; optional Redis for multi-worker deployments
- **Terminal sandbox**: explicit command allowlist, shell injection blocked
- **Filesystem sandbox**: all writes restricted to workspace dir
- **Browser/HTTP**: SSRF protection, private IP blocking, scheme enforcement
- **WhatsApp**: HMAC-SHA256 signature verification

## Self-improvement

Every completed task triggers:
1. **Pattern detection** — step sequences fingerprinted and counted
2. **Tool building** — repeated patterns (≥3×) trigger automatic tool generation
3. **Prompt optimization** — underperforming agent prompts rewritten by Claude
4. **Performance monitoring** — 5-min background loop with alerts

## License

Proprietary — Pantheon Meditech Private Limited
