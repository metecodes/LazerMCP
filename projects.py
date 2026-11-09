"""User projects, design versions, history."""

from __future__ import annotations

import re
import secrets
from typing import Any

from studio_store import now_iso, read_json, write_json
from persist.env import uses_supabase_app_db
from persist.supabase_rest import rest, rows, upsert


_AUTO = object()
# Light listing: only the fields Studio history shows, latest version picked server-side.
_LIST_SELECT = (
    "id,name:payload->>name,created:payload->>created,updated:payload->>updated,"
    "n:payload->versions->-1->>n,file_id:payload->versions->-1->>file_id,"
    "final_status:payload->versions->-1->>final_status,product:payload->versions->-1->>product,"
    "at:payload->versions->-1->>at,approved:payload->versions->-1->>approved,"
    "owner_org:payload->versions->-1->>owner_org,"
    "owner_user:payload->versions->-1->>owner_user"
)
_LATEST = "payload->versions->-1->>"
_OWNED_FILES_LIMIT = 150  # keeps the or=(…in.(…)) filter well under URL limits


def _current_principal() -> dict[str, Any] | None:
    try:
        from keys import current_auth

        return current_auth.get()
    except Exception:
        return None


def _owner_org(principal: dict[str, Any] | None) -> str:
    if not principal:
        return ""
    try:
        from persist.job import _org_id

        return _org_id(principal) or ""
    except Exception:
        return str(principal.get("organization_id") or "")


def _owner_user(principal: dict[str, Any] | None) -> str:
    if not principal:
        return ""
    return str(principal.get("id") or principal.get("user_id") or "").strip()


def visible_scope(principal: dict[str, Any] | None) -> dict[str, set[str]] | None:
    """Which projects a caller may see. None = all (operator, or single-tenant local store).

    New versions carry owner_org / owner_user. Older rows are matched through the
    caller's SVG artifacts, the same ownership record /files/ uses.
    """
    if not uses_supabase_app_db():
        return None
    if principal:
        from supabase_auth import is_admin

        if is_admin(principal) or (str(principal.get("id")) == "admin" and str(principal.get("role")) == "admin"):
            return None
    org = _owner_org(principal)
    uid = _owner_user(principal)
    if not org and not uid:
        return {"orgs": set(), "users": set(), "files": set()}
    files: set[str] = set()
    if org:
        try:
            found = rows(
                "lasermcp_artifacts",
                select="source_file_id",
                organization_id=f"eq.{org}",
                kind="eq.svg",
                order="created_at.desc",
                limit=_OWNED_FILES_LIMIT,
            )
            files = {str(r.get("source_file_id")) for r in found if r.get("source_file_id")}
        except Exception:
            files = set()
    return {
        "orgs": {org} if org else set(),
        "users": {uid} if uid else set(),
        "files": files,
    }


def _resolve_scope(scope: Any) -> dict[str, set[str]] | None:
    return visible_scope(_current_principal()) if scope is _AUTO else scope


def _project_visible(project: dict[str, Any] | None, scope: dict[str, set[str]] | None) -> bool:
    if not isinstance(project, dict):
        return False
    if scope is None:
        return True
    users = scope.get("users") or set()
    orgs = scope.get("orgs") or set()
    files = scope.get("files") or set()
    for ver in project.get("versions") or []:
        if not isinstance(ver, dict):
            continue
        if ver.get("owner_user") and ver.get("owner_user") in users:
            return True
        if ver.get("owner_org") and ver.get("owner_org") in orgs:
            return True
        if ver.get("file_id") and ver.get("file_id") in files:
            return True
    return False


def _quoted(values: set[str]) -> str:
    return ",".join('"' + str(v).replace('"', "") + '"' for v in sorted(values))


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", (name or "job").strip()).strip("-").lower()
    return (slug[:32] or "job")


def _load() -> dict[str, Any]:
    if uses_supabase_app_db():
        return {row["id"]: row["payload"] for row in rows("lasermcp_projects")}
    raw = read_json("projects.json", {})
    return raw if isinstance(raw, dict) else {}


def _may_extend(project_id: str) -> bool:
    """A caller-supplied project id may only add versions to a project the caller can see.

    Unknown ids start a new project. Projects no organization owns (guest saves) stay open,
    so a guest can keep revising their own draft.
    """
    if not uses_supabase_app_db():
        return True
    found = rows("lasermcp_projects", id=f"eq.{project_id}", limit=1)
    project = found[0].get("payload") if found else None
    if not isinstance(project, dict):
        return True
    if _project_visible(project, visible_scope(_current_principal())):
        return True
    return not any(isinstance(v, dict) and v.get("owner_org") for v in project.get("versions") or [])


