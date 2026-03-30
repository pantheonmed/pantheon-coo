"""tools/filesystem.py — File system operations."""
from pathlib import Path
from typing import Any


async def execute(action: str, params: dict[str, Any]) -> Any:
    handlers = {
        "read_file":   _read,
        "write_file":  _write,
        "list_dir":    _list,
        "make_dir":    _mkdir,
        "delete_file": _delete,
        "file_exists": _exists,
    }
    fn = handlers.get(action)
    if fn is None:
        raise ValueError(f"Unknown filesystem action: '{action}'. Available: {list(handlers)}")
    return await fn(params)


async def _read(p): return Path(p["path"]).read_text(encoding="utf-8")

async def _write(p):
    path = Path(p["path"]); path.parent.mkdir(parents=True, exist_ok=True)
    content = p.get("content", "")
    if p.get("mode") == "a":
        with path.open("a", encoding="utf-8") as f: f.write(content)
    else:
        path.write_text(content, encoding="utf-8")
    return {"path": str(path), "bytes": len(content.encode())}

async def _list(p):
    path = Path(p["path"])
    if not path.exists(): raise FileNotFoundError(f"Not found: {path}")
    return [{"name": e.name, "type": "dir" if e.is_dir() else "file", "size": e.stat().st_size}
            for e in sorted(path.iterdir())]

async def _mkdir(p):
    Path(p["path"]).mkdir(parents=True, exist_ok=True)
    return {"created": p["path"]}

async def _delete(p):
    path = Path(p["path"])
    if not path.exists(): return {"deleted": False, "reason": "not found"}
    path.unlink(); return {"deleted": True}

async def _exists(p): return Path(p["path"]).exists()
