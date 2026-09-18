"""Application authorization. RLS is defense in depth, not the MCP path."""

from __future__ import annotations

from typing import Any
from datetime import datetime, timedelta, timezone

from persist.artifacts import ArtifactRepository
from persist.orgs import OrganizationRepository

BLOCKED_GLOBAL = {"latest.svg", "latest.dxf"}
PUBLIC_ORG_ID = "00000000-0000-0000-0000-000000000001"


def principal_org_id(principal: dict[str, Any] | None) -> str:
    if not principal:
        return ""
    return str(principal.get("organization_id") or "")


def can_access_org(principal: dict[str, Any] | None, organization_id: str) -> bool:
    if organization_id in {"public", PUBLIC_ORG_ID}:
        return True
    if not principal or not organization_id:
        return False
    if str(principal.get("id") or "") == "admin" and str(principal.get("role") or "") == "admin":
        return True
    if str(principal.get("organization_id") or "") == organization_id:
        return True
    key_org = str(principal.get("organization_id") or "")
    if key_org and key_org == organization_id:
        return True
    uid = str(principal.get("id") or principal.get("owner") or "")
    if uid and OrganizationRepository().member_of(uid, organization_id):
        return True
    return False


def resolve_artifact_ref(ref: str) -> dict[str, Any] | None:
    name = (ref or "").strip()
    if not name:
        return None
    repo = ArtifactRepository()
    hit = repo.get(name)
    if hit:
        return hit
    return repo.by_source(name)


def authorize_customer_file(filename: str, principal: dict[str, Any] | None, *, auth_on: bool) -> dict[str, Any]:
    """Return {allow, reason, artifact, workshop}."""
    name = (filename or "").strip()
    if not name:
        return {"allow": False, "reason": "invalid"}
    if name.lower() in BLOCKED_GLOBAL and auth_on:
        return {"allow": False, "reason": "global-name"}
    artifact = resolve_artifact_ref(name)
    if artifact:
        if can_access_org(principal, str(artifact.get("organization_id") or "")):
            expires = artifact.get("expires_at")
            if not expires and artifact.get("created_at"):
                expires = (datetime.fromisoformat(str(artifact["created_at"]).replace("Z", "+00:00")) + timedelta(hours=24)).isoformat()
            if expires and datetime.fromisoformat(str(expires).replace("Z", "+00:00")) <= datetime.now(timezone.utc):
                return {"allow": False, "reason": "expired", "artifact": artifact}
            return {"allow": True, "reason": "owner", "artifact": artifact}
        return {"allow": False, "reason": "forbidden", "artifact": artifact}
    if not auth_on:
        # Local output copies must not resurrect a cleaned-up artifact.
        from boxes_adapter import _safe_output_file
        try:
            source = _safe_output_file(name)
        except (FileNotFoundError, ValueError):
            return {"allow": False, "reason": "unknown"}
        if datetime.fromtimestamp(source.stat().st_mtime, timezone.utc) + timedelta(hours=24) <= datetime.now(timezone.utc):
            return {"allow": False, "reason": "expired"}
        return {"allow": True, "reason": "workshop", "workshop": True}
    return {"allow": False, "reason": "unknown"}
