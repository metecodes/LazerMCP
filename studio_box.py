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


def drawer_cell_heights(h: float, raised: float, shelves: int, thickness: float, lid_eat: float = 0.0) -> list[float]:
    """Clear opening height of each shelf bay (shelf plate thickness removed)."""
    span = max(0.0, float(h) - float(raised) - float(lid_eat))
    n = max(1, int(shelves) + 1)
    step = span / n
    clear = max(0.0, step - float(thickness))
    return [round(clear, 3)] * n


def build_drawer_specs(
    *,
    sx: list[float],
    sy: list[float],
    cell_heights: list[float],
    thickness: float,
    clearance: float = 1.0,
    pull_r: float | None = None,
    max_drawers: int = 12,
) -> list[dict[str, Any]]:
    """One open tray drawer per cubby. Sizes are outer cut mm after clearance."""
    t = float(thickness)
    play = max(0.4, min(3.0, float(clearance)))
    specs: list[dict[str, Any]] = []
    for zi, ch in enumerate(cell_heights):
        for yi, dy in enumerate(sy):
            for xi, dx in enumerate(sx):
                if len(specs) >= max_drawers:
                    return specs
                w = round(float(dx) - play, 2)
                d = round(float(dy) - play, 2)
                h = round(float(ch) - play, 2)
                if w < 14 or d < 14 or h < 10:
                    continue
                r = float(pull_r) if pull_r not in (None, "") else min(12.0, w * 0.16, h * 0.38)
                r = max(4.0, min(r, w / 2 - 2, h * 0.45))
                specs.append(
                    {
                        "id": f"drawer-{len(specs) + 1}",
                        "col": xi,
                        "row_y": yi,
                        "row_z": zi,
                        "w_mm": w,
                        "d_mm": d,
                        "h_mm": h,
                        "pull_r_mm": round(r, 2),
                        "label_mm": f"{w:.0f}×{d:.0f}×{h:.0f}",
                        "thickness_mm": t,
                        "clearance_mm": play,
                    }
                )
    return specs


def _parse_locks(raw: Any, cell_count: int) -> dict[int, float]:
    """Map of cell index → locked width mm."""
    out: dict[int, float] = {}
    if not isinstance(raw, dict):
        return out
    for key, val in raw.items():
        try:
            idx = int(key)
            width = float(val)
        except (TypeError, ValueError):
            continue
        if 0 <= idx < cell_count and width >= 8.0:
            out[idx] = width
    return out


