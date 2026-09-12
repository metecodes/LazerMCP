"""Attach durable artifacts after CAD write. Does not change geometry."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import time

from persist.artifacts import ArtifactRepository
from persist.authz import principal_org_id
from persist.cleanup import cleanup_expired
from persist.orgs import ensure_personal_org
from persist.storage import StorageService, expires_in_hours, ext_for, maybe_webp, sha256_hex

_last_gc = 0.0

from keys import current_auth

DURABLE_STATUSES = {"PROTOTYPE READY", "PRODUCTION READY"}


def _principal() -> dict[str, Any] | None:
    return current_auth.get()


def _org_id(principal: dict[str, Any] | None) -> str:
    if not principal:
        return ""
    oid = principal_org_id(principal)
    if oid:
        return oid
    uid = str(principal.get("id") or principal.get("owner") or "")
    if uid and uid != "admin":
        return ensure_personal_org(uid, str(principal.get("name") or ""))
    return ""


def persist_bytes(
    *,
    organization_id: str,
    kind: str,
    data: bytes,
    mime_type: str,
    source_file_id: str = "",
    durable: bool = True,
    name: str = "",
) -> dict[str, Any]:
    if not data:
        raise ValueError("empty artifact")
    store = StorageService()
    digest = sha256_hex(data)
    ext = ext_for(mime_type, name)
    repo = ArtifactRepository()
    import uuid

    artifact_id = str(uuid.uuid4())
    if durable:
        path = store.durable_path(organization_id, artifact_id, digest, ext)
        expires = None
    else:
        path = store.tmp_path(organization_id, ext)
        expires = expires_in_hours(24)
    store.put(path, data, mime_type)
    meta = repo.insert(
        {
            "id": artifact_id,
            "organization_id": organization_id,
            "kind": kind,
            "storage_path": path,
            "file_size": len(data),
            "mime_type": mime_type,
            "hash": digest,
            "expires_at": expires,
            "source_file_id": source_file_id or None,
        }
    )
    if any(k in meta for k in ("svg", "svg_bytes", "content")):
        raise RuntimeError("artifact metadata must not contain file bodies")
    return meta


def attach_durable_artifacts(result: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Best-effort durable save. Generation success is independent."""
    extra = extra or {}
    global _last_gc
    if time.time() - _last_gc > 3600:
        _last_gc = time.time()
        try:
            cleanup_expired()
        except Exception:
            pass
    principal = _principal()
    org = _org_id(principal)
    result["design_generation"] = "DESIGN_GENERATION_SUCCESS"
    result["durable_persistence"] = False
    if not org:
        result["persistence_note"] = "no organization boundary; local file only"
        return result
    status = str(result.get("final_status") or extra.get("final_status") or "")
    durable = status in DURABLE_STATUSES
    from boxes_adapter import OUTPUT_DIR, _safe_output_file

    saved: list[dict[str, Any]] = []
    try:
        file_id = str(result.get("file_id") or "")
        if file_id:
            svg = Path(_safe_output_file(file_id)).read_bytes()
            saved.append(
                persist_bytes(
                    organization_id=org,
                    kind="svg",
                    data=svg,
                    mime_type="image/svg+xml",
                    source_file_id=file_id,
                    durable=durable,
                    name=file_id,
                )
            )
        preview_id = str(result.get("preview_id") or "")
        if preview_id:
            raw = (OUTPUT_DIR / preview_id).read_bytes()
            data, mime = maybe_webp(raw)
            kind = "preview_webp" if mime == "image/webp" else "preview_png"
            saved.append(
                persist_bytes(
                    organization_id=org,
                    kind=kind,
                    data=data,
                    mime_type=mime,
                    source_file_id=preview_id,
                    durable=durable,
                    name=preview_id,
                )
            )
        dxf_id = str(result.get("dxf_id") or "")
        if dxf_id:
            dxf = (OUTPUT_DIR / dxf_id).read_bytes()
            saved.append(
                persist_bytes(
                    organization_id=org,
                    kind="dxf",
                    data=dxf,
                    mime_type="image/vnd.dxf",
                    source_file_id=dxf_id,
                    durable=durable,
                    name=dxf_id,
                )
            )
    except Exception:
        result["artifact_persistence"] = "ARTIFACT_PERSISTENCE_FAILED"
        looks = result.get("look_again")
        note = "Durable artifact save failed. Local prototype file may still exist. Do not treat this as a stored customer artifact."
        if isinstance(looks, list):
            looks.append(note)
        elif looks:
            result["look_again"] = [str(looks), note]
        else:
            result["look_again"] = [note]
        return result
    result["durable_persistence"] = durable and bool(saved)
    result["artifact_persistence"] = (
        "ARTIFACT_PERSISTENCE_SUCCESS" if saved else "ARTIFACT_PERSISTENCE_SKIPPED"
    )
    result["artifacts"] = [
        {
            "id": a["id"],
            "kind": a["kind"],
            "file_size": a["file_size"],
            "mime_type": a["mime_type"],
            "hash": a["hash"],
            "expires_at": a.get("expires_at"),
        }
        for a in saved
    ]
    if saved and file_id:
        result["artifact_id"] = saved[0]["id"]
    return result
