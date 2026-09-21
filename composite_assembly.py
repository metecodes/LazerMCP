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
import math


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
           edges: str, placement: dict[str, Any], features: dict[str, Any], thickness: float, role: str="structural") -> dict[str, Any]:
    pid = f"{parent_id}/{name}"
    explicit = (parent.get("child_placements") or {}).get(name)
    pose = deepcopy(explicit or placement)
    pose["source"] = "explicit" if explicit else "derived"
    geometry=_rect(w,h,edges,thickness);inner=[]
    for slot in features.get("slots") or []:
        if not isinstance(slot,dict):continue
        x=float(slot.get("x") if slot.get("x") is not None else slot.get("cx") or 0);y=float(slot.get("y") if slot.get("y") is not None else slot.get("cy") or 0)
        sw=float(slot.get("w") or slot.get("width") or slot.get("dx") or 0);sh=float(slot.get("h") or slot.get("height") or slot.get("dy") or 0)
        if sw>0 and sh>0:inner.append({"id":str(slot.get("id") or ""),"role":"SLOT","semantic_role":slot.get("semantic_role") or "inner_cut","operation":"CUT","parent_part_id":pid,"points":[[x-sw/2,y-sh/2],[x+sw/2,y-sh/2],[x+sw/2,y+sh/2],[x-sw/2,y+sh/2]],"clearance_mm":slot.get("clearance_mm")})
    from math import cos,sin,pi
    for hole in features.get("holes") or []:
        if not isinstance(hole,dict):continue
        x=float(hole.get("x") if hole.get("x") is not None else hole.get("cx") or 0);y=float(hole.get("y") if hole.get("y") is not None else hole.get("cy") or 0);d=float(hole.get("d") or hole.get("diameter") or 2*float(hole.get("r") or 0))
        if d>0:inner.append({"id":str(hole.get("id") or ""),"role":"HARDWARE_HOLE","semantic_role":"hardware_hole","operation":"CUT","parent_part_id":pid,"diameter_mm":d,"points":[[x+d/2*cos(2*pi*i/32),y+d/2*sin(2*pi*i/32)] for i in range(32)]})
    geometry["inner_cuts"]=inner
    return {
        "id": pid,
        "physical_part_id": pid,
        "label": pid,
        "type": "panel",
        "composite_parent": parent_id,
        "composite_role": name,
        "role":role,
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
        "_cut_geometry": geometry,
    }


def _box(parent: dict[str, Any], index: int, thickness: float):
    parent_id = str(parent.get("label") or parent.get("id") or f"box-{index}")
    x = _num(parent.get("x") or parent.get("w"), 80)
    y = _num(parent.get("y") or parent.get("d") or parent.get("depth"), 80)
    h = _num(parent.get("h") or parent.get("height"), 80)
    bottom_value=parent.get("bottom", True);lid_value=parent.get("lid", False)
    bottom_on = bottom_value is not False
    lid_on = bool(lid_value)
    lid_type=str(lid_value.get("type") if isinstance(lid_value,dict) else "finger_joint").lower()
    top = str(parent.get("top") or "e")[:1]
    b = "F" if bottom_on else "e"
    walls = parent.get("walls") if isinstance(parent.get("walls"), dict) else {}
    from enclosure_features import normalize
    def feats(name):
        value=walls.get(name) if isinstance(walls.get(name),dict) else {}
        if name=="bottom" and isinstance(bottom_value,dict):value={**bottom_value,**value}
        if name in {"lid","top"} and isinstance(lid_value,dict):value={**lid_value,**value}
        return normalize(value)
    if lid_on and lid_type in {"finger","finger_joint","fixed"}:top="F"
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
        specs.append(("lid", x, y, "ffff" if lid_type in {"finger","finger_joint","fixed"} else "eeee", {"origin": [0, 0, h + t], "u": [1, 0, 0], "v": [0, 1, 0]}, feats("lid") or feats("top"),"removable" if lid_type in {"removable","sliding"} else "structural"))
    children = [_child(parent,parent_id,*spec[:6],thickness,*(spec[6:] or ["structural"])) for spec in specs]
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
    if lid_on and lid_type in {"finger","finger_joint","fixed"}:
        constraints.extend([("lid","bottom","front","top"),("lid","top","back","top"),("lid","left","left","top"),("lid","right","right","top")])
    elif lid_on:
        constraints.extend([("lid","bottom","front","top")])
    joints = [{
        "part_a": f"{parent_id}/{a}", "edge_a": edge(a, ea),
        "part_b": f"{parent_id}/{bpart}", "edge_b": edge(bpart, eb),
        "joint_type": "removable_lid" if a=="lid" and lid_type in {"removable","sliding"} else "finger_joint", "expected_transform": "vertical_removal_path" if a=="lid" and lid_type in {"removable","sliding"} else "orthogonal_edge_mate",
        "tolerance": 0.05, "result": "NOT_VERIFIED",
    } for a, ea, bpart, eb in constraints]
    return parent_id, children, joints

