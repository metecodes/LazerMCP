"""MCP OAuth 2.1 + PKCE. ChatGPT/Claude open Google via Supabase; no anonymous MCP."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlparse

from studio_store import now_iso, read_json, write_json

SCOPES = ["mcp"]
GRANTS = ["authorization_code", "refresh_token"]
ACCESS_TTL_SEC = 30 * 24 * 3600
REFRESH_TTL_SEC = 90 * 24 * 3600
_FIRST_PARTY_REDIRECT_HOSTS = {
    "chatgpt.com",
    "www.chatgpt.com",
    "chat.openai.com",
    "claude.ai",
    "www.claude.ai",
    "cursor.com",
    "www.cursor.com",
}


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


def _oauth_secret() -> bytes:
    from supabase_auth import SessionSecretError, _session_secret

    try:
        return _session_secret()
    except SessionSecretError as exc:
        raise ValueError(str(exc)) from exc


def _sign(payload: dict[str, Any]) -> str:
    body = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    sig = _b64url(hmac.new(_oauth_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _unsign(raw: str) -> dict[str, Any] | None:
    if "." not in raw:
        return None
    body, _, sig = raw.partition(".")
    if not body or not sig:
        return None
    try:
        expected = _b64url(hmac.new(_oauth_secret(), body.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(_b64d(body).decode("utf-8"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    if int(payload.get("exp") or 0) <= int(time.time()):
        return None
    return payload


def _load(name: str) -> list[dict[str, Any]]:
    rows = read_json(name, [])
    return rows if isinstance(rows, list) else []


def _save(name: str, rows: list[dict[str, Any]]) -> None:
    write_json(name, rows)


def issuer(base: str) -> str:
    return base.rstrip("/")


def metadata(base: str) -> dict[str, Any]:
    root = issuer(base)
    return {
        "issuer": root,
        "authorization_endpoint": f"{root}/oauth/authorize",
        "token_endpoint": f"{root}/oauth/token",
        "registration_endpoint": f"{root}/oauth/register",
        "response_types_supported": ["code"],
        "grant_types_supported": list(GRANTS),
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none"],
        "scopes_supported": SCOPES,
    }


def resource_metadata(base: str) -> dict[str, Any]:
    root = issuer(base)
    return {
        "resource": f"{root}/mcp",
        "authorization_servers": [root],
        "bearer_methods_supported": ["header"],
        "scopes_supported": SCOPES,
    }


def register_client(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = body if isinstance(body, dict) else {}
    uris = [str(u) for u in (payload.get("redirect_uris") or []) if str(u).startswith("http")]
    if not uris:
        raise ValueError("redirect_uris required")
    if any(not redirect_host_ok(u) for u in uris):
        raise ValueError("redirect_uri host is not allowed")
    client_id = "cli_" + secrets.token_urlsafe(16)
    row = {
        "client_id": client_id,
        "client_name": str(payload.get("client_name") or "mcp-client")[:80],
        "redirect_uris": uris,
        "token_endpoint_auth_method": "none",
        "created": now_iso(),
    }
    rows = _load("oauth_clients.json")
    rows.append(row)
    _save("oauth_clients.json", rows[-200:])
    return {
        "client_id": client_id,
        "client_name": row["client_name"],
        "redirect_uris": uris,
        "token_endpoint_auth_method": "none",
        "grant_types": list(GRANTS),
        "response_types": ["code"],
    }


def _client(client_id: str) -> dict[str, Any] | None:
    for row in _load("oauth_clients.json"):
        if row.get("client_id") == client_id:
            return row
    return None


def _uri_ok(client: dict[str, Any] | None, redirect_uri: str) -> bool:
    if not client:
        return False
    allowed = [str(u) for u in (client.get("redirect_uris") or [])]
    return redirect_uri in allowed


def redirect_hosts() -> set[str]:
    extra = (os.environ.get("LASERMCP_OAUTH_REDIRECT_HOSTS") or "").strip()
    more = {p.strip().lower() for p in extra.split(",") if p.strip()}
    return _FIRST_PARTY_REDIRECT_HOSTS | more


def redirect_host_ok(redirect_uri: str) -> bool:
    parsed = urlparse(redirect_uri)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and host in redirect_hosts():
        return True
    return parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}


def issue_code(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    challenge: str,
    user: dict[str, Any],
) -> str:
    if not redirect_host_ok(redirect_uri):
        raise ValueError("redirect_uri host is not allowed")
    client = _client(client_id)
    if not client:
        client = {
            "client_id": client_id or "cli_pending",
            "redirect_uris": [redirect_uri],
        }
        rows = _load("oauth_clients.json")
        rows.append({**client, "client_name": "implicit", "created": now_iso()})
        _save("oauth_clients.json", rows[-200:])
    elif not _uri_ok(client, redirect_uri):
        raise ValueError("redirect_uri is not registered")
    if not challenge:
        raise ValueError("PKCE code_challenge required")
    return _sign(
        {
            "typ": "code",
            "client_id": client.get("client_id"),
            "redirect_uri": redirect_uri,
            "challenge": challenge,
            "user_id": user.get("id"),
            "email": user.get("email"),
            "name": str(user.get("name") or "")[:80],
            "kind": user.get("kind") or "individual",
            "exp": int(time.time()) + 300,
        }
    )


def authorize_redirect(redirect_uri: str, code: str, state: str) -> str:
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in {"https", "http"}:
        raise ValueError("invalid redirect_uri")
    q = urlencode({"code": code, "state": state})
    join = "&" if parsed.query else "?"
    return f"{redirect_uri}{join}{q}"


def _digest(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _principal(row: dict[str, Any]) -> dict[str, Any]:
    kind = str(row.get("kind") or "individual")
    return {
        "id": row.get("user_id"),
        "name": row.get("name") or row.get("email") or "user",
        "email": row.get("email"),
        "role": "workshop" if kind == "org" else "individual",
        "plan": "maker" if kind == "org" else "free",
        "kind": kind,
        "provider": "google",
    }


def _user_fields(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_id": user.get("user_id") if user.get("user_id") else user.get("id"),
        "email": user.get("email"),
        "name": str(user.get("name") or "")[:80],
        "kind": user.get("kind") or "individual",
    }


def _issue_pair(user: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    issued = int(time.time() if now is None else now)
    fields = _user_fields(user)
    access = "mcp_" + _sign(
        {**fields, "typ": "access", "jti": secrets.token_urlsafe(8), "exp": issued + ACCESS_TTL_SEC}
    )
    refresh = "mcpr_" + _sign(
        {**fields, "typ": "refresh", "jti": secrets.token_urlsafe(8), "exp": issued + REFRESH_TTL_SEC}
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": ACCESS_TTL_SEC,
        "refresh_token_expires_in": REFRESH_TTL_SEC,
        "scope": "mcp",
    }


def _check_pkce(hit: dict[str, Any], verifier: str, redirect_uri: str) -> None:
    digest = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    if not verifier or not hmac.compare_digest(digest, str(hit.get("challenge") or "")):
        raise ValueError("PKCE verifier does not match")
    if redirect_uri and redirect_uri != hit.get("redirect_uri"):
        raise ValueError("redirect_uri mismatch")


def _legacy_code(code: str, now: float) -> dict[str, Any] | None:
    rows = _load("oauth_codes.json")
    hit = None
    keep: list[dict[str, Any]] = []
    for row in rows:
        if row.get("code") == code and hit is None:
            hit = row
            continue
        if float(row.get("exp") or 0) > now:
            keep.append(row)
    _save("oauth_codes.json", keep)
    if not hit or float(hit.get("exp") or 0) <= now:
        return None
    return hit


def _exchange_code(payload: dict[str, Any]) -> dict[str, Any]:
    code = str(payload.get("code") or "")
    verifier = str(payload.get("code_verifier") or "")
    redirect_uri = str(payload.get("redirect_uri") or "")
    hit = _unsign(code)
    if not hit or hit.get("typ") != "code":
        hit = _legacy_code(code, time.time())
    if not hit:
        raise ValueError("code expired or unknown")
    _check_pkce(hit, verifier, redirect_uri)
    return _issue_pair(hit)


def _legacy_refresh(raw: str, now: float) -> dict[str, Any] | None:
    digest = _digest(raw)
    for row in _load("oauth_tokens.json"):
        stored = str(row.get("refresh_hash") or "")
        if not stored or not hmac.compare_digest(stored, digest):
            continue
        if float(row.get("refresh_exp") or 0) <= now:
            return None
        return row
    return None


def _exchange_refresh(payload: dict[str, Any]) -> dict[str, Any]:
    raw = str(payload.get("refresh_token") or "").strip()
    if not raw.startswith("mcpr_"):
        raise ValueError("refresh_token expired or unknown")
    signed = _unsign(raw[5:])
    if signed and signed.get("typ") == "refresh":
        return _issue_pair(signed)
    hit = _legacy_refresh(raw, time.time())
    if not hit:
        raise ValueError("refresh_token expired or unknown")
    return _issue_pair(hit)


def exchange_token(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = body if isinstance(body, dict) else {}
    grant = str(payload.get("grant_type") or "")
    if grant == "authorization_code":
        return _exchange_code(payload)
    if grant == "refresh_token":
        return _exchange_refresh(payload)
    raise ValueError("grant_type must be authorization_code or refresh_token")


def resolve_oauth_token(token: str | None) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if not raw.startswith("mcp_") or raw.startswith("mcpr_"):
        return None
    signed = _unsign(raw[4:])
    if signed and signed.get("typ") == "access":
        return _principal(signed)
    digest = _digest(raw)
    now = time.time()
    for row in _load("oauth_tokens.json"):
        stored = str(row.get("hash") or "")
        if stored and hmac.compare_digest(stored, digest) and float(row.get("exp") or 0) > now:
            return _principal(row)
    return None
