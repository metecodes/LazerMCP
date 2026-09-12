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


def create_key(
    name: str,
    role: str = "workshop",
    plan: str = "",
    *,
    owner: str = "",
    email: str = "",
    kind: str = "org",
) -> dict[str, Any]:
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
        "kind": kind or "org",
        "owner": owner,
        "email": email,
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
                "kind": row.get("kind") or "org",
                "owner": row.get("owner"),
                "email": row.get("email"),
            }
    return None


def resolve_bearer(token: str | None) -> dict[str, Any] | None:
    """API key, MCP OAuth token, or Supabase Google access token."""
    raw = (token or "").strip()
    if not raw:
        return None
    hit = resolve_key(raw)
    if hit:
        return hit
    try:
        from oauth_mcp import resolve_oauth_token

        hit = resolve_oauth_token(raw)
        if hit:
            return hit
    except Exception:
        pass
    try:
        from supabase_auth import principal_from_identity, upsert_user, verify_access_token

        identity = verify_access_token(raw)
        if identity:
            stored = upsert_user(identity)
            return principal_from_identity(identity, stored)
    except Exception:
        pass
    return None


def auth_required() -> bool:
    try:
        from supabase_auth import configured

        if configured():
            return True
    except Exception:
        pass
    return bool(admin_token() or _load())


def list_keys(owner: str = "") -> list[dict[str, Any]]:
    rows = _load()
    if owner:
        rows = [r for r in rows if str(r.get("owner") or "") == owner]
    return [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "role": r.get("role"),
            "plan": r.get("plan") or "maker",
            "kind": r.get("kind") or "org",
            "email": r.get("email"),
            "created": r.get("created"),
            "last_used": r.get("last_used"),
        }
        for r in rows
    ]
