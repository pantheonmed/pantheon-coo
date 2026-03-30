# Changelog — Pantheon COO OS

## [2.0.0]

### Added — Tasks 83–92 (voice calls, social tools, teams, marketplace, insights, enterprise, scale, ML, E2E tests)

- **Voice / calls (83):** `agents/call_agent.py`; `tools/phone.py` — `start_conference`, `record_call`, `transcribe_call`, `schedule_callback` (+ Twilio flows); scheduler `[oneshot]` rows; templates `call_supplier`, updated `call_followup`, `medical_appointment`.
- **LinkedIn / social (84–85):** `tools/linkedin.py` (50 actions/day guard), `tools/instagram.py`, `tools/twitter.py`; `ToolName` + registry entries; templates for LinkedIn + Instagram calendar.
- **Teams (86):** migrations `0018_teams.sql`; `POST /teams`, `/teams/join`, members/tasks/assign/remove; dashboard **Team** tab + **team-switcher**; `CommandRequest.team_id` + `link_team_task` on execute.
- **Marketplace (87):** `0019_marketplace.sql`; publish/list/detail/purchase/rate; admin approve; **70/30** split in `tool_purchases`; `GET /marketplace/earnings`; dashboard **Marketplace** tab.
- **Insights (88):** `insights_engine.py` + `POST /insights/weekly-report`, `GET /insights/automation-opportunities`, `GET /insights/predict`; dashboard **Analytics+** tab.
- **Enterprise (89):** `tools/gem_portal.py`; `0020_audit_gem.sql`; `insert_audit_log` on JWT **login**; `GET /admin/audit-logs`; SAML stub `GET /auth/saml/login`, `POST /auth/saml/callback`; config `saml_*`.
- **Scale (90):** `taskqueue/task_queue.py` (in-memory FIFO + optional workers); `distributed_task_queue` / `worker_count` / `max_queue_depth`; `GET /ready`; `/health` includes `worker_count`, `active_tasks`, `ready`; **k8s/** manifests + README.
- **ML (91):** `ml/data_collector.py`, `ml/training_config.py`, `ml/README.md`; `GET /admin/ml/stats`, `POST /admin/ml/export`, `POST /admin/ml/prepare-dataset`, `GET /admin/ml/dataset-quality`.
- **Integration (92):** `tests/test_full_user_journey.py`, `tests/test_performance_benchmark.py`, `tests/test_task92_integration.py`; `GET /onboarding/status`.
- **Auth refactor:** `require_admin` moved to `security/auth.py` (shared dependency).
- **Tests:** `test_task83_calls.py` … `test_task92_integration.py`; suite **540+** tests.

### Added — Tasks 77–82 (GitHub OSS, SEO, admin dashboard, monitoring, performance, docs)

- **GitHub / OSS:** `.github/ISSUE_TEMPLATE/` (bug report, feature request), `PULL_REQUEST_TEMPLATE.md`, **`CONTRIBUTING.md`**, **`CODE_OF_CONDUCT.md`**, **`SECURITY.md`** (`security@pantheon.ai`); **`.github/workflows/ci.yml`** (Python 3.11, `requirements-dev.txt`, Playwright Chromium, pytest + ruff); **`.github/workflows/deploy.yml`** (Railway on `main` push, `RAILWAY_TOKEN`).
- **SEO & public pages:** `static/landing.html` — title, description, keywords, Open Graph, Twitter Card, Schema.org `SoftwareApplication` JSON-LD; **`static/robots.txt`**, **`static/og-image.svg`**; **`GET /sitemap.xml`**, **`GET /robots.txt`**, **`GET /docs-page`** (developer docs).
- **Admin founder dashboard:** **`GET /admin/dashboard-stats`** (system / users / revenue / usage / activity feed; ~60s Redis + in-memory cache); **`GET /admin/errors`**; `memory/store.py` — `get_admin_dashboard_stats`, `get_queue_depth`; dashboard **Admin** tab (hidden unless `role === "admin"`).
- **Monitoring:** **`monitoring/error_tracker.py`** — in-process error buffer, critical-type alerts, `error_count_last_hour` / `alert_count_today` on **`GET /health`**; wired via middleware / orchestrator / billing paths; **`monitor.py`** extra alert paths.
- **Performance:** **`memory/redis_client.cached()`** decorator (no-op when Redis off); composite indexes **`migrations/versions/0017_perf_indexes.sql`** (applied from store init); **`tools/lazy_loader.get_tool()`** for on-demand tool module import.
- **Documentation:** **`static/docs.html`**, **`USER_GUIDE.md`**, **`OPERATOR_GUIDE.md`**.
- **Tests:** `test_task77_github.py` … `test_task82_docs.py`; full suite **498** tests.

### Added — Tasks 71–76 (deploy, Docker Hub, VPS, onboarding, pricing UX)

- **Installers:** `install.sh` (macOS/Linux, Python 3.11+, git clone, deps, Playwright, `.env` bootstrap), `uninstall.sh`; **`INSTALL.md`**, **`DEPLOYMENT_GUIDE.md`** (options + cost table).
- **Railway:** `railway.json`, `.railway.env.example`, **`RAILWAY_DEPLOY.md`**; **`Dockerfile`** multi-stage build (builder + runtime), non-root `coo` user, `HEALTHCHECK` on `/health`, `PORT` for uvicorn.
- **VPS:** `vps_setup.sh` (Ubuntu 22.04, nginx reverse proxy, Let’s Encrypt, systemd `pantheon-coo.service`), **`VPS_DEPLOY.md`**.
- **Docker:** `docker-compose.yml` — production-style `backend` image `pantheonai/coo-os:latest` + local `build` fallback, healthcheck, data volume; optional **postgres** / **redis** profiles preserved; **`docker-start.sh`**, **`DOCKER.md`**.
- **Onboarding:** `GET /onboarding/samples?industry=` (medical, retail, tech, finance, other); `GET /tutorials` (markdown index under `static/tutorials/`); **`templates/emails/welcome.html`**; dashboard **first-login tour** (`tour_completed` in `localStorage`) + highlights command / execute / tasks / tabs / sample command.
- **Pricing:** `static/landing.html` — Free / Starter / Pro cards, INR/USD/EUR/AED toggle; **`billing.py`** plan feature copy aligned with landing; dashboard **usage bar** (green &lt;60%, amber 60–90%, red ≥90%), **upgrade modal** at monthly limit, **`POST /billing/create-order`** starter flow (Razorpay/Stripe response surfaced in UI).
- **Tests:** `test_task71_installer.py` … `test_task76_pricing.py`; suite **460+** tests.

### Added — Tasks 65–70 (mobile app, collaboration, Zapier, HubSpot, WordPress/Shopify, Chrome extension)

- **`mobile_app/`** — Expo SDK 51 + React Native 0.74 + TypeScript: login, dashboard (execute + task list + pull-to-refresh), task detail (logs/plan/eval), voice (`expo-av` + `POST /voice/transcribe`), settings (API URL, plan, logout); bottom tabs Home / History / Voice / Settings; `services/api.ts` with `execute()`.
- **Collaboration (Task 66):** `memory/store.py` — multiple `asyncio.Queue` subscribers per task (`subscribe_task_stream`, `unsubscribe_task_stream`, broadcast `push_stream_event`); `task_shares` table; `POST /tasks/{id}/share`, `GET /tasks/{id}/watchers`, `GET /shared/{token}`, `GET /shared/{token}/stream` (public read-only + SSE); dashboard task rows — **Share** + live watcher count.
- **Zapier (Task 67):** `tools/zapier.py` (`ToolName.ZAPIER`) — `send_to_webhook`, `trigger_zap`; `POST /webhook/zapier` (header `X-Zapier-Secret`, body `command`, optional `user_email`); config `zapier_webhook_secret`; template `zapier_notify`.
- **HubSpot (Task 68):** `tools/hubspot.py` (`ToolName.HUBSPOT`); config `hubspot_api_key`; templates `hubspot_lead`, `hubspot_pipeline`.
- **WordPress + Shopify (Task 69):** `tools/wordpress.py`, `tools/shopify.py` (`ToolName.WORDPRESS`, `ToolName.SHOPIFY`); config `wordpress_*`, `shopify_*`; templates `wp_blog_post`, `shopify_daily_report`.
- **`chrome_extension/`** — MV3 popup (`execute` → `/execute`), background notifications + context menu, content script for page text; `README.md` install steps.
- **Tests:** `test_task65_mobile.py` … `test_task70_chrome.py`; suite grew toward **460+** tests (see Tasks 71–76).

### Added — Tasks 58–64 (i18n, global billing, Amazon/Meesho/WhatsApp commerce, global templates, timezone/locale)

- **i18n** (`i18n/translations.py`): 12 languages; `t()`, `get_supported_languages()`, `parse_accept_language()`; public `GET /i18n/languages`, `GET /i18n/translations/{lang}`; config `default_language`, `supported_languages`; middleware sets `request.state.lang` (query `?lang=`, `Accept-Language`, JWT user preference); `PATCH /auth/me/language`; users columns `language` (+ migration notes in `migrations/versions/0015_language_currency.sql`).
- **Agents:** reasoning/planner append “respond in user language” via `prompt_respond_in_language_clause`; `orchestrator` resolves `context["language"]` from user profile; `agents/base.py` supports `system_prompt_override` (thread-safe vs mutating class prompts).
- **Dashboard:** language selector, `/i18n` strings for key labels, RTL CSS + `applyRTL()` for Arabic; **`GET /landing`** serves `static/landing.html` (12-language badge + USD/EUR/AED sample pricing).
- **Billing:** `GLOBAL_PRICING` + `supported_currencies`; INR → Razorpay, other currencies → Stripe `PaymentIntent` when `STRIPE_SECRET_KEY` set; `orders.stripe_payment_intent_id`, `payment_gateway`; `POST /billing/verify-payment` accepts Razorpay or `stripe_payment_intent_id`; `POST /webhook/stripe` (`payment_intent.*`, `customer.subscription.deleted`); `GET /billing/plans?currency=`; registration optional `country_code`, `timezone` → `COUNTRY_TO_CURRENCY`, `TIMEZONE_BY_COUNTRY`, `LOCALE_BY_COUNTRY`; users `currency`, `country_code`.
- **Tools:** `tools/amazon_seller.py` (`ToolName.AMAZON_SELLER`), `tools/meesho.py` (`ToolName.MEESHO`), `tools/whatsapp_commerce.py` (`ToolName.WHATSAPP_COMMERCE`); `whatsapp.py` — `send_catalog`, `send_product`, `handle_order`, inbound `type=order` webhook; config for Amazon, Meesho, WhatsApp catalog IDs.
- **Templates:** UAE/US/Europe/Brazil/Japan/Nigeria/Indonesia + Amazon/Meesho/WhatsApp entries in `templates.py`.
- **Timezone & locale** (`utils/timezone.py`, `utils/locale_format.py`): `pytz==2024.1`; users `timezone`, `locale`; `PATCH /auth/me/timezone`; schedules `timezone` column, cron interpreted in that zone (`scheduler.py`); `migrations/versions/0016_timezone_locale.sql`.
- **Deps:** `stripe==9.12.0`, `pytz==2024.1`.
- **Tests:** `test_task58_i18n.py` … `test_task64_timezone.py`; full suite **400+** tests.

### Added — Tasks 51–57 (Redis, tracing, white-label, affiliates, semantic memory, rate tiers, Tally)

- **Redis** (`memory/redis_client.py`): optional `get_redis`, `close_redis`, `cache_get` / `cache_set` / `cache_delete` / `cache_delete_prefix`; `redis==5.0.4`, `hiredis==2.3.2`; config `redis_url`, `redis_enabled`, `cache_ttl_seconds`; **docker-compose** optional `redis` service (profile `redis`, host port **6380**); `security/rate_limit.py` uses Redis sliding window when enabled, else in-memory; **cached:** `GET /report`, `GET /admin/analytics`, `GET /templates` (invalidates report prefix on task completion).
- **OpenTelemetry** (`monitoring/tracing.py`): `init_tracing`, `get_tracer`, `span` context manager; deps `opentelemetry-*` + OTLP gRPC exporter; config `otel_enabled`, `otel_endpoint`, `otel_service_name`; lifespan hooks; spans in `orchestrator.py` and `POST /execute`.
- **White-label** (`branding_runtime.py`): `GET /config/branding` (public); `GET`/`PATCH /admin/branding`; `branding.json` under workspace when `WHITE_LABEL_ENABLED`; dashboard `loadBranding()` updates title, logo, `--purple`.
- **Affiliates** (`memory/store.py` + migrations `0013_affiliates.sql`): tables `affiliates`, `referrals`, `affiliate_payout_requests`; `POST /affiliate/join`, `GET /affiliate/dashboard`, `GET /affiliate/link` (redirect), `POST /affiliate/payout-request`, `GET /admin/affiliates`; `POST /auth/register` optional `ref_code`; commission on `verify-payment` + Razorpay webhook; `DEFAULT_AFFILIATE_COMMISSION`.
- **Semantic memory** (`memory/semantic_store.py`, migration `0014_semantic_memory.sql`): tag + keyword recall; wired in orchestrator; `GET /memory/semantic`, `GET /memory/stats`, `DELETE /memory/semantic/{id}`.
- **Plan rate tiers** (`security/rate_limit.py`): `PLAN_RATE_LIMITS` for free/starter/pro/enterprise; `require_auth` returns `plan`; `GET /usage` includes `rate_limits` + current usage; `GET /stats` uses `require_auth` + `rate_limit`.
- **Tally** (`tools/tally.py`): `ToolName.TALLY`, `get_ledgers`, `get_balance`, `create_voucher`, `get_trial_balance`, `sync_invoices`; config `tally_host`, `tally_port`, `tally_company`; templates `tally_sync`, `tally_balance`, `pantheon_med_tally`.
- **Tests:** `test_task51_redis.py` … `test_task57_tally.py`; full suite **351+** tests.

### Added — Tasks 45–50 (deploy, video, PostgreSQL pool, Notion, Zoho, Calendar)

- **Deployer** (`tools/deployer.py`): `deploy_to_railway`, `deploy_to_vercel`, `create_github_repo`, `push_to_github`, `check_deployment`; config `github_token`, `github_username`, `railway_token`, `vercel_token`; sandbox: workspace `project_path` / `local_path`, GitHub `repo_name` `[a-zA-Z0-9-]{1,100}`; templates `deploy_website`, `deploy_api`.
- **Video generator** (`tools/video_generator.py`): `text_to_video`, `images_to_slideshow` (ffmpeg or HTML), `create_product_demo`, `create_social_video`; config `did_api_key`, `synthesia_api_key`, `video_generation_enabled`; graceful HTML/script fallbacks when APIs off; templates `product_video_script`, `biovital_video`.
- **PostgreSQL-ready pool** (`memory/db_pool.py`): `DBPool.backend` reflects `DATABASE_URL` (`postgresql` / `mysql` / `sqlite`); `acquire()` uses **asyncpg** only when `POSTGRES_STORE_ENABLED=true` (default false so existing SQLite store unchanged); `normalize_asyncpg_dsn()` strips `+asyncpg`; dependency `asyncpg==0.29.0`; `migrations/versions/0012_postgres_compat.sql` (operator notes); **docker-compose** optional `postgres` service (profile `postgres`, port **5433**).
- **Notion** (`tools/notion.py`): Notion API v1 — `create_page`, `update_page`, `read_page`, `create_database_entry`, `search_pages`, `append_to_page`; config `notion_api_key`; sandbox UUID validation for page/database IDs; templates `notion_report`, `notion_meeting_notes`.
- **Zoho CRM** (`tools/zoho_crm.py`): India host `zohoapis.in` — leads, contacts, deals, search; config `zoho_access_token`, refresh/client fields; templates `lead_capture`, `crm_report`, `medical_lead`.
- **Google Calendar** (`tools/google_calendar.py`): Calendar v3 via same service account JSON as Sheets; `create_event`, `get_events`, `update_event`, `delete_event`, `find_free_slot`; config `google_calendar_scope`; templates `schedule_meeting`, `weekly_schedule`, `demo_schedule`.
- **Tests:** `test_task45_deployer.py` … `test_task50_calendar.py`; full suite **311** tests.

### Added — Voice interface (Task 31)
- `agents/voice.py`: `transcribe_audio()` (OpenAI Whisper), `text_to_speech()` (OpenAI TTS, voice `nova`)
- Config: `openai_whisper_model`, `voice_enabled`; `.env` `VOICE_ENABLED` (requires `OPENAI_API_KEY` for voice)
- `whatsapp.py`: `type=audio` inbound → download media → transcribe → task; optional MP3 reply via `send_audio` after completion when voice path used
- `telegram_bot.py`: `message.voice` / `message.audio` → `getFile` download → transcribe → same task flow as text
- API: `POST /voice/transcribe` (multipart audio, optional `auto_execute=true`), `GET /voice/speak?text=` (MP3)
- Tests: `tests/test_task31_voice.py`

### Added — Tasks 38–44 (phone, database, PDF, vision, research, security, compliance)

- **Phone** (`tools/phone.py`): Twilio `make_call` (TwiML `Say` + Polly voices), `send_sms`, `get_call_status`; config `twilio_account_sid`, `twilio_auth_token`, `twilio_phone_number`; sandbox E.164-style `+` and 10–15 digits, blocks `000`/`999` prefixes; templates `call_followup`, `sms_blast`.
- **Database** (`tools/database.py`): `connect_and_query`, `execute_statement`, `get_schema`, `backup_sqlite` (SQLite full support; PostgreSQL/MySQL when drivers + `DATABASE_WHITELIST` allow host); sandbox blocks `DROP`/`TRUNCATE`, `DELETE` without `WHERE`, restricts SQLite paths to workspace and blocks internal IPs for remote URLs; `database_whitelist` in config; templates `db_report`, `db_backup`.
- **PDF** (`tools/pdf_generator.py`): `reportlab==4.1.0` — `create_invoice_pdf`, `create_report_pdf`, `create_letter_pdf`, `markdown_to_pdf`; templates `invoice_pdf`, `report_pdf`.
- **Image analyzer** (`tools/image_analyzer.py`): Claude vision — `analyze_image`, `extract_text_from_image`, `compare_images`, `analyze_document_image`; sandbox: image extensions only, 10MB max, workspace paths; templates `invoice_scan`, `document_ocr`.
- **Researcher** (`tools/researcher.py`): Google News RSS (`gl=IN`), `research_topic` (Claude synthesis via model router), `monitor_keyword` → `schedules` row, `get_industry_news`; templates `daily_news_brief`, `competitor_news`, `medical_device_news`.
- **Security scanner** (`tools/security_scanner.py`): `scan_website`, `check_ssl`, `check_security_headers`, `check_password_strength` (password never logged), `generate_security_report` → markdown; sandbox blocks internal hosts and URLs with embedded credentials; templates `website_security_audit`, `ssl_monitor`.
- **Compliance** (`tools/compliance.py`): GSTIN checksum validation, PAN format, `gst_compliance_check`, `generate_compliance_doc`, `create_nda`, `create_mou` (legal disclaimer on all templates); templates `cdsco_checklist`, `gstin_validator`, `nda_generator`.
- **Tests:** `test_task38_phone.py` … `test_task44_compliance.py`.

### Added — Tasks 32–37 (trading, websites, content, finance, CTO, brand)

- **Market data** (`tools/market_data.py`): Yahoo `v8/finance/chart` + `v10/finance/quoteSummary` — `get_quote`, `get_history`, `get_news`, `get_indices`, `get_screener`; `ToolName.MARKET_DATA`; sandbox symbol pattern + news query validation; `agents/trading_analyst.py` + `TradingAnalysisOutput`; trading templates.
- **Website builder** (`tools/website_builder.py`): `create_landing_page`, `create_portfolio`, `create_product_page`, `add_section`, `optimize_seo` (Claude via `agents/website_generator.py`); `ToolName.WEBSITE_BUILDER`; business/medical templates.
- **Content creator** (`tools/content_creator.py`): blog, social, email, ads, calendar → markdown under `content/`; `ToolName.CONTENT_CREATOR`; LinkedIn/blog/product/BioVital templates.
- **Finance** (`tools/finance.py`): `calculate_gst`, `generate_invoice`, `generate_pnl`, `analyze_cashflow`, `categorize_expenses` (pure Python; GST rates 0/5/12/18/28); `ToolName.FINANCE`; GST/invoice/P&L/PantheonMed invoice templates.
- **Code builder** (`tools/code_builder.py`): FastAPI + Telegram bot scaffolds, `run_code_review`, `generate_tests`, `add_docstrings`; `agents/code_agent.py`; `ToolName.CODE_BUILDER`; `CodeReviewOutput`; build_api + generate_tests templates.
- **Brand** (`agents/brand_agent.py`): strategy, viral ideas, content pack; `POST /brand/strategy`, `/brand/viral-ideas`, `/brand/content-pack`; brand strategy / viral / Nishant templates; conftest mocks for trading + brand agents.
- **Tests:** `test_task32_trading.py` … `test_task37_brand.py`.

### Added — Tasks 24–30 (integrations, analytics, webhooks, mobile, performance)

- **Google Sheets** (`tools/google_sheets.py`): read/write/append/clear/create via Google Sheets API v4; `ToolName.GOOGLE_SHEETS`; service-account auth (`google-auth`); spreadsheet ID validation in `security/sandbox.py`; templates `sheets_export`, `sheets_read_report`; config `google_service_account_json`, `google_sheets_scope`.
- **Telegram** (`telegram_bot.py`): `POST /webhook/telegram`, `GET /webhook/telegram/setup`; `notifications.send_telegram`; task context `telegram_chat_id`; config `telegram_bot_token`, `telegram_webhook_secret`; public path `/webhook/telegram`.
- **Analytics** (`analytics.py`): `analytics_events` table; `track()`; admin `GET /admin/analytics`, `GET /admin/analytics/export` (CSV); dashboard **Analytics** tab (admin-only) with period buttons, SVG daily chart, goal-type bars, churn table.
- **Outbound webhooks** (`webhook_sender.py`): `webhook_subscriptions` / `webhook_logs`; `POST/GET/DELETE /webhooks`, `GET /webhooks/{id}/logs`; HMAC-SHA256 delivery with retry; wired from orchestrator on task completion/failure.
- **Suggestions** (`agents/suggester.py`): `tasks.suggestions_json`; `SuggestionOutput`; orchestrator saves suggestions after successful evaluation; API and Logs tab chips.
- **DB pool** (`memory/db_pool.py`): `get_pool().acquire()` replaces raw `aiosqlite.connect` in `memory/store.py`; slow-query logging; `GET /health` adds `memory_mb`, `uptime_seconds`, `db_pool_size` (psutil); startup timing + graceful shutdown in `main.py` lifespan.
- **PWA**: `static/manifest.json`, `static/icon.svg`; `GET /app`; responsive CSS + mobile FAB in `static/dashboard.html`.
- **Scripts**: `scripts/load_test.py` for concurrent registration + `/execute` smoke load tests.
- **Migrations**: `0009_analytics.sql`, `0010_webhooks.sql`, `0011_suggestions.sql`.
- **Tests**: `test_task24_sheets.py` … `test_task30_performance.py`; suite **196** tests.

### Added — PantheonMed vertical (Task 23)
- `templates.py`: four **medical** templates (`inventory_check`, `patient_report_summary`, `supplier_email`, `compliance_checklist`) plus helpers (`prioritize_medical_first`, `validate_industry`, etc.)
- `users.industry` (`medical` | `retail` | `agency` | `tech` | `other`); optional on `POST /auth/register`; returned from login and `GET /auth/me`
- `GET /onboarding/suggested-commands` — three starter commands (medical vs default); `GET /templates`, `GET /templates/{id}`, `POST /templates/{id}/run`
- Dashboard: **Dark | Medical** theme toggle (`localStorage` key `pantheon_theme`), **Templates** tab, PantheonMed header when `industry === "medical"`, suggested-command chips when JWT present
- Migration marker `migrations/versions/0008_users_industry.sql` (runtime column ensure remains in `memory/store.py`)
- Tests: `tests/test_task23_medical.py` (full suite grew to **196** tests after Tasks 24–30)

### Added — Razorpay billing (Task 17)
- `billing.py`: `GET /billing/plans` (public), `GET /billing/summary`, `POST /billing/create-order`, `POST /billing/verify-payment`, `GET /billing/history`, `POST /webhook/razorpay` (HMAC body verification with `RAZORPAY_WEBHOOK_SECRET`)
- `orders` table in `memory/store.py`; migration `migrations/versions/0006_orders.sql`
- Config: `razorpay_key_id`, `razorpay_key_secret`, `razorpay_webhook_secret`; `PLAN_PRICING` (paise); `PLAN_LIMITS` for monthly task caps
- Dependency: `razorpay==1.4.1`
- Dashboard **Billing** tab: plan badge, usage, plan grid, Razorpay Checkout JS, payment history; optional JWT via `localStorage.pantheon_jwt` or `PANTHEON_CONFIG.jwtToken`
- `tests/test_billing.py`

### Added — Multi-user authentication (Task 12)
- SQLite `users` + `user_sessions` tables; `tasks.user_id` for ownership; migration `migrations/versions/0004_users_and_sessions.sql`
- `security/user_auth.py` — bcrypt passwords, JWT (PyJWT), per-user API keys, logout JWT jti blocklist
- Endpoints: `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `POST /auth/refresh`, `POST /auth/reset-api-key`
- `AUTH_MODE=jwt` resolves **Bearer JWT** or **X-COO-API-Key** (per-user key or legacy `COO_API_KEY`); `require_auth` returns `user_id`, `email`, `role`
- `GET /tasks`, `GET /tasks/{id}`, logs, stream, retry — scoped by user; `role=admin` sees all tasks
- Per-user workspace: `security/sandbox.py` context + `orchestrator` passes `context["user_id"]` → `{workspace}/users/{user_id}/`
- Config: `jwt_secret`, `jwt_expiry_hours`, `allow_registration`; deps: `bcrypt`, `PyJWT`
- `security/auth.py` reads `AUTH_MODE` / `COO_API_KEY` from `os.environ` each request (test-friendly)
- Tests: `tests/test_auth.py`

### Changed — Grounded evaluator (Task 8)
- After Claude scores, auto-checks verify `filesystem.write_file` paths on disk, `terminal.run_command` exit codes, and **all** `http` steps via `status_code`
- `EvaluatorOutput.auto_checks`: each item `{check_type, step_id, passed, detail}`; `auto_check_override` when score capped to `min(Claude score, 0.50)`
- Warning log per failed check when `EvaluatorInput.task_id` is set

### Added — Stuck task recovery
- `memory.store.recover_stuck_tasks()` marks `reasoning` / `planning` / `executing` / `evaluating` tasks as `failed` after restart with retry guidance
- Startup log: recovered count and per-task summary

### Added — Performance report API
- `GET /report?period=24h|7d|30d` — aggregates, tool usage from plans, model router call counts, cached Claude recommendation (5 min TTL)
- Dashboard **Report** tab with metric cards and period switcher

### Added — Command palette (dashboard)
- Recent commands (localStorage, chips), quick actions (Execute, Dry Run, New Project, Briefing)
- Goal-type + complexity badges, ⌘/Ctrl+Enter, Esc clear, ↑/↓ history

### Added — Real-time agent thinking stream
- `memory.store.push_stream_event` + per-task asyncio queues for structured SSE events
- Event types: `agent_start`, `agent_done`, `step_start`, `step_done`, `loop_start`, `loop_done`
- Orchestrator and Execution agent push transitions; `GET /tasks/{id}/stream` emits `type: activity` JSON
- Dashboard: **Agent activity** panel (current agent, step, live score, scrolling feed)

### Added — Phase 5 (Full Autonomous COO)
- Project Decomposer Agent: breaks goals into parallel sub-tasks with dependency graph
- Parallel Project Runner: wave-based execution respecting depends_on
- Daily Briefing Agent: COO report with email + WhatsApp distribution
- Structured JSON logging with rotation and dev pretty-print
- Projects API: POST /projects, GET /projects/{id}, GET /projects/{id}/logs
- Briefing API: POST /briefing, GET /briefing/latest
- Dashboard: Projects + Briefing panels

### Added — Phase 4 (Self-Monitoring)
- Multi-model router: Claude primary, OpenAI fallback, circuit breaker
- Confidence Scorer: pre-flight quality check; low confidence triggers re-loop
- Prompt Optimizer: Claude rewrites underperforming agent prompts from failure data
- Performance Monitor: 5-min background loop with score trend and alerts
- Dashboard: Monitor panel with sparkline, circuit breaker status, optimize button

### Added — Phase 3 (Self-Building)
- Pattern Detector: fingerprints step sequences, detects repetition >= 3x
- Tool Builder Agent: writes + validates + hot-loads Python tool modules
- Dynamic Tool Registry: importlib-based loader, persists across restarts
- Email Tool: SMTP + Resend backends
- Scheduler: cron-based runner with */n step support and CRUD API
- Dashboard: Tools + Schedule panels