def save_version(parameters: dict[str, Any] | None, result: dict[str, Any] | None) -> dict[str, Any] | None:
    params = parameters or {}
    data = result or {}
    name = str(params.get("project") or params.get("project_name") or data.get("title") or data.get("product") or "").strip()
    pid = str(params.get("project_id") or "").strip() or None
    if not name and not pid and not data.get("file_id"):
        return None
    remote = uses_supabase_app_db()
    store = {} if remote else _load()
    if pid and not _may_extend(pid):
        pid = None  # not theirs: keep the work, but as a new project
    if not pid:
        pid = _slug(name or str(data.get("product") or "design")) + "-" + secrets.token_hex(2)
    # The assembly result is written by the Automatic Assembly stage before
    # the project id may exist.  Bind both durable identifiers before storing
    # this version so previews can consume the exact verified result later.
    if isinstance(data.get("assembly_result"), dict):
        data["assembly_result"].setdefault("project_id", pid)
        data["assembly_result"].setdefault("file_id", data.get("file_id"))
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
        "assembly_result": data.get("assembly_result") if isinstance(data.get("assembly_result"), dict) else None,
        # Owner of this version; guests save as "" and get no shared history.
        "owner_org": _owner_org(_current_principal()),
        "owner_user": _owner_user(_current_principal()),
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
    if project_history(project_id) is None:
        raise ValueError("unknown project")
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


def _clamp_limit(limit: Any) -> int | None:
    if limit is None:
        return None
    try:
        return max(1, min(500, int(limit)))
    except (TypeError, ValueError):
        return 80


def _list_remote(limit: int | None, scope: dict[str, set[str]] | None) -> list[dict[str, Any]]:
    params: dict[str, Any] = {"select": _LIST_SELECT, "order": "payload->>updated.desc.nullslast",
                              "limit": limit or 500}
    if scope is not None:
        clauses = []
        if scope.get("orgs"):
            clauses.append(f"{_LATEST}owner_org.in.({_quoted(scope['orgs'])})")
        if scope.get("users"):
            clauses.append(f"{_LATEST}owner_user.in.({_quoted(scope['users'])})")
        if scope.get("files"):
            clauses.append(f"{_LATEST}file_id.in.({_quoted(scope['files'])})")
        if not clauses:
            return []
        params["or"] = "(" + ",".join(clauses) + ")"
    out = []
    for row in rest("lasermcp_projects", params=params) or []:
        n = row.get("n")
        latest = {
            "n": int(n) if str(n or "").isdigit() else n,
            "file_id": row.get("file_id"),
            "final_status": row.get("final_status"),
            "product": row.get("product"),
            "at": row.get("at"),
            "approved": str(row.get("approved")).lower() == "true",
            "owner_user": row.get("owner_user") or "",
            "owner_org": row.get("owner_org") or "",
        }
        out.append({
            "id": row.get("id"),
            "name": row.get("name"),
            "updated": row.get("updated"),
            "versions": latest["n"] if isinstance(latest["n"], int) else None,
            "latest": latest,
        })
    return out


def list_projects(limit: int | None = None, scope: Any = _AUTO) -> list[dict[str, Any]]:
    """Projects the caller may see, newest first. Pass scope=None only for operator/internal use."""
    resolved = _resolve_scope(scope)
    n = _clamp_limit(limit)
    if uses_supabase_app_db():
        return _list_remote(n, resolved)
    store = _load()
    out = []
    for pid, project in store.items():
        if not _project_visible(project, resolved):
            continue
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
    return out[:n] if n is not None else out


def project_history(project_id: str, scope: Any = _AUTO) -> dict[str, Any] | None:
    """Full project for a caller who may see it; None when unknown or not theirs."""
    if uses_supabase_app_db():
        found = rows("lasermcp_projects", id=f"eq.{project_id}", limit=1)
        project = found[0]["payload"] if found else None
    else:
        project = _load().get(project_id)
    return project if _project_visible(project, _resolve_scope(scope)) else None


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
                "assembly_result": ver.get("assembly_result") if isinstance(ver.get("assembly_result"), dict) else None,
            }
    return None


def attach_assembly_result(file_id: str, assembly_result: dict[str, Any]) -> bool:
    """Persist a fallback Automatic Assembly run on its existing version.

    This deliberately updates the same project version: opening an old design
    for an assembled preview must not create a cosmetic design revision.
    """
    needle = str(file_id or "").replace("\\", "/").split("/")[-1].strip()
    if not needle or not isinstance(assembly_result, dict):
        return False
    store = _load()
    for pid, project in store.items():
        if not isinstance(project, dict):
            continue
        for version in reversed(project.get("versions") or []):
            if not isinstance(version, dict):
                continue
            fid = str(version.get("file_id") or "").replace("\\", "/").split("/")[-1].strip()
            if fid != needle:
                continue
            saved = dict(assembly_result)
            saved.setdefault("project_id", pid)
            saved.setdefault("file_id", needle)
            version["assembly_result"] = saved
            project["updated"] = now_iso()
            _save_store(store)
            return True
    return False
