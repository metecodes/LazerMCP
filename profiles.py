"""Material and machine profiles. Incoming AIs pick a name; they do not invent kerf."""

from __future__ import annotations

from typing import Any

from boxes_adapter import PAYAS_DEFAULTS

MATERIALS: dict[str, dict[str, Any]] = {
    "poplar_3mm": {
        "id": "poplar_3mm",
        "name": "3 mm kavak kontrplak",
        "thickness": 3.0,
        "kerf": 0.15,
        "density_g_cm3": 0.45,
        "sheet_w": 1500,
        "sheet_h": 3000,
        "note": "Payas STEM default. Coupon first on a new batch.",
    },
    "poplar_4mm": {
        "id": "poplar_4mm",
        "name": "4 mm kavak kontrplak",
        "thickness": 4.0,
        "kerf": 0.18,
        "density_g_cm3": 0.45,
        "sheet_w": 1500,
        "sheet_h": 3000,
        "note": "Thicker walls; tab-slots must be ~4 mm.",
    },
    "mdf_3mm": {
        "id": "mdf_3mm",
        "name": "3 mm MDF",
        "thickness": 3.0,
        "kerf": 0.20,
        "density_g_cm3": 0.75,
        "sheet_w": 1220,
        "sheet_h": 2440,
        "note": "More burn than poplar. Recalibrate.",
    },
    "acrylic_3mm": {
        "id": "acrylic_3mm",
        "name": "3 mm akrilik",
        "thickness": 3.0,
        "kerf": 0.12,
        "density_g_cm3": 1.18,
        "sheet_w": 600,
        "sheet_h": 400,
        "note": "Flame-polish edges. Holding nicks still required.",
    },
}

MACHINES: dict[str, dict[str, Any]] = {
    "payas_workshop": {
        "id": "payas_workshop",
        "name": "Payas STEM LaserCAD 1500×3000",
        "bed_w": 1500,
        "bed_h": 3000,
        "y_up": True,
        "cut": "#FF0000",
        "etch": "#000000",
        "gap_mm": 3.0,
        "nick_mm": 1.0,
        "dxf": True,
        "note": "Do not flip/rotate/mirror.",
    },
    "desktop_400": {
        "id": "desktop_400",
        "name": "Masaüstü 400×400",
        "bed_w": 400,
        "bed_h": 400,
        "y_up": True,
        "cut": "#FF0000",
        "etch": "#000000",
        "gap_mm": 2.5,
        "nick_mm": 1.0,
        "dxf": True,
        "note": "Small bed; nest may need more than one sheet.",
    },
    "lasercad_900": {
        "id": "lasercad_900",
        "name": "LaserCAD 900×600",
        "bed_w": 900,
        "bed_h": 600,
        "y_up": True,
        "cut": "#FF0000",
        "etch": "#000000",
        "gap_mm": 3.0,
        "nick_mm": 1.0,
        "dxf": True,
        "note": "Common school bed.",
    },
}


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def resolve_material(parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    params = parameters or {}
    raw = _norm(params.get("material") or params.get("material_id") or "poplar_3mm")
    aliases = {
        "kavak": "poplar_3mm",
        "poplar": "poplar_3mm",
        "plywood": "poplar_3mm",
        "default": "poplar_3mm",
        "mdf": "mdf_3mm",
        "acrylic": "acrylic_3mm",
        "pleksi": "acrylic_3mm",
    }
    mid = aliases.get(raw, raw)
    if mid not in MATERIALS and raw.endswith("4mm"):
        mid = "poplar_4mm"
    mat = dict(MATERIALS.get(mid) or MATERIALS["poplar_3mm"])
    batch_id = str(params.get("batch_id") or "").strip()
    if batch_id:
        try:
            from catalog import get_batch

            batch = get_batch(batch_id)
        except Exception:
            batch = None
        if batch:
            mat["batch_id"] = batch.get("id")
            mat["supplier"] = batch.get("supplier")
            mat["lot"] = batch.get("lot")
            if batch.get("measured_thickness"):
                mat["thickness"] = batch["measured_thickness"]
            if batch.get("kerf"):
                mat["kerf"] = batch["kerf"]
            mat["note"] = (mat.get("note") or "") + " Batch " + str(batch.get("id"))
    return mat


def resolve_machine(parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    params = parameters or {}
    raw = _norm(params.get("machine") or params.get("machine_id") or "payas_workshop")
    aliases = {"default": "payas_workshop", "payas": "payas_workshop", "workshop": "payas_workshop"}
    mid = aliases.get(raw, raw)
    try:
        from catalog import get_machine

        extra = get_machine(mid)
    except Exception:
        extra = None
    if extra:
        return extra
    return dict(MACHINES.get(mid) or MACHINES["payas_workshop"])


def apply_profiles(parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(parameters or {})
    material = resolve_material(params)
    machine = resolve_machine(params)
    params.setdefault("thickness", material["thickness"])
    raw_burn = params.get("burn")
    default_burn = PAYAS_DEFAULTS["burn"]
    unused_default = (
        raw_burn in (None, "")
        or (
            params.get("measured_bar_mm") in (None, "")
            and float(raw_burn) == float(default_burn)
            and float(material["kerf"]) != float(default_burn)
        )
    )
    if unused_default:
        params["_need_burn"] = True
        params["burn"] = material["kerf"]
    params["material"] = material["id"]
    params["machine"] = machine["id"]
    params["_material"] = material
    params["_machine"] = machine
    return params


def list_profiles() -> dict[str, Any]:
    machines = list(MACHINES.values())
    try:
        from catalog import all_machines

        machines = all_machines()
    except Exception:
        pass
    return {
        "success": True,
        "defaults": dict(PAYAS_DEFAULTS),
        "materials": list(MATERIALS.values()),
        "machines": machines,
        "note": "Pass parameters.material and parameters.machine to create_design. Do not invent kerf.",
    }
