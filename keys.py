"""Named API keys. MCP_AUTH_TOKEN remains the admin key."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from contextvars import ContextVar
from typing import Any

current_auth: ContextVar[dict[str, Any] | None] = ContextVar("current_auth", default=None)

from studio_store import now_iso, read_json, write_json


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def admin_token() -> str:
    return (os.environ.get("MCP_AUTH_TOKEN") or "").strip()


def _load() -> list[dict[str, Any]]:
    raw = read_json("api_keys.json", [])
    return raw if isinstance(raw, list) else []


def create_key(name: str, role: str = "workshop", plan: str = "") -> dict[str, Any]:
    token = "lzr_" + secrets.token_urlsafe(24)
    plan_id = (plan or ("pro" if role == "admin" else "maker" if role == "workshop" else role) or "free").strip().lower()
    if plan_id not in {"free", "maker", "pro", "admin"}:
        plan_id = "maker"
    if plan_id == "admin":
        plan_id = "pro"
    row = {
        "id": secrets.token_hex(4),
        "name": str(name or "key")[:40],
        "role": role,
        "plan": plan_id,
        "hash": _hash(token),
        "created": now_iso(),
        "last_used": None,
    }
    rows = _load()
    rows.append(row)
    write_json("api_keys.json", rows)
    return {"id": row["id"], "name": row["name"], "role": role, "token": token, "note": "shown once"}


def touch_key(key_id: str) -> None:
    rows = _load()
    changed = False
    for row in rows:
        if row.get("id") == key_id:
            row["last_used"] = now_iso()
            changed = True
    if changed:
        write_json("api_keys.json", rows)


def resolve_key(token: str | None) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if not raw:
        return None
    admin = admin_token()
    if admin:
        left = raw.encode("utf-8")
        right = admin.encode("utf-8")
        if len(left) == len(right) and hmac.compare_digest(left, right):
            return {"id": "admin", "name": "MCP_AUTH_TOKEN", "role": "admin", "plan": "pro"}
    digest = _hash(raw)
    for row in _load():
        if row.get("hash") == digest:
            touch_key(str(row.get("id")))
            return {
                "id": row.get("id"),
                "name": row.get("name"),
                "role": row.get("role") or "workshop",
                "plan": row.get("plan") or "maker",
            }
    return None


def auth_required() -> bool:
    return bool(admin_token() or _load())


def list_keys() -> list[dict[str, Any]]:
    return [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "role": r.get("role"),
            "plan": r.get("plan") or "maker",
            "created": r.get("created"),
            "last_used": r.get("last_used"),
        }
        for r in _load()
    ]
