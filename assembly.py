"""Mechanical fit + nominal assembly check from toolbox primitives. No new kit tools."""

from __future__ import annotations

import math
from typing import Any

from boxes_adapter import PAYAS_DEFAULTS

_EDGE = "bottom", "right", "top", "left"


def _kind(part: dict[str, Any]) -> str:
    return str(part.get("type") or part.get("kind") or "").strip().lower()


def _num(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def _count(part: dict[str, Any]) -> int:
    return max(1, min(20, int(part.get("count") or part.get("n") or 1)))


def _round(length: float) -> float:
    return round(float(length), 2)


def _features(part: dict[str, Any]) -> dict[str, list]:
    raw = part if isinstance(part, dict) else {}
    return {
        "holes": list(raw.get("holes") or []),
        "slots": list(raw.get("slots") or raw.get("rect_holes") or []),
        "finger_holes": list(raw.get("finger_holes") or []),
    }


def _inside(x: float, y: float, w: float, h: float, pad: float) -> bool:
    return pad <= x <= w - pad and pad <= y <= h - pad


def _circle_hits_rect(cx: float, cy: float, r: float, rx: float, ry: float, rw: float, rh: float) -> bool:
    nearest_x = min(max(cx, rx - rw / 2.0), rx + rw / 2.0)
    nearest_y = min(max(cy, ry - rh / 2.0), ry + rh / 2.0)
    return (cx - nearest_x) ** 2 + (cy - nearest_y) ** 2 < (r + 0.5) ** 2


def expand_faces(primitives: list[Any]) -> list[dict[str, Any]]:
    """Flatten box walls and counted parts into named faces for matching."""
    faces: list[dict[str, Any]] = []
    for part in primitives or []:
        if not isinstance(part, dict):
            continue
        kind = _kind(part)
        n = _count(part)
        if kind == "box":
            x = _num(part.get("x") or part.get("w"), 80)
            y = _num(part.get("y") or part.get("d") or part.get("depth"), 80)
            h = _num(part.get("h"), 80)
            top = str(part.get("top") or "e")[:1]
            bottom_on = bool(part.get("bottom", True))
            lid_on = bool(part.get("lid", False))
            gable_top = bool(part.get("gable_top") or part.get("lock_roof"))
            b = "F" if bottom_on else "e"
            wall_top = "F" if gable_top else top
            side_top = "e" if gable_top else top
            walls = part.get("walls") if isinstance(part.get("walls"), dict) else {}
            faces.append(
                {"name": "front", "kind": "wall", "w": x, "h": h, "edges": f"{b}F{wall_top}F", "features": _features(walls.get("front") or {})}
            )
            faces.append(
                {"name": "back", "kind": "wall", "w": x, "h": h, "edges": f"{b}F{wall_top}F", "features": _features(walls.get("back") or {})}
            )
            if bottom_on:
                faces.append(
                    {"name": "bottom", "kind": "floor", "w": x, "h": y, "edges": "ffff", "features": _features(walls.get("bottom") or {})}
                )
            faces.append(
                {"name": "left", "kind": "wall", "w": y, "h": h, "edges": f"{b}f{side_top}f", "features": _features(walls.get("left") or {})}
            )
            faces.append(
                {"name": "right", "kind": "wall", "w": y, "h": h, "edges": f"{b}f{side_top}f", "features": _features(walls.get("right") or {})}
            )
            if lid_on:
                faces.append(
                    {
                        "name": "lid",
                        "kind": "floor",
                        "w": x,
                        "h": y,
                        "edges": "ffff" if top in "fF" else "eeee",
                        "features": _features(walls.get("top") or walls.get("lid") or {}),
                    }
                )
            continue
        label = str(part.get("label") or kind or "part")
        for i in range(n):
            name = label if n == 1 else f"{label}-{i + 1}"
            if kind in {"panel", "wall", "rect", "roof", "roof_panel", "motor_mount", "motor_plate", "mount_plate", "solar", "solar_panel", "carrier", "tray", "support", "brace"}:
                faces.append(
                    {
                        "name": name,
                        "kind": "panel",
                        "w": _num(part.get("w") or part.get("x"), 80),
                        "h": _num(part.get("h") or part.get("y") or part.get("length"), 80),
                        "edges": str(part.get("edges") or part.get("edge") or "eeee")[:4].ljust(4, "e"),
                        "features": _features(part),
                    }
                )
            elif kind in {"triangle", "gable"}:
                faces.append(
                    {
                        "name": name,
                        "kind": "gable",
                        "w": _num(part.get("w") or part.get("x"), 80),
                        "h": _num(part.get("h") or part.get("rise"), 30),
                        "edges": str(part.get("edges") or "eee")[:3],
                        "features": _features(part),
                    }
                )
            elif kind in {"propeller", "pervane", "blades", "fan", "cross", "plus"}:
                faces.append(
                    {
                        "name": name,
                        "kind": "propeller",
                        "d": _num(part.get("d") or part.get("diameter"), 80),
                        "hole": _num(part.get("hole") or part.get("shaft"), 4),
                        "blades": int(part.get("blades") or 4),
                        "features": _features(part),
                    }
                )
            elif kind in {"disc", "disk", "circle", "washer", "spacer", "shaft", "axle", "adapter", "washer_plate"}:
                faces.append(
                    {
                        "name": name,
                        "kind": "disc",
                        "d": _num(part.get("d") or part.get("diameter") or part.get("w"), 40),
                        "hole": _num(part.get("hole") or part.get("shaft"), 0),
                        "features": _features(part),
                    }
                )
            elif kind in {"polygon", "contour", "outline", "polyline"}:
                faces.append({"name": name, "kind": "contour", "features": _features(part), "hole": _num(part.get("hole"), 0)})
            elif kind in {"coupon", "kerf_test", "burn_test", "kerf"}:
                faces.append({"name": name, "kind": "coupon", "w": _num(part.get("x") or part.get("w"), 40), "h": 12, "edges": "", "features": _features(part)})
    return faces


def _edge_length(face: dict[str, Any], index: int) -> float:
    w, h = float(face.get("w") or 0), float(face.get("h") or 0)
    if face.get("kind") == "gable":
        if index == 0:
            return w
        if index == 1:
            return h
        return round(math.hypot(w, h), 2)
    return w if index % 2 == 0 else h


def apply_roof_lock(primitives: list[Any] | None) -> tuple[list[Any], list[dict[str, Any]]]:
    """Put Boxes.py FingerJoint on gable↔wall and roof↔hypotenuse so the roof actually locks."""
    parts: list[Any] = [dict(p) if isinstance(p, dict) else p for p in (primitives or [])]
    locks: list[dict[str, Any]] = []
    box = next((p for p in parts if isinstance(p, dict) and _kind(p) == "box"), None)
    gables = [p for p in parts if isinstance(p, dict) and _kind(p) in {"triangle", "gable"}]
    roofs = [
        p
        for p in parts
        if isinstance(p, dict)
        and _kind(p) in {"panel", "wall", "rect", "roof", "roof_panel"}
        and "roof" in str(p.get("label") or p.get("type") or "").lower()
    ]
    if not box or not gables:
        return parts, locks
    bx = _num(box.get("x") or box.get("w"), 80)
    by = _num(box.get("y") or box.get("d"), 80)
    box["gable_top"] = True
    box["top"] = "F"
    rise = max(_num(g.get("h") or g.get("rise"), 24) for g in gables)
    slope = round(math.hypot(bx, rise), 2)
    for gable in gables:
        gable["w"] = bx
        gable["h"] = _num(gable.get("h") or gable.get("rise"), rise)
        gable["edges"] = "feF" if roofs else "fee"
        locks.append(
            {
                "joint": "gable-to-wall",
                "via": "Boxes.py FingerJoint: gable bottom f into front/back top F",
                "length_mm": bx,
                "result": "LOCK",
            }
        )
    n_roofs = sum(max(1, int(r.get("count") or r.get("n") or 1)) for r in roofs)
    for roof in roofs:
        roof["w"] = slope
        roof["h"] = max(_num(roof.get("h") or roof.get("y"), by), by)
        roof["edges"] = "fefe" if n_roofs == 1 else "feee"
        locks.append(
            {
                "joint": "roof-to-gable",
                "via": "Boxes.py FingerJoint: roof f into gable hypotenuse F",
                "length_mm": slope,
                "result": "LOCK",
            }
        )
    return parts, locks


def _check_seating(
    errors: list[str],
    warnings: list[str],
    bx: float,
    by: float,
    t: float,
    gables: list[dict[str, Any]],
    roofs: list[dict[str, Any]],
    props: list[dict[str, Any]],
    front: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Require FingerJoint lock, not just overlapping bounding boxes."""
    roof_lock: list[dict[str, Any]] = []
    if roofs and len(gables) < 2:
        errors.append("pitched roof needs 2 gables locked to front/back top F (got fewer)")
    for gable in gables:
        edges = str(gable.get("edges") or "eee")
        if abs(float(gable["w"]) - bx) > 2.0:
            errors.append(f"gable {gable['name']} width {gable['w']} mm must equal box x={bx} mm to lock")
        if not edges or edges[0] != "f":
            errors.append(f"gable {gable['name']} bottom must be f to lock into the wall top F")
        else:
            roof_lock.append(
                {
                    "joint": "gable-to-wall",
                    "part": gable["name"],
                    "result": "LOCK",
                    "via": "FingerJoint f/F",
                    "length_mm": bx,
                }
            )
        if roofs and (len(edges) < 3 or edges[2] != "F"):
            errors.append(f"gable {gable['name']} hypotenuse must be F so the roof can lock")
    slope = math.hypot(bx, max((float(g["h"]) for g in gables), default=0.0)) if gables else 0.0
    for roof in roofs:
        edges = str(roof.get("edges") or "eeee")
        if "f" not in edges:
            errors.append(f"roof {roof['name']} needs an f edge to lock into the gable hypotenuse F")
        else:
            roof_lock.append(
                {
                    "joint": "roof-to-gable",
                    "part": roof["name"],
                    "result": "LOCK",
                    "via": "FingerJoint f/F",
                    "length_mm": round(slope, 2),
                }
            )
        dims = sorted([float(roof["w"]), float(roof["h"])])
        if slope and dims[1] < slope - 8:
            warnings.append(f"roof {roof['name']} may be short of gable slope {slope:.1f} mm")
        if dims[0] < by - 8:
            warnings.append(f"roof {roof['name']} may not cover depth {by} mm")
    if front and props:
        holes = front.get("features") or {}
        for hole in holes.get("holes") or []:
            y = _num(hole.get("y") or hole.get("cy"), 0)
            d = _num(hole.get("d") or hole.get("diameter"), 0)
            if d <= 0:
                continue
            for prop in props:
                radius = float(prop.get("d") or 0) / 2.0
                if radius > y - t - 1:
                    errors.append(
                        f"{prop['name']} radius {radius} mm would hit the floor from shaft height y={y} mm"
                    )
    return roof_lock


def check_assembly(
    primitives: list[Any] | None,
    thickness: float | None = None,
    burn: float | None = None,
) -> dict[str, Any]:
    """Return mechanical pairs, shaft/slot fit, and a nominal assembly sequence."""
    t = float(thickness if thickness is not None else PAYAS_DEFAULTS["thickness"])
    kerf = float(burn if burn is not None else PAYAS_DEFAULTS["burn"])
    errors: list[str] = []
    warnings: list[str] = []
    joints: list[dict[str, Any]] = []
    shaft_pairs: list[dict[str, Any]] = []
    faces = expand_faces(primitives or [])
    if not faces:
        return {
            "ok": False,
            "look_again": ["Pass box/panel/disc/triangle/propeller primitives to assemble."],
            "warnings": [],
            "joints": [],
            "roof_lock": [],
            "shaft_pairs": [],
            "assembled_mm": None,
            "sequence": [],
            "thickness": t,
            "burn": kerf,
        }

    males: list[tuple[str, int, float]] = []
    females: list[tuple[str, int, float]] = []
    for face in faces:
        edges = str(face.get("edges") or "")
        if len(edges) < 3:
            continue
        for i, ch in enumerate(edges[:4]):
            length = _round(_edge_length(face, i))
            if ch == "f":
                males.append((face["name"], i, length))
            elif ch == "F":
                females.append((face["name"], i, length))

    used_f: set[int] = set()
    used_m: set[int] = set()
    for fi, (fn, fe, fl) in enumerate(females):
        hit = None
        for mi, (mn, me, ml) in enumerate(males):
            if mi in used_m:
                continue
            if abs(fl - ml) <= 0.05:
                hit = mi
                break
        if hit is None:
            errors.append(f"female edge {fn}.{_EDGE[fe] if fe < 4 else fe} ({fl} mm) has no matching f fingers")
            continue
        mn, me, ml = males[hit]
        used_m.add(hit)
        used_f.add(fi)
        joints.append(
            {
                "female": fn,
                "female_edge": _EDGE[fe] if fe < 4 else fe,
                "male": mn,
                "male_edge": _EDGE[me] if me < 4 else me,
                "length_mm": fl,
                "result": "MATCH",
                "via": "Boxes.py FingerJoint (same length, f/F)",
            }
        )
    for mi, (mn, me, ml) in enumerate(males):
        if mi not in used_m:
            errors.append(f"male edge {mn}.{_EDGE[me] if me < 4 else me} ({ml} mm) has no matching F holes")

    walls = [f for f in faces if f.get("kind") == "wall"]
    for face in walls:
        w, h = float(face["w"]), float(face["h"])
        pad = t + 2.0
        for hole in face["features"]["holes"]:
            x = _num(hole.get("x") or hole.get("cx"), 0)
            y = _num(hole.get("y") or hole.get("cy"), 0)
            d = _num(hole.get("d") or hole.get("diameter") or ((hole.get("r") or 0) * 2), 0)
            if d <= 0:
                continue
            if not _inside(x, y, w, h, d / 2 + 1.5):
                errors.append(f"hole on {face['name']} at {x},{y} d={d} leaves the wall")
            if y < t + d / 2 or y > h - t - d / 2:
                warnings.append(f"hole on {face['name']} is close to a finger edge")
        for slot in face["features"]["slots"]:
            x = _num(slot.get("x") or slot.get("cx"), 0)
            y = _num(slot.get("y") or slot.get("cy"), 0)
            sw = _num(slot.get("w") or slot.get("dx"), 0)
            sh = _num(slot.get("h") or slot.get("dy"), 0)
            if sw <= 0 or sh <= 0:
                continue
            thin = min(sw, sh)
            if thin <= t + 0.6:
                if abs(thin - t) > 0.35:
                    errors.append(
                        f"tab-slot on {face['name']} is {thin:.2f} mm thick; 3 mm plywood + kerf {kerf} needs ~{t:.1f} mm"
                    )
                else:
                    joints.append(
                        {
                            "female": face["name"],
                            "kind": "tab-slot",
                            "size_mm": [sw, sh],
                            "result": "MATCH",
                            "via": "slot ≈ material thickness",
                        }
                    )
            if not _inside(x, y, w, h, max(sw, sh) / 2 + 1.0):
                errors.append(f"slot on {face['name']} at {x},{y} {sw}×{sh} leaves the wall")
        for hole in face["features"]["holes"]:
            hx = _num(hole.get("x") or hole.get("cx"), 0)
            hy = _num(hole.get("y") or hole.get("cy"), 0)
            hd = _num(hole.get("d") or hole.get("diameter") or ((hole.get("r") or 0) * 2), 0)
            if hd <= 0:
                continue
            for slot in face["features"]["slots"]:
                sx = _num(slot.get("x") or slot.get("cx"), 0)
                sy = _num(slot.get("y") or slot.get("cy"), 0)
                sw = _num(slot.get("w") or slot.get("dx"), 0)
                sh = _num(slot.get("h") or slot.get("dy"), 0)
                if sw <= 0 or sh <= 0:
                    continue
                if _circle_hits_rect(hx, hy, hd / 2.0, sx, sy, sw, sh):
                    errors.append(
                        f"shaft/window clash on {face['name']}: hole at {hx},{hy} d={hd} sits inside slot {sw}×{sh} at {sx},{sy}"
                    )

    front = next((f for f in faces if f["name"] == "front"), None)
    back = next((f for f in faces if f["name"] == "back"), None)
    if front and back:
        fh = [(_num(h.get("d") or h.get("diameter"), 0), _num(h.get("x"), 0), _num(h.get("y"), 0)) for h in front["features"]["holes"]]
        bh = [(_num(h.get("d") or h.get("diameter"), 0), _num(h.get("x"), 0), _num(h.get("y"), 0)) for h in back["features"]["holes"]]
        for d, x, y in fh:
            if d <= 0:
                continue
            mates = [q for q in bh if abs(q[0] - d) <= 0.15 and abs(q[2] - y) <= 1.0]
            if not mates:
                errors.append(f"front hole d={d} y={y} has no coaxial back hole (same d, same height)")
            else:
                shaft_pairs.append({"axis": "front-back", "d": d, "y": y, "result": "MATCH"})

    shaft_ds = [p["d"] for p in shaft_pairs]
    for face in faces:
        if face.get("kind") not in {"propeller", "disc"}:
            continue
        hole = float(face.get("hole") or 0)
        if hole <= 0:
            if face.get("kind") == "propeller":
                errors.append(f"{face['name']} needs a shaft hole")
            continue
        if shaft_ds and not any(abs(hole - d) <= 0.15 for d in shaft_ds):
            errors.append(f"{face['name']} hole {hole} mm does not match wall shaft {shaft_ds}")
        elif not shaft_ds and face.get("kind") == "propeller":
            warnings.append(f"{face['name']} has a shaft hole but no matching holes on opposite walls")
        if face.get("kind") == "propeller":
            d = float(face.get("d") or 0)
            if d < hole + 10:
                errors.append(f"{face['name']} diameter {d} is too small around hole {hole}")
            shaft_pairs.append({"part": face["name"], "d": hole, "rotor_d": d, "result": "MATCH" if hole else "FAIL"})

    box = next((p for p in (primitives or []) if isinstance(p, dict) and _kind(p) == "box"), None)
    gables = [f for f in faces if f.get("kind") == "gable"]
    roofs = [f for f in faces if f.get("kind") == "panel" and "roof" in str(f.get("name") or "").lower()]
    props = [f for f in faces if f.get("kind") == "propeller"]
    if box:
        bx = _num(box.get("x") or box.get("w"), 80)
        by = _num(box.get("y") or box.get("d"), 80)
        bh = _num(box.get("h"), 80)
        assembled = [round(bx + 2 * t, 2), round(by + 2 * t, 2), round(bh + t, 2)]
        if gables:
            assembled[2] = round(assembled[2] + max(float(g["h"]) for g in gables), 2)
        if props:
            assembled[1] = round(assembled[1] + t + max(float(p.get("d") or 0) for p in props) / 2, 2)
        roof_lock = _check_seating(errors, warnings, bx, by, t, gables, roofs, props, front)
    else:
        assembled = None
        roof_lock = []
        if gables and roofs:
            warnings.append("gables/roofs without a box: cannot lock them to a wall top")

    sequence = []
    names = {f["name"] for f in faces}
    if any(f.get("kind") == "coupon" for f in faces):
        sequence.append("Cut the coupon first: dry-fit male f into female F, then measure the 100 mm bar (shrinkage / 2 ≈ burn).")
    if "bottom" in names:
        sequence.append("Stand the bottom panel; fingers point up.")
    for wall in ("front", "back", "left", "right"):
        if wall in names:
            sequence.append(f"Insert {wall} wall fingers into matching F holes / floor edge.")
    if any(f.get("kind") == "gable" for f in faces):
        sequence.append("Lock gable bottom fingers into the front and back top F edges.")
    if any(f.get("kind") == "panel" and "roof" in f["name"] for f in faces):
        sequence.append("Lock roof f fingers into the gable hypotenuse F — the roof must click, not rest.")
    if any(f.get("kind") == "propeller" for f in faces):
        sequence.append("Pass the shaft through front and back holes, spacers, then the propeller. Do not force; kerf is 0.15 mm.")
    if not sequence:
        sequence.append("Dry-fit every f/F pair and every hole/shaft before glue.")

    ok = not errors
    return {
        "ok": ok,
        "warnings": warnings,
        "look_again": errors,
        "joints": joints,
        "roof_lock": roof_lock,
        "finger_pairs": len(joints),
        "shaft_pairs": shaft_pairs,
        "assembled_mm": assembled,
        "sequence": sequence,
        "parts": [f["name"] for f in faces],
        "thickness": t,
        "burn": kerf,
        "look_again": errors,
        "note": (
            "Roof is locked only when gable bottom f mates wall top F and roof f mates gable hypotenuse F "
            "(Boxes.py FingerJoint). A sitting rectangle is not a lock."
        ),
    }
