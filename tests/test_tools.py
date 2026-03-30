"""
tests/test_tools.py
────────────────────
Tests for the tool execution layer.
Uses the real filesystem/terminal tools (no mocking) with a temp workspace.
"""
import asyncio
import os
import pytest
import pytest_asyncio
from pathlib import Path


WORKSPACE = "/tmp/pantheon_test_tools"


@pytest.fixture(autouse=True)
def setup_workspace():
    Path(WORKSPACE).mkdir(parents=True, exist_ok=True)
    yield
    # cleanup
    import shutil
    if Path(WORKSPACE).exists():
        shutil.rmtree(WORKSPACE)


# ─────────────────────────────────────────────────────────────────────────────
# Filesystem tool
# ─────────────────────────────────────────────────────────────────────────────

class TestFilesystemTool:
    @pytest.mark.asyncio
    async def test_make_dir(self):
        from tools.filesystem import execute
        result = await execute("make_dir", {"path": f"{WORKSPACE}/newdir"})
        assert "created" in result
        assert Path(f"{WORKSPACE}/newdir").is_dir()

    @pytest.mark.asyncio
    async def test_write_and_read_file(self):
        from tools.filesystem import execute
        path = f"{WORKSPACE}/hello.txt"
        await execute("write_file", {"path": path, "content": "hello world"})
        content = await execute("read_file", {"path": path})
        assert content == "hello world"

    @pytest.mark.asyncio
    async def test_write_append_mode(self):
        from tools.filesystem import execute
        path = f"{WORKSPACE}/append.txt"
        await execute("write_file", {"path": path, "content": "line1\n"})
        await execute("write_file", {"path": path, "content": "line2\n", "mode": "a"})
        content = await execute("read_file", {"path": path})
        assert "line1" in content
        assert "line2" in content

    @pytest.mark.asyncio
    async def test_list_dir(self):
        from tools.filesystem import execute
        await execute("write_file", {"path": f"{WORKSPACE}/a.txt", "content": "a"})
        await execute("write_file", {"path": f"{WORKSPACE}/b.txt", "content": "b"})
        result = await execute("list_dir", {"path": WORKSPACE})
        names = [e["name"] for e in result]
        assert "a.txt" in names
        assert "b.txt" in names

    @pytest.mark.asyncio
    async def test_file_exists_true(self):
        from tools.filesystem import execute
        path = f"{WORKSPACE}/exists.txt"
        await execute("write_file", {"path": path, "content": "x"})
        assert await execute("file_exists", {"path": path}) is True

    @pytest.mark.asyncio
    async def test_file_exists_false(self):
        from tools.filesystem import execute
        assert await execute("file_exists", {"path": f"{WORKSPACE}/nope.txt"}) is False

    @pytest.mark.asyncio
    async def test_read_missing_file_raises(self):
        from tools.filesystem import execute
        with pytest.raises(FileNotFoundError):
            await execute("read_file", {"path": f"{WORKSPACE}/missing.txt"})

    @pytest.mark.asyncio
    async def test_delete_file(self):
        from tools.filesystem import execute
        path = f"{WORKSPACE}/del.txt"
        await execute("write_file", {"path": path, "content": "x"})
        result = await execute("delete_file", {"path": path})
        assert result["deleted"] is True
        assert not Path(path).exists()

    @pytest.mark.asyncio
    async def test_delete_missing_file_returns_not_found(self):
        from tools.filesystem import execute
        result = await execute("delete_file", {"path": f"{WORKSPACE}/ghost.txt"})
        assert result["deleted"] is False

    @pytest.mark.asyncio
    async def test_unknown_action_raises(self):
        from tools.filesystem import execute
        with pytest.raises(ValueError, match="Unknown"):
            await execute("explode", {"path": f"{WORKSPACE}/x"})

    @pytest.mark.asyncio
    async def test_creates_nested_dirs(self):
        from tools.filesystem import execute
        path = f"{WORKSPACE}/a/b/c/deep.txt"
        await execute("write_file", {"path": path, "content": "deep"})
        assert Path(path).exists()


# ─────────────────────────────────────────────────────────────────────────────
# Terminal tool
# ─────────────────────────────────────────────────────────────────────────────

class TestTerminalTool:
    @pytest.mark.asyncio
    async def test_echo_command(self):
        from tools.terminal import execute
        result = await execute("run_command", {"command": "echo hello_pantheon"})
        assert result["success"] is True
        assert "hello_pantheon" in result["stdout"]

    @pytest.mark.asyncio
    async def test_pwd_command(self):
        from tools.terminal import execute
        result = await execute("run_command", {"command": "pwd"})
        assert result["exit_code"] == 0
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_failed_command_captures_stderr(self):
        from tools.terminal import execute
        result = await execute("run_command", {"command": "ls /nonexistent_path_xyz"})
        assert result["success"] is False
        assert result["exit_code"] != 0

    @pytest.mark.asyncio
    async def test_timeout_returns_error(self):
        from tools.terminal import execute
        result = await execute("run_command", {"command": "sleep 10", "timeout": 1})
        assert result["success"] is False
        assert "Timed out" in result["stderr"]

    @pytest.mark.asyncio
    async def test_cwd_parameter(self):
        from tools.terminal import execute
        result = await execute("run_command", {
            "command": "pwd",
            "cwd": "/tmp",
        })
        assert result["success"] is True
        assert "/tmp" in result["stdout"]

    @pytest.mark.asyncio
    async def test_unknown_action_raises(self):
        from tools.terminal import execute
        with pytest.raises(ValueError, match="Unknown"):
            await execute("hack", {"command": "ls"})
