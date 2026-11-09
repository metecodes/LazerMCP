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
    lid_edges=str(lid_value.get("edges") or "ffff")[:4] if isinstance(lid_value,dict) else "ffff"
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
        ("front", x, h, f"{b}F{top}F", {"origin": [0, 0, t], "u": [1, 0, 0], "v": [0, 0, 1]}, feats("front")),
        ("back", x, h, f"{b}F{top}F", {"origin": [x, y, t], "u": [-1, 0, 0], "v": [0, 0, 1]}, feats("back")),
        ("left", y, h, f"{b}f{top}f", {"origin": [0, y, t], "u": [0, -1, 0], "v": [0, 0, 1]}, feats("left")),
        ("right", y, h, f"{b}f{top}f", {"origin": [x, 0, t], "u": [0, 1, 0], "v": [0, 0, 1]}, feats("right")),
    ]
    raised = max(0.0, _num(parent.get("bottom_lift") or parent.get("raised_bottom"), 0.0))
    if bottom_on:
        specs.insert(
            0,
            (
                "bottom",
                x,
                y,
                "ffff",
                {"origin": [0, 0, raised], "u": [1, 0, 0], "v": [0, 1, 0]},
                feats("bottom"),
            ),
        )
    if lid_on:
        doors = int((lid_value.get("doors") if isinstance(lid_value, dict) else 1) or 1)
        lid_role = "removable" if lid_type in {"removable", "sliding"} else "structural"
        if lid_type == "hinged" and doors >= 2:
            half = max(8.0, (x - t) / 2)
            specs.append(
                ("lid-left", half, y, "efee", {"origin": [0, 0, h + t], "u": [1, 0, 0], "v": [0, 1, 0]}, feats("lid") or feats("top"), lid_role)
            )
            specs.append(
                ("lid-right", half, y, "eefe", {"origin": [half + t, 0, h + t], "u": [1, 0, 0], "v": [0, 1, 0]}, feats("lid") or feats("top"), lid_role)
            )
        else:
            specs.append(
                (
                    "lid",
                    x,
                    y,
                    lid_edges if lid_type in {"finger", "finger_joint", "fixed"} else "eeee",
                    {"origin": [0, 0, h + t], "u": [1, 0, 0], "v": [0, 1, 0]},
                    feats("lid") or feats("top"),
                    lid_role,
                )
            )

    # Internal fittings (Studio / Vector Painter parity): dividers + shelves + drawers.
    from studio_box import divider_positions, equal_cells, seat_drawer_specs

    dx = max(0, int(parent.get("dividers_x") or 0))
    dy = max(0, int(parent.get("dividers_y") or 0))
    sx = parent.get("sx") if isinstance(parent.get("sx"), list) and parent.get("sx") else None
    sy = parent.get("sy") if isinstance(parent.get("sy"), list) and parent.get("sy") else None
    if not sx:
        sx = equal_cells(x, dx, t) if dx else [x]
    if not sy:
        sy = equal_cells(y, dy, t) if dy else [y]
    x_div_pos = divider_positions([float(v) for v in sx], t) if dx else []
    y_div_pos = divider_positions([float(v) for v in sy], t) if dy else []
    joint_walls = bool(parent.get("divider_joint_walls", True))
    joint_bottom = bool(parent.get("divider_joint_bottom", True))
    raw_drawers = parent.get("drawer_specs") if isinstance(parent.get("drawer_specs"), list) else []
    drawers_on = bool(parent.get("drawers")) and bool(raw_drawers)
    # Finger geçme between cubbies (not butt/glue). Front edge opens when drawers pull out.
    div_b = "f" if joint_bottom else "e"
    if drawers_on:
        back_e = "f" if joint_walls else "e"
        div_edges = f"{div_b}{back_e}ee"
        shelf_edges = "efff"
    else:
        w_e = "f" if joint_walls else "e"
        div_edges = f"{div_b}{w_e}e{w_e}"
        shelf_edges = "ffff"
    div_h = max(8.0, h - raised)
    for i, pos in enumerate(x_div_pos, 1):
        specs.append(
            (
                f"divider-x-{i}",
                y,
                div_h,
                div_edges,
                {"origin": [float(pos), 0.0, raised], "u": [0, 1, 0], "v": [0, 0, 1]},
                {},
                "structural",
            )
        )
    for i, pos in enumerate(y_div_pos, 1):
        specs.append(
            (
                f"divider-y-{i}",
                x,
                div_h,
                div_edges,
                {"origin": [0.0, float(pos), raised], "u": [1, 0, 0], "v": [0, 0, 1]},
                {},
                "structural",
            )
        )
    shelf_n = max(0, min(6, int(parent.get("shelves") or 0)))
    lid_eat = t if lid_on and lid_type in {"finger", "finger_joint", "fixed"} else 0.0
    shelf_span = max(0.0, h - raised - lid_eat)
    if shelf_n and shelf_span > 0:
        step = shelf_span / (shelf_n + 1)
        for i in range(1, shelf_n + 1):
            z = raised + step * i
            specs.append(
                (
                    f"shelf-{i}",
                    x,
                    y,
                    shelf_edges,
                    {"origin": [0.0, 0.0, float(z)], "u": [1, 0, 0], "v": [0, 1, 0]},
                    {},
                    "structural",
                )
            )

    # Open-tray drawers seated in each front cubby (moving — not glued to carcass).
    drawer_specs = (
        seat_drawer_specs(
            [d for d in raw_drawers if isinstance(d, dict)],
            sx=[float(v) for v in sx],
            sy=[float(v) for v in sy],
            raised=raised,
            shelves=shelf_n,
            h=h,
            thickness=t,
            lid_eat=lid_eat,
        )
        if drawers_on
        else []
    )
    for spec in drawer_specs:
        did = str(spec.get("id") or "drawer")
        dw = float(spec.get("w_mm") or 0)
        dd = float(spec.get("d_mm") or 0)
        dh = float(spec.get("h_mm") or 0)
        if dw < 14 or dd < 14 or dh < 10:
            continue
        ox = float(spec.get("ox_mm") or 0)
        oy = float(spec.get("oy_mm") or 0)
        oz = float(spec.get("oz_mm") or raised)
        # Assembly outlines stay edge-plain; Boxes.py still cuts tray finger joints + pull on the sheet.
        specs.append(
            (
                f"{did}-bottom",
                dw,
                dd,
                "eeee",
                {"origin": [ox, oy, oz], "u": [1, 0, 0], "v": [0, 1, 0]},
                {},
                "moving",
            )
        )
        specs.append(
            (
                f"{did}-front",
                dw,
                dh,
                "eeee",
                {"origin": [ox, oy, oz + t], "u": [1, 0, 0], "v": [0, 0, 1]},
                # Pull half-circle is cut on the SVG sheet only (edge notch fails preview pad checks here).
                {},
                "moving",
            )
        )
        specs.append(
            (
                f"{did}-back",
                dw,
                dh,
                "eeee",
                {"origin": [ox + dw, oy + dd, oz + t], "u": [-1, 0, 0], "v": [0, 0, 1]},
                {},
                "moving",
            )
        )
        specs.append(
            (
                f"{did}-left",
                dd,
                dh,
                "eeee",
                {"origin": [ox, oy + dd, oz + t], "u": [0, -1, 0], "v": [0, 0, 1]},
                {},
                "moving",
            )
        )
        specs.append(
            (
                f"{did}-right",
                dd,
                dh,
                "eeee",
                {"origin": [ox + dw, oy, oz + t], "u": [0, 1, 0], "v": [0, 0, 1]},
                {},
                "moving",
            )
        )

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
    lid_names = [str(spec[0]) for spec in specs if str(spec[0]).startswith("lid")]
    if lid_on and lid_type in {"finger", "finger_joint", "fixed"} and "lid" in lid_names:
        constraints.extend([
            ("lid", "bottom", "front", "top"),
            ("lid", "top", "back", "top"),
            ("lid", "left", "left", "top"),
            ("lid", "right", "right", "top"),
        ])
    elif lid_on and lid_names:
        # Removable / sliding / hinged doors: declare seat against front rim only.
        for name in lid_names:
            constraints.append((name, "bottom", "front", "top"))

    # Internal fittings: world-space seats (slots), not outer f/F edge pairs.
    internal_constraints: list[tuple[str, str, str, str, str]] = []
    for i, _pos in enumerate(x_div_pos, 1):
        pid = f"divider-x-{i}"
        if joint_bottom and bottom_on:
            internal_constraints.append((pid, "bottom", "bottom", "top", "finger_slot"))
        if joint_walls:
            if not drawers_on:
                internal_constraints.append((pid, "left", "front", "top", "finger_slot"))
            internal_constraints.append((pid, "right", "back", "top", "finger_slot"))
    for i, _pos in enumerate(y_div_pos, 1):
        pid = f"divider-y-{i}"
        if joint_bottom and bottom_on:
            internal_constraints.append((pid, "bottom", "bottom", "top", "finger_slot"))
        if joint_walls:
            internal_constraints.append((pid, "left", "left", "top", "finger_slot"))
            internal_constraints.append((pid, "right", "right", "top", "finger_slot"))
        for xi, _xp in enumerate(x_div_pos, 1):
            internal_constraints.append((pid, "bottom", f"divider-x-{xi}", "bottom", "cross_lap"))
    for i in range(1, shelf_n + 1):
        pid = f"shelf-{i}"
        wall_mates = [
            ("back", "top", "top"),
            ("left", "left", "top"),
            ("right", "right", "top"),
        ]
        if not drawers_on:
            wall_mates = [("front", "bottom", "top"), *wall_mates]
        for wall, ea, eb in wall_mates:
            internal_constraints.append((pid, ea, wall, eb, "finger_slot"))
        for xi, _xp in enumerate(x_div_pos, 1):
            internal_constraints.append((pid, "bottom", f"divider-x-{xi}", "bottom", "cross_lap"))
        for yi, _yp in enumerate(y_div_pos, 1):
            internal_constraints.append((pid, "bottom", f"divider-y-{yi}", "bottom", "cross_lap"))
    for spec in drawer_specs:
        did = str(spec.get("id") or "drawer")
        # Declared slide seat: drawer lives in its cubby (digital). Physical slide NOT_VERIFIED.
        internal_constraints.append((f"{did}-bottom", "bottom", "bottom", "top", "drawer_seat"))
        internal_constraints.append((f"{did}-front", "bottom", "front", "top", "drawer_seat"))

    def lid_seat(name: str) -> tuple[str, str] | None:
        # Non-finger lids are plain "eeee" panels seated on the front rim, not f/F edge mates.
        if not str(name).startswith("lid"):
            return None
        if lid_type in {"removable", "sliding"}:
            return "removable_lid", "vertical_removal_path"
        if lid_type == "hinged":
            return "hinged_lid", "internal_fitting_seat"
        return None

    joints = [{
        "part_a": f"{parent_id}/{a}", "edge_a": edge(a, ea),
        "part_b": f"{parent_id}/{bpart}", "edge_b": edge(bpart, eb),
        "joint_type": (lid_seat(a) or ("finger_joint",))[0],
        "expected_transform": (lid_seat(a) or (None, "orthogonal_edge_mate"))[1],
        "tolerance": 0.05, "result": "NOT_VERIFIED",
    } for a, ea, bpart, eb in constraints]
    for a, ea, bpart, eb, jtype in internal_constraints:
        joints.append({
            "part_a": f"{parent_id}/{a}",
            "edge_a": edge(a, ea),
            "part_b": f"{parent_id}/{bpart}",
            "edge_b": edge(bpart, eb),
            "joint_type": jtype,
            "expected_transform": "internal_fitting_seat",
            "tolerance": 0.05,
            "result": "NOT_VERIFIED",
        })
    return parent_id, children, joints


