"""
security/sandbox.py
────────────────────
Validates every execution step before the Execution Agent runs it.

Phase 1: Command allowlist + workspace path enforcement.
Phase 2+: Process isolation, resource limits, network rules.

Per-user workspace: when `set_user_workspace(user_id)` is active, filesystem
steps are confined to `/tmp/pantheon_v2/users/{user_id}/` (or configured root).
"""
import contextvars
import ipaddress
import os
import re
import shlex
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

from config import settings
from models import ExecutionStep, ToolName

_user_workspace: contextvars.ContextVar[Optional[Path]] = contextvars.ContextVar(
    "pantheon_user_workspace", default=None
)


def set_user_workspace(user_id: Optional[str]) -> contextvars.Token:
    """
    Scope filesystem sandbox to the given user's directory under workspace_dir.
    Returns a token that must be passed to reset_user_workspace().
    """
    if user_id:
        base = Path(settings.workspace_dir) / "users" / user_id
        base.mkdir(parents=True, exist_ok=True)
        return _user_workspace.set(base.resolve())
    return _user_workspace.set(None)


def reset_user_workspace(token: contextvars.Token) -> None:
    _user_workspace.reset(token)


def workspace_root() -> Path:
    """Effective workspace root for path checks (per-user or global)."""
    v = _user_workspace.get()
    if v is not None:
        return v
    return Path(settings.workspace_dir).resolve()

BLOCKED_URL_HOSTS = {
    "localhost", "127.0.0.1", "0.0.0.0",
    "169.254.169.254", "metadata.google.internal",
}

DANGEROUS_SHELL = ["&&", "||", ";", "|", "`", "$(", ">", ">>", "<"]

MAX_COMMAND_LENGTH = 2000

# Extra input sanitization for user-provided commands (API layer)
DANGEROUS_PATTERNS = [
    # Command injection
    ";",
    "&&",
    "||",
    "`",
    "$(",
    "${",
    # Path traversal
    "../",
    "..\\",
    "/etc/passwd",
    "/etc/shadow",
    # SQL injection
    "DROP TABLE",
    "DELETE FROM",
    "INSERT INTO",
    "UPDATE SET",
    "UNION SELECT",
    "--",
    # Python injection
    "__import__",
    "eval(",
    "exec(",
    "compile(",
    "subprocess",
    "os.system",
    # Sensitive files
    ".env",
    "config.py",
    "secrets",
    "password",
    "api_key",
    "token",
]


class SecurityError(Exception):
    pass


def sanitize_command(command: str) -> str:
    raw = command or ""
    if not raw.strip():
        raise SecurityError("Empty command")
    if len(raw) > MAX_COMMAND_LENGTH:
        raise SecurityError("Command too long")
    lower = raw.lower()
    for p in DANGEROUS_PATTERNS:
        if p.lower() in lower:
            raise SecurityError("Blocked: suspicious pattern detected")
    return raw


_SPREADSHEET_ID_RE = re.compile(r"^[a-zA-Z0-9\-]+$")

# Yahoo-style symbols: RELIANCE.NS, ^NSEI (1–20 chars)
_MARKET_SYMBOL_RE = re.compile(r"^[A-Z0-9.\^\-]{1,20}$")
_MARKET_NEWS_QUERY_RE = re.compile(r"^[A-Za-z0-9.\^\- ]{1,100}$")

_BLOCKED_SQL_FRAGMENTS = re.compile(
    r"(?is)\b(DROP\s+TABLE|DROP\s+DATABASE|TRUNCATE)\b"
)
_IMAGE_EXT = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})
_MAX_IMAGE_BYTES = 10 * 1024 * 1024

_DEPLOY_REPO_NAME_RE = re.compile(r"^[a-zA-Z0-9-]{1,100}$")
_NOTION_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)


def validate_spreadsheet_id(spreadsheet_id: str) -> None:
    """
    Google spreadsheet IDs: alphanumeric + hyphens, length 20–80.
    Blocks path traversal patterns and whitespace.
    """
    raw = spreadsheet_id or ""
    if not raw.strip():
        raise SecurityError("spreadsheet_id is required.")
    if " " in raw or "\t" in raw or "\n" in raw:
        raise SecurityError("Invalid spreadsheet_id: contains whitespace.")
    sid = raw.strip()
    if ".." in sid or "/" in sid or "\\" in sid:
        raise SecurityError("Invalid spreadsheet_id: contains forbidden characters.")
    if len(sid) < 20 or len(sid) > 80:
        raise SecurityError(
            f"spreadsheet_id length must be 20–80 characters (got {len(sid)})."
        )
    if not _SPREADSHEET_ID_RE.match(sid):
        raise SecurityError(
            "spreadsheet_id must contain only letters, digits, and hyphens."
        )


