"""Minimum parametric repair. Do not rewrite the product. Do not invent parts the photo did not need."""

from __future__ import annotations

import copy
from typing import Any

from assembly import apply_roof_lock
from boxes_adapter import PAYAS_DEFAULTS

_T = float(PAYAS_DEFAULTS["thickness"])


def _kind(part: dict[str, Any]) -> str:
    return str(part.get("type") or part.get("kind") or "").strip().lower()


def _num(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def _label(part: dict[str, Any]) -> str:
    return str(part.get("label") or part.get("type") or "").lower()


def _box(parts: list[dict[str, Any]]) -> dict[str, Any] | None:
    return next((p for p in parts if _kind(p) == "box"), None)


def _wall(box: dict[str, Any], name: str) -> dict[str, Any]:
    walls = box.setdefault("walls", {})
    if not isinstance(walls, dict):
        walls = {}
        box["walls"] = walls
    face = walls.setdefault(name, {})
    if not isinstance(face, dict):
        face = {}
        walls[name] = face
    face.setdefault("holes", [])
    face.setdefault("slots", [])
    return face


def _gables(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [p for p in parts if _kind(p) in {"triangle", "gable"}]


def _gable_n(parts: list[dict[str, Any]]) -> int:
    return sum(max(1, int(p.get("count") or p.get("n") or 1)) for p in _gables(parts))


def _roofs(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found = []
    for p in parts:
        if _kind(p) not in {"panel", "wall", "rect", "roof", "roof_panel"}:
            continue
        if "roof" in _label(p) or _kind(p) in {"roof", "roof_panel"}:
            found.append(p)
    return found


def _props(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from mechanisms import mechanism_type
    out = []
    for p in parts:
        semantic=mechanism_type(p)
        if semantic in {"propeller", "rotor"}:
            out.append(p)
        elif semantic is None and _kind(p) in {"disc", "disk"} and (p.get("blades") or "prop" in _label(p) or "pervane" in _label(p)):
            out.append(p)
    return out


def repair_primitives(primitives: list[Any] | None, review: dict[str, Any] | None = None) -> tuple[list[Any], list[dict[str, Any]]]:
    """Return repaired primitives and the list of actions taken. Empty actions = cannot repair further."""
    parts: list[Any] = copy.deepcopy(list(primitives or []))
    if (review or {}).get('canonical_mates',{}).get('active'):
        # Connector failures require a targeted edit with renewed geometric
        # evidence. Legacy product-wide heuristics must not move locked mates.
        return parts, []
    actions: list[dict[str, Any]] = []
    looks = " ".join(str(x) for x in (review or {}).get("look_again") or [])
    looks += " " + " ".join(
        str(n)
        for cat in ((review or {}).get("categories") or {}).values()
        for n in (cat.get("notes") or [])
    )

    for part in parts:
        if not isinstance(part, dict):
            continue
        from mechanisms import mechanism_type
        semantic=mechanism_type(part)
        if semantic not in {"wheel","road_roller_drum","pulley","gear","disc","flywheel"} and _kind(part) in {"disc", "disk"} and (part.get("blades") or "prop" in _label(part) or "pervane" in _label(part)):
            part["type"] = "propeller"
            part.setdefault("blades", int(part.get("blades") or 4))
            actions.append({"fix": "disc_to_propeller", "part": _label(part)})

    box = _box([p for p in parts if isinstance(p, dict)])
    dict_parts = [p for p in parts if isinstance(p, dict)]

    if box and _roofs(dict_parts) and _gable_n(dict_parts) < 2:
        bx = _num(box.get("x") or box.get("w"), 80)
        by = _num(box.get("y") or box.get("d"), 80)
        existing = _gables(dict_parts)
        if existing:
            existing[0]["count"] = 2
            actions.append({"fix": "gable_count_2", "part": existing[0].get("label") or "gable"})
        else:
            parts.append(
                {
                    "type": "triangle",
                    "w": bx,
                    "h": round(max(18.0, by * 0.42), 1),
                    "count": 2,
                    "label": "roof-support",
                }
            )
            actions.append({"fix": "add_gables", "count": 2})
        dict_parts = [p for p in parts if isinstance(p, dict)]

    before_lock = _snapshot(parts)
    parts, locks = apply_roof_lock(parts)
    if locks and _snapshot(parts) != before_lock:
        actions.append({"fix": "roof_fingerjoint_lock", "locks": len(locks)})

    box = _box([p for p in parts if isinstance(p, dict)])
    dict_parts = [p for p in parts if isinstance(p, dict)]

    if box:
        bx = _num(box.get("x") or box.get("w"), 80)
        bh = _num(box.get("h"), 80)
        front = _wall(box, "front")
        back = _wall(box, "back")
        props = _props(dict_parts)

        def _holes(face: dict[str, Any]) -> list[dict[str, Any]]:
            raw = face.get("holes") or []
            return [h for h in raw if isinstance(h, dict)]

        fh = _holes(front)
        bh_holes = _holes(back)
        if fh and not bh_holes:
            back["holes"] = copy.deepcopy(fh)
            actions.append({"fix": "copy_front_shaft_to_back"})
            bh_holes = _holes(back)
        if bh_holes and not fh:
            front["holes"] = copy.deepcopy(bh_holes)
            actions.append({"fix": "copy_back_shaft_to_front"})
            fh = _holes(front)

        shaft_d = 4.0
        shaft_y = None
        if fh:
            shaft_d = _num(fh[0].get("d") or fh[0].get("diameter"), 4.0)
            shaft_y = _num(fh[0].get("y") or fh[0].get("cy"), bh * 0.88)

        if props and not fh:
            cx = round(bx / 2, 1)
            y = round(bh * 0.88, 1)
            front.setdefault("holes", []).append({"x": cx, "y": y, "d": 4.0})
            back.setdefault("holes", []).append({"x": cx, "y": y, "d": 4.0})
            actions.append({"fix": "add_coaxial_shaft_holes", "d": 4.0, "y": y})
            fh = _holes(front)
            shaft_d = 4.0
            shaft_y = y

        for prop in props:
            hole = _num(prop.get("hole") or prop.get("shaft"), 0)
            if hole <= 0:
                prop["hole"] = shaft_d
                actions.append({"fix": "propeller_shaft_hole", "d": shaft_d})
                hole = shaft_d
            elif abs(hole - shaft_d) > 0.15 and fh:
                prop["hole"] = shaft_d
                actions.append({"fix": "match_propeller_to_wall_shaft", "d": shaft_d})
            diameter = _num(prop.get("d") or prop.get("diameter"), 80)
            if shaft_y is not None and diameter / 2.0 > shaft_y - _T - 1:
                need = diameter / 2.0 + _T + 2.0
                if need < bh - _T - shaft_d / 2:
                    for face in (front, back):
                        for h in _holes(face):
                            if abs(_num(h.get("d"), shaft_d) - shaft_d) <= 0.2:
                                h["y"] = round(need, 1)
                    actions.append({"fix": "raise_shaft_for_rotor_clearance", "y": round(need, 1)})
                    shaft_y = need
                else:
                    new_d = max(20.0, (shaft_y - _T - 2.0) * 2.0)
                    if new_d < diameter:
                        prop["d"] = round(new_d, 1)
                        actions.append({"fix": "shrink_rotor_to_clear_floor", "d": round(new_d, 1)})

        existing_walls = box.get("walls") if isinstance(box.get("walls"), dict) else {}
        for face_name, face in list(existing_walls.items()):
            if not isinstance(face, dict):
                continue
            wall_w = bx if face_name in {"front", "back"} else _num(box.get("y") or box.get("d"), 80)
            wall_h = bh
            for hole in _holes(face):
                d = _num(hole.get("d") or hole.get("diameter"), 0)
                if d <= 0:
                    continue
                pad = d / 2.0 + 1.5
                x = _num(hole.get("x") or hole.get("cx"), wall_w / 2)
                y = _num(hole.get("y") or hole.get("cy"), wall_h / 2)
                nx = min(max(x, pad), max(pad, wall_w - pad))
                ny = min(max(y, pad), max(pad, wall_h - pad))
                if abs(nx - x) > 0.2 or abs(ny - y) > 0.2:
                    hole["x"] = round(nx, 2)
                    hole["y"] = round(ny, 2)
                    actions.append({"fix": "clamp_hole_inside_wall", "wall": face_name})
            for slot in list(face.get("slots") or []):
                if not isinstance(slot, dict):
                    continue
                sw = _num(slot.get("w") or slot.get("dx"))
                sh = _num(slot.get("h") or slot.get("dy"))
                thin = min(sw, sh) if sw and sh else 0
                if 0 < thin <= _T + 1.2 and abs(thin - _T) > 0.35:
                    if sw <= sh:
                        slot["w"] = _T
                    else:
                        slot["h"] = _T
                    actions.append({"fix": "snap_tab_slot_to_thickness", "wall": face_name})

    for part in dict_parts:
        if _kind(part) not in {"panel", "wall", "rect", "solar", "motor_mount"}:
            continue
        if "roof" in _label(part):
            continue
        edges = str(part.get("edges") or "eeee")
        if "f" in edges.lower() and ("solar" in _label(part) or "motor" in _label(part)):
            part["edges"] = "eeee"
            actions.append({"fix": "clear_unmated_panel_fingers", "part": _label(part)})

    seen: list[str] = []
    uniq: list[dict[str, Any]] = []
    for act in actions:
        key = str(act)
        if key in seen:
            continue
        seen.append(key)
        uniq.append(act)
    return parts, uniq


def _snapshot(parts: list[Any]) -> str:
    import json

    return json.dumps(parts, sort_keys=True, default=str)
