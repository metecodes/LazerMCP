"""KeyRepository — hashed keys only. Never stores or lists the raw token."""

from __future__ import annotations

from typing import Any

from persist.db import connect
from studio_store import now_iso

_PUBLIC = (
    "id",
    "name",
    "prefix",
    "owner_user_id",
    "organization_id",
    "role",
    "plan",
    "kind",
    "email",
    "created_at",
    "last_used_at",
    "expires_at",
    "revoked_at",
)


def _public(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {k: row.get(k) for k in _PUBLIC}


class KeyRepository:
    def insert(self, row: dict[str, Any]) -> dict[str, Any]:
        now = now_iso()
        payload = {
            "id": row["id"],
            "name": row.get("name") or "key",
            "hash": row["hash"],
            "prefix": row.get("prefix") or "",
            "owner_user_id": row.get("owner_user_id") or row.get("owner") or "",
            "organization_id": row.get("organization_id") or "",
            "role": row.get("role") or "workshop",
            "plan": row.get("plan") or "maker",
            "kind": row.get("kind") or "org",
            "email": row.get("email") or "",
            "created_at": row.get("created_at") or row.get("created") or now,
            "last_used_at": row.get("last_used_at") or row.get("last_used"),
            "expires_at": row.get("expires_at"),
            "revoked_at": row.get("revoked_at"),
        }
        with connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO api_keys (
                  id, name, hash, prefix, owner_user_id, organization_id, role, plan, kind, email,
                  created_at, last_used_at, expires_at, revoked_at
                ) VALUES (
                  :id, :name, :hash, :prefix, :owner_user_id, :organization_id, :role, :plan, :kind, :email,
                  :created_at, :last_used_at, :expires_at, :revoked_at
                )
                """,
                payload,
            )
            conn.commit()
        return _public(payload) or {}

    def by_hash(self, digest: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE hash = ?", (digest,)).fetchone()
        return dict(row) if row else None

    def by_id(self, key_id: str) -> dict[str, Any] | None:
        with connect() as conn:
            row = conn.execute("SELECT * FROM api_keys WHERE id = ?", (key_id,)).fetchone()
        return dict(row) if row else None

    def list_for_owner(self, owner: str) -> list[dict[str, Any]]:
        with connect() as conn:
            rows = conn.execute(
                "SELECT * FROM api_keys WHERE owner_user_id = ? ORDER BY created_at DESC",
                (owner,),
            ).fetchall()
        return [_public(dict(r)) or {} for r in rows]

    def touch(self, key_id: str) -> None:
        with connect() as conn:
            conn.execute("UPDATE api_keys SET last_used_at = ? WHERE id = ?", (now_iso(), key_id))
            conn.commit()

    def revoke(self, key_id: str, owner: str = "") -> bool:
        with connect() as conn:
            if owner:
                cur = conn.execute(
                    "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND owner_user_id = ? AND revoked_at IS NULL",
                    (now_iso(), key_id, owner),
                )
            else:
                cur = conn.execute(
                    "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                    (now_iso(), key_id),
                )
            conn.commit()
            return cur.rowcount > 0
