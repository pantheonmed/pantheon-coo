# Makefile — Pantheon COO OS v2
# All common developer commands.
#
# Usage:
#   make dev         start in development mode (hot reload)
#   make start       start in production mode
#   make stop        stop all running processes
#   make test        run full test suite
#   make test-watch  run tests on file change (requires pytest-watch)
#   make lint        run ruff linter
#   make fmt         auto-format with ruff
#   make typecheck   run mypy
#   make coverage    run tests with coverage report
#   make docker-up   start with Docker Compose
#   make docker-down stop Docker containers
#   make docker-logs follow Docker container logs
#   make migrate     run DB migrations
#   make install     install production deps
#   make install-dev install dev deps
#   make clean       remove temp files, pycache, logs
#   make key         generate a new API key

.PHONY: all dev start stop status test test-watch lint fmt typecheck coverage \
        docker-up docker-down docker-logs docker-build migrate \
        install install-dev clean key help

# ── Defaults ──────────────────────────────────────────────────────────────────
PYTHON     := python3
PYTEST     := $(PYTHON) -m pytest
PID_DIR    := /tmp/pantheon_v2/pids
LOG_DIR    := /tmp/pantheon_v2/logs
PORT       ?= 8002
FPORT      ?= 3002

# ── Startup ───────────────────────────────────────────────────────────────────
dev:
	@./run_all.sh --dev

start:
	@./run_all.sh

stop:
	@./run_all.sh --stop

status:
	@./run_all.sh --status

# ── Testing ───────────────────────────────────────────────────────────────────
test:
	$(PYTEST) tests/ -v

test-fast:
	$(PYTEST) tests/ -q --timeout=10

test-watch:
	$(PYTHON) -m pytest_watch tests/ -- -q

test-security:
	$(PYTEST) tests/test_security.py -v

test-api:
	$(PYTEST) tests/test_api.py -v

test-tools:
	$(PYTEST) tests/test_tools.py -v

test-agents:
	$(PYTEST) tests/test_agents.py -v

coverage:
	$(PYTEST) tests/ --cov=. --cov-report=term-missing --cov-report=html
	@echo "HTML report: htmlcov/index.html"

# ── Code quality ──────────────────────────────────────────────────────────────
lint:
	$(PYTHON) -m ruff check .

fmt:
	$(PYTHON) -m ruff format .
	$(PYTHON) -m ruff check --fix .

typecheck:
	$(PYTHON) -m mypy . --ignore-missing-imports

check: lint typecheck test-fast
	@echo "All checks passed."

# ── Docker ────────────────────────────────────────────────────────────────────
docker-build:
	docker compose build

docker-up:
	docker compose up -d
	@echo "Backend:  http://localhost:$(PORT)"
	@echo "Frontend: http://localhost:$(FPORT)"
	@echo "Logs:     make docker-logs"

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f

docker-restart:
	docker compose restart

docker-clean:
	docker compose down -v --remove-orphans

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	$(PYTHON) migrations/migrate.py

db-shell:
	@echo "Opening SQLite shell on $$(grep DB_PATH .env 2>/dev/null | cut -d= -f2 || echo pantheon_v2.db)"
	sqlite3 $$(grep DB_PATH .env 2>/dev/null | cut -d= -f2 || echo pantheon_v2.db)

db-reset:
	@echo "WARNING: This will delete all data."
	@read -p "Type 'yes' to confirm: " c; [ "$$c" = "yes" ] && rm -f pantheon_v2.db && echo "DB deleted." || echo "Cancelled."

# ── Installation ──────────────────────────────────────────────────────────────
install:
	pip install -r requirements.txt
	playwright install chromium

install-dev:
	pip install -r requirements-dev.txt
	playwright install chromium
	pre-commit install

setup: install-dev
	@cp -n .env.example .env 2>/dev/null || true
	@echo "Setup complete. Edit .env and set ANTHROPIC_API_KEY."

# ── Utilities ─────────────────────────────────────────────────────────────────
key:
	@$(PYTHON) -c "import secrets; print(secrets.token_urlsafe(32))"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type f -name "*.pyo" -delete 2>/dev/null || true
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
	rm -f /tmp/pantheon_v2/pids/*.pid
	@echo "Cleaned."

logs:
	tail -f $(LOG_DIR)/backend.log

help:
	@echo ""
	@echo "Pantheon COO OS v2 — Make targets"
	@echo "──────────────────────────────────"
	@echo "  make setup        First-time setup (install deps + copy .env)"
	@echo "  make dev          Start in development mode (hot reload)"
	@echo "  make start        Start in production mode"
	@echo "  make stop         Stop all running processes"
	@echo "  make test         Run full test suite"
	@echo "  make coverage     Tests with HTML coverage report"
	@echo "  make lint         Lint with ruff"
	@echo "  make fmt          Format code with ruff"
	@echo "  make docker-up    Start with Docker (ports $(PORT)/$(FPORT))"
	@echo "  make docker-down  Stop Docker containers"
	@echo "  make migrate      Run DB migrations"
	@echo "  make key          Generate a new API key"
	@echo "  make clean        Remove temp files"
	@echo ""

all: help