def cells_with_locks(
    inner: float,
    dividers: int,
    thickness: float,
    locks: dict[int, float] | None = None,
) -> list[float]:
    """Equal cells, then enforce locked widths and redistribute the rest."""
    n = max(0, int(dividers))
    count = n + 1
    base = equal_cells(inner, n, thickness)
    if not locks:
        return base
    locked = _parse_locks(locks, count)
    if not locked:
        return base
    usable = float(inner) - n * float(thickness)
    locked_sum = sum(locked.values())
    free_idx = [i for i in range(count) if i not in locked]
    if locked_sum > usable - 8.0 * len(free_idx) + 1e-6:
        raise ValueError("locked cells leave other cells under 8 mm")
    remaining = usable - locked_sum
    free_w = remaining / len(free_idx) if free_idx else 0.0
    if free_idx and free_w < 8.0 - 1e-6:
        raise ValueError("locked cells leave other cells under 8 mm")
    cells = []
    for i in range(count):
        cells.append(round(locked[i] if i in locked else free_w, 3))
    return cells


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

    locks_x = body.get("locked_cells_x") if isinstance(body.get("locked_cells_x"), dict) else None
    locks_y = body.get("locked_cells_y") if isinstance(body.get("locked_cells_y"), dict) else None

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
        sx = cells_with_locks(xi, dx, thickness, locks_x) if dx else [xi]

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
        sy = cells_with_locks(yi, dy, thickness, locks_y) if dy else [yi]

    handle = bool(body.get("handle", lid_raw in {"removable", "sliding", "hinged", "door", "double_door"}))
    if "handle" in body and body.get("handle") in (False, 0, "0", "false", "off", "no"):
        handle = False
    handle_w = _f(body.get("handle_w"), min(40.0, xi * 0.35))
    handle_h = _f(body.get("handle_h"), min(20.0, yi * 0.25))
    lid_r = max(0.0, _f(body.get("lid_radius") or body.get("corner_radius"), 0))

    lid_value: Any = False
    if lid_raw == "open":
        lid_value = False
    elif lid_raw in {"finger", "finger_joint", "fixed"}:
        lid_value = {"type": "finger_joint"}
    elif lid_raw in {"removable", "drop", "friction"}:
        lid_value = {
            "type": "removable",
            "handle": handle,
            "handle_w": handle_w,
            "handle_h": handle_h,
            "radius": lid_r,
        }
    elif lid_raw in {"sliding", "slide"}:
        lid_value = {
            "type": "sliding",
            "handle": handle,
            "handle_w": handle_w,
            "handle_h": handle_h,
            "radius": lid_r,
        }
    elif lid_raw in {"hinged", "door", "single_door"}:
        lid_value = {
            "type": "hinged",
            "doors": 1,
            "handle": handle,
            "handle_w": handle_w,
            "handle_h": handle_h,
            "radius": lid_r,
        }
    elif lid_raw in {"double_door", "two_door", "double"}:
        lid_value = {
            "type": "hinged",
            "doors": 2,
            "handle": handle,
            "handle_w": handle_w / 2,
            "handle_h": handle_h,
            "radius": lid_r,
        }
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
    bump_d = _f(body.get("bump_diameter") or body.get("bump_d"), 0.5)

    shelves = _i(body.get("shelves") or body.get("araf"), 0, lo=0, hi=6)
    # Usable inner height for shelf spacing (below lid / above raised floor)
    lid_eat = 0.0 if lid_raw == "open" else thickness
    shelf_span = hi - raised - lid_eat
    if shelves and shelf_span < (shelves + 1) * 12:
        raise ValueError("too many shelves for this box height — reduce shelves or grow H")

    drawers_flag = body.get("drawers")
    if drawers_flag is None:
        # Auto: produce drawers when there is a bay grid (shelves and/or X dividers).
        make_drawers = bool(shelves > 0 or dx > 0)
    else:
        make_drawers = bool(drawers_flag)
    drawer_clearance = _f(body.get("drawer_clearance") or body.get("drawer_play"), 1.0)
    cell_h = drawer_cell_heights(hi, raised, shelves, thickness, lid_eat)
    drawer_specs = (
        build_drawer_specs(
            sx=sx,
            sy=sy,
            cell_heights=cell_h,
            thickness=thickness,
            clearance=drawer_clearance,
            pull_r=_f(body.get("drawer_pull_r"), 0) or None,
        )
        if make_drawers
        else []
    )

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
        "shelves": shelves,
        "drawers": make_drawers,
        "drawer_specs": drawer_specs,
        "drawer_clearance": drawer_clearance,
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
        "shelves": shelves,
        "sx": sx,
        "sy": sy,
        "divider_x_pos": divider_positions(sx, thickness) if dx else [],
        "divider_y_pos": divider_positions(sy, thickness) if dy else [],
        "locked_cells_x": locks_x or {},
        "locked_cells_y": locks_y or {},
        "cell_heights_mm": cell_h,
        "drawers": make_drawers,
        "drawer_count": len(drawer_specs),
        "drawer_clearance_mm": round(drawer_clearance, 3),
        "drawers_mm": [
            {
                "id": d["id"],
                "cell": f"c{d['col']+1}-y{d['row_y']+1}-z{d['row_z']+1}",
                "w": d["w_mm"],
                "d": d["d_mm"],
                "h": d["h_mm"],
                "pull_r": d["pull_r_mm"],
                "label": d["label_mm"],
            }
            for d in drawer_specs
        ],
        "finger_mult": round(finger_mult, 3),
        "press_fit": press_fit,
        "handle": handle,
        "handle_w_mm": handle_w,
        "lid_radius_mm": lid_r,
    }

    parameters: dict[str, Any] = {
        "thickness": thickness,
        "project": str(body.get("project") or body.get("name") or "studio-box"),
        "material": str(body.get("material") or "poplar_3mm"),
        "machine": str(body.get("machine") or "payas_workshop"),
        "what_you_see": "studio parametric finger-joint box",
        "FingerJoint_finger": finger_mult,
        "FingerJoint_space": finger_mult,
        "FingerJoint_style": "springs" if press_fit else "rectangular",
        "FingerJoint_play": max(0.0, min(0.4, play)),
    }
    if body.get("nest_gap_mm") not in (None, ""):
        try:
            parameters["nest_gap_mm"] = max(2.0, min(30.0, float(body.get("nest_gap_mm"))))
        except (TypeError, ValueError):
            pass
    if press_fit:
        parameters["FingerJoint_surround"] = max(0.1, min(2.0, bump_d))

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

    guide = build_assembly_guide(box, summary)
    summary["assembly_guide"] = guide
    summary["assembly_order"] = guide["assembly_order"]

    return {
        "primitives": [box],
        "parameters": parameters,
        "summary": summary,
        "assembly_guide": guide,
    }