def _normal(part):
    pose=part.get("placement") or {};u=pose.get("u") or [];v=pose.get("v") or []
    if len(u)!=3 or len(v)!=3:return None
    n=[float(u[1])*float(v[2])-float(u[2])*float(v[1]),float(u[2])*float(v[0])-float(u[0])*float(v[2]),float(u[0])*float(v[1])-float(u[1])*float(v[0])]
    mag=math.sqrt(sum(x*x for x in n));return [x/mag for x in n] if mag else None

def _edge_points(part,name,z):
    w,h=float(part.get("w") or 0),float(part.get("h") or 0)
    ends={"bottom":((0,0),(w,0)),"right":((w,0),(w,h)),"top":((0,h),(w,h)),"left":((0,0),(0,h))}.get(name)
    return [world(part,x,y,z) for x,y in ends] if ends else []

def validate_box_transforms(parts,constraints,thickness):
    """Prove compiler-derived box poses against the actual joint graph."""
    lookup={str(p.get("physical_part_id")):p for p in parts};checks=[];tol=.05;t=float(thickness)
    expected={"bottom":[0,0,1],"lid":[0,0,1],"front":[0,-1,0],"back":[0,1,0],"left":[-1,0,0],"right":[1,0,0]}
    for part in parts:
        role=str(part.get("composite_role") or "");normal=_normal(part);target=expected.get(role)
        status="PASS" if normal and target and math.sqrt(sum((normal[i]-target[i])**2 for i in range(3)))<=1e-6 else "FAIL"
        checks.append({"type":"PART_TRANSFORM","part":part.get("physical_part_id"),"status":status,"origin":(part.get("placement") or {}).get("origin"),"u":(part.get("placement") or {}).get("u"),"v":(part.get("placement") or {}).get("v"),"normal":normal,"expected_normal":target})
    for joint in constraints:
        a,b=lookup.get(str(joint.get("part_a"))),lookup.get(str(joint.get("part_b")));ea=str(joint.get("edge_a") or "").split(":")[-1];eb=str(joint.get("edge_b") or "").split(":")[-1]
        best=None
        if a and b:
            for za in (0,t):
                for zb in (0,t):
                    ap,bp=_edge_points(a,ea,za),_edge_points(b,eb,zb)
                    if len(ap)!=2 or len(bp)!=2:continue
                    direct=max(math.dist(ap[i],bp[i]) for i in (0,1));reverse=max(math.dist(ap[i],bp[1-i]) for i in (0,1));candidate=(min(direct,reverse),za,zb)
                    if best is None or candidate[0]<best[0]:best=candidate
        la=float(a.get("w") if ea in {"bottom","top"} else a.get("h") or 0) if a else 0;lb=float(b.get("w") if eb in {"bottom","top"} else b.get("h") or 0) if b else 0
        na,nb=_normal(a or {}),_normal(b or {});angle=math.degrees(math.acos(min(1,abs(sum(na[i]*nb[i] for i in range(3)))))) if na and nb else None
        ok=bool(best and best[0]<=tol and abs(la-lb)<=tol and angle is not None and abs(angle-90)<=.01)
        joint.update(result="MATCH" if ok else "FAIL",world_edge_error_mm=round(best[0],6) if best else None,edge_length_delta_mm=round(abs(la-lb),6),normal_angle_deg=round(angle,6) if angle is not None else None,material_surface_offsets_mm=[best[1],best[2]] if best else None)
        checks.append({"type":"JOINT_TRANSFORM","part_a":joint.get("part_a"),"part_b":joint.get("part_b"),"status":"PASS" if ok else "FAIL","world_edge_error_mm":joint.get("world_edge_error_mm"),"edge_length_delta_mm":joint.get("edge_length_delta_mm"),"normal_angle_deg":joint.get("normal_angle_deg"),"material_surface_offsets_mm":joint.get("material_surface_offsets_mm")})
    bottoms=[p for p in parts if p.get("composite_role")=="bottom"];walls={p.get("composite_role"):p for p in parts if p.get("composite_role") in {"front","back","left","right"}}
    volume_ok=bool(bottoms and len(walls)==4 and float(bottoms[0].get("w") or 0)>0 and float(bottoms[0].get("h") or 0)>0 and min(float(p.get("h") or 0) for p in walls.values())>0)
    checks.append({"type":"INTERIOR_VOLUME","status":"PASS" if volume_ok else "FAIL","inner_dimensions_mm":[float(bottoms[0].get("w")),float(bottoms[0].get("h")),float(walls["front"].get("h"))] if volume_ok else None})
    return {"status":"PASS" if checks and all(c["status"]=="PASS" for c in checks) else "FAIL","checks":checks}


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
    validation=validate_box_transforms(physical,constraints,thickness) if groups else {"status":"N/A","checks":[]}
    return {"physical_parts": physical, "logical_groups": groups, "derived_constraints": constraints,"transform_validation":validation}


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
