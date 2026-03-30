# Contributing to Pantheon COO OS

Thank you for helping improve Pantheon COO OS.

## Development setup

1. **Python 3.11+** recommended (matches Docker/CI).
2. Clone the repo and enter the project root (`pantheon_v2/`).
3. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements-dev.txt
   playwright install chromium
   ```

4. Copy environment template and set at least `ANTHROPIC_API_KEY`:

   ```bash
   cp .env.example .env
   ```

5. For local JWT tests, set `AUTH_MODE=jwt` and `JWT_SECRET` (see `.env.example`).

## Running tests

```bash
python3 -m pytest tests/ -q
```

With coverage (optional):

```bash
pip install pytest-cov
pytest tests/ --cov=. --cov-report=html
```

## Code style

- **Ruff** is configured for lint + format (`ruff check .`, `ruff format .`).
- Match existing patterns: type hints where helpful, focused changes, no drive-by refactors.
- Keep **400+** tests green before opening a PR.

## Submitting a PR

1. Open an issue first for large features (or use the feature request template).
2. Branch from `main`, make commits with clear messages.
3. Fill out `.github/PULL_REQUEST_TEMPLATE.md`.
4. Ensure `CHANGELOG.md` is updated for user-visible changes.

## Architecture (short)

- **`main.py`** — FastAPI app, routes, middleware.
- **`orchestrator.py`** — Reason → Plan → Execute → Evaluate → Memory loop.
- **`memory/store.py`** — SQLite persistence and task/log APIs.
- **`tools/`** — Built-in tools + registry for custom tools.
- **`agents/`** — LLM-backed agents and prompts.
- **`security/`** — Auth modes, sandbox, rate limits.

For deployment options see `DEPLOYMENT_GUIDE.md` and `README.md`.