def validate_step(step: ExecutionStep) -> None:
    """Raises SecurityError if the step is unsafe. Called before every tool invocation."""
    if step.tool == ToolName.TERMINAL:
        _check_terminal(step)
    elif step.tool == ToolName.FILESYSTEM:
        _check_filesystem(step)
    elif step.tool == ToolName.BROWSER:
        _check_url(step.params.get("url", ""), "Browser")
    elif step.tool == ToolName.HTTP:
        url = step.params.get("url", "")
        if not url:
            raise SecurityError("HTTP step missing 'url' param.")
        _check_url(url, "HTTP")
    elif step.tool == ToolName.GOOGLE_SHEETS:
        _check_google_sheets(step)
    elif step.tool == ToolName.MARKET_DATA:
        _check_market_data(step)
    elif step.tool == ToolName.PHONE:
        _check_phone(step)
    elif step.tool == ToolName.DATABASE:
        _check_database(step)
    elif step.tool == ToolName.IMAGE_ANALYZER:
        _check_image_analyzer(step)
    elif step.tool == ToolName.SECURITY_SCANNER:
        _check_security_scanner(step)
    elif step.tool == ToolName.DEPLOYER:
        _check_deployer(step)
    elif step.tool == ToolName.NOTION:
        _check_notion(step)
    elif step.tool == ToolName.LINKEDIN:
        pass
    elif step.tool == ToolName.INSTAGRAM:
        _check_instagram(step)


def _check_instagram(step: ExecutionStep) -> None:
    act = (step.action or "").strip().lower()
    p = step.params or {}
    if act != "post_image":
        return
    path_str = str(p.get("image_path", "")).strip()
    if not path_str:
        raise SecurityError("image_path is required.")
    ip = Path(path_str).resolve()
    ws = workspace_root()
    allowed = [ws, Path("/tmp/pantheon_v2").resolve()]
    if not any(_is_inside(ip, a) for a in allowed):
        raise SecurityError("image_path must be under workspace.")
    if not ip.is_file():
        raise SecurityError("image_path must exist.")


def validate_notion_id(raw: str, field: str = "id") -> None:
    s = (raw or "").strip()
    if not s:
        raise SecurityError(f"{field} is required.")
    if ".." in s or "/" in s or "\\" in s or " " in s:
        raise SecurityError(f"Invalid {field}: forbidden characters.")
    if not _NOTION_UUID_RE.match(s):
        raise SecurityError(f"{field} must be a UUID.")


def _check_deployer(step: ExecutionStep) -> None:
    act = (step.action or "").strip().lower()
    p = step.params or {}
    ws = workspace_root()
    allowed = [ws, Path("/tmp/pantheon_v2").resolve()]
    if act in ("deploy_to_railway", "deploy_to_vercel"):
        pp = Path(str(p.get("project_path", ""))).resolve()
        if not any(_is_inside(pp, a) for a in allowed):
            raise SecurityError("project_path must be under the workspace.")
    elif act == "create_github_repo":
        name = str(p.get("repo_name", "")).strip()
        if not name or not _DEPLOY_REPO_NAME_RE.match(name):
            raise SecurityError("repo_name must be alphanumeric with hyphens only (1–100 chars).")
    elif act == "push_to_github":
        lp = Path(str(p.get("local_path", ""))).resolve()
        if not any(_is_inside(lp, a) for a in allowed):
            raise SecurityError("local_path must be under the workspace.")


def _check_notion(step: ExecutionStep) -> None:
    act = (step.action or "").strip().lower()
    p = step.params or {}
    if act == "create_page":
        validate_notion_id(str(p.get("parent_page_id", "")), "parent_page_id")
    elif act in ("update_page", "read_page", "append_to_page"):
        validate_notion_id(str(p.get("page_id", "")), "page_id")
    elif act == "create_database_entry":
        validate_notion_id(str(p.get("database_id", "")), "database_id")


def validate_phone_number(num: str) -> str:
    """E.164-style: + then 10–15 digits; blocks 000/999 prefixes after +."""
    raw = (num or "").strip()
    if not raw.startswith("+"):
        raise SecurityError("Phone number must start with +.")
    digits = raw[1:]
    if not digits.isdigit():
        raise SecurityError("Phone number must contain only digits after +.")
    if len(digits) < 10 or len(digits) > 15:
        raise SecurityError("Phone number must have 10–15 digits after +.")
    if digits.startswith("000") or digits.startswith("999"):
        raise SecurityError("Phone numbers starting with 000 or 999 are blocked.")
    return raw


def validate_database_sql(sql: str) -> None:
    """Blocks dangerous patterns in SQL passed to the database tool."""
    q = sql or ""
    if _BLOCKED_SQL_FRAGMENTS.search(q):
        raise SecurityError("SQL contains forbidden keywords (DROP TABLE, DROP DATABASE, TRUNCATE).")
    for m in re.finditer(r"(?is)\bdelete\s+from\s+[^;]+", q):
        chunk = m.group(0)
        if not re.search(r"\bwhere\b", chunk):
            raise SecurityError("DELETE without WHERE is not allowed.")


