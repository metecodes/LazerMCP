"""Supabase Google identity. Individuals sign in; software does not invent a user."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from studio_store import now_iso, read_json, write_json


def supabase_url() -> str:
    return (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")


def supabase_anon_key() -> str:
    return (
        os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("SUPABASE_PUBLISHABLE_KEY")
        or ""
    ).strip()


def configured() -> bool:
    return bool(supabase_url() and supabase_anon_key())


def org_domains() -> list[str]:
    raw = (os.environ.get("LASERMCP_ORG_DOMAINS") or "").strip()
    return [p.strip().lower() for p in raw.split(",") if p.strip()]


_SAFE_NEXT_PATH = re.compile(r"^/[A-Za-z0-9/._~-]*$")


def _email_host(email: str) -> str:
    raw = str(email or "").strip().lower()
    return raw.split("@")[-1] if "@" in raw else ""


def is_org_email(email: str) -> bool:
    domains = org_domains()
    host = _email_host(email)
    return bool(domains) and host in domains


def safe_next_path(raw: str, *, origins: list[str] | None = None) -> str:
    value = (raw or "").strip()
    if not value or any(ch in value for ch in ("\n", "\r", "\\")):
        return ""
    if value.startswith("//"):
        return ""
    if value.startswith("/"):
        path = value.split("?", 1)[0]
        return value if _SAFE_NEXT_PATH.fullmatch(path) else ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    allowed = {urlparse(o).netloc.lower() for o in (origins or []) if o}
    if not allowed or parsed.netloc.lower() not in allowed:
        return ""
    path = parsed.path or "/"
    if not _SAFE_NEXT_PATH.fullmatch(path):
        return ""
    return path + (("?" + parsed.query) if parsed.query else "")


def public_config(mcp_url: str) -> dict[str, Any]:
    return {
        "success": True,
        "configured": configured(),
        "url": supabase_url() if configured() else "",
        "anon_key": supabase_anon_key() if configured() else "",
        "google": True,
        "mcp_url": mcp_url,
        "org_domains": org_domains(),
        "note": (
            "Individuals must sign in with Google. "
            "Organizations mint API keys after Google sign-in. "
            "A bare MCP URL is not enough."
        ),
    }


def verify_access_token(token: str | None) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if not raw or not configured():
        return None
    req = urllib.request.Request(
        f"{supabase_url()}/auth/v1/user",
        headers={
            "Authorization": f"Bearer {raw}",
            "apikey": supabase_anon_key(),
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or not payload.get("id"):
        return None
    email = str(payload.get("email") or "")
    meta = payload.get("user_metadata") if isinstance(payload.get("user_metadata"), dict) else {}
    return {
        "id": str(payload.get("id")),
        "email": email,
        "name": str(meta.get("full_name") or meta.get("name") or email or "user"),
        "provider": "google",
    }


def _users() -> list[dict[str, Any]]:
    rows = read_json("users.json", [])
    return rows if isinstance(rows, list) else []


def upsert_user(identity: dict[str, Any], *, kind: str | None = None) -> dict[str, Any]:
    rows = _users()
    uid = str(identity.get("id") or "")
    hit: dict[str, Any] | None = None
    for row in rows:
        if str(row.get("id")) == uid:
            hit = row
            break
    if hit is None:
        hit = {
            "id": uid,
            "email": identity.get("email"),
            "name": identity.get("name"),
            "kind": "individual",
            "created": now_iso(),
        }
        rows.append(hit)
    hit["email"] = identity.get("email") or hit.get("email")
    hit["name"] = identity.get("name") or hit.get("name")
    hit["last_seen"] = now_iso()
    hit["kind"] = "org" if is_org_email(str(hit.get("email") or "")) else "individual"
    write_json("users.json", rows)
    return dict(hit)


def user_by_id(uid: str) -> dict[str, Any] | None:
    for row in _users():
        if str(row.get("id")) == str(uid):
            return dict(row)
    return None


def can_mint_keys(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    return is_org_email(str(user.get("email") or ""))


def _session_secret() -> bytes:
    raw = (
        os.environ.get("MCP_SESSION_SECRET")
        or os.environ.get("MCP_AUTH_TOKEN")
        or supabase_anon_key()
        or "lasermcp-dev-session"
    )
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def new_session(user: dict[str, Any]) -> str:
    payload = {
        "id": user.get("id"),
        "email": user.get("email"),
        "name": user.get("name"),
        "kind": "org" if is_org_email(str(user.get("email") or "")) else "individual",
        "exp": int(time.time()) + 30 * 24 * 3600,
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    sig = _b64(hmac.new(_session_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _parse_signed_session(raw: str) -> dict[str, Any] | None:
    if "." not in raw:
        return None
    body, _, sig = raw.partition(".")
    if not body or not sig:
        return None
    expected = _b64(hmac.new(_session_secret(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        payload = json.loads(_b64d(body).decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict) or not payload.get("id"):
        return None
    if int(payload.get("exp") or 0) <= int(time.time()):
        return None
    email = str(payload.get("email") or "")
    kind = "org" if is_org_email(email) else "individual"
    return {
        "id": str(payload.get("id")),
        "email": email,
        "name": str(payload.get("name") or email or "user"),
        "kind": kind,
    }


def session_user(sid: str | None) -> dict[str, Any] | None:
    raw = (sid or "").strip()
    if not raw:
        return None
    signed = _parse_signed_session(raw)
    if signed:
        return signed
    for row in read_json("sessions.json", []) or []:
        if isinstance(row, dict) and row.get("id") == raw:
            stored = user_by_id(str(row.get("user_id") or ""))
            if stored:
                return stored
    return None


def principal_from_identity(identity: dict[str, Any], stored: dict[str, Any] | None = None) -> dict[str, Any]:
    row = stored or {}
    kind = str(row.get("kind") or "individual")
    return {
        "id": identity.get("id") or row.get("id"),
        "name": identity.get("name") or row.get("name") or "user",
        "email": identity.get("email") or row.get("email"),
        "role": "workshop" if kind == "org" else "individual",
        "plan": "maker" if kind == "org" else "free",
        "kind": kind,
        "provider": "google",
    }
