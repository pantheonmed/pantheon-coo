"""
tests/test_security.py
───────────────────────
Tests for the security sandbox, API auth, and rate limiter.
All tests run without real API calls.
"""
import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient

from security.sandbox import SecurityError, validate_step, _check_url
from security.rate_limit import _check, _windows
from models import ExecutionStep, ToolName, StepStatus


# ─────────────────────────────────────────────────────────────────────────────
# Sandbox — terminal validation
# ─────────────────────────────────────────────────────────────────────────────

class TestTerminalSandbox:
    def _make_step(self, command: str) -> ExecutionStep:
        return ExecutionStep(
            step_id=1, tool=ToolName.TERMINAL, action="run_command",
            params={"command": command},
        )

    def test_allowed_command_passes(self):
        step = self._make_step("ls -la /tmp/pantheon_v2")
        validate_step(step)  # should not raise

    def test_blocked_command_raises(self):
        step = self._make_step("rm -rf /")
        with pytest.raises(SecurityError, match="not allowed"):
            validate_step(step)

    def test_empty_command_raises(self):
        step = self._make_step("")
        with pytest.raises(SecurityError, match="empty"):
            validate_step(step)

    def test_shell_injection_pipe_blocked(self):
        step = self._make_step("ls | cat /etc/passwd")
        with pytest.raises(SecurityError):
            validate_step(step)

    def test_shell_injection_semicolon_blocked(self):
        step = self._make_step("ls; rm -rf /tmp")
        with pytest.raises(SecurityError):
            validate_step(step)

    def test_shell_injection_redirect_blocked(self):
        step = self._make_step("echo hello > /etc/hosts")
        with pytest.raises(SecurityError):
            validate_step(step)

    def test_shell_injection_subshell_blocked(self):
        step = self._make_step("echo $(cat /etc/passwd)")
        with pytest.raises(SecurityError):
            validate_step(step)

    def test_python3_allowed(self):
        step = self._make_step("python3 --version")
        validate_step(step)  # should not raise

    def test_git_allowed(self):
        step = self._make_step("git status")
        validate_step(step)


# ─────────────────────────────────────────────────────────────────────────────
# Sandbox — filesystem validation
# ─────────────────────────────────────────────────────────────────────────────

class TestFilesystemSandbox:
    def _make_step(self, path: str, action: str = "read_file") -> ExecutionStep:
        return ExecutionStep(
            step_id=1, tool=ToolName.FILESYSTEM, action=action,
            params={"path": path},
        )

    def test_workspace_path_allowed(self):
        step = self._make_step("/tmp/pantheon_v2/output.txt")
        validate_step(step)  # should not raise

    def test_system_path_blocked(self):
        step = self._make_step("/etc/passwd")
        with pytest.raises(SecurityError, match="workspace"):
            validate_step(step)

    def test_home_dir_blocked(self):
        step = self._make_step("/root/.ssh/id_rsa")
        with pytest.raises(SecurityError, match="workspace"):
            validate_step(step)

    def test_path_traversal_blocked(self):
        step = self._make_step("/tmp/pantheon_v2/../../etc/passwd")
        with pytest.raises(SecurityError, match="workspace"):
            validate_step(step)

    def test_missing_path_raises(self):
        step = self._make_step("")
        with pytest.raises(SecurityError, match="missing"):
            validate_step(step)


# ─────────────────────────────────────────────────────────────────────────────
# Sandbox — URL validation
# ─────────────────────────────────────────────────────────────────────────────

class TestURLSandbox:
    def test_https_allowed(self):
        _check_url("https://example.com/api", "HTTP")  # no raise

    def test_http_allowed(self):
        _check_url("http://api.example.com", "HTTP")  # no raise

    def test_ftp_blocked(self):
        with pytest.raises(SecurityError, match="http"):
            _check_url("ftp://files.example.com", "HTTP")

    def test_localhost_blocked(self):
        with pytest.raises(SecurityError, match="blocked"):
            _check_url("http://localhost/api", "Browser")

    def test_loopback_blocked(self):
        with pytest.raises(SecurityError, match="blocked"):
            _check_url("http://127.0.0.1/", "HTTP")

    def test_aws_metadata_blocked(self):
        with pytest.raises(SecurityError, match="blocked"):
            _check_url("http://169.254.169.254/latest/meta-data/", "HTTP")

    def test_private_ip_blocked(self):
        with pytest.raises(SecurityError, match="blocked"):
            _check_url("http://192.168.1.100/admin", "HTTP")


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter
# ─────────────────────────────────────────────────────────────────────────────

class TestRateLimiter:
    def setup_method(self):
        """Clear rate limit state between tests."""
        _windows.clear()

    def test_under_limit_passes(self):
        for _ in range(5):
            _check("test_key", 10)  # no raise

    def test_over_limit_raises(self):
        from fastapi import HTTPException
        for _ in range(10):
            _check("test_key2", 10)
        with pytest.raises(HTTPException) as exc_info:
            _check("test_key2", 10)
        assert exc_info.value.status_code == 429

    def test_different_keys_independent(self):
        for _ in range(10):
            _check("key_a", 10)
        # key_b should be unaffected
        _check("key_b", 10)  # no raise


# ─────────────────────────────────────────────────────────────────────────────
# API authentication
# ─────────────────────────────────────────────────────────────────────────────

class TestAPIAuth:
    def test_no_auth_mode_allows_all(self, client):
        """AUTH_MODE=none (default in tests) allows all requests."""
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_apikey_mode_rejects_missing_key(self, client):
        """Missing key when auth is configured raises 401."""
        with patch.dict(os.environ, {"AUTH_MODE": "apikey", "COO_API_KEY": "s3cr3t"}):
            from security import auth as auth_mod
            import importlib
            importlib.reload(auth_mod)
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                auth_mod._check_api_key(None)
            assert exc.value.status_code == 401

    def test_apikey_mode_rejects_wrong_key(self):
        with patch.dict(os.environ, {"AUTH_MODE": "apikey", "COO_API_KEY": "correct-key"}):
            from security import auth as auth_mod
            import importlib
            importlib.reload(auth_mod)
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc:
                auth_mod._check_api_key("wrong-key")
            assert exc.value.status_code == 403

    def test_apikey_mode_accepts_correct_key(self):
        with patch.dict(os.environ, {"AUTH_MODE": "apikey", "COO_API_KEY": "correct-key"}):
            from security import auth as auth_mod
            import importlib
            importlib.reload(auth_mod)
            result = auth_mod._check_api_key("correct-key")
            assert result["authenticated"] is True
