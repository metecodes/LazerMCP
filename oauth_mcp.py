"""MCP OAuth 2.1 + PKCE. ChatGPT/Claude open Google via Supabase; no anonymous MCP."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from typing import Any
from urllib.parse import urlencode, urlparse

from studio_store import now_iso, read_json, write_json

SCOPES = ["mcp"]


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


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
        "grant_types_supported": ["authorization_code"],
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
        "grant_types": ["authorization_code"],
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


def issue_code(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    challenge: str,
    user: dict[str, Any],
) -> str:
    client = _client(client_id)
    if not client:
        # First-party assistants often skip DCR. Bind the URI to a generated client.
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
    code = secrets.token_urlsafe(24)
    rows = _load("oauth_codes.json")
    rows.append(
        {
            "code": code,
            "client_id": client.get("client_id"),
            "redirect_uri": redirect_uri,
            "state": state,
            "challenge": challenge,
            "user_id": user.get("id"),
            "email": user.get("email"),
            "name": user.get("name"),
            "kind": user.get("kind") or "individual",
            "exp": time.time() + 300,
        }
    )
    _save("oauth_codes.json", rows[-200:])
    return code


def authorize_redirect(redirect_uri: str, code: str, state: str) -> str:
    parsed = urlparse(redirect_uri)
    if parsed.scheme not in {"https", "http"}:
        raise ValueError("invalid redirect_uri")
    q = urlencode({"code": code, "state": state})
    join = "&" if parsed.query else "?"
    return f"{redirect_uri}{join}{q}"


def exchange_token(body: dict[str, Any] | None) -> dict[str, Any]:
    payload = body if isinstance(body, dict) else {}
    if str(payload.get("grant_type") or "") != "authorization_code":
        raise ValueError("grant_type must be authorization_code")
    code = str(payload.get("code") or "")
    verifier = str(payload.get("code_verifier") or "")
    redirect_uri = str(payload.get("redirect_uri") or "")
    now = time.time()
    rows = _load("oauth_codes.json")
    hit = None
    keep: list[dict[str, Any]] = []
    for row in rows:
        if row.get("code") == code and hit is None:
            hit = row
            continue
        if float(row.get("exp") or 0) > now:
            keep.append(row)
    if not hit or float(hit.get("exp") or 0) <= now:
        _save("oauth_codes.json", keep)
        raise ValueError("code expired or unknown")
    digest = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
    if not verifier or not hmac.compare_digest(digest, str(hit.get("challenge") or "")):
        raise ValueError("PKCE verifier does not match")
    if redirect_uri and redirect_uri != hit.get("redirect_uri"):
        raise ValueError("redirect_uri mismatch")
    _save("oauth_codes.json", keep)
    token = "mcp_" + secrets.token_urlsafe(24)
    tokens = _load("oauth_tokens.json")
    tokens.append(
        {
            "hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
            "user_id": hit.get("user_id"),
            "email": hit.get("email"),
            "name": hit.get("name"),
            "kind": hit.get("kind") or "individual",
            "created": now_iso(),
            "exp": time.time() + 30 * 24 * 3600,
        }
    )
    _save("oauth_tokens.json", tokens[-400:])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 30 * 24 * 3600,
        "scope": "mcp",
    }


def resolve_oauth_token(token: str | None) -> dict[str, Any] | None:
    raw = (token or "").strip()
    if not raw.startswith("mcp_"):
        return None
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    now = time.time()
    for row in _load("oauth_tokens.json"):
        if row.get("hash") == digest and float(row.get("exp") or 0) > now:
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
    return None
