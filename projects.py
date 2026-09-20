"""User projects, design versions, history."""

from __future__ import annotations

import re
import secrets
from typing import Any

from studio_store import now_iso, read_json, write_json
from persist.env import uses_supabase_app_db
from persist.supabase_rest import rest, rows, upsert


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "job").strip()).strip("-").lower()
    return (slug[:32] or "job")


def _load() -> dict[str, Any]:
    if uses_supabase_app_db():
        return {row["id"]: row["payload"] for row in rows("lasermcp_projects")}
    raw = read_json("projects.json", {})
    return raw if isinstance(raw, dict) else {}


def save_version(parameters: dict[str, Any] | None, result: dict[str, Any] | None) -> dict[str, Any] | None:
    params = parameters or {}
    data = result or {}
    name = str(params.get("project") or params.get("project_name") or data.get("title") or data.get("product") or "").strip()
    pid = str(params.get("project_id") or "").strip() or None
    if not name and not pid and not data.get("file_id"):
        return None
    remote = uses_supabase_app_db()
    store = {} if remote else _load()
    if not pid:
        pid = _slug(name or str(data.get("product") or "design")) + "-" + secrets.token_hex(2)
    project = store.get(pid) or {"id": pid, "name": name or pid, "created": now_iso(), "versions": []}
    if name:
        project["name"] = name
    version = {
        "n": len(project.get("versions") or []) + 1,
        "at": now_iso(),
        "file_id": data.get("file_id"),
        "svg_url": data.get("svg_url"),
        "dxf_id": data.get("dxf_id"),
        "preview_url": data.get("preview_url"),
        "final_status": data.get("final_status"),
        "product": data.get("product") or data.get("generator"),
        "speak": data.get("speak"),
        "bom": (data.get("bom") or {}).get("speak") if isinstance(data.get("bom"), dict) else data.get("bom"),
        "machine": params.get("machine") or (
            ((data.get("profiles") or {}).get("machine") or {}).get("id")
            if isinstance(data.get("profiles"), dict)
            else None
        ),
        "material": params.get("material"),
        "batch_id": params.get("batch_id"),
        "parameters": {k: v for k, v in params.items() if not str(k).startswith("_")},
        "primitives": data.get("primitives") if isinstance(data.get("primitives"), list) else None,
        "preflight": data.get("preflight") if isinstance(data.get("preflight"), dict) else None,
        "feedback": data.get("feedback") if isinstance(data.get("feedback"), dict) else None,
        "approved": bool(data.get("approved")),
    }
    if remote:
        return rest("rpc/append_lasermcp_version", method="POST", body={
            "p_id": pid, "p_name": name, "p_version": version,
        })
    project.setdefault("versions", []).append(version)
    project["updated"] = now_iso()
    store[pid] = project
    write_json("projects.json", store)
    return {"project_id": pid, "name": project["name"], "version": version["n"]}


def _save_store(store: dict[str, Any]) -> None:
    if uses_supabase_app_db():
        for pid, payload in store.items():
            upsert("lasermcp_projects", {"id": pid, "payload": payload})
        return
    write_json("projects.json", store)


def approve_latest(project_id: str) -> dict[str, Any]:
    if uses_supabase_app_db():
        return rest("rpc/approve_lasermcp_version", method="POST", body={"p_id": project_id})
    store = _load()
    project = store.get(project_id)
    if not project:
        raise ValueError("unknown project")
    versions = project.get("versions") or []
    if not versions:
        raise ValueError("no versions to approve")
    versions[-1].update(approved=True, approved_at=now_iso())
    _save_store(store)
    return {"project_id": project_id, "version": versions[-1].get("n")}


def list_projects() -> list[dict[str, Any]]:
    store = _load()
    out = []
    for pid, project in store.items():
        versions = project.get("versions") or []
        out.append(
            {
                "id": pid,
                "name": project.get("name"),
                "updated": project.get("updated"),
                "versions": len(versions),
                "latest": versions[-1] if versions else None,
            }
        )
    out.sort(key=lambda r: str(r.get("updated") or ""), reverse=True)
    return out


def project_history(project_id: str) -> dict[str, Any] | None:
    if uses_supabase_app_db():
        found = rows("lasermcp_projects", id=f"eq.{project_id}", limit=1)
        return found[0]["payload"] if found else None
    store = _load()
    return store.get(project_id)


def project_by_file(file_id: str) -> dict[str, Any] | None:
    needle = str(file_id or "").replace("\\", "/").split("/")[-1].strip()
    if not needle:
        return None
    for pid, project in _load().items():
        if not isinstance(project, dict):
            continue
        versions = project.get("versions") or []
        for ver in reversed(versions):
            if not isinstance(ver, dict):
                continue
            fid = str(ver.get("file_id") or "").replace("\\", "/").split("/")[-1].strip()
            if fid != needle:
                continue
            primitives = ver.get("primitives") if isinstance(ver.get("primitives"), list) else []
            if not primitives:
                for older in reversed(versions):
                    if isinstance(older, dict) and isinstance(older.get("primitives"), list) and older["primitives"]:
                        primitives = older["primitives"]
                        break
            return {
                "project_id": pid,
                "name": project.get("name") or pid,
                "version": ver.get("n"),
                "file_id": fid,
                "dxf_id": ver.get("dxf_id"),
                "primitives": [dict(p) for p in primitives if isinstance(p, dict)],
                "material": ver.get("material"),
                "machine": ver.get("machine"),
                "parameters": dict(ver.get("parameters") or {}),
            }
    return None
