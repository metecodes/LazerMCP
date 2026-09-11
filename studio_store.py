"""On-disk studio data: profiles, keys, usage, projects. Not a new kit catalog."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from boxes_adapter import OUTPUT_DIR, ROOT


def data_dir() -> Path:
    env = (os.environ.get("MCP_DATA_DIR") or "").strip()
    path = Path(env) if env else (OUTPUT_DIR / "studio")
    path.mkdir(parents=True, exist_ok=True)
    return path


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def read_json(name: str, default: Any) -> Any:
    path = data_dir() / name
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(name: str, payload: Any) -> None:
    path = data_dir() / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(name: str, row: dict[str, Any]) -> None:
    path = data_dir() / name
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def repo_root() -> Path:
    return ROOT