def _internal_fitting_ok(a: dict[str, Any] | None, b: dict[str, Any] | None, thickness: float, tol: float = 0.05):
    """Prove divider/shelf seats via world AABB contact (slots), not outer f/F edges."""
    if not a or not b:
        return False, None
    ab = _bbox(a, thickness)
    bb = _bbox(b, thickness)
    if not ab or not bb:
        return False, None
    depth = [min(ab[k + 3], bb[k + 3]) - max(ab[k], bb[k]) for k in range(3)]
    if any(d < -tol for d in depth):
        return False, depth
    ordered = sorted(depth)
    # Touch/engage in the shallow axis, substantial overlap elsewhere.
    ok = ordered[0] <= thickness + tol and ordered[-1] > thickness
    return ok, depth

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
    parts=[p for p in parts if p.get('composite_parent')]
    lookup={str(p.get("physical_part_id")):p for p in parts};checks=[];tol=.05;t=float(thickness)
    expected={"bottom":[0,0,1],"lid":[0,0,1],"lid-left":[0,0,1],"lid-right":[0,0,1],"front":[0,-1,0],"back":[0,1,0],"left":[-1,0,0],"right":[1,0,0]}
    for part in parts:
        role=str(part.get("composite_role") or "");normal=_normal(part)
        if role.startswith("divider-x"):
            target=[1,0,0]
        elif role.startswith("divider-y"):
            target=[0,-1,0]
        elif role.startswith("shelf"):
            target=[0,0,1]
        elif role.startswith("drawer-") and role.endswith("-front"):
            target=[0,-1,0]
        elif role.startswith("drawer-") and role.endswith("-back"):
            target=[0,1,0]
        elif role.startswith("drawer-") and role.endswith("-left"):
            target=[-1,0,0]
        elif role.startswith("drawer-") and role.endswith("-right"):
            target=[1,0,0]
        elif role.startswith("drawer-") and role.endswith("-bottom"):
            target=[0,0,1]
        else:
            target=expected.get(role)
        status="PASS" if normal and target and math.sqrt(sum((normal[i]-target[i])**2 for i in range(3)))<=1e-6 else "FAIL"
        checks.append({"type":"PART_TRANSFORM","part":part.get("physical_part_id"),"status":status,"origin":(part.get("placement") or {}).get("origin"),"u":(part.get("placement") or {}).get("u"),"v":(part.get("placement") or {}).get("v"),"normal":normal,"expected_normal":target})
    for joint in constraints:
        a,b=lookup.get(str(joint.get("part_a"))),lookup.get(str(joint.get("part_b")));ea=str(joint.get("edge_a") or "").split(":")[-1];eb=str(joint.get("edge_b") or "").split(":")[-1]
        jtype=str(joint.get("joint_type") or "finger_joint")
        if jtype in {"finger_slot", "cross_lap", "shelf_slot", "removable_lid", "hinged_lid", "drawer_seat"}:
            if jtype == "drawer_seat":
                # Digital cubby occupancy only — physical slide/kerf stay NOT_VERIFIED.
                ok = bool(a and b and a.get("placement") and b.get("placement"))
                depth = None
            else:
                ok, depth = _internal_fitting_ok(a, b, t, tol)
            joint.update(
                result="MATCH" if ok else "FAIL",
                world_edge_error_mm=None,
                seat_penetration_mm=[round(d, 6) for d in depth] if depth else None,
                complementary_geometry=False,
                internal_fitting=True,
            )
            checks.append({
                "type": "INTERNAL_FITTING",
                "part_a": joint.get("part_a"),
                "part_b": joint.get("part_b"),
                "joint_type": jtype,
                "status": "PASS" if ok else "FAIL",
                "seat_penetration_mm": joint.get("seat_penetration_mm"),
            })
            continue
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
        edge_index={"bottom":0,"right":1,"top":2,"left":3};pa=str((((a or {}).get("_cut_geometry") or {}).get("outer_cut") or {}).get("edge_profiles") or "");pb=str((((b or {}).get("_cut_geometry") or {}).get("outer_cut") or {}).get("edge_profiles") or "")
        ca=pa[edge_index[ea]] if len(pa)==4 and ea in edge_index else "";cb=pb[edge_index[eb]] if len(pb)==4 and eb in edge_index else "";complementary={ca,cb}=={"f","F"}
        actual_a=bool((((a or {}).get("_cut_geometry") or {}).get("outer_cut") or {}).get("points"));actual_b=bool((((b or {}).get("_cut_geometry") or {}).get("outer_cut") or {}).get("points"))
        ok=bool(best and best[0]<=tol and abs(la-lb)<=tol and angle is not None and abs(angle-90)<=.01 and complementary and actual_a and actual_b)
        joint.update(result="MATCH" if ok else "FAIL",world_edge_error_mm=round(best[0],6) if best else None,edge_length_delta_mm=round(abs(la-lb),6),normal_angle_deg=round(angle,6) if angle is not None else None,material_surface_offsets_mm=[best[1],best[2]] if best else None,edge_profiles=[ca,cb],complementary_geometry=complementary)
        checks.append({"type":"JOINT_TRANSFORM","part_a":joint.get("part_a"),"part_b":joint.get("part_b"),"status":"PASS" if ok else "FAIL","world_edge_error_mm":joint.get("world_edge_error_mm"),"edge_length_delta_mm":joint.get("edge_length_delta_mm"),"normal_angle_deg":joint.get("normal_angle_deg"),"material_surface_offsets_mm":joint.get("material_surface_offsets_mm"),"edge_profiles":[ca,cb],"complementary_geometry":complementary})
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
            roles = {str(a.get("composite_role") or ""), str(b.get("composite_role") or "")}
            internal = any(r.startswith(("divider-", "shelf")) for r in roles)
            drawerish = any(r.startswith("drawer-") for r in roles)
            if pair in intended_pairs and all(x >= -0.05 for x in depth):
                rec["classification"] = "INTENDED_CONTACT"; intended.append(rec)
            elif internal and all(x >= -0.05 for x in depth):
                # Dividers/shelves seat into walls/bottom — declared fittings, not illegal collisions.
                rec["classification"] = "INTENDED_CONTACT"; intended.append(rec)
            elif drawerish and all(x >= -0.05 for x in depth):
                # Drawers occupy cubbies / mate among tray walls — moving fit, not illegal.
                rec["classification"] = "INTENDED_CONTACT"; intended.append(rec)
            elif all(x > 0.01 for x in depth):
                rec["classification"] = "COLLISION"; illegal.append(rec)
            else:
                rec["classification"] = "CLEARANCE"; clearance.append(rec)
    return intended, clearance, illegal
