"""Normalize Studio parametric-box requests into toolbox primitives + parameters."""

from __future__ import annotations

from typing import Any


def _f(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def _i(value: Any, default: int = 0, lo: int = 0, hi: int = 12) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(lo, min(hi, n))


def _unit_to_mm(value: float, unit: str) -> float:
    return float(value) * 25.4 if str(unit).lower() in {"in", "inch", "inches"} else float(value)


def equal_cells(inner: float, dividers: int, thickness: float) -> list[float]:
    """Cell widths that leave room for divider thickness between them."""
    n = max(0, int(dividers))
    if n <= 0:
        return [float(inner)]
    usable = float(inner) - n * float(thickness)
    if usable < (n + 1) * 8:
        raise ValueError("dividers leave cells under 8 mm — reduce count or grow the box")
    cell = usable / (n + 1)
    return [round(cell, 3)] * (n + 1)


def divider_positions(cells: list[float], thickness: float) -> list[float]:
    """Centerline of each divider, measured from the inner 0 edge."""
    pos: list[float] = []
    cursor = 0.0
    t = float(thickness)
    for cell in cells[:-1]:
        cursor += float(cell) + t
        pos.append(round(cursor - t / 2.0, 3))
    return pos


def cells_from_divider_positions(inner: float, positions: list[float], thickness: float) -> list[float]:
    """Invert divider centerlines → cell widths (room for divider thickness)."""
    t = float(thickness)
    span = float(inner)
    ps = sorted(float(p) for p in positions)
    if not ps:
        return [span]
    cells: list[float] = []
    prev = 0.0
    for p in ps:
        lo = p - t / 2.0
        if lo - prev < 8.0 - 1e-6:
            raise ValueError("divider leaves a cell under 8 mm — move it or grow the box")
        if lo < 0 or p + t / 2.0 > span + 1e-6:
            raise ValueError("divider position outside the inner span")
        cells.append(round(lo - prev, 3))
        prev = p + t / 2.0
    last = span - prev
    if last < 8.0 - 1e-6:
        raise ValueError("divider leaves a cell under 8 mm — move it or grow the box")
    cells.append(round(last, 3))
    return cells


def _parse_cell_list(raw: Any) -> list[float] | None:
    if not isinstance(raw, (list, tuple)) or not raw:
        return None
    out: list[float] = []
    for item in raw:
        try:
            out.append(float(item))
        except (TypeError, ValueError):
            return None
    return out if out else None


def resolve_inner_outer(
    x: float,
    y: float,
    h: float,
    thickness: float,
    *,
    dimension_mode: str = "internal",
) -> dict[str, float]:
    t = float(thickness)
    mode = str(dimension_mode or "internal").lower()
    if mode in {"external", "outside", "outer"}:
        xi = max(8.0, x - 2 * t)
        yi = max(8.0, y - 2 * t)
        hi = max(8.0, h - t)  # bottom panel eats one thickness of outer height
        return {
            "x_inner": xi,
            "y_inner": yi,
            "h_inner": hi,
            "x_outer": float(x),
            "y_outer": float(y),
            "h_outer": float(h),
        }
    return {
        "x_inner": float(x),
        "y_inner": float(y),
        "h_inner": float(h),
        "x_outer": float(x) + 2 * t,
        "y_outer": float(y) + 2 * t,
        "h_outer": float(h) + t,
    }


def volume_liters(x_inner: float, y_inner: float, h_usable: float) -> float:
    return round((x_inner * y_inner * max(0.0, h_usable)) / 1_000_000.0, 4)


def build_studio_box(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return {primitives, parameters, summary} for create_design / studio."""
    body = payload or {}
    unit = str(body.get("unit") or "mm").lower()
    thickness = _unit_to_mm(_f(body.get("thickness"), 3), unit if unit != "mm" else "mm")
    # thickness field is always mm in studio UI; only X/Y/H honour inch toggle
    if "thickness" in body:
        thickness = _f(body.get("thickness"), 3)

    x_in = _unit_to_mm(_f(body.get("x") or body.get("width"), 150), unit)
    y_in = _unit_to_mm(_f(body.get("y") or body.get("depth"), 120), unit)
    h_in = _unit_to_mm(_f(body.get("h") or body.get("height"), 50), unit)

    dims = resolve_inner_outer(
        x_in,
        y_in,
        h_in,
        thickness,
        dimension_mode=str(body.get("dimension_mode") or body.get("dims") or "internal"),
    )
    xi, yi, hi = dims["x_inner"], dims["y_inner"], dims["h_inner"]

    lid_raw = str(body.get("lid") or ("open" if body.get("open", body.get("open_top", True)) else "finger")).lower()
    if lid_raw in {"1", "true", "closed", "top"}:
        lid_raw = "finger"
    if lid_raw in {"0", "false", "none", ""}:
        lid_raw = "open"

    raised = max(0.0, _f(body.get("bottom_lift") or body.get("raised_bottom"), 0))
    if raised and raised + thickness + 8 > hi:
        raise ValueError("bottom_lift too high for this box height")

    dx = _i(body.get("dividers_x") or body.get("nx"), 0)
    dy = _i(body.get("dividers_y") or body.get("ny"), 0)

    custom_sx = _parse_cell_list(body.get("sx") or body.get("cells_x"))
    custom_sy = _parse_cell_list(body.get("sy") or body.get("cells_y"))
    pos_x = _parse_cell_list(body.get("divider_x_mm") or body.get("divider_x_pos"))
    pos_y = _parse_cell_list(body.get("divider_y_mm") or body.get("divider_y_pos"))

    if pos_x is not None:
        sx = cells_from_divider_positions(xi, pos_x, thickness)
        dx = max(0, len(sx) - 1)
    elif custom_sx is not None and len(custom_sx) >= 2:
        if abs(sum(custom_sx) + (len(custom_sx) - 1) * thickness - xi) > 0.6:
            raise ValueError("sx cells + divider thickness must equal inner X")
        if any(c < 8.0 for c in custom_sx):
            raise ValueError("each sx cell must be ≥ 8 mm")
        sx = [round(c, 3) for c in custom_sx]
        dx = len(sx) - 1
    else:
        sx = equal_cells(xi, dx, thickness) if dx else [xi]

    if pos_y is not None:
        sy = cells_from_divider_positions(yi, pos_y, thickness)
        dy = max(0, len(sy) - 1)
    elif custom_sy is not None and len(custom_sy) >= 2:
        if abs(sum(custom_sy) + (len(custom_sy) - 1) * thickness - yi) > 0.6:
            raise ValueError("sy cells + divider thickness must equal inner Y")
        if any(c < 8.0 for c in custom_sy):
            raise ValueError("each sy cell must be ≥ 8 mm")
        sy = [round(c, 3) for c in custom_sy]
        dy = len(sy) - 1
    else:
        sy = equal_cells(yi, dy, thickness) if dy else [yi]

    handle = bool(body.get("handle", lid_raw in {"removable", "sliding", "hinged", "door", "double_door"}))
    handle_w = _f(body.get("handle_w"), min(40.0, xi * 0.35))
    handle_h = _f(body.get("handle_h"), min(20.0, yi * 0.25))

    lid_value: Any = False
    if lid_raw == "open":
        lid_value = False
    elif lid_raw in {"finger", "finger_joint", "fixed"}:
        lid_value = {"type": "finger_joint"}
    elif lid_raw in {"removable", "drop", "friction"}:
        lid_value = {"type": "removable", "handle": handle, "handle_w": handle_w, "handle_h": handle_h}
    elif lid_raw in {"sliding", "slide"}:
        lid_value = {"type": "sliding", "handle": True, "handle_w": handle_w, "handle_h": handle_h}
    elif lid_raw in {"hinged", "door", "single_door"}:
        lid_value = {"type": "hinged", "doors": 1, "handle": True, "handle_w": handle_w, "handle_h": handle_h}
    elif lid_raw in {"double_door", "two_door", "double"}:
        lid_value = {"type": "hinged", "doors": 2, "handle": True, "handle_w": handle_w / 2, "handle_h": handle_h}
    else:
        raise ValueError(f"unknown lid type {lid_raw!r}")

    finger = body.get("finger")
    if finger in (None, ""):
        finger_mult = 2.0
    else:
        # UI may send mm; convert to multiples of thickness
        fv = _f(finger, 2.0)
        finger_mult = fv / thickness if fv > 8 else fv
        finger_mult = max(0.8, min(6.0, finger_mult))

    press_fit = bool(body.get("press_fit") or body.get("bumps") or body.get("springs"))
    play = _f(body.get("play") or body.get("joint_play"), 0.0)

    box: dict[str, Any] = {
        "type": "box",
        "label": str(body.get("label") or body.get("name") or "studio-box"),
        "x": xi,
        "y": yi,
        "h": hi,
        "bottom": True,
        "lid": lid_value,
        "bottom_lift": raised,
        "dividers_x": dx,
        "dividers_y": dy,
        "sx": sx,
        "sy": sy,
        "divider_joint_walls": bool(body.get("divider_joint_walls", True)),
        "divider_joint_bottom": bool(body.get("divider_joint_bottom", True)),
    }
    if lid_raw == "open":
        box["top"] = False
        box["lid"] = False

    h_usable = hi - raised - (0.0 if lid_raw == "open" else 0.0)
    summary = {
        "unit": unit if unit in {"mm", "in", "inch", "inches"} else "mm",
        "dimension_mode": "external" if str(body.get("dimension_mode") or "").lower() in {"external", "outside", "outer"} else "internal",
        "x_inner_mm": round(xi, 3),
        "y_inner_mm": round(yi, 3),
        "h_inner_mm": round(hi, 3),
        "x_outer_mm": round(dims["x_outer"], 3),
        "y_outer_mm": round(dims["y_outer"], 3),
        "h_outer_mm": round(dims["h_outer"], 3),
        "thickness_mm": round(thickness, 3),
        "bottom_lift_mm": round(raised, 3),
        "h_usable_mm": round(h_usable, 3),
        "volume_l": volume_liters(xi, yi, h_usable),
        "lid": lid_raw,
        "dividers_x": dx,
        "dividers_y": dy,
        "sx": sx,
        "sy": sy,
        "divider_x_pos": divider_positions(sx, thickness) if dx else [],
        "divider_y_pos": divider_positions(sy, thickness) if dy else [],
        "finger_mult": round(finger_mult, 3),
        "press_fit": press_fit,
    }

    parameters: dict[str, Any] = {
        "thickness": thickness,
        "project": str(body.get("project") or body.get("name") or "studio-box"),
        "material": body.get("material") or "poplar_3mm",
        "machine": body.get("machine") or "payas_workshop",
        "what_you_see": "studio parametric finger-joint box",
        "FingerJoint_finger": finger_mult,
        "FingerJoint_space": finger_mult,
        "FingerJoint_style": "springs" if press_fit else "rectangular",
        "FingerJoint_play": max(0.0, min(0.4, play)),
    }
    burn = body.get("burn")
    burn_set = burn not in (None, "")
    if burn_set:
        parameters["burn"] = _f(burn)

    joints = validate_joint_settings(
        thickness=thickness,
        finger_mult=finger_mult,
        press_fit=press_fit,
        play=play,
        burn=parameters.get("burn") if burn_set else None,
    )
    summary["joints"] = joints
    summary["burn_mm"] = joints.get("burn_mm")
    summary["kerf_status"] = joints.get("kerf_status")
    return {"primitives": [box], "parameters": parameters, "summary": summary}


def validate_joint_settings(
    *,
    thickness: float,
    finger_mult: float,
    press_fit: bool = False,
    play: float = 0.0,
    burn: float | None = None,
) -> dict[str, Any]:
    """Digital finger / bump / kerf checks. Physical fit stays NOT_VERIFIED."""
    t = float(thickness)
    fm = float(finger_mult)
    finger_mm = round(fm * t, 3)
    warnings: list[str] = []
    failures: list[str] = []

    if t < 1.0 or t > 12.0:
        failures.append(f"thickness {t} mm outside digital range 1–12 mm")
    if fm < 0.8 or fm > 6.0:
        failures.append(f"finger multiplier {fm} outside 0.8–6×thickness")
    elif fm < 1.2 or fm > 4.0:
        warnings.append(f"finger {fm}×thickness ({finger_mm} mm) is uncommon — dry-fit before production")

    # Minimum finger width vs material thickness (digital manufacturability)
    if finger_mm + 1e-9 < t:
        warnings.append(f"finger width {finger_mm} mm < thickness {t} mm — weak male fingers possible")

    play_v = max(0.0, float(play or 0))
    if press_fit and play_v > 0.15:
        warnings.append("press-fit bumps with play>0.15 mm may feel loose — measure kerf first")
    if play_v > 0.4:
        failures.append("joint play > 0.4 mm rejected digitally")

    if burn is None:
        kerf_status = "NOT_VERIFIED"
        warnings.append("burn/kerf not set — software will not invent kerf; measure coupon before production")
        burn_mm = None
    else:
        burn_mm = round(float(burn), 4)
        if burn_mm < 0.05 or burn_mm > 0.60:
            failures.append(f"burn {burn_mm} mm outside digital range 0.05–0.60")
            kerf_status = "FAIL"
        elif burn_mm < 0.08 or burn_mm > 0.35:
            warnings.append(f"burn {burn_mm} mm is unusual for 3 mm wood — confirm coupon")
            kerf_status = "WARNING"
        else:
            kerf_status = "ASSUMED"  # user-supplied number, not a physical test

    status = "FAIL" if failures else ("WARNING" if warnings else "PASS")
    return {
        "status": status,
        "kerf_status": kerf_status,
        "burn_mm": burn_mm,
        "finger_mult": round(fm, 3),
        "finger_mm": finger_mm,
        "press_fit": bool(press_fit),
        "style": "springs" if press_fit else "rectangular",
        "play_mm": round(play_v, 3),
        "physical_fit": "NOT_VERIFIED",
        "warnings": warnings,
        "failures": failures,
    }
