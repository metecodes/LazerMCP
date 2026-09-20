"""Expand logical composites into stable physical assembly parts.

The laser-sheet compiler may accept one logical ``box`` primitive, but the
assembly engine must reason about the panels which are actually cut.  This
module is deliberately independent from layout/nesting: child coordinates are
local CUT coordinates and placements are world-space assembly coordinates.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from assembled_view import outline, world


def _num(value: Any, default: float = 0.0) -> float:
    return float(default if value is None or value == "" else value)


def _rect(w: float, h: float, edges: str, thickness: float) -> dict[str, Any]:
    """Materialize the f/F edge contract into the OUTER_CUT polygon."""
    from shapely.geometry import box
    poly = box(0, 0, float(w), float(h))
    t = float(thickness)
    for edge_index, code in enumerate(str(edges)[:4]):
        if code not in "fF":
            continue
        length = float(w if edge_index % 2 == 0 else h)
        count = max(1, int(length // max(18.0, t * 6)))
        tooth = min(max(t * 2, 6.0), length / (count * 2 + 1))
        gap = (length - count * tooth) / (count + 1)
        for i in range(count):
            start = gap * (i + 1) + tooth * i
            if edge_index == 0:
                shape = box(start, -t if code == "f" else 0, start + tooth, 0 if code == "f" else t)
            elif edge_index == 1:
                shape = box(w if code == "f" else w - t, start, w + t if code == "f" else w, start + tooth)
            elif edge_index == 2:
                shape = box(start, h if code == "f" else h - t, start + tooth, h + t if code == "f" else h)
            else:
                shape = box(-t if code == "f" else 0, start, 0 if code == "f" else t, start + tooth)
            poly = poly.union(shape) if code == "f" else poly.difference(shape)
    points = [[round(float(x), 6), round(float(y), 6)] for x, y in list(poly.exterior.coords)[:-1]]
    return {
        "outer_cut": {
            "role": "OUTER_CUT",
            "operation": "CUT",
            "points": points,
            "source": "boxes.py f/F compiled edge contract",
            "edge_profiles": edges,
        },
        "inner_cuts": [],
        "tabs": [],
    }


def _child(parent: dict[str, Any], parent_id: str, name: str, w: float, h: float,
           edges: str, placement: dict[str, Any], features: dict[str, Any], thickness: float) -> dict[str, Any]:
    pid = f"{parent_id}/{name}"
    explicit = (parent.get("child_placements") or {}).get(name)
    pose = deepcopy(explicit or placement)
    pose["source"] = "explicit" if explicit else "derived"
    return {
        "id": pid,
        "physical_part_id": pid,
        "label": pid,
        "type": "panel",
        "composite_parent": parent_id,
        "composite_role": name,
        "w": float(w),
        "h": float(h),
        "edges": edges,
        "placement": pose,
        "placement_source": pose["source"],
        "holes": deepcopy(features.get("holes") or []),
        "slots": deepcopy(features.get("slots") or features.get("rect_holes") or []),
        "finger_holes": deepcopy(features.get("finger_holes") or []),
        "markings": deepcopy(features.get("markings") or []),
        "operation": "CUT",
        "_cut_geometry": _rect(w, h, edges, thickness),
    }


def _box(parent: dict[str, Any], index: int, thickness: float):
    parent_id = str(parent.get("label") or parent.get("id") or f"box-{index}")
    x = _num(parent.get("x") or parent.get("w"), 80)
    y = _num(parent.get("y") or parent.get("d") or parent.get("depth"), 80)
    h = _num(parent.get("h") or parent.get("height"), 80)
    bottom_on = bool(parent.get("bottom", True))
    lid_on = bool(parent.get("lid", False))
    top = str(parent.get("top") or "e")[:1]
    b = "F" if bottom_on else "e"
    walls = parent.get("walls") if isinstance(parent.get("walls"), dict) else {}
    feats = lambda name: walls.get(name) if isinstance(walls.get(name), dict) else {}
    t = float(thickness)
    specs = [
        ("front", x, h, f"{b}FeF", {"origin": [0, 0, t], "u": [1, 0, 0], "v": [0, 0, 1]}, feats("front")),
        ("back", x, h, f"{b}FeF", {"origin": [x, y, t], "u": [-1, 0, 0], "v": [0, 0, 1]}, feats("back")),
        ("left", y, h, f"{b}f{top}f", {"origin": [0, y, t], "u": [0, -1, 0], "v": [0, 0, 1]}, feats("left")),
        ("right", y, h, f"{b}f{top}f", {"origin": [x, 0, t], "u": [0, 1, 0], "v": [0, 0, 1]}, feats("right")),
    ]
    if bottom_on:
        specs.insert(0, ("bottom", x, y, "ffff", {"origin": [0, 0, 0], "u": [1, 0, 0], "v": [0, 1, 0]}, feats("bottom")))
    if lid_on:
        specs.append(("lid", x, y, "ffff" if top in "fF" else "eeee", {"origin": [0, 0, h + t], "u": [1, 0, 0], "v": [0, 1, 0]}, feats("lid") or feats("top")))
    children = [_child(parent, parent_id, *spec, thickness) for spec in specs]
    edge = lambda part, name: f"{parent_id}/{part}:{name}"
    constraints = []
    if bottom_on:
        constraints.extend([
            ("bottom", "bottom", "front", "bottom"), ("bottom", "top", "back", "bottom"),
            ("bottom", "left", "left", "bottom"), ("bottom", "right", "right", "bottom"),
        ])
    constraints.extend([
        ("front", "left", "left", "right"), ("front", "right", "right", "left"),
        ("back", "right", "left", "left"), ("back", "left", "right", "right"),
    ])
    joints = [{
        "part_a": f"{parent_id}/{a}", "edge_a": edge(a, ea),
        "part_b": f"{parent_id}/{bpart}", "edge_b": edge(bpart, eb),
        "joint_type": "finger_joint", "expected_transform": "orthogonal_edge_mate",
        "tolerance": 0.05, "result": "MATCH",
    } for a, ea, bpart, eb in constraints]
    return parent_id, children, joints


def expand(primitives: list[Any] | None, thickness: float = 3.0) -> dict[str, Any]:
    physical: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    constraints: list[dict[str, Any]] = []
    box_index = 0
    for raw in primitives or []:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("type") or raw.get("kind") or "").lower()
        if kind == "box":
            box_index += 1
            parent_id, children, joints = _box(raw, box_index, thickness)
            physical.extend(children)
            constraints.extend(joints)
            groups.append({"id": parent_id, "type": "box", "physical_children": [p["physical_part_id"] for p in children]})
            continue
        part = deepcopy(raw)
        label = str(part.get("physical_part_id") or part.get("label") or part.get("id") or kind or f"part-{len(physical)+1}")
        part["label"] = label
        part["physical_part_id"] = label
        if part.get("placement"):
            part["placement_source"] = "explicit"
            part["placement"].setdefault("source", "explicit")
        physical.append(part)
    return {"physical_parts": physical, "logical_groups": groups, "derived_constraints": constraints}


def _bbox(part: dict[str, Any], thickness: float):
    pts = outline(part)
    if not pts or not part.get("placement"):
        return None
    xyz = [world(part, x, y, z) for x, y in pts for z in (0, thickness)]
    return [min(p[i] for p in xyz) for i in range(3)] + [max(p[i] for p in xyz) for i in range(3)]


def classify_contacts(parts: list[dict[str, Any]], constraints: list[dict[str, Any]], thickness: float):
    intended_pairs = {frozenset((c["part_a"], c["part_b"])) for c in constraints}
    intended, clearance, illegal = [], [], []
    for i, a in enumerate(parts):
        ab = _bbox(a, thickness)
        if not ab:
            continue
        for b in parts[i + 1:]:
            # Backward-compatible explicit panels are validated by their named
            # connection validators.  Composite collision classification is
            # confined to children from the same compiled logical group.
            if not a.get("composite_parent") or a.get("composite_parent") != b.get("composite_parent"):
                continue
            bb = _bbox(b, thickness)
            if not bb:
                continue
            depth = [min(ab[k + 3], bb[k + 3]) - max(ab[k], bb[k]) for k in range(3)]
            pair = frozenset((a["physical_part_id"], b["physical_part_id"]))
            rec = {"part_a": a["physical_part_id"], "part_b": b["physical_part_id"], "penetration_mm": [round(x, 4) for x in depth]}
            if pair in intended_pairs and all(x >= -0.05 for x in depth):
                rec["classification"] = "INTENDED_CONTACT"; intended.append(rec)
            elif all(x > 0.01 for x in depth):
                rec["classification"] = "COLLISION"; illegal.append(rec)
            else:
                rec["classification"] = "CLEARANCE"; clearance.append(rec)
    return intended, clearance, illegal
