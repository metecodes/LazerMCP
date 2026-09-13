"""Signed-in users request org/dealer access. Admin decides. Software does not mint keys for them."""

from __future__ import annotations

import secrets
from typing import Any

from studio_store import now_iso, read_json, write_json
from supabase_auth import normalize_account_model, public_user, set_account_model, user_by_id


def _rows() -> list[dict[str, Any]]:
    raw = read_json("key_requests.json", [])
    return raw if isinstance(raw, list) else []


def _save(rows: list[dict[str, Any]]) -> None:
    write_json("key_requests.json", rows[-400:])


def _public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "email": row.get("email"),
        "name": row.get("name"),
        "note": row.get("note") or "",
        "want": row.get("want") or "org",
        "status": row.get("status") or "open",
        "at": row.get("at"),
        "decided_at": row.get("decided_at"),
        "decided_by": row.get("decided_by") or "",
    }


def open_request_for(email: str) -> dict[str, Any] | None:
    needle = str(email or "").strip().lower()
    for row in reversed(_rows()):
        if str(row.get("email") or "").strip().lower() == needle and row.get("status") == "open":
            return _public(row)
    return None


def submit_key_request(user: dict[str, Any], *, note: str = "", want: str = "org") -> dict[str, Any]:
    email = str(user.get("email") or "").strip().lower()
    if "@" not in email:
        return {"success": True, "look_again": ["Google ile gir, sonra talep aç."]}
    model = normalize_account_model(want) or "org"
    if model not in {"org", "dealer"}:
        model = "org"
    existing = open_request_for(email)
    if existing:
        return {
            "success": True,
            "request": existing,
            "look_again": ["Talebin zaten açık. Admin bakınca haberin olur."],
        }
    row = {
        "id": "req-" + secrets.token_hex(3),
        "email": email,
        "user_id": str(user.get("id") or ""),
        "name": str(user.get("name") or "")[:120],
        "note": str(note or "")[:400],
        "want": model,
        "status": "open",
        "at": now_iso(),
    }
    rows = _rows()
    rows.append(row)
    _save(rows)
    return {
        "success": True,
        "request": _public(row),
        "look_again": ["Talep alındı. Admin kurumsal veya bayi yapınca anahtar üretebilirsin."],
    }


def list_key_requests(*, status: str = "open", limit: int = 40) -> list[dict[str, Any]]:
    wanted = str(status or "open").strip().lower()
    out: list[dict[str, Any]] = []
    for row in reversed(_rows()):
        if wanted != "all" and str(row.get("status") or "") != wanted:
            continue
        out.append(_public(row))
        if len(out) >= limit:
            break
    return out


def decide_key_request(ident: str, *, approve: bool, by: str, model: str | None = None) -> dict[str, Any] | None:
    needle = str(ident or "").strip().lower()
    if not needle:
        return None
    rows = _rows()
    hit: dict[str, Any] | None = None
    for row in rows:
        email = str(row.get("email") or "").strip().lower()
        if email == needle or str(row.get("id") or "").strip().lower() == needle:
            hit = row
            break
    if hit is None:
        return None
    hit["status"] = "approved" if approve else "denied"
    hit["decided_at"] = now_iso()
    hit["decided_by"] = str(by or "")[:120]
    user = None
    if approve:
        chosen = normalize_account_model(model or hit.get("want") or "org") or "org"
        if chosen not in {"org", "dealer"}:
            chosen = "org"
        hit["want"] = chosen
        user = set_account_model(str(hit.get("email") or ""), chosen, by=by)
        if user is None and hit.get("user_id"):
            stored = user_by_id(str(hit.get("user_id")))
            if stored:
                user = set_account_model(str(stored.get("email") or ""), chosen, by=by)
    try:
        _save(rows)
    except Exception:
        return None
    stored = user_by_id(str(hit.get("user_id") or "")) if hit.get("user_id") else None
    return {"request": _public(hit), "user": user or (public_user(stored) if stored else None)}
