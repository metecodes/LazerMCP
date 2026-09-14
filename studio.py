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
        return {"success": True, "rows": list_calibrations()}
    if verb in {"projects", "project", "history"}:
        if project_id:
            hit = project_history(project_id)
            if not hit:
                return {"success": True, "look_again": [f"No project {project_id}."], "projects": list_projects()}
            return {"success": True, "project": hit}
        return {"success": True, "projects": list_projects()}
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
