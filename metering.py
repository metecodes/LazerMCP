"""Per-key usage log."""

from __future__ import annotations

from typing import Any

from datetime import datetime, timezone

from studio_store import append_jsonl, data_dir, now_iso


def record_usage(key: dict[str, Any] | None, tool: str, extra: dict[str, Any] | None = None) -> None:
    row = {"at": now_iso(), "key": (key or {}).get("id") or "anon", "name": (key or {}).get("name") or "anon", "tool": tool}
    if extra:
        for field in ("file_id", "bytes", "final_status", "product"):
            if extra.get(field) is not None:
                row[field] = extra[field]
    append_jsonl("usage.jsonl", row)


def usage_summary(limit: int = 200) -> dict[str, Any]:
    path = data_dir() / "usage.jsonl"
    rows: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    if path.is_file():
        import json

        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                row = json.loads(line)
            except Exception:
                continue
            rows.append(row)
            k = str(row.get("key") or "anon")
            counts[k] = counts.get(k, 0) + 1
    return {"success": True, "events": rows[-80:], "by_key": counts, "count": len(rows)}


def designs_this_month(key_id: str | None) -> int:
    path = data_dir() / "usage.jsonl"
    if not path.is_file():
        return 0
    import json

    month = datetime.now(timezone.utc).strftime("%Y-%m")
    kid = str(key_id or "anon")
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except Exception:
            continue
        if str(row.get("key") or "anon") != kid:
            continue
        if not str(row.get("at") or "").startswith(month):
            continue
        if row.get("file_id"):
            n += 1
    return n
