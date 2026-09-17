"""OrganizationRepository — personal org per auth user. No workspace UI."""

from __future__ import annotations

import uuid
from typing import Any

from persist.db import connect
from studio_store import now_iso
from persist.env import uses_supabase_app_db
from persist.supabase_rest import rows, upsert

PERSONAL_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")


def personal_org_id(user_id: str) -> str:
    return str(uuid.uuid5(PERSONAL_NS, f"lasermcp-personal:{user_id}"))


class OrganizationRepository:
    def get(self, org_id: str) -> dict[str, Any] | None:
        if uses_supabase_app_db():
            found = rows("lasermcp_organizations", id=f"eq.{org_id}", limit=1)
            return found[0] if found else None
        with connect() as conn:
            row = conn.execute("SELECT * FROM organizations WHERE id = ?", (org_id,)).fetchone()
        return dict(row) if row else None

    def membership(self, org_id: str, user_id: str) -> dict[str, Any] | None:
        if uses_supabase_app_db():
            found = rows("lasermcp_organization_members", organization_id=f"eq.{org_id}", user_id=f"eq.{user_id}", limit=1)
            return found[0] if found else None
        with connect() as conn:
            row = conn.execute(
                "SELECT * FROM organization_members WHERE organization_id = ? AND user_id = ?",
                (org_id, user_id),
            ).fetchone()
        return dict(row) if row else None

    def member_of(self, user_id: str, org_id: str) -> bool:
        return self.membership(org_id, str(user_id or "")) is not None

    def ensure_personal(self, user_id: str, name: str = "") -> dict[str, Any]:
        uid = str(user_id or "").strip()
        if not uid:
            raise ValueError("user_id required")
        oid = personal_org_id(uid)
        label = (name or "Personal").strip()[:80] or "Personal"
        now = now_iso()
        if uses_supabase_app_db():
            upsert("lasermcp_organizations", {"id": oid, "kind": "personal", "name": label,
                   "created_by": uid, "created_at": now}, ignore=True)
            upsert("lasermcp_organization_members", {"organization_id": oid, "user_id": uid,
                   "role": "owner", "created_at": now}, "organization_id,user_id", ignore=True)
            return {"id": oid, "kind": "personal", "name": label, "created_by": uid}
        with connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO organizations (id, kind, name, created_by, created_at)
                VALUES (?, 'personal', ?, ?, ?)
                """,
                (oid, label, uid, now),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO organization_members (organization_id, user_id, role, created_at)
                VALUES (?, ?, 'owner', ?)
                """,
                (oid, uid, now),
            )
            conn.commit()
        return {"id": oid, "kind": "personal", "name": label, "created_by": uid}


def ensure_personal_org(user_id: str, name: str = "") -> str:
    return OrganizationRepository().ensure_personal(user_id, name)["id"]
