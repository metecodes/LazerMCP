"""Studio facade: profiles, kerf log, BOM, project versions, preview, telemetry."""

from __future__ import annotations

from typing import Any

from bom import build_bom
from calibrate import apply_stored_burn, list_calibrations, record_calibration
from keys import create_key, list_keys
from metering import record_usage, usage_summary
from profiles import apply_profiles, list_profiles
from projects import list_projects, project_history, save_version
from telemetry import emit, recent


def _principal() -> dict[str, Any] | None:
    from keys import current_auth

    return current_auth.get()


def prepare_parameters(parameters: dict[str, Any] | None) -> dict[str, Any]:
    from plans import entitled

    incoming = dict(parameters or {})
    if not entitled("custom_materials"):
        incoming["material"] = "poplar_3mm"
    if not entitled("machine_profiles"):
        incoming["machine"] = "payas_workshop"
    if "joint_clearance_mm" in incoming and incoming["joint_clearance_mm"] not in (None, ""):
        try:
            clearance = float(incoming["joint_clearance_mm"])
        except (TypeError, ValueError) as exc:
            raise ValueError("joint_clearance_mm must be a number") from exc
        if not -0.15 <= clearance <= 0.40:
            raise ValueError("joint_clearance_mm must be between -0.15 and 0.40 mm")
        incoming["joint_clearance_mm"] = round(clearance, 3)
    return apply_stored_burn(apply_profiles(incoming))


def attach(extra: dict[str, Any], svg_bytes: bytes | None = None, primitives: list[Any] | None = None) -> dict[str, Any]:
    """Enrich a saved job. Does not invent kerf, hardware, or physical PASS."""
    data = extra if extra is not None else {}
    params = prepare_parameters(data.get("parameters") if isinstance(data.get("parameters"), dict) else {})
    material = params.get("_material") or {}
    machine = params.get("_machine") or {}
    data["parameters"] = {k: v for k, v in params.items() if not str(k).startswith("_")}
    data["profiles"] = {"material": material, "machine": machine}
    cal = record_calibration(params, data.get("physical"))
    if cal:
        data["calibration"] = cal
    from plans import entitled

    parts = primitives if primitives is not None else data.get("primitives")
    if entitled("bom"):
        bom = build_bom(
            primitives=parts if isinstance(parts, list) else None,
            product=str(data.get("product") or "") or None,
            material=material,
            nesting=data.get("nesting") if isinstance(data.get("nesting"), dict) else None,
            machine=machine,
            parameters=data.get("parameters") if isinstance(data.get("parameters"),dict) else None,
        )
        data["bom"] = bom
        data["materials_speak"] = bom["speak"]
        speak = str(data.get("speak") or "").rstrip()
        if bom["speak"] and "MATERIALS (MCP)" not in speak:
            data["speak"] = (speak + "\n\n" + bom["speak"]).strip() if speak else bom["speak"]
    return data


