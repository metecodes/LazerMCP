"""Supabase Google identity. Individuals sign in; software does not invent a user."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
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
APPROVAL_STATUSES = ("pending", "approved", "denied")
TRIAL_DAYS = 3
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


def approval_status_of(user: dict[str, Any] | None) -> str:
    """Return the stored account review state.

    Records created before manual review was introduced are deliberately
    treated as approved so deploying this change does not lock out customers
    who already had an account.
    """
    if is_admin(user):
        return "approved"
    raw = str((user or {}).get("approval_status") or "").strip().lower()
    return raw if raw in APPROVAL_STATUSES else "approved"


def _stamp(raw: str | None) -> datetime | None:
    text = str(raw or "").replace("Z", "+00:00")
    if not text:
        return None
    try:
        value = datetime.fromisoformat(text)
    except ValueError:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def account_access_state(user: dict[str, Any] | None, *, now: datetime | None = None) -> str:
    """The current usable state, including a time-limited first approval."""
    status = approval_status_of(user)
    if status != "approved":
        return status
    expires = _stamp((user or {}).get("trial_expires_at"))
    current = now or datetime.now(timezone.utc)
    if expires and current >= expires:
        return "trial_expired"
    return "trial" if expires else "approved"


def account_is_approved(user: dict[str, Any] | None) -> bool:
    return account_access_state(user) in {"approved", "trial"}


def _approve_for_access(row: dict[str, Any], *, by: str) -> None:
    """First approval is a three-day trial; expiry needs a second approval."""
    prior = account_access_state(row)
    row["approval_status"] = "approved"
    actor = str(by or "")[:120]
    if prior == "trial_expired":
        row.pop("trial_expires_at", None)
        row["membership_approved_at"] = now_iso()
        row["membership_approved_by"] = actor
    elif prior in {"pending", "denied"}:
        started = datetime.now(timezone.utc).replace(microsecond=0)
        row["trial_started_at"] = started.isoformat()
        row["trial_expires_at"] = (started + timedelta(days=TRIAL_DAYS)).isoformat()
        row["trial_approved_by"] = actor
    row["approved_at"] = now_iso()
    row["approved_by"] = actor


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
        "password": True,
        "mcp_url": mcp_url,
        "org_domains": org_domains(),
        "note": (
            "Sign in with Google or email and password. "
            "Organizations mint API keys after sign-in. "
            "A bare MCP URL is not enough."
        ),
        "look_again": (
            []
            if ready
            else ["Production needs an independent MCP_SESSION_SECRET. Sign-in can finish but the site cannot keep you signed in."]
        ),
    }


def _identity_from_user_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or not payload.get("id"):
        return None
    email = str(payload.get("email") or "")
    # Admin rights and org-domain grants are keyed on the email, so an address
    # nobody has proven ownership of must not sign in (Google sets this field).
    if email and not (payload.get("email_confirmed_at") or payload.get("confirmed_at")):
        return None
    meta = payload.get("user_metadata") if isinstance(payload.get("user_metadata"), dict) else {}
    app = payload.get("app_metadata") if isinstance(payload.get("app_metadata"), dict) else {}
    provider = str(app.get("provider") or meta.get("provider") or "email").strip().lower() or "email"
    return {
        "id": str(payload.get("id")),
        "email": email,
        "name": str(meta.get("full_name") or meta.get("name") or email or "user"),
        "provider": provider,
    }


def password_grant(email: str, password: str) -> tuple[dict[str, Any] | None, str]:
    """Exchange email/password for a Supabase access token. Never logs the password."""
    mail = str(email or "").strip().lower()
    pwd = str(password or "")
    if not mail or "@" not in mail or not pwd:
        return None, "Email and password are required."
    if not configured():
        return None, "Supabase is not configured."
    body = json.dumps({"email": mail, "password": pwd}).encode("utf-8")
    req = urllib.request.Request(
        f"{supabase_url()}/auth/v1/token?grant_type=password",
        data=body,
        headers={
            "apikey": supabase_anon_key(),
            "Authorization": f"Bearer {supabase_anon_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            err = json.loads(exc.read().decode("utf-8"))
            detail = str(err.get("error_description") or err.get("msg") or err.get("error") or "")
        except Exception:
            detail = ""
        if exc.code in (400, 401, 422):
            return None, detail or "Invalid email or password."
        return None, detail or "Sign-in failed."
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError):
        return None, "Sign-in failed."
    if not isinstance(payload, dict):
        return None, "Sign-in failed."
    token = str(payload.get("access_token") or "").strip()
    if not token:
        return None, "Sign-in failed."
    user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
    identity = _identity_from_user_payload(user) if user else None
    return {"access_token": token, "identity": identity}, ""


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
    return _identity_from_user_payload(payload)


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
            "approval_status": "approved" if is_admin(identity) else "pending",
            "approval_requested_at": now_iso(),
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
    return account_is_approved(user) and user_is_org(user)


def can_mint_activation(user: dict[str, Any] | None) -> bool:
    return account_is_approved(user) and (user_is_org(user) or user_is_dealer(user) or is_admin(user))


def public_user(row: dict[str, Any]) -> dict[str, Any]:
    model = account_model_of(row)
    access_state = account_access_state(row)
    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "name": row.get("name"),
        "account_model": model,
        "kind": _KIND_FOR_MODEL[model],
        "org_grant": model == "org",
        "approval_status": approval_status_of(row),
        "approved": account_is_approved(row),
        "access_state": access_state,
        "approval_requested_at": row.get("approval_requested_at"),
        "trial_started_at": row.get("trial_started_at"),
        "trial_expires_at": row.get("trial_expires_at"),
        "last_seen": row.get("last_seen"),
        "created": row.get("created"),
    }


def _seen_at(raw: str):
    return _stamp(raw)


def user_stats(*, active_days: int = 30) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    rows = _users()
    now = datetime.now(timezone.utc)
    window = timedelta(days=max(1, int(active_days)))
    active = 0
    org = 0
    dealer = 0
    users = 0
    pending = 0
    approved = 0
    denied = 0
    trial = 0
    trial_expired = 0
    for row in rows:
        model = account_model_of(row)
        if model == "org":
            org += 1
        elif model == "dealer":
            dealer += 1
        else:
            users += 1
        state = account_access_state(row)
        if state == "pending":
            pending += 1
        elif state == "denied":
            denied += 1
        elif state == "trial_expired":
            trial_expired += 1
        elif state == "trial":
            trial += 1
        else:
            approved += 1
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
        "pending_users": pending,
        "approved_users": approved,
        "denied_users": denied,
        "trial_users": trial,
        "trial_expired_users": trial_expired,
        "review_users": pending + trial_expired,
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
    _approve_for_access(hit, by=by)
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
    # Selecting a model in the operator panel is also an explicit approval.
    _approve_for_access(hit, by=by)
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


def pending_users(*, limit: int = 40) -> list[dict[str, Any]]:
    rows = [row for row in _users() if approval_status_of(row) == "pending"]
    rows.sort(key=lambda row: str(row.get("approval_requested_at") or row.get("created") or ""), reverse=True)
    return [public_user(row) for row in rows[: max(1, int(limit))]]


def review_users(*, limit: int = 40) -> list[dict[str, Any]]:
    rows = [row for row in _users() if account_access_state(row) in {"pending", "trial_expired"}]
    rows.sort(
        key=lambda row: str(row.get("trial_expires_at") or row.get("approval_requested_at") or row.get("created") or ""),
        reverse=True,
    )
    return [public_user(row) for row in rows[: max(1, int(limit))]]


def set_account_approval(email: str, *, approve: bool, by: str) -> dict[str, Any] | None:
    needle = str(email or "").strip().lower()
    if "@" not in needle:
        return None
    rows = _users()
    hit = next((row for row in rows if str(row.get("email") or "").strip().lower() == needle), None)
    if hit is None:
        return None
    if approve:
        _approve_for_access(hit, by=by)
    else:
        hit["approval_status"] = "denied"
        hit.pop("trial_expires_at", None)
        hit["denied_at"] = now_iso()
        hit["denied_by"] = str(by or "")[:120]
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
        # The repository is public, so a fixed fallback would let anyone sign
        # sessions (including the admin email). Use a per-process random key:
        # local sessions simply reset when the server restarts.
        return _EPHEMERAL_SESSION_SECRET
    return hashlib.sha256(raw.encode("utf-8")).digest()


_EPHEMERAL_SESSION_SECRET = secrets.token_bytes(32)


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
        "approval_status": approval_status_of(user),
        "trial_expires_at": user.get("trial_expires_at") or "",
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
        "approval_status": approval_status_of(stored or payload),
        "trial_expires_at": (stored or payload).get("trial_expires_at") or "",
        "provider": "google",
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
        "approval_status": approval_status_of(row or identity),
        "approved": account_is_approved(row or identity),
        "access_state": account_access_state(row or identity),
        "trial_expires_at": (row or identity).get("trial_expires_at") or "",
        "provider": "google",
        "organization_id": org_id,
    }
