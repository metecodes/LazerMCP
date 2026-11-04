"""Per-key usage log with durable monthly counters for quota enforcement."""

from __future__ import annotations

from typing import Any

from datetime import datetime, timezone

from studio_store import append_jsonl, data_dir, now_iso, read_json, write_json


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _counters() -> dict[str, Any]:
    raw = read_json("usage_counters.json", {})
    return raw if isinstance(raw, dict) else {}


def _bump_counter(key_id: str) -> int:
    store = _counters()
    month = _month_key()
    bucket = store.get(month) if isinstance(store.get(month), dict) else {}
    kid = str(key_id or "anon")
    n = int(bucket.get(kid) or 0) + 1
    bucket[kid] = n
    store[month] = bucket
    # keep last 6 months
    keep = sorted(k for k in store.keys() if isinstance(k, str) and len(k) == 7)[-6:]
    write_json("usage_counters.json", {k: store[k] for k in keep})
    return n


def record_usage(key: dict[str, Any] | None, tool: str, extra: dict[str, Any] | None = None) -> None:
    kid = (key or {}).get("id") or "anon"
    row = {"at": now_iso(), "key": kid, "name": (key or {}).get("name") or "anon", "tool": tool}
    if extra:
        for field in ("file_id", "bytes", "final_status", "product"):
            if extra.get(field) is not None:
                row[field] = extra[field]
    append_jsonl("usage.jsonl", row)
    if extra and extra.get("file_id"):
        _bump_counter(str(kid))


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
    month = _month_key()
    durable = (_counters().get(month) or {}) if isinstance(_counters().get(month), dict) else {}
    return {
        "success": True,
        "events": rows[-80:],
        "by_key": counts,
        "count": len(rows),
        "month": month,
        "designs_by_key": {str(k): int(v) for k, v in durable.items()},
    }


def designs_this_month(key_id: str | None) -> int:
    kid = str(key_id or "anon")
    month = _month_key()
    durable = _counters().get(month)
    if isinstance(durable, dict) and kid in durable:
        return int(durable.get(kid) or 0)
    # Fallback scan of jsonl for older deployments without counters file
    path = data_dir() / "usage.jsonl"
    if not path.is_file():
        return 0
    import json

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
