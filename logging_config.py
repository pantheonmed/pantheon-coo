"""
logging_config.py
──────────────────
Phase 5 — Production Logging

Configures structured JSON logging for production deployment.
Replaces uvicorn's default text logs with structured output
that works with log aggregators (Datadog, CloudWatch, Loki, etc.)

Features:
  - JSON-structured log lines
  - Request ID tracking through the agent loop
  - Log rotation (10MB files, 5 backups)
  - Separate error log
  - Console pretty-print in dev mode

Usage:
  from logging_config import setup_logging
  setup_logging()   # call once at startup in main.py lifespan
"""
import logging
import logging.handlers
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path("/tmp/pantheon_v2/logs")


class JSONFormatter(logging.Formatter):
    """Emit one JSON object per log line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if hasattr(record, "task_id"):
            payload["task_id"] = record.task_id
        if hasattr(record, "agent"):
            payload["agent"] = record.agent
        return json.dumps(payload, ensure_ascii=False)


class DevFormatter(logging.Formatter):
    """Human-readable for local development."""
    COLORS = {
        "DEBUG": "\033[37m",
        "INFO": "\033[36m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        ts = datetime.now().strftime("%H:%M:%S")
        prefix = f"{color}[{ts}] {record.levelname:8s}{self.RESET}"
        name = record.name.replace("pantheon_v2.", "")
        return f"{prefix} {name}: {record.getMessage()}"


def setup_logging(dev_mode: bool = False) -> None:
    """Configure logging for the application. Call once at startup."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Remove any existing handlers (uvicorn may have added some)
    root.handlers.clear()

    if dev_mode:
        # Pretty console output for development
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(DevFormatter())
        root.addHandler(handler)
    else:
        # JSON to stdout (for Docker log collection)
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(JSONFormatter())
        stdout_handler.setLevel(logging.INFO)
        root.addHandler(stdout_handler)

        # Rotating file log
        file_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "pantheon_coo.log",
            maxBytes=10 * 1024 * 1024,   # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(JSONFormatter())
        file_handler.setLevel(logging.INFO)
        root.addHandler(file_handler)

        # Separate error log
        error_handler = logging.handlers.RotatingFileHandler(
            LOG_DIR / "errors.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        error_handler.setFormatter(JSONFormatter())
        error_handler.setLevel(logging.ERROR)
        root.addHandler(error_handler)

    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "asyncio", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logging.info(
        "Logging initialised",
        extra={"mode": "dev" if dev_mode else "production"},
    )