def validate_image_analysis_path(path_str: str) -> Path:
    if not path_str:
        raise SecurityError("image_path is required.")
    p = Path(path_str).resolve()
    ws = workspace_root()
    allowed = [ws, Path("/tmp/pantheon_v2").resolve()]
    if not any(_is_inside(p, a) for a in allowed):
        raise SecurityError("Image path must be within the workspace.")
    ext = p.suffix.lower()
    if ext not in _IMAGE_EXT:
        raise SecurityError(f"Image must be one of: {sorted(_IMAGE_EXT)}")
    if p.is_file() and p.stat().st_size > _MAX_IMAGE_BYTES:
        raise SecurityError("Image file exceeds 10MB limit.")
    return p


def validate_security_target_url(url: str) -> None:
    if not url:
        raise SecurityError("url is required.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SecurityError("URL must use http or https.")
    if parsed.username is not None or parsed.password is not None:
        raise SecurityError("URLs with embedded credentials are not allowed.")
    host = (parsed.hostname or "").lower()
    if not host:
        raise SecurityError("URL must include a host.")
    _raise_if_internal_host(host)


def validate_security_target_domain(domain: str) -> None:
    d = (domain or "").strip().lower()
    if not d:
        raise SecurityError("domain is required.")
    d = d.split("/")[0].split(":")[0]
    _raise_if_internal_host(d)


def _raise_if_internal_host(host: str) -> None:
    h = host.strip().lower()
    if h in BLOCKED_URL_HOSTS or h.endswith(".localhost"):
        raise SecurityError(f"Access to '{h}' is blocked (internal / unsafe host).")
    if h.startswith("192.168.") or h.startswith("10.") or h.startswith("172.16."):
        raise SecurityError(f"Access to '{h}' is blocked (private network).")
    if h.startswith("172."):
        try:
            first_octets = h.split(".")
            if len(first_octets) >= 2:
                second = int(first_octets[1])
                if 16 <= second <= 31:
                    raise SecurityError(f"Access to '{h}' is blocked (private network).")
        except (ValueError, IndexError):
            pass
    try:
        ip = ipaddress.ip_address(h)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            raise SecurityError(f"Access to '{h}' is blocked (non-public address).")
    except ValueError:
        pass


def validate_database_connection_string(cs: str) -> None:
    raw = (cs or "").strip()
    if not raw:
        raise SecurityError("connection_string is required.")
    p = urlparse(raw)
    scheme = (p.scheme or "").lower()
    if scheme == "sqlite":
        path_part = unquote(p.path or "")
        if path_part.startswith("/"):
            db_path = Path(path_part)
        else:
            db_path = Path(path_part)
        if not db_path.is_absolute():
            db_path = Path.cwd() / db_path
        db_path = db_path.resolve()
        ws = workspace_root()
        allowed_paths = [ws, Path("/tmp/pantheon_v2").resolve()]
        if not any(_is_inside(db_path, a) for a in allowed_paths):
            raise SecurityError("SQLite database path must be under the workspace.")
        return
    if scheme in ("postgresql", "postgres", "mysql"):
        wl = (settings.database_whitelist or os.environ.get("DATABASE_WHITELIST") or "").strip()
        allowed_hosts = {x.strip().lower() for x in wl.split(",") if x.strip()}
        host = (p.hostname or "").lower()
        if not host:
            raise SecurityError("Database URL must include a host.")
        _raise_if_internal_host(host)
        if not allowed_hosts:
            raise SecurityError(
                "PostgreSQL/MySQL requires DATABASE_WHITELIST to list allowed hosts."
            )
        if host not in allowed_hosts:
            raise SecurityError(
                "Database host is not in DATABASE_WHITELIST."
            )
        return
    raise SecurityError(f"Unsupported database scheme: {scheme}")


def _check_phone(step: ExecutionStep) -> None:
    act = (step.action or "").strip().lower()
    p = step.params or {}
    if act in ("make_call", "send_sms", "schedule_callback"):
        validate_phone_number(str(p.get("to_number", "")))
    if act == "start_conference":
        parts = p.get("participants") or []
        if not isinstance(parts, list):
            raise SecurityError("participants must be a list.")
        for n in parts:
            validate_phone_number(str(n).strip())


def _check_database(step: ExecutionStep) -> None:
    p = step.params or {}
    act = (step.action or "").strip().lower()
    if act == "backup_sqlite":
        db_path = str(p.get("db_path", "")).strip()
        if not db_path:
            raise SecurityError("db_path is required.")
        resolved = Path(db_path).resolve()
        ws = workspace_root()
        allowed = [ws, Path("/tmp/pantheon_v2").resolve()]
        if not any(_is_inside(resolved, a) for a in allowed):
            raise SecurityError("db_path must be under the workspace.")
        return
    cs = str(p.get("connection_string", "")).strip()
    validate_database_connection_string(cs)
    if act == "connect_and_query":
        validate_database_sql(str(p.get("query", "")))
    elif act == "execute_statement":
        validate_database_sql(str(p.get("statement", "")))


def _check_image_analyzer(step: ExecutionStep) -> None:
    p = step.params or {}
    path_str = str(p.get("image_path", "")).strip()
    if path_str:
        validate_image_analysis_path(path_str)
        return
    p1 = str(p.get("image1_path", "")).strip()
    p2 = str(p.get("image2_path", "")).strip()
    if p1:
        validate_image_analysis_path(p1)
    if p2:
        validate_image_analysis_path(p2)


def _check_security_scanner(step: ExecutionStep) -> None:
    act = (step.action or "").strip().lower()
    p = step.params or {}
    if act in ("scan_website", "check_security_headers", "generate_security_report"):
        validate_security_target_url(str(p.get("url", p.get("target_url", ""))))
    elif act == "check_ssl":
        validate_security_target_domain(str(p.get("domain", "")))


def validate_market_symbol(symbol: str) -> str:
    s = (symbol or "").strip().upper()
    if not s or not _MARKET_SYMBOL_RE.match(s):
        raise SecurityError(
            "Invalid market symbol: use 1–20 chars [A-Z0-9.^\\-] only (e.g. RELIANCE.NS)."
        )
    return s


def validate_market_symbols_batch(symbols: list[str], max_n: int = 10) -> list[str]:
    if len(symbols) > max_n:
        raise SecurityError(f"At most {max_n} symbols allowed per market_data call.")
    return [validate_market_symbol(str(x)) for x in symbols]


def validate_market_news_query(q: str) -> str:
    s = (q or "").strip()
    if not s or not _MARKET_NEWS_QUERY_RE.match(s):
        raise SecurityError(
            "Invalid news query: letters, digits, spaces, .^\\- only, max 100 chars."
        )
    return s


def _check_market_data(step: ExecutionStep) -> None:
    act = (step.action or "").strip().lower()
    p = step.params or {}
    if act in ("get_quote", "get_history"):
        validate_market_symbol(str(p.get("symbol", "")))
    elif act == "get_news":
        validate_market_news_query(str(p.get("query", "")))
    elif act in ("get_screener", "get_indices"):
        return
    else:
        raise SecurityError(f"Unknown market_data action: {act}")


def _check_google_sheets(step: ExecutionStep) -> None:
    action = (step.action or "").strip()
    if action == "create_sheet":
        return
    sid = step.params.get("spreadsheet_id", "")
    if not sid:
        raise SecurityError("Google Sheets step missing 'spreadsheet_id'.")
    validate_spreadsheet_id(str(sid))


def _check_terminal(step: ExecutionStep) -> None:
    cmd: str = step.params.get("command", "").strip()
    if not cmd:
        raise SecurityError("Terminal step has empty command.")

    try:
        tokens = shlex.split(cmd)
    except ValueError as e:
        raise SecurityError(f"Cannot parse command: {e}")

    base = Path(tokens[0]).name
    if base not in settings.allowed_commands:
        raise SecurityError(
            f"Command '{base}' is not allowed. "
            f"Allowed: {sorted(settings.allowed_commands)}"
        )

    # One shell command per step: no chaining (curl a; curl b). curl may use multiple flags per argv.
    for pattern in DANGEROUS_SHELL:
        if pattern in cmd:
            raise SecurityError(
                f"Shell pattern '{pattern}' is not allowed. Use separate steps."
            )


def _check_filesystem(step: ExecutionStep) -> None:
    path_str: str = step.params.get("path", "")
    if not path_str:
        raise SecurityError("Filesystem step missing 'path' param.")

    resolved = Path(path_str).resolve()
    ws = workspace_root()
    if _user_workspace.get() is not None:
        allowed = [ws]
    else:
        # Legacy: configured workspace + default pantheon path
        allowed = [ws, Path("/tmp/pantheon_v2").resolve()]

    if not any(_is_inside(resolved, a) for a in allowed):
        raise SecurityError(
            f"Path '{resolved}' is outside the workspace '{ws}'. "
            "All file operations must stay within the workspace."
        )


def _check_url(url: str, tool: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise SecurityError(f"{tool} URL must use http/https. Got: '{parsed.scheme}'")
    host = (parsed.hostname or "").lower()
    if host in BLOCKED_URL_HOSTS or host.startswith(("192.168.", "10.", "172.16.")):
        raise SecurityError(f"{tool}: access to '{host}' is blocked (internal address).")


def _is_inside(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
