"""Named API keys. MCP_AUTH_TOKEN remains the admin key."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from contextvars import ContextVar
from typing import Any

current_auth: ContextVar[dict[str, Any] | None] = ContextVar("current_auth", default=None)

from studio_store import now_iso, read_json, write_json

_TOUCH_INTERVAL = 3600
_last_touch: dict[str, float] = {}


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
    prefix = token[:12]
    row = {
        "id": secrets.token_hex(4),
        "name": str(name or "key")[:40],
        "role": role,
        "plan": plan_id,
        "kind": kind or "org",
        "owner": owner,
        "email": email,
        "hash": _hash(token),
        "prefix": prefix,
        "created": now_iso(),
        "last_used": None,
        "expires_at": None,
        "revoked_at": None,
    }
    rows = _load()
    rows.append(row)
    write_json("api_keys.json", rows)
    org_id = ""
    if owner:
        try:
            from persist.orgs import ensure_personal_org

            org_id = ensure_personal_org(owner, email or owner)
        except Exception:
            org_id = ""
    try:
        from persist.keys_repo import KeyRepository

        KeyRepository().insert(
            {
                **row,
                "owner_user_id": owner,
                "organization_id": org_id,
                "created_at": row["created"],
            }
        )
    except Exception:
        pass
    return {"id": row["id"], "name": row["name"], "role": role, "token": token, "prefix": prefix, "note": "shown once"}


def touch_key(key_id: str) -> None:
    now = time.time()
    if now - _last_touch.get(key_id, 0) < _TOUCH_INTERVAL:
        return
    _last_touch[key_id] = now
    rows = _load()
    changed = False
    stamp = now_iso()
    for row in rows:
        if row.get("id") == key_id:
            prev = str(row.get("last_used") or "")
            if prev and prev[:13] == stamp[:13]:
                return
            row["last_used"] = stamp
            changed = True
    if changed:
        write_json("api_keys.json", rows)
    try:
        from persist.keys_repo import KeyRepository

        KeyRepository().touch(key_id)
    except Exception:
        pass


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
    durable = None
    try:
        from persist.keys_repo import KeyRepository

        durable = KeyRepository().by_hash(digest)
    except Exception:
        durable = None
    if durable:
        if _key_blocked(durable):
            return None
        touch_key(str(durable.get("id")))
        return _principal_from_key_row(durable, owner_field="owner_user_id")
    for row in _load():
        if row.get("hash") == digest:
            if _key_blocked(row):
                return None
            touch_key(str(row.get("id")))
            return _principal_from_key_row(row, owner_field="owner")
    return None


def _key_blocked(row: dict[str, Any]) -> bool:
    if row.get("revoked_at") or row.get("revoked"):
        return True
    exp = str(row.get("expires_at") or "")
    return bool(exp and exp <= now_iso())


def _principal_from_key_row(row: dict[str, Any], *, owner_field: str) -> dict[str, Any]:
    owner = str(row.get(owner_field) or row.get("owner") or "")
    org_id = str(row.get("organization_id") or "")
    if owner and not org_id:
        try:
            from persist.orgs import ensure_personal_org

            org_id = ensure_personal_org(owner, str(row.get("email") or ""))
        except Exception:
            org_id = ""
    return {
        "id": row.get("id"),
        "name": row.get("name"),
        "role": row.get("role") or "workshop",
        "plan": row.get("plan") or "maker",
        "kind": row.get("kind") or "org",
        "owner": owner,
        "email": row.get("email"),
        "organization_id": org_id,
    }


def revoke_key(key_id: str, owner: str = "") -> bool:
    stamp = now_iso()
    rows = _load()
    changed = False
    for row in rows:
        if str(row.get("id")) != str(key_id):
            continue
        if owner and str(row.get("owner") or "") != owner:
            continue
        row["revoked_at"] = stamp
        changed = True
    if changed:
        write_json("api_keys.json", rows)
    durable = False
    try:
        from persist.keys_repo import KeyRepository

        durable = KeyRepository().revoke(key_id, owner)
    except Exception:
        durable = False
    return changed or durable


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
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        kid = str(r.get("id") or "")
        seen.add(kid)
        out.append(
            {
                "id": r.get("id"),
                "name": r.get("name"),
                "prefix": r.get("prefix"),
                "role": r.get("role"),
                "plan": r.get("plan") or "maker",
                "kind": r.get("kind") or "org",
                "email": r.get("email"),
                "created": r.get("created") or r.get("created_at"),
                "last_used": r.get("last_used") or r.get("last_used_at"),
                "expires_at": r.get("expires_at"),
                "revoked_at": r.get("revoked_at"),
            }
        )
    if owner:
        try:
            from persist.keys_repo import KeyRepository

            for r in KeyRepository().list_for_owner(owner):
                if str(r.get("id") or "") in seen:
                    continue
                out.append(
                    {
                        "id": r.get("id"),
                        "name": r.get("name"),
                        "prefix": r.get("prefix"),
                        "role": r.get("role"),
                        "plan": r.get("plan") or "maker",
                        "kind": r.get("kind") or "org",
                        "email": r.get("email"),
                        "created": r.get("created_at"),
                        "last_used": r.get("last_used_at"),
                        "expires_at": r.get("expires_at"),
                        "revoked_at": r.get("revoked_at"),
                    }
                )
        except Exception:
            pass
    return out