def build_assembly_guide(box: dict[str, Any], summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Topological digital assembly order + declared finger mates for Studio.

    Physical dry-fit stays NOT_VERIFIED. No self-connections. No invented PASS.
    """
    summary = summary or {}
    lid_raw = str(summary.get("lid") or "open").lower()
    dx = int(box.get("dividers_x") or 0)
    dy = int(box.get("dividers_y") or 0)
    shelves = int(box.get("shelves") or 0)
    joint_walls = bool(box.get("divider_joint_walls", True))
    joint_bottom = bool(box.get("divider_joint_bottom", True))
    lid_value = box.get("lid")
    raised = float(box.get("bottom_lift") or 0)

    titles = {
        "bottom": ("Taban", "Tabanı düz koy; duvar finger’ları buraya oturur."),
        "front": ("Ön duvar", "Ön paneli tabana finger-joint ile oturt."),
        "back": ("Arka duvar", "Arka paneli tabana finger-joint ile oturt."),
        "left": ("Sol duvar", "Sol paneli taban + ön/arka köşelerine oturt."),
        "right": ("Sağ duvar", "Sağ paneli taban + ön/arka köşelerine oturt."),
        "lid": ("Kapak", "Kapağı tipine göre yerleştir (finger / sürtünme / menteşe / kayar)."),
        "lid-left": ("Sol kapı", "Sol kapı kanadını menteşe kenarına oturt."),
        "lid-right": ("Sağ kapı", "Sağ kapı kanadını menteşe kenarına oturt."),
    }

    connections: list[dict[str, Any]] = []
    conn_n = 0

    def add_conn(
        a: str,
        b: str,
        *,
        joint_type: str = "finger_joint",
        edge_hint: str = "",
        gender_a: str = "male",
        gender_b: str = "female",
        note: str = "",
    ) -> str:
        nonlocal conn_n
        if a == b:
            raise ValueError(f"self-connection forbidden: {a}")
        forbidden = {
            frozenset({"top", "bottom"}),
            frozenset({"lid", "bottom"}),
            frozenset({"front", "front"}),
            frozenset({"back", "back"}),
            frozenset({"left", "left"}),
            frozenset({"right", "right"}),
        }
        if frozenset({a, b}) in forbidden:
            raise ValueError(f"forbidden connection: {a}↔{b}")
        conn_n += 1
        cid = f"G{conn_n:02d}"
        connections.append(
            {
                "connection_id": cid,
                "part_a": a,
                "part_b": b,
                "joint_type": joint_type,
                "edge_hint": edge_hint,
                "gender_a": gender_a,
                "gender_b": gender_b,
                "digital_status": "DECLARED",
                "physical_fit": "NOT_VERIFIED",
                "note": note or f"{a} ↔ {b} ({joint_type})",
            }
        )
        return cid

    # Structural walls ↔ bottom + corners
    for wall, hint in (
        ("front", "bottom↔front"),
        ("back", "bottom↔back"),
        ("left", "bottom↔left"),
        ("right", "bottom↔right"),
    ):
        add_conn(
            "bottom",
            wall,
            edge_hint=hint,
            gender_a="female" if raised > 0.05 else "female",
            gender_b="male",
            note="raised-bottom slot" if raised > 0.05 else "finger joint floor",
        )
    for a, b, hint in (
        ("front", "left", "front↔left corner"),
        ("front", "right", "front↔right corner"),
        ("back", "left", "back↔left corner"),
        ("back", "right", "back↔right corner"),
    ):
        add_conn(a, b, edge_hint=hint)

    order: list[str] = ["bottom", "front", "back", "left", "right"]

    for i in range(1, dx + 1):
        pid = f"divider-x-{i}"
        order.append(pid)
        titles[pid] = (f"X bölücü {i}", "Dikey X bölücüyü taban/duvar yuvalarına oturt.")
        if joint_bottom:
            add_conn(pid, "bottom", joint_type="finger_slot", edge_hint="divider→bottom", gender_a="male", gender_b="female")
        if joint_walls:
            add_conn(pid, "front", joint_type="finger_slot", edge_hint="divider→front", gender_a="male", gender_b="female")
            add_conn(pid, "back", joint_type="finger_slot", edge_hint="divider→back", gender_a="male", gender_b="female")

    for i in range(1, dy + 1):
        pid = f"divider-y-{i}"
        order.append(pid)
        titles[pid] = (f"Y bölücü {i}", "Dikey Y bölücüyü taban/duvar yuvalarına oturt; X ile cross-lap.")
        if joint_bottom:
            add_conn(pid, "bottom", joint_type="finger_slot", edge_hint="divider→bottom", gender_a="male", gender_b="female")
        if joint_walls:
            add_conn(pid, "left", joint_type="finger_slot", edge_hint="divider→left", gender_a="male", gender_b="female")
            add_conn(pid, "right", joint_type="finger_slot", edge_hint="divider→right", gender_a="male", gender_b="female")
        if dx > 0:
            for xi in range(1, dx + 1):
                add_conn(
                    pid,
                    f"divider-x-{xi}",
                    joint_type="cross_lap",
                    edge_hint="X∩Y half-slot",
                    gender_a="slot_top",
                    gender_b="slot_bottom",
                    note="cross-lap half-slot",
                )

    for i in range(1, shelves + 1):
        pid = f"shelf-{i}"
        order.append(pid)
        titles[pid] = (f"Ara raf {i}", "Yatay rafı duvar finger yuvalarına kaydır.")
        for wall in ("front", "back", "left", "right"):
            add_conn(pid, wall, joint_type="finger_slot", edge_hint=f"shelf→{wall}", gender_a="male", gender_b="female")

    lid_parts: list[str] = []
    if lid_raw != "open" and lid_value:
        doors = 1
        if isinstance(lid_value, dict):
            doors = int(lid_value.get("doors") or 1)
            lid_type = str(lid_value.get("type") or "finger_joint").lower()
        else:
            lid_type = "finger_joint"
        if lid_type == "hinged" and doors >= 2:
            lid_parts = ["lid-left", "lid-right"]
        else:
            lid_parts = ["lid"]
        for pid in lid_parts:
            order.append(pid)
            if lid_type in {"finger", "finger_joint", "fixed"}:
                for wall in ("front", "back", "left", "right"):
                    add_conn(pid, wall, joint_type="finger_joint", edge_hint=f"lid↔{wall}")
            elif lid_type in {"sliding", "slide"}:
                add_conn(pid, "left", joint_type="slide_rail", edge_hint="lid↔left rail", gender_a="male", gender_b="female")
                add_conn(pid, "right", joint_type="slide_rail", edge_hint="lid↔right rail", gender_a="male", gender_b="female")
            elif lid_type == "hinged":
                add_conn(pid, "back", joint_type="hinge", edge_hint="lid↔back hinge", gender_a="male", gender_b="female")
            else:
                # removable / friction — declared seat, not a locked finger
                for wall in ("front", "back", "left", "right"):
                    add_conn(
                        pid,
                        wall,
                        joint_type="friction_seat",
                        edge_hint=f"lid seat {wall}",
                        gender_a="male",
                        gender_b="female",
                        note="removable friction seat",
                    )

    joins_by_part: dict[str, list[str]] = {p: [] for p in order}
    for c in connections:
        for p in (c["part_a"], c["part_b"]):
            if p in joins_by_part:
                joins_by_part[p].append(c["connection_id"])

    steps: list[dict[str, Any]] = []
    for i, pid in enumerate(order, 1):
        title, detail = titles.get(pid, (pid, f"{pid} panelini yerleştir."))
        steps.append(
            {
                "step": i,
                "part_id": pid,
                "title_tr": title,
                "detail_tr": detail,
                "joins": joins_by_part.get(pid, []),
            }
        )

    speak_bits = [f"{s['step']}) {s['title_tr']}" for s in steps]
    speak = "Montaj sırası (dijital): " + " → ".join(speak_bits) + ". Fiziksel dry-fit NOT_VERIFIED."

    return {
        "assembly_order": order,
        "steps": steps,
        "connections": connections,
        "speak": speak,
        "physical_assembly": "NOT_VERIFIED",
        "digital_status": "DECLARED",
        "self_connection_count": 0,
        "forbidden_connection_count": 0,
        "connection_count": len(connections),
        "step_count": len(steps),
    }


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