def finish_result(result: dict[str, Any], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    from plans import apply_plan_to_result

    payload = extra or result
    params = payload.get("parameters") if isinstance(payload.get("parameters"), dict) else {}
    if result.get("primitives") is None and isinstance(payload.get("primitives"), list):
        result["primitives"] = payload.get("primitives")
    project = save_version(params, result)
    if project:
        result["project"] = project
        payload["project"] = project
        result["project_persistence"] = "PROJECT_PERSISTENCE_SUCCESS"
    result = apply_plan_to_result(result, extra)
    key = _principal()
    record_usage(
        key,
        str(result.get("generator") or result.get("product") or "job"),
        {
            "file_id": result.get("file_id"),
            "bytes": result.get("bytes"),
            "final_status": result.get("final_status"),
            "product": result.get("product"),
        },
    )
    emit(
        "info",
        "job_saved",
        str(result.get("file_id") or ""),
        {"file_id": result.get("file_id"), "final_status": result.get("final_status"), "key": (key or {}).get("id")},
    )
    if result.get("look_again"):
        emit("warn", "look_again", "; ".join(str(x) for x in result.get("look_again") or [])[:300], {"file_id": result.get("file_id")})
    return result


def studio_action(
    action: str,
    name: str = "",
    project_id: str = "",
    role: str = "workshop",
    plan: str = "",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verb = str(action or "profiles").strip().lower()
    body = dict(payload or {})
    if name and not body.get("name"):
        body["name"] = name
    if project_id and not body.get("project_id"):
        body["project_id"] = project_id
    workshop_verbs = {
        "onboard",
        "onboarding",
        "catalog",
        "library",
        "machine",
        "machines",
        "batch",
        "batches",
        "feedback",
        "fit",
        "preflight",
        "pre_flight",
        "check",
        "revise",
        "edit",
        "cost",
        "quote",
        "make",
        "make_this",
        "structure",
        "box",
        "studio_box",
        "parametric",
        "ai",
        "studio_ai",
        "design_ai",
        "approve",
        "activate",
        "redeem",
        "mint",
        "codes",
    }
    if verb in workshop_verbs:
        from workshop import workshop_action

        return workshop_action(verb, body, _principal())
    if verb in {"profiles", "profile"}:
        return list_profiles()
    if verb in {"calibrate", "calibration", "calibrations"}:
        # POST measured_bar_mm → human kerf record (never invent PASS without measurement).
        if body.get("measured_bar_mm") not in (None, ""):
            from physical import read_physical

            params = {
                "machine": body.get("machine") or "payas_workshop",
                "material": body.get("material") or "poplar_3mm",
                "measured_bar_mm": body.get("measured_bar_mm"),
                "nominal_bar_mm": body.get("nominal_bar_mm") or 100,
            }
            phys = read_physical(params)
            row = record_calibration(params, phys)
            looks = []
            if phys.get("kerf") == "FAIL":
                looks.append(str((phys.get("notes") or {}).get("kerf") or "measured_bar_mm rejected"))
            elif not row:
                looks.append("Calibration not stored — kerf must be PASS with a measured bar.")
            elif row.get("stored") is False:
                looks.append(
                    f"Burn {row.get('burn')} mm hesaplandı — misafir olarak kalıcı kaydedilmedi; "
                    "atölyene kaydetmek için giriş yap (fiziksel fit NOT_VERIFIED)."
                )
            else:
                looks.append(
                    f"Stored burn {row.get('burn')} mm for {row.get('machine')}/{row.get('material')} "
                    "(physical fit still NOT_VERIFIED until dry-fit)."
                )
            return {
                "success": phys.get("kerf") == "PASS" and bool(row),
                "calibration": row,
                "physical": phys,
                "suggested_burn": (row or {}).get("burn") or phys.get("suggested_burn"),
                "rows": list_calibrations(),
                "look_again": looks,
            }
        return {"success": True, "rows": list_calibrations()}
    if verb in {"projects", "project", "history"}:
        raw_limit = body.get("limit")
        limit = None if raw_limit in (None, "", "all") else raw_limit
        if project_id or body.get("project_id"):
            pid = str(project_id or body.get("project_id") or "")
            hit = project_history(pid)
            if not hit:
                return {"success": True, "look_again": [f"No project {pid}."], "projects": list_projects(limit=limit)}
            return {"success": True, "project": hit}
        rows = list_projects(limit=limit)
        return {
            "success": True,
            "projects": rows,
            "limit": None if limit in (None, "") else int(limit) if str(limit).isdigit() else limit,
            "returned": len(rows),
        }
    if verb in {"usage", "metering"}:
        return usage_summary()
    if verb in {"keys", "key"}:
        from supabase_auth import can_mint_keys, configured

        key = _principal()
        if configured() and not can_mint_keys(key):
            return {
                "success": True,
                "look_again": ["Organization accounts mint API keys. Individuals sign in with Google."],
                "keys": list_keys(owner=str((key or {}).get("id") or "")),
            }
        if name:
            return {
                "success": True,
                **create_key(
                    name,
                    role,
                    plan,
                    owner=str((key or {}).get("id") or ""),
                    email=str((key or {}).get("email") or ""),
                    kind="org",
                ),
            }
        oid = str((key or {}).get("id") or "")
        if configured():
            return {"success": True, "keys": list_keys(owner=oid) if oid else []}
        return {"success": True, "keys": list_keys()}
    if verb in {"telemetry", "events"}:
        return {"success": True, "events": recent()}
    return {
        "success": True,
        "look_again": [
            "action=profiles|calibrate|projects|usage|keys|telemetry|onboard|catalog|feedback|preflight|revise|cost|make_this|activate"
        ],
        "actions": [
            "profiles",
            "calibrate",
            "projects",
            "usage",
            "keys",
            "telemetry",
            "onboard",
            "catalog",
            "feedback",
            "preflight",
            "revise",
            "cost",
            "make_this",
            "activate",
        ],
    }


def overview() -> dict[str, Any]:
    from keys import list_keys as keys_for_owner

    key = _principal()
    owner = str((key or {}).get("id") or "")
    return {
        "success": True,
        "profiles": list_profiles(),
        "calibrations": list_calibrations(),
        "projects": list_projects(),
        "usage": usage_summary(),
        "keys": keys_for_owner(owner=owner) if owner else [],
        "telemetry": recent(40),
        "plans": __import__("plans").public_plans(),
        "workshop": __import__("workshop").get_onboarding(key),
        "feedback": __import__("workshop").list_feedback(),
    }
