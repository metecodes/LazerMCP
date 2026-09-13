"""Machine library, dealer machines, material batches, activation codes. Kerf stays human."""

from __future__ import annotations

import secrets
from typing import Any

from studio_store import now_iso, read_json, write_json

LIBRARY: dict[str, dict[str, Any]] = {
    "payas_workshop": {
        "id": "payas_workshop",
        "brand": "Payas STEM",
        "model": "LaserCAD 1500",
        "name": "Payas STEM LaserCAD 1500×3000",
        "bed_w": 1500,
        "bed_h": 3000,
        "y_up": True,
        "cut": "#FF0000",
        "etch": "#000000",
        "gap_mm": 3.0,
        "nick_mm": 1.0,
        "dxf": True,
        "source": "library",
        "verified": True,
        "note": "Payas atölye yatağı. Do not flip/rotate/mirror.",
    },
    "lasercad_900": {
        "id": "lasercad_900",
        "brand": "LaserCAD",
        "model": "900",
        "name": "LaserCAD 900×600",
        "bed_w": 900,
        "bed_h": 600,
        "y_up": True,
        "cut": "#FF0000",
        "etch": "#000000",
        "gap_mm": 3.0,
        "nick_mm": 1.0,
        "dxf": True,
        "source": "library",
        "verified": True,
        "note": "Common school bed.",
    },
    "desktop_400": {
        "id": "desktop_400",
        "brand": "Desktop",
        "model": "400",
        "name": "Masaüstü 400×400",
        "bed_w": 400,
        "bed_h": 400,
        "y_up": True,
        "cut": "#FF0000",
        "etch": "#000000",
        "gap_mm": 2.5,
        "nick_mm": 1.0,
        "dxf": True,
        "source": "library",
        "verified": False,
        "note": "Small bed; nest may need more than one sheet.",
    },
}


def _load(name: str, default: Any) -> Any:
    raw = read_json(name, default)
    return raw if isinstance(raw, type(default)) else default


def _save(name: str, payload: Any) -> None:
    write_json(name, payload)


