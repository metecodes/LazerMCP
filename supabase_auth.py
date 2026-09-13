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


DEFAULT_ADMIN_EMAIL = "metehan1387@gmail.com"


def admin_emails() -> list[str]:
    raw = (os.environ.get("LASERMCP_ADMIN_EMAILS") or DEFAULT_ADMIN_EMAIL).strip()
    emails = [p.strip().lower() for p in raw.split(",") if p.strip()]
    if DEFAULT_ADMIN_EMAIL not in emails:
        emails.append(DEFAULT_ADMIN_EMAIL)
    return emails


def is_admin(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    email = str(user.get("email") or "").strip().lower()
    return bool(email) and email in admin_emails()


ACCOUNT_MODELS = ("user", "dealer", "org")
_MODEL_ALIASES = {
    "user": "user",
    "individual": "user",
    "normal": "user",
    "bireysel": "user",
    "dealer": "dealer",
    "bayi": "dealer",
    "org": "org",
    "organization": "org",
    "kurumsal": "org",
}
_KIND_FOR_MODEL = {"user": "individual", "dealer": "dealer", "org": "org"}


def normalize_account_model(raw: str | None) -> str:
    return _MODEL_ALIASES.get(str(raw or "").strip().lower(), "")


def account_model_of(user: dict[str, Any] | None) -> str:
    if not user:
        return "user"
    if is_org_email(str(user.get("email") or "")):
        return "org"
    stored = normalize_account_model(user.get("account_model"))
    if stored in ACCOUNT_MODELS:
        return stored
    if user.get("org_grant"):
        return "org"
    if str(user.get("kind") or "").strip().lower() == "dealer":
        return "dealer"
    return "user"


def _apply_account_model(row: dict[str, Any], model: str) -> dict[str, Any]:
    resolved = normalize_account_model(model) or "user"
    row["account_model"] = resolved
    row["kind"] = _KIND_FOR_MODEL[resolved]
    row["org_grant"] = resolved == "org"
    return row


def user_is_org(user: dict[str, Any] | None) -> bool:
    return account_model_of(user) == "org"


def user_is_dealer(user: dict[str, Any] | None) -> bool:
    return account_model_of(user) == "dealer"


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


def session_ready() -> bool:
    """True when a cookie can be signed. Never returns the secret."""
    try:
        _session_secret()
    except SessionSecretError:
        return False
    except Exception:
        return False
    return True


def public_config(mcp_url: str) -> dict[str, Any]:
    ready = session_ready()
    return {
        "success": True,
        "configured": configured(),
        "session_ready": ready,
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
        "look_again": (
            []
            if ready
            else ["Production needs an independent MCP_SESSION_SECRET. Google can finish but the site cannot keep you signed in."]
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
            "account_model": "user",
            "kind": "individual",
            "created": now_iso(),
        }
        rows.append(hit)
    hit["email"] = identity.get("email") or hit.get("email")
    hit["name"] = identity.get("name") or hit.get("name")
    hit["last_seen"] = now_iso()
    _apply_account_model(hit, account_model_of(hit))
    try:
        write_json("users.json", rows)
    except Exception:
        pass
    stored = dict(hit)
    try:
        from persist.orgs import ensure_personal_org

        stored["organization_id"] = ensure_personal_org(str(stored.get("id") or ""), str(stored.get("name") or ""))
    except Exception:
        pass
    return stored


def user_by_id(uid: str) -> dict[str, Any] | None:
    for row in _users():
        if str(row.get("id")) == str(uid):
            return dict(row)
    return None


def can_mint_keys(user: dict[str, Any] | None) -> bool:
    return user_is_org(user)


def can_mint_activation(user: dict[str, Any] | None) -> bool:
    return user_is_org(user) or user_is_dealer(user) or is_admin(user)


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    model = account_model_of(row)
    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "name": row.get("name"),
        "account_model": model,
        "kind": _KIND_FOR_MODEL[model],
        "org_grant": model == "org",
        "last_seen": row.get("last_seen"),
        "created": row.get("created"),
    }


def _seen_at(raw: str):
    from datetime import datetime, timezone

    text = str(raw or "").replace("Z", "+00:00")
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp


def user_stats(*, active_days: int = 30) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    rows = _users()
    now = datetime.now(timezone.utc)
    window = timedelta(days=max(1, int(active_days)))
    active = 0
    org = 0
    dealer = 0
    users = 0
    for row in rows:
        model = account_model_of(row)
        if model == "org":
            org += 1
        elif model == "dealer":
            dealer += 1
        else:
            users += 1
        seen = _seen_at(str(row.get("last_seen") or ""))
        if seen and now - seen <= window:
            active += 1
    return {
        "active_users": active,
        "active_window_days": int(active_days),
        "total_users": len(rows),
        "org_users": org,
        "dealer_users": dealer,
        "user_users": users,
    }


def search_users(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    needle = str(query or "").strip().lower()
    if len(needle) < 2:
        return []
    out: list[dict[str, Any]] = []
    for row in _users():
        email = str(row.get("email") or "").lower()
        if needle in email:
            out.append(public_user(row))
        if len(out) >= limit:
            break
    return out


def grant_org(email: str, *, by: str) -> dict[str, Any] | None:
    needle = str(email or "").strip().lower()
    if "@" not in needle:
        return None
    rows = _users()
    hit: dict[str, Any] | None = None
    for row in rows:
        if str(row.get("email") or "").strip().lower() == needle:
            hit = row
            break
    if hit is None:
        return None
    _apply_account_model(hit, "org")
    hit["org_granted_at"] = now_iso()
    hit["org_granted_by"] = str(by or "")[:120]
    try:
        write_json("users.json", rows)
    except Exception:
        return None
    return public_user(hit)


def set_account_model(email: str, model: str, *, by: str) -> dict[str, Any] | None:
    resolved = normalize_account_model(model)
    if resolved not in ACCOUNT_MODELS:
        return None
    needle = str(email or "").strip().lower()
    if "@" not in needle:
        return None
    rows = _users()
    hit: dict[str, Any] | None = None
    for row in rows:
        if str(row.get("email") or "").strip().lower() == needle:
            hit = row
            break
    if hit is None:
        return None
    _apply_account_model(hit, resolved)
    hit["model_set_at"] = now_iso()
    hit["model_set_by"] = str(by or "")[:120]
    if resolved == "org":
        hit["org_granted_at"] = now_iso()
        hit["org_granted_by"] = str(by or "")[:120]
    try:
        write_json("users.json", rows)
    except Exception:
        return None
    return public_user(hit)


class SessionSecretError(RuntimeError):
    """Production is missing an independent MCP_SESSION_SECRET."""


def _session_secret() -> bytes:
    """HMAC material. Anon/publishable keys are never used. Production requires MCP_SESSION_SECRET."""
    from persist.env import is_production

    raw = (os.environ.get("MCP_SESSION_SECRET") or "").strip()
    anon = supabase_anon_key()
    if raw and anon and raw == anon:
        raw = ""
    publishable = (os.environ.get("SUPABASE_PUBLISHABLE_KEY") or "").strip()
    if raw and publishable and raw == publishable:
        raw = ""
    if is_production():
        if not raw:
            raise SessionSecretError("MCP_SESSION_SECRET is required in production")
        return hashlib.sha256(raw.encode("utf-8")).digest()
    if not raw:
        raw = "lasermcp-dev-session"
    return hashlib.sha256(raw.encode("utf-8")).digest()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def new_session(user: dict[str, Any]) -> str:
    secret = _session_secret()
    payload = {
        "id": user.get("id"),
        "email": user.get("email"),
        "name": user.get("name"),
        "account_model": account_model_of(user),
        "kind": _KIND_FOR_MODEL[account_model_of(user)],
        "organization_id": user.get("organization_id") or "",
        "exp": int(time.time()) + 30 * 24 * 3600,
    }
    body = _b64(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    sig = _b64(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _parse_signed_session(raw: str) -> dict[str, Any] | None:
    if "." not in raw:
        return None
    body, _, sig = raw.partition(".")
    if not body or not sig:
        return None
    try:
        secret = _session_secret()
    except SessionSecretError:
        return None
    expected = _b64(hmac.new(secret, body.encode("ascii"), hashlib.sha256).digest())
    try:
        if not hmac.compare_digest(sig, expected):
            return None
    except (TypeError, ValueError):
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
    uid = str(payload.get("id"))
    stored = user_by_id(uid) if uid else None
    model = account_model_of(stored or {"email": email, "account_model": payload.get("account_model"), "kind": payload.get("kind")})
    kind = _KIND_FOR_MODEL[model]
    org_id = str(payload.get("organization_id") or "")
    if uid and not org_id:
        try:
            from persist.orgs import ensure_personal_org

            org_id = ensure_personal_org(uid, str(payload.get("name") or ""))
        except Exception:
            org_id = ""
    return {
        "id": uid,
        "email": email,
        "name": str(payload.get("name") or email or "user"),
        "account_model": model,
        "kind": kind,
        "organization_id": org_id,
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
    model = account_model_of(row) if row else normalize_account_model(identity.get("account_model") or identity.get("kind")) or "user"
    kind = _KIND_FOR_MODEL[model]
    uid = str(identity.get("id") or row.get("id") or "")
    org_id = str(row.get("organization_id") or "")
    if uid and not org_id:
        try:
            from persist.orgs import ensure_personal_org

            org_id = ensure_personal_org(uid, str(identity.get("name") or row.get("name") or ""))
        except Exception:
            org_id = ""
    return {
        "id": identity.get("id") or row.get("id"),
        "name": identity.get("name") or row.get("name") or "user",
        "email": identity.get("email") or row.get("email"),
        "role": "workshop" if model == "org" else ("dealer" if model == "dealer" else "individual"),
        "plan": "maker" if model == "org" else ("pro" if model == "dealer" else "free"),
        "account_model": model,
        "kind": kind,
        "provider": "google",
        "organization_id": org_id,
    }