### Added — Phase 2 (Automation)
- Browser Tool: Playwright navigate, click, fill_form, screenshot, get_links
- HTTP Tool: GET, POST, PUT, DELETE, webhook sender
- WhatsApp Webhook: Meta Cloud API receive/reply pipeline
- SSE Streaming: GET /tasks/{id}/stream real-time log stream
- Dashboard: dark-mode control panel, 6 tabs

### Added — Phase 1 (Core)
- 6-Agent architecture: Reasoning, Planning, Execution, Evaluation, Memory, Tool Builder
- Autonomous loop: Reason > Plan > Execute > Evaluate > Learn > Repeat
- SQLite memory: 11 tables, all created via central schema
- Security sandbox: command allowlist, workspace enforcement, SSRF blocking
- FastAPI backend with async background tasks

### Added — Production Hardening
- API authentication: AUTH_MODE = none | apikey | jwt
- Rate limiting: sliding window, 60 rpm global / 10 rpm on /execute
- WhatsApp HMAC signature verification
- Database migration system: versioned SQL files, schema_migrations table
- Test suite: 103 tests, 0 failures
- Makefile: make dev, test, lint, fmt, docker-up, migrate, key
- pyproject.toml: ruff, mypy, pytest, coverage config
- .gitignore, requirements-dev.txt, CHANGELOG.md