def _norm(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def dealer_machines() -> list[dict[str, Any]]:
    rows = _load("dealer_machines.json", [])
    return [row for row in rows if isinstance(row, dict)]


def upsert_machine(body: dict[str, Any], *, owner: str = "") -> dict[str, Any]:
    brand = str(body.get("brand") or "").strip()[:40]
    model = str(body.get("model") or "").strip()[:40]
    mid = _norm(body.get("id") or f"{brand}_{model}" or "custom_laser")
    if mid in LIBRARY and body.get("source") != "dealer":
        mid = mid + "_" + secrets.token_hex(2)
    try:
        bed_w = float(body.get("bed_w") or body.get("bed_width") or 0)
        bed_h = float(body.get("bed_h") or body.get("bed_height") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("bed_w and bed_h are required millimetres") from exc
    if bed_w < 50 or bed_h < 50:
        raise ValueError("bed must be at least 50×50 mm")
    row = {
        "id": mid,
        "brand": brand or "Custom",
        "model": model or mid,
        "name": str(body.get("name") or f"{brand} {model}".strip() or mid)[:80],
        "bed_w": bed_w,
        "bed_h": bed_h,
        "y_up": True,
        "cut": "#FF0000",
        "etch": "#000000",
        "gap_mm": float(body.get("gap_mm") or 3.0),
        "nick_mm": float(body.get("nick_mm") or 1.0),
        "dxf": True,
        "source": "dealer" if owner else "custom",
        "verified": False,
        "owner": owner,
        "note": str(body.get("note") or "Dealer or workshop defined. Not a physical PASS."),
        "created": now_iso(),
    }
    rows = [r for r in dealer_machines() if r.get("id") != mid]
    rows.append(row)
    _save("dealer_machines.json", rows[-200:])
    return row


def all_machines() -> list[dict[str, Any]]:
    extra = {row["id"]: row for row in dealer_machines() if row.get("id")}
    out = [dict(row) for row in LIBRARY.values()]
    known = {row["id"] for row in out}
    for mid, row in extra.items():
        if mid in known:
            out = [row if item.get("id") == mid else item for item in out]
        else:
            out.append(row)
    return out


def get_machine(machine_id: str) -> dict[str, Any] | None:
    mid = _norm(machine_id)
    for row in all_machines():
        if row.get("id") == mid:
            return dict(row)
    return None


def batches() -> list[dict[str, Any]]:
    rows = _load("material_batches.json", [])
    return [row for row in rows if isinstance(row, dict)]


def upsert_batch(body: dict[str, Any], *, owner: str = "") -> dict[str, Any]:
    material = _norm(body.get("material") or body.get("material_id") or "mdf_3mm")
    bid = _norm(body.get("id") or "") or ("batch_" + secrets.token_hex(3))
    measured = body.get("measured_thickness")
    kerf = body.get("kerf")
    try:
        measured_n = float(measured) if measured not in (None, "") else None
    except (TypeError, ValueError):
        measured_n = None
    try:
        kerf_n = float(kerf) if kerf not in (None, "") else None
    except (TypeError, ValueError):
        kerf_n = None
    if kerf_n is not None and not (0.05 <= kerf_n <= 0.60):
        raise ValueError("batch kerf must come from a coupon (0.05–0.60 mm)")
    row = {
        "id": bid,
        "material": material,
        "supplier": str(body.get("supplier") or "")[:60],
        "lot": str(body.get("lot") or body.get("batch") or "")[:40],
        "nominal_thickness": float(body.get("thickness") or body.get("nominal_thickness") or 3.0),
        "measured_thickness": measured_n,
        "kerf": kerf_n,
        "owner": owner,
        "note": str(body.get("note") or "Coupon first. Software does not invent kerf."),
        "updated": now_iso(),
    }
    rows = [r for r in batches() if r.get("id") != bid]
    rows.append(row)
    _save("material_batches.json", rows[-300:])
    return row


def get_batch(batch_id: str) -> dict[str, Any] | None:
    bid = _norm(batch_id)
    for row in batches():
        if row.get("id") == bid:
            return dict(row)
    return None


def activation_codes() -> list[dict[str, Any]]:
    rows = _load("activation_codes.json", [])
    return [row for row in rows if isinstance(row, dict)]


def mint_activation(body: dict[str, Any], *, owner: str = "") -> dict[str, Any]:
    machine_id = _norm(body.get("machine_id") or body.get("machine") or "")
    if not machine_id or not get_machine(machine_id):
        raise ValueError("machine_id must be a known library or dealer machine")
    try:
        days = int(body.get("trial_days") or 30)
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 90))
    code = str(body.get("code") or "").strip().upper() or ("LM-" + secrets.token_hex(3).upper())
    row = {
        "code": code,
        "machine_id": machine_id,
        "dealer_id": owner,
        "plan": "pro",
        "trial_days": days,
        "created": now_iso(),
        "redeemed_by": None,
        "redeemed_at": None,
    }
    rows = activation_codes()
    rows.append(row)
    _save("activation_codes.json", rows[-400:])
    return row


def redeem_activation(code: str, *, owner: str = "") -> dict[str, Any]:
    raw = str(code or "").strip().upper()
    if not raw:
        raise ValueError("activation code required")
    rows = activation_codes()
    hit = None
    for row in rows:
        if str(row.get("code") or "").upper() == raw:
            hit = row
            break
    if not hit:
        raise ValueError("unknown activation code")
    if hit.get("redeemed_by") and hit.get("redeemed_by") != owner:
        raise ValueError("activation code already used")
    hit["redeemed_by"] = owner or hit.get("redeemed_by")
    hit["redeemed_at"] = now_iso()
    _save("activation_codes.json", rows)
    machine = get_machine(str(hit.get("machine_id") or ""))
    return {
        "success": True,
        "code": hit["code"],
        "machine": machine,
        "plan": hit.get("plan") or "pro",
        "trial_days": hit.get("trial_days") or 30,
        "note": "Machine profile applied. Coupon still required before a physical PASS.",
    }


def public_catalog() -> dict[str, Any]:
    return {
        "success": True,
        "machines": all_machines(),
        "batches": batches(),
        "note": "Pick a library or dealer machine. Verified means catalog geometry, not a physical PASS.",
    }
