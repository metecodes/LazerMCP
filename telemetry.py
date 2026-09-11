"""Structured events. Never store SVG bodies or secrets."""

from __future__ import annotations

from typing import Any

from studio_store import append_jsonl, data_dir, now_iso


def emit(level: str, event: str, detail: str = "", extra: dict[str, Any] | None = None) -> None:
    row = {"at": now_iso(), "level": level, "event": event, "detail": str(detail)[:400]}
    if extra:
        for field in ("file_id", "final_status", "tool", "key"):
            if extra.get(field) is not None:
                row[field] = extra[field]
    append_jsonl("telemetry.jsonl", row)


def recent(limit: int = 80) -> list[dict[str, Any]]:
    path = data_dir() / "telemetry.jsonl"
    if not path.is_file():
        return []
    import json

    rows = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows
