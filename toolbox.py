"""Boxes.py toolbox: the incoming AI composes parts; we do not add a kit per product."""

from __future__ import annotations

import math
import re
from typing import Any

import boxes_adapter  # noqa: F401  # sys.path for vendor Boxes.py

from boxes import Boxes
from boxes import edges
from boxes_adapter import PAYAS_DEFAULTS, _svg_metrics

ASSEMBLY_TYPES = frozenset(
    {
        "box",
        "panel",
        "wall",
        "rect",
        "disc",
        "disk",
        "circle",
        "washer",
        "spacer",
        "triangle",
        "gable",
        "roof",
        "roof_panel",
        "polygon",
        "contour",
        "outline",
        "polyline",
        "propeller",
        "pervane",
        "blades",
        "fan",
        "cross",
        "plus",
        "coupon",
        "kerf_test",
        "burn_test",
        "kerf",
        "motor_mount",
        "motor_plate",
        "mount_plate",
        "solar",
        "solar_panel",
        "carrier",
        "tray",
        "support",
        "brace",
        "shaft",
        "axle",
        "adapter",
        "washer_plate",
    }
)

GRAMMAR = {
    "edges": (
        "rectangularWall edges are bottom,right,top,left. "
        "e=straight, f=male fingers, F=female finger holes, "
        "h=hole, s/S=stackable, l/L=slide-on lid, X=living hinge. "
        "Hinge/flex/lid need those letters on panel.edges — do not ask for a new tool."
    ),
    "box": {
        "type": "box",
        "x": "inner width mm",
        "y": "inner depth mm",
        "h": "inner height mm",
        "bottom": "true or {holes:[{x,y,d}]} ",
        "lid": "false | true (finger-joint) | {type:finger_joint|removable|sliding, holes/slots/ports:[]}",
        "top": "e",
        "walls": {
            "front": {
                "holes": [{"x": 40, "y": 90, "d": 4}],
                "slots": [{"x": 40, "y": 40, "w": 20, "h": 28}],
                "ports": [{"id":"usb-c","x":20,"y":15,"connector_width":10,"connector_height":5,"plug_width":12,"plug_height":7,"clearance":0.5}],
            }
        },
    },
    "assembled_panel_contract": {"role":"structural|removable|moving|hardware_mount|decorative", "placement": {"origin": "[x,y,z] mm", "u": "unit local X axis", "v": "unit local Y axis; n=normalize(cross(u,v)); position only, never mate evidence"}, "tabs": "[{id,x,y,w,h,side?}] centered rectangles compiled once into the actual OUTER_CUT polygon", "slots": "[{x,y,w,h,mate:{part:label,tab:id}}] centered closed INNER_CUT polygons; partners are transformed and compared in assembled coordinates", "slides":"parameters.connections:[{id,type:linear_slide|removable_slide,moving_part,rails,axis,travel_mm,clearance_mm}]", "mechanism": "{type:wheel|road_roller_drum|pulley|gear|disc|propeller|rotor|flywheel,rotating,shaft}; explicit type wins", "hardware": "parameters.hardware:[{id,type:shaft,diameter,axis,origin,length}]", "shaft_drive": "parameters.connections:[{type:shaft_rotation,shaft,driven_part,hardware_clearance,required_length,allowed_contact_parts}]", "direct_drive": "parameters.connections:[{type:direct_motor_shaft,motor_part,driven_part,shaft_axis,driven_center,radius_mm}]", "preview": "render_preview(file_id,view=assembled); uniquely constrained poses may be derived; ambiguity blocks"},
    "engraving_composition": {"layout":"grid | image_caption | radial", "safe_margin_mm":3, "mechanical_clearance_mm":1, "columns":3, "items":"engraving-only text/image/path/icon items; image_caption uses {illustration,caption}"},
    "panel": {
        "type": "panel",
        "w": 80,
        "h": 120,
        "edges": "eFeF",
        "count": 1,
        "holes": [{"x": 40, "y": 60, "d": 4}],
        "slots": [{"x": 40, "y": 40, "w": 10, "h": 3}],
        "finger_holes": [{"x": 1.5, "y": 1.5, "length": 80, "angle": 0}],
        "markings": [{"kind": "text", "value": "PAYAS", "x": 40, "y": 12, "height": 6, "align": "center", "operation": "engrave"}],
    },
    "disc": {"type": "disc", "d": 50, "hole": 4, "count": 1},
    "triangle": {"type": "triangle", "w": 80, "h": 28, "edges": "eee", "count": 2},
    "propeller": {
        "type": "propeller",
        "blades": 4,
        "d": 80,
        "blade_w": 18,
        "hole": 4,
        "note": "4-blade mill rotor. Do NOT use disc for this. Do not ask for a new tool.",
    },
    "contour": {
        "type": "contour",
        "points": [[40, 0], [8, 8], [0, 40], [-8, 8], [-40, 0], [-8, -8], [0, -40], [8, -8]],
        "hole": 4,
        "note": (
            "Closed outline in mm. points may be [[x,y],...], [{x,y},...], "
            "flat [x,y,x,y,...], or a string 'x,y x,y ...'. Origin can be center or any corner; packed by bbox."
        ),
    },
    "polygon": {
        "type": "polygon",
        "points": [[0, 0], [80, 0], [40, 50]],
        "or_borders": [80, 120, 50, 120, 50],
        "note": "Prefer points [[x,y],...]. borders is Boxes.py [length, turn_angle, ...] only if you already have that.",
    },
    "odd_shapes": (
        "If the photo is not a rectangle/circle, do not give up and do not request a kit. "
        "Count blades/sides from the photo, then call create_design with type=propeller or type=contour. "
        "Read millimetres off the picture. Never hand-write SVG."
    ),
    "coupon": {
        "type": "coupon",
        "x": 40,
        "note": (
            "Male f + female F of the same length (Boxes.py FingerJoint) plus a 100 mm reference bar. "
            "First job on an uncalibrated laser/sheet. Do not add this to every mill — only if they asked to calibrate."
        ),
    },
    "scale": (
        "If the user stated cm/mm, that is the footprint. Otherwise pick ONE length from the photo. "
        "parameters.reference = {feature, mm, drawn_mm} scales the whole recipe so that feature becomes mm. "
        "Do not invent a second size. Coupon parts are not scaled."
    ),
    "coords": "Wall holes and markings: x,y mm from the bottom-left of that part. Contour points: mm in the part's own plane.",
    "markings": {
        "note": (
            "Optional engrave or cut on an existing part. Not a new part type. "
            "Put markings on the part or pass {type:marking, target_part}."
        ),
        "item": {
            "kind": "text | path | logo | icon | line",
            "target_part": "part label or box wall (front/back/left/right/bottom/lid)",
            "x": 20,
            "y": 16,
            "width_or_height": "mm; one is enough, both fits the box",
            "rotation": 0,
            "align": "center | left | right | top | bottom | left|bottom",
            "operation": "CUT | ENGRAVE | SCORE | GUIDE | LABEL (default by semantic_role)",
            "semantic_role": "outer_contour | hole | slot | finger_joint | tab | text | logo | texture | decorative_detail | construction_guide",
        },
        "text": {"kind": "text", "value": "PAYAS", "x": 35, "y": 20, "height": 6, "align": "center", "operation": "engrave"},
        "icon": {"kind": "icon", "icon": "plus", "x": 18, "y": 18, "width": 10, "operation": "engrave"},
        "path": {"kind": "path", "d": "M 0 0 L 12 0 L 6 10 Z", "x": 20, "y": 30, "width": 14, "operation": "engrave"},
        "line": {"kind": "line", "points": [[8, 8], [28, 8], [28, 20]], "x": 0, "y": 0, "operation": "engrave"},
        "icons": "plus, arrow, star, heart, circle, x, square, triangle",
        "standalone": {
            "type": "marking",
            "target_part": "motor-mount",
            "kind": "text",
            "value": "M",
            "x": 18,
            "y": 6,
            "height": 5,
            "rotation": 0,
            "align": "center",
            "operation": "engrave",
        },
    },
    "assembly": (
        "create_design runs Designer → Reviewer → Repair → Reviewer → Final Gate → SVG. "
        "It nests parts (no rotate) and checks f/F, coaxial shafts, tab-slots ≈ 3 mm, roof FingerJoint lock, "
        "and propeller floor clearance. Paste speak as the status card. "
        "final_status BLOCKED means edit primitives and call create_design again. "
        "PROTOTYPE READY authorizes Prototype SVG only. Physical tests stay NOT VERIFIED. "
        "PRODUCTION EXPORT is BLOCKED. Never say LAZER KESİME HAZIR."
    ),
    "never": "Never request a new MCP tool. Never hand-write SVG. Call create_design with primitives.",
    "not_a_generator": (
        "create_design compiles YOUR primitives with Boxes.py. The result is method=compose_primitives, "
        "generator=create_design. That is the drawing — not a missed windmill kit and not a Boxes.py catalog class."
    ),
    "mill": {
        "note": "Example only. There is no create_mill tool. Door/window are slots in the front wall.",
        "primitives": [
            {
                "type": "box",
                "x": 70,
                "y": 52,
                "h": 180,
                "bottom": True,
                "walls": {
                    "front": {
                        "holes": [{"x": 35, "y": 158, "d": 4}],
                        "slots": [
                            {"x": 35, "y": 36, "w": 24, "h": 40},
                            {"x": 35, "y": 88, "w": 26, "h": 32},
                        ],
                        "markings": [
                            {
                                "kind": "text",
                                "value": "PAYAS",
                                "x": 35,
                                "y": 168,
                                "height": 5,
                                "align": "center",
                                "operation": "engrave",
                            }
                        ],
                    },
                    "back": {"holes": [{"x": 35, "y": 158, "d": 4}]},
                },
            },
            {"type": "triangle", "w": 70, "h": 24, "count": 2, "label": "roof-support"},
            {"type": "panel", "w": 80, "h": 58, "edges": "eeee", "count": 2, "label": "roof"},
            {"type": "panel", "w": 78, "h": 48, "edges": "eeee", "label": "solar"},
            {
                "type": "panel",
                "w": 36,
                "h": 36,
                "edges": "eeee",
                "holes": [{"x": 18, "y": 18, "d": 4}, {"x": 8, "y": 8, "d": 3}, {"x": 28, "y": 8, "d": 3}],
                "label": "motor-mount",
            },
            {"type": "propeller", "blades": 4, "d": 48, "blade_w": 12, "hole": 4, "label": "propeller"},
            {"type": "disc", "d": 14, "hole": 4, "count": 2, "label": "spacer"},
        ],
    },
}

HINT = (
    "create_design draws the mill from primitives — there is no windmill generator. "
    "Door/window = slots on the front wall. Motor plate/solar/roof brace = type=panel. "
    "4-blade rotor = type=propeller. Odd outline = type=contour with points:[[x,y],...] mm. "
    "Scale: parameters.reference={feature, mm, drawn_mm}. Calibrate once: {type:\"coupon\"}. "
    "Optional marks: part.markings or {type:marking, target_part} with kind=text|path|icon|line, "
    "x,y,width or height, rotation, align, operation=engrave|cut. "
    "Do not use disc for a propeller. Do not ask for a new kit tool."
)

# e/E straight, f/F fingers, h hole, s/S stackable, l/L slide lid, X living hinge.
_EDGE_OK = set("eEfFhHsSlLxX")
_MAX_PARTS = 48

# Incoming AIs send these as parts. They are features on a wall, not a part type.
_NOT_A_PART = {
    "slot": (
        "type=slot is not a part. Cut openings on a wall: "
        "box.walls.front.slots=[{x,y,w,h}] or panel.slots=[{x,y,w,h}]. "
        "Door and window are slots in the front panel, not separate sliding pieces."
    ),
    "slots": (
        "slots belong on a panel or box wall, not as their own primitive. "
        "Example: {type:panel, w:70, h:180, slots:[{x:35,y:50,w:22,h:28}]}."
    ),
    "door": (
        "A door is a slot cut into the front wall, not a separate part. "
        "Put it on box.walls.front.slots. Do not add type=door."
    ),
    "window": (
        "A window is a slot cut into the front wall, not a separate part. "
        "Put it on box.walls.front.slots. Do not add type=window."
    ),
    "hole": "holes go on panel.holes or box.walls.*.holes as [{x,y,d}].",
    "holes": "holes go on panel.holes or box.walls.*.holes as [{x,y,d}].",
    "marking": (
        "A marking is not a part. Engrave or cut on a wall: "
        "panel.markings=[{kind,x,y,height,operation}] or {type:marking, target_part, ...}."
    ),
    "markings": "markings belong on a panel or box wall, not as their own part.",
    "mark": "Use markings on the target part. type=mark is not a part.",
    "engrave": "Use markings with operation=engrave on the target part.",
    "etch": "Use markings with operation=engrave on the target part.",
    "engraving": "Use markings with operation=engrave on the target part.",
    "logo": "A logo is a marking (kind=path or kind=icon) on target_part, not a new part.",
    "icon": "An icon is a marking (kind=icon) on target_part, not a new part.",
    "lineart": "Line art is a marking (kind=line, points:[[x,y],...]) on target_part.",
    "line_art": "Line art is a marking (kind=line, points:[[x,y],...]) on target_part.",
}

_TYPE_ALIAS = {
    "motor_mount": "panel",
    "motor_plate": "panel",
    "mount_plate": "panel",
    "solar": "panel",
    "solar_panel": "panel",
    "carrier": "panel",
    "tray": "panel",
    "support": "panel",
    "brace": "panel",
    "shaft": "disc",
    "axle": "disc",
    "adapter": "disc",
    "washer_plate": "disc",
}


def _num(value: Any, default: float | None = None) -> float:
    if value is None or value == "":
        if default is None:
            raise ValueError("missing number")
        return float(default)
    return float(value)


def _int(value: Any, default: int = 1, lo: int = 1, hi: int = 20) -> int:
    n = int(value if value is not None else default)
    return max(lo, min(hi, n))


def _kind(part: dict[str, Any]) -> str:
    return str(part.get("type") or part.get("kind") or "").strip().lower()


def is_assembly(primitives: list[Any] | None) -> bool:
    if not primitives:
        return False
    for item in primitives:
        if not isinstance(item, dict):
            continue
        kind = _kind(item)
        if kind in _NOT_A_PART or kind in _TYPE_ALIAS or kind in ASSEMBLY_TYPES:
            return True
        if kind == "text" and isinstance(item, dict) and (item.get("target_part") or item.get("target")):
            return True
    return False


def _prepare_parts(primitives: list[Any]) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    absorb: list[dict[str, Any]] = []
    for part in primitives:
        if not isinstance(part, dict):
            continue
        kind = _kind(part)
        item = dict(part)
        if kind in _NOT_A_PART or (kind == "text" and (item.get("target_part") or item.get("target"))):
            absorb.append(item)
            continue
        if kind in _TYPE_ALIAS:
            item["type"] = _TYPE_ALIAS[kind]
            item.setdefault("label", kind)
            kind = item["type"]
        if kind in ASSEMBLY_TYPES:
            hole=_num(item.get('hole') or item.get('d_hole'),0)
            if kind in {'disc','disk','circle','washer','spacer','propeller'} and hole>0:
                item.setdefault('canonical_holes',[{'id':'center-hole','x':0.0,'y':0.0,'diameter':hole,'type':'shaft_hole'}])
            parts.append(item)
    box = next((p for p in parts if _kind(p) == "box"), None)
    panel = next((p for p in parts if _kind(p) in {"panel", "wall", "rect"}), None)
    for extra in absorb:
        kind = _kind(extra)
        host = box or panel
        if host is None:
            host = {"type": "panel", "w": 80, "h": 120, "edges": "eeee", "slots": [], "holes": [], "label": "front"}
            parts.insert(0, host)
            panel = host
        if box and host is box:
            walls = host.setdefault("walls", {})
            if not isinstance(walls, dict):
                walls = {}
                host["walls"] = walls
            front = walls.setdefault("front", {})
            if not isinstance(front, dict):
                front = {}
                walls["front"] = front
            target = front
        else:
            target = host
        if kind in {"slot", "slots", "door", "window"}:
            target.setdefault("slots", []).append(
                {
                    "x": extra.get("x") or extra.get("cx") or (_num(host.get("x") or host.get("w"), 80) / 2),
                    "y": extra.get("y") or extra.get("cy") or 40,
                    "w": extra.get("w") or extra.get("width") or 22,
                    "h": extra.get("h") or extra.get("height") or 28,
                }
            )
        elif kind in {
            "marking",
            "markings",
            "mark",
            "engrave",
            "etch",
            "engraving",
            "logo",
            "icon",
            "lineart",
            "line_art",
            "text",
            "illustration",
        }:
            from markings import attach_marking

            attach_marking(parts, extra)
        else:
            target.setdefault("holes", []).append(
                {
                    "x": extra.get("x") or extra.get("cx") or 20,
                    "y": extra.get("y") or extra.get("cy") or 20,
                    "d": extra.get("d") or extra.get("diameter") or extra.get("hole") or 4,
                }
            )
    from engraving_composition import prepare as prepare_engraving
    parts,reports=prepare_engraving(parts)
    for part in parts:
        if reports:part.setdefault('_engraving_reports',reports)
    return [_materialize_cut_geometry(part) for part in parts]


def _materialize_cut_geometry(part: dict[str, Any]) -> dict[str, Any]:
    """Build the outer CUT and slot INNER_CUT polygons used by both renderer and reviewer."""
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union

    item=dict(part);kind=_TYPE_ALIAS.get(_kind(item),_kind(item))
    # Compilation can be reached by the renderer, assembly validator and final
    # reviewer.  Recompiling an already materialized L/R/T/B tab used the
    # expanded outline as its new base and moved the tab on every pass.
    existing=item.get('_cut_geometry')
    if isinstance(existing,dict) and isinstance(existing.get('outer_cut'),dict) and existing['outer_cut'].get('points'):
        return item
    raw=item.get('points') or item.get('vertices') or item.get('coords') or item.get('contour')
    if raw:
        base=Polygon(_as_points(raw))
    elif kind in {'panel','wall','rect','roof','roof_panel'}:
        w=_num(item.get('w') or item.get('x') or item.get('width'),80)
        h=_num(item.get('h') or item.get('y') or item.get('height') or item.get('length'),80)
        base=box(0,0,w,h)
    else:
        return item
    if not base.is_valid or base.area<=0:return item
    tabs=[];tab_geometry=[];normalized_tabs=[]
    minx,miny,maxx,maxy=base.bounds
    for source_tab in item.get('tabs') or []:
        tab=dict(source_tab) if isinstance(source_tab,dict) else source_tab
        if not isinstance(tab,dict):continue
        x,y,w,h=[_num(tab.get(k),0) for k in ('x','y','w','h')]
        if w>0 and h>0:
            side_raw=tab.get('side') or tab.get('edge')
            if side_raw is None and str(tab.get('id') or '') in {'L','R','T','B'}:side_raw=tab.get('id')
            side=str(side_raw or '').strip().lower()
            if side in {'l','left'}:x=minx-w/2
            elif side in {'r','right'}:x=maxx+w/2
            elif side in {'b','bottom'}:y=miny-h/2
            elif side in {'t','top'}:y=maxy+h/2
            tab['x']=x;tab['y']=y
            shape=box(x-w/2,y-h/2,x+w/2,y+h/2);outside=shape.difference(base).area;touches=shape.buffer(.02).intersects(base.boundary)
            shared=base.boundary.buffer(.02).intersection(shape.boundary).length
            already=base.buffer(.02).covers(shape) and shared >= max(w,h)+1.5*min(w,h)
            if outside>.001 and touches:tabs.append(shape)
            tab_geometry.append({'id':str(tab.get('id') or ''),'role':'TAB','operation':'CUT','points':[[float(a),float(b)] for a,b in list(shape.exterior.coords)[:-1]],'materialized':bool(already or (outside>.001 and touches)),'outside_area_mm2':float(outside)})
        normalized_tabs.append(tab)
    merged=unary_union([base,*tabs]) if tabs else base
    if merged.geom_type!='Polygon':return item
    points=[[float(x),float(y)] for x,y in list(merged.exterior.coords)[:-1]]
    slots=[]
    for slot in item.get('slots') or item.get('rect_holes') or []:
        if not isinstance(slot,dict):continue
        x,y,w,h=[_num(slot.get(k) or slot.get({'x':'cx','y':'cy','w':'width','h':'height'}[k]),0) for k in ('x','y','w','h')]
        if w<=0 or h<=0:continue
        ring=[[x-w/2,y-h/2],[x+w/2,y-h/2],[x+w/2,y+h/2],[x-w/2,y+h/2]]
        slots.append({'id':str(slot.get('id') or ''),'role':'SLOT','operation':'CUT','points':ring,'mate':slot.get('mate')})
    item['points']=points
    if normalized_tabs:item['tabs']=normalized_tabs
    item['_cut_geometry']={'outer_cut':{'role':'OUTER_CUT','operation':'CUT','points':points},'inner_cuts':slots,'tabs':tab_geometry}
    if kind in {'panel','wall','rect','roof','roof_panel'} and tabs:item['_render_outer_cut_points']=points
    return item


def _edges4(raw: Any, default: str = "eeee") -> str:
    text = "".join(str(raw or default).strip() or default)
    if len(text) != 4:
        raise ValueError(f"panel edges must be 4 letters (bottom,right,top,left), got {text!r}")
    bad = [c for c in text if c not in _EDGE_OK]
    if bad:
        raise ValueError(f"unknown edge {bad}. Use e,f,F,h,s,S,l,L,X.")
    return text


def _edges3(raw: Any, default: str = "eee") -> str:
    text = "".join(str(raw or default).strip() or default)
    if len(text) not in {2, 3}:
        raise ValueError(f"triangle edges must be 2 or 3 letters, got {text!r}")
    bad = [c for c in text if c not in _EDGE_OK]
    if bad:
        raise ValueError(f"unknown edge {bad}. Use e,f,F,h,s,S,l,L,X.")
    return text


def _features(part: dict[str, Any]) -> dict[str, Any]:
    from markings import collect_markings
    from enclosure_features import normalize
    result=normalize(part);result["markings"]=collect_markings(part)
    return result


def _as_points(raw: Any) -> list[tuple[float, float]]:
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", raw)]
        if len(nums) < 6:
            raise ValueError("contour points need at least 3 x,y pairs in mm")
        raw = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
    if isinstance(raw, list) and raw and isinstance(raw[0], (int, float)):
        nums = [float(x) for x in raw]
        if len(nums) < 6:
            raise ValueError("contour points need at least 3 x,y pairs in mm")
        raw = [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]
    pts: list[tuple[float, float]] = []
    for item in raw:
        if isinstance(item, dict):
            pts.append((_num(item.get("x"), 0.0), _num(item.get("y"), 0.0)))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            pts.append((float(item[0]), float(item[1])))
        else:
            raise ValueError(f"bad point {item!r}; use [x,y] millimetres")
    if len(pts) > 240:
        raise ValueError("too many contour points (max 240)")
    if len(pts) < 3:
        raise ValueError("contour needs at least 3 points [[x,y], ...] in mm")
    if math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) < 0.05:
        pts = pts[:-1]
    return pts


def propeller_points(blades: int, diameter: float, blade_w: float) -> list[tuple[float, float]]:
    n = max(2, min(12, int(blades)))
    radius = max(12.0, float(diameter) / 2.0)
    width = min(max(6.0, float(blade_w)), radius * 0.9)
    half = width / 2.0
    inner = min(radius * 0.55, half / math.sin(math.pi / n))
    pts: list[tuple[float, float]] = []
    for i in range(n):
        ang = i * 2 * math.pi / n
        ux, uy = math.cos(ang), math.sin(ang)
        vx, vy = -uy, ux
        pts.append((radius * ux - half * vx, radius * uy - half * vy))
        pts.append((radius * ux + half * vx, radius * uy + half * vy))
        bisect = ang + math.pi / n
        pts.append((inner * math.cos(bisect), inner * math.sin(bisect)))
    return pts


class PayasToolbox(Boxes):
    """Compose rectangularWall / disc / triangle from a JSON recipe. Not a named product."""

    ui_group = "Unlisted"
    webinterface = False

    def __init__(self) -> None:
        Boxes.__init__(self)
        self.addSettingsArgs(edges.FingerJointSettings)
        self.addSettingsArgs(edges.StackableSettings)
        self.addSettingsArgs(edges.SlideOnLidSettings)
        self.addSettingsArgs(edges.FlexSettings)
        self.parts_spec: list[dict[str, Any]] = []
        self.drawn_labels: list[str] = []

    def _note_part(self, label: str) -> None:
        self.drawn_labels.append(str(label or "part"))

    def render(self) -> None:
        drawn = 0
        for part in self.parts_spec:
            if not isinstance(part, dict):
                continue
            n = self._render_part(part)
            drawn += n
            if drawn > _MAX_PARTS:
                raise ValueError(f"too many parts (max {_MAX_PARTS})")
        if drawn < 1:
            raise ValueError("primitives produced no parts")

    def _callback(self, feats: dict[str, Any], origin: tuple[float, float] = (0.0, 0.0)):
        ox, oy = origin

        def _cb() -> None:
            for hole in feats.get("holes") or []:
                if not isinstance(hole, dict):
                    continue
                x = _num(hole.get("x") or hole.get("cx"), 0) + ox
                y = _num(hole.get("y") or hole.get("cy"), 0) + oy
                d = hole.get("d") or hole.get("diameter")
                r = hole.get("r") or hole.get("radius")
                if d:
                    self.hole(x, y, d=float(d))
                elif r:
                    self.hole(x, y, r=float(r))
            for slot in feats.get("slots") or []:
                if not isinstance(slot, dict):
                    continue
                x = _num(slot.get("x") or slot.get("cx"), 0) + ox
                y = _num(slot.get("y") or slot.get("cy"), 0) + oy
                w = _num(slot.get("w") or slot.get("dx") or slot.get("width"), 0)
                h = _num(slot.get("h") or slot.get("dy") or slot.get("height"), 0)
                if w <= 0 or h <= 0:
                    continue
                r = float(slot.get("r") or 0)
                self.rectangularHole(x, y, w, h, r=r, center_x=True, center_y=True)
            for row in feats.get("finger_holes") or []:
                if not isinstance(row, dict):
                    continue
                x = _num(row.get("x"), 0) + ox
                y = _num(row.get("y"), 0) + oy
                length = _num(row.get("length") or row.get("l"), 0)
                angle = _num(row.get("angle") or row.get("a"), 0)
                if length <= 0:
                    continue
                self.fingerHolesAt(x, y, length, angle)
            from markings import draw_markings

            draw_markings(self, feats.get("markings") or [], origin)

        return _cb

    def _has_draw_feats(self, feats: dict[str, Any]) -> bool:
        return bool(
            feats.get("holes") or feats.get("slots") or feats.get("finger_holes") or feats.get("markings")
        )

    def _wall_cb(self, feats: dict[str, Any], origin: tuple[float, float] = (0.0, 0.0)):
        if not self._has_draw_feats(feats):
            return None
        return [self._callback(feats, origin)]

    def _closed_contour(
        self,
        points: list[tuple[float, float]],
        hole_d: float,
        label: str,
        move: str = "up",
        feats: dict[str, Any] | None = None,
    ) -> None:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        minx, maxx = min(xs), max(xs)
        miny, maxy = min(ys), max(ys)
        pad = 2.0
        tw = (maxx - minx) + pad * 2
        th = (maxy - miny) + pad * 2
        if tw < 4 or th < 4:
            raise ValueError("contour bounding box is too small")
        if self.move(tw, th, move, True, label=label):
            return
        ox = pad - minx
        oy = pad - miny
        shifted = [(x + ox, y + oy) for x, y in points]
        if hole_d and hole_d > 0:
            self.hole((minx + maxx) / 2 + ox, (miny + maxy) / 2 + oy, d=float(hole_d))
        if feats and self._has_draw_feats(feats):
            self._callback(feats, origin=(ox, oy))()
        # Offset one closed polygon; turtle corner rotations can leave a gap
        # on acute contours (for example the five-point decorative star).
        from shapely.geometry import Polygon
        from text_path import stroke_geom
        outline = Polygon(shifted).buffer(float(self.burn), join_style=2)
        if outline.geom_type != 'Polygon' or not outline.is_valid or outline.is_empty:
            raise ValueError(f"invalid compensated contour: {label}")
        with self.saved_context():
            stroke_geom(self.ctx, outline)
        self.move(tw, th, move, label=label)

    def _render_part(self, part: dict[str, Any]) -> int:
        kind = _TYPE_ALIAS.get(_kind(part), _kind(part))
        count = _int(part.get("count") or part.get("n"), 1)
        label = str(part.get("label") or kind or "")
        if kind in {"coupon", "kerf_test", "burn_test", "kerf"}:
            self._coupon(part)
            return 3
        if kind in {"box"}:
            self._box(part)
            return 4 + int(bool(part.get("bottom", True))) + int(bool(part.get("lid")))
        if kind in {"panel", "wall", "rect", "roof", "roof_panel"}:
            w = _num(part.get("w") or part.get("x") or part.get("width"), 80)
            h = _num(part.get("h") or part.get("y") or part.get("height") or part.get("length"), 80)
            edge = _edges4(part.get("edges") or part.get("edge"), "eeee")
            cb = self._wall_cb(_features(part))
            for i in range(count):
                name = label if count == 1 else f"{label}-{i + 1}"
                if part.get('_render_outer_cut_points'):
                    self._closed_contour(_as_points(part['_render_outer_cut_points']),0,name,feats=_features(part))
                else:
                    self.rectangularWall(w, h, edge, callback=cb, move="up", label=name)
                self._note_part(name)
            return count
        if kind in {"disc", "disk", "circle", "washer", "spacer"}:
            d = _num(part.get("d") or part.get("diameter") or part.get("w"), 40)
            hole = _num(part.get("hole") or part.get("shaft") or part.get("d_hole"), 0 if kind in {"disc", "disk", "circle"} else 4)
            if kind in {"washer", "spacer"} and hole <= 0:
                hole = max(3.0, float(self.thickness) + 0.2)
            feats = _features(part)
            cb = self._callback(feats, origin=(-d / 2.0, -d / 2.0)) if self._has_draw_feats(feats) else None
            for i in range(count):
                name = label if count == 1 else f"{label}-{i + 1}"
                self.parts.disc(d, hole=hole, callback=cb, move="up", label=name)
                self._note_part(name)
            return count
        if kind in {"triangle", "gable"}:
            w = _num(part.get("w") or part.get("x") or part.get("width"), 80)
            h = _num(part.get("h") or part.get("y") or part.get("rise") or part.get("height"), 30)
            edge = _edges3(part.get("edges") or part.get("edge"), "eee")
            cb = self._wall_cb(_features(part))
            for i in range(count):
                name = label if count == 1 else f"{label}-{i + 1}"
                self.rectangularTriangle(w, h, edge, callback=cb, move="up", label=name)
                self._note_part(name)
            return count
        if kind in {"propeller", "pervane", "blades", "fan", "cross", "plus"}:
            d = _num(part.get("d") or part.get("diameter") or part.get("w"), 80)
            blades = _int(part.get("blades") or part.get("n_blades") or 4, 4, lo=2, hi=12)
            blade_w = _num(part.get("blade_w") or part.get("width") or part.get("blade_width"), max(8.0, d * 0.22))
            hole = _num(part.get("hole") or part.get("shaft") or part.get("d_hole"), 4)
            pts = propeller_points(blades, d, blade_w)
            feats = _features(part)
            for i in range(count):
                name = label if count == 1 else f"{label}-{i + 1}"
                self._closed_contour(pts, hole, name, feats=feats)
                self._note_part(name)
            return count
        if kind in {"polygon", "contour", "outline", "polyline"}:
            raw_pts = part.get("points") or part.get("vertices") or part.get("coords") or part.get("contour")
            if raw_pts:
                pts = _as_points(raw_pts)
                hole = _num(part.get("hole") or part.get("shaft") or part.get("d_hole"), 0)
                feats = _features(part)
                for i in range(count):
                    name = label if count == 1 else f"{label}-{i + 1}"
                    self._closed_contour(pts, hole, name, feats=feats)
                    self._note_part(name)
                return count
            borders = part.get("borders") or part.get("sides")
            if not isinstance(borders, list) or len(borders) < 4:
                raise ValueError(
                    "polygon/contour needs points:[[x,y],...] in mm (preferred) "
                    "or Boxes.py borders:[length, angle, length, angle, ...]. " + HINT
                )
            edge = str(part.get("edge") or part.get("edges") or "e")
            if any(c not in _EDGE_OK for c in edge):
                raise ValueError("polygon edge must be e/f/F")
            cb = self._wall_cb(_features(part))
            for i in range(count):
                name = label if count == 1 else f"{label}-{i + 1}"
                self.polygonWall(list(borders), edge=edge, callback=cb, move="up", label=name)
                self._note_part(name)
            return count
        raise ValueError(
            f"Unknown primitive type {kind!r}. Assembly types: "
            + ", ".join(sorted(ASSEMBLY_TYPES))
            + ". "
            + HINT
        )

    def _box(self, part: dict[str, Any]) -> None:
        x = _num(part.get("x") or part.get("w") or part.get("width"), 80)
        y = _num(part.get("y") or part.get("d") or part.get("depth"), 80)
        h = _num(part.get("h") or part.get("height"), 80)
        if min(x, y, h) < 8:
            raise ValueError("box x, y, h must be at least 8 mm inner")
        top = str(part.get("top") or "e")[:1]
        if top not in _EDGE_OK:
            top = "e"
        gable_top = bool(part.get("gable_top") or part.get("lock_roof"))
        wall_top = "F" if gable_top else top
        side_top = "e" if gable_top else top
        bottom_value=part.get("bottom", True);lid_value=part.get("lid", False)
        bottom_on = bottom_value is not False
        lid_on = bool(lid_value)
        lid_type=str(lid_value.get("type") if isinstance(lid_value,dict) else "finger_joint").lower()
        lid_edges=str(lid_value.get("edges") or "ffff")[:4] if isinstance(lid_value,dict) else "ffff"
        if lid_on and lid_type in {"finger","finger_joint","fixed"}:wall_top=side_top="F"
        b = "F" if bottom_on else "e"
        walls = part.get("walls") if isinstance(part.get("walls"), dict) else {}
        ignore = [1, 6] if bottom_on else []

        def wall(name: str) -> dict[str, Any]:
            raw = walls.get(name) if isinstance(walls.get(name), dict) else {}
            if name=="bottom" and isinstance(bottom_value,dict):raw={**bottom_value,**raw}
            if name in {"top","lid"} and isinstance(lid_value,dict):raw={**lid_value,**raw}
            return _features(raw)

        self.rectangularWall(
            x, h, f"{b}F{wall_top}F", ignore_widths=ignore,
            callback=self._wall_cb(wall("front")), move="up", label="front",
        )
        self._note_part("front")
        self.rectangularWall(
            x, h, f"{b}F{wall_top}F", ignore_widths=ignore,
            callback=self._wall_cb(wall("back")), move="up", label="back",
        )
        self._note_part("back")
        if bottom_on:
            self.rectangularWall(
                x, y, "ffff", callback=self._wall_cb(wall("bottom")), move="up", label="bottom",
            )
            self._note_part("bottom")
        self.rectangularWall(
            y, h, f"{b}f{side_top}f", ignore_widths=ignore,
            callback=self._wall_cb(wall("left")), move="up", label="left",
        )
        self._note_part("left")
        self.rectangularWall(
            y, h, f"{b}f{side_top}f", ignore_widths=ignore,
            callback=self._wall_cb(wall("right")), move="up", label="right",
        )
        self._note_part("right")
        if lid_on:
            self.rectangularWall(
                x, y, lid_edges if lid_type in {"finger","finger_joint","fixed"} else "eeee",
                callback=self._wall_cb(wall("lid")),
                move="up",
                label="lid",
            )
            self._note_part("lid")

    def _coupon(self, part: dict[str, Any]) -> None:
        """Dry-fit FingerJoint pair + 100 mm bar (Boxes.py rectangularWall, not hand-drawn)."""
        x = _num(part.get("x") or part.get("w") or part.get("length"), 40)
        x = max(20.0, min(120.0, x))
        strip_h = max(12.0, float(self.thickness) * 4)
        label = str(part.get("label") or "coupon")
        self.rectangularWall(x, strip_h, "fefe", move="up", label=f"{label}-male")
        self._note_part(f"{label}-male")
        self.rectangularWall(x, strip_h, "FeFe", move="up", label=f"{label}-female")
        self._note_part(f"{label}-female")
        self.rectangularWall(100, 8, "eeee", move="up", label=f"{label}-100mm")
        self._note_part(f"{label}-100mm")


def compile_toolbox(primitives: list[Any], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    """Designer → Reviewer → Repair → Final Gate, then SVG."""
    from pipeline import run_pipeline

    return run_pipeline(primitives, parameters)


def render_toolbox(primitives: list[Any], parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    """One Boxes.py compile. The pipeline calls this; incoming AIs call create_design."""
    if not primitives:
        raise ValueError("primitives is empty")
    from studio import prepare_parameters
    params = prepare_parameters(parameters)
    from explicit_panel_assembly import compile_connections
    primitives, explicit_panel_assembly = compile_connections(
        primitives, params, float(params.get("thickness") or PAYAS_DEFAULTS["thickness"]),
        float(params.get("burn") or PAYAS_DEFAULTS["burn"]),
    )
    parts = _prepare_parts(primitives)
    if not parts:
        raise ValueError("no assembly primitives (box, panel, disc, triangle, propeller, contour, coupon). " + HINT)
    from surface_branding import apply_surface_content
    parts, surface_content = apply_surface_content(parts, params)
    from scale import scale_primitives

    from manufacturing import annotate_primitives

    parts = annotate_primitives(parts)
    parts, scale_info = scale_primitives(parts, params)
    from design_contract import snapshot, compare
    intent_contract = snapshot(parts)
    from assembly import apply_roof_lock, check_assembly

    parts, roof_lock = apply_roof_lock(parts)
    from physical import resolve_burn

    from mechanisms import classify
    moving = any(row.get('rotating') for row in classify(parts))
    thickness = float(params.get("thickness") or PAYAS_DEFAULTS["thickness"])
    burn, physical = resolve_burn(params, moving=moving)
    clearance = float(params.get("joint_clearance_mm") or 0.0)
    effective_burn = round(burn + clearance, 3)
    if not 0.05 <= effective_burn <= 0.60:
        raise ValueError("kerf plus joint_clearance_mm must be between 0.05 and 0.60 mm")
    box = PayasToolbox()
    box.parseArgs(
        [
            f"--thickness={thickness}",
            f"--burn={effective_burn}",
            "--format=svg",
            "--labels=0",
            "--reference=0",
            "--tabs=0",
            "--inner_corners=corner",
            "--qr_code=0",
        ]
    )
    box.parts_spec = parts
    box.open()
    box.render()
    data = box.close()
    svg_bytes = data.getvalue() if hasattr(data, "getvalue") else data.read()
    from nesting import nest_svg
    from topology import inspect_topology

    assembly = check_assembly(parts, thickness=thickness, burn=effective_burn)
    assembly["explicit_panel_assembly"] = explicit_panel_assembly
    from linear_motion import validate as validate_linear_motion
    physical_for_motion = assembly.pop("_physical_primitives", None) or parts
    linear_motion = validate_linear_motion(physical_for_motion, params, thickness)
    assembly["linear_motion"] = linear_motion
    for slide in linear_motion.get("slides") or []:
        for rail in slide.get("rails") or []:
            assembly.setdefault("graph", {}).setdefault("edges", []).append({"from":slide.get("moving_part"),"to":rail,"type":"linear_slide","result":slide.get("status"),"via":"world-space sampled travel"})
    if assembly.get("graph"):
        assembly["graph"]["edge_count"] = len(assembly["graph"].get("edges") or [])
    if linear_motion.get("status") == "FAIL":
        assembly["ok"] = False
        assembly.setdefault("look_again", []).extend(r.get("reason") for r in linear_motion.get("slides") or [] if r.get("status") == "FAIL")
    if roof_lock:
        assembly["roof_lock"] = assembly.get("roof_lock") or roof_lock
    machine = params.get("_machine") or {}
    svg_bytes, nesting = nest_svg(
        svg_bytes,
        bed_width=machine.get("bed_w"),
        bed_height=machine.get("bed_h"),
        gap=float(machine.get("gap_mm") or 3.0),
        panel_names=list(box.drawn_labels),
        allow_rotation=bool(params.get("allow_part_rotation", True)),
    )
    try:
        from text_path import prepare_lasercad_svg

        prepared = prepare_lasercad_svg(svg_bytes)
        if prepared:
            svg_bytes = prepared
    except Exception:
        pass
    manufacturing = None
    try:
        from manufacturing import finish_manufacturing_svg

        stamped, manufacturing = finish_manufacturing_svg(svg_bytes, parts)
        if stamped:
            svg_bytes = stamped
    except Exception:
        manufacturing = None
    from project_options import apply_holding_nicks
    svg_bytes = apply_holding_nicks(svg_bytes, params)
    topology = inspect_topology(svg_bytes)
    metrics = _svg_metrics(svg_bytes.decode("utf-8", errors="replace"))
    return {
        "svg_bytes": svg_bytes,
        "width_mm": metrics.get("width_mm"),
        "height_mm": metrics.get("height_mm"),
        "count": len(parts),
        "card_w": None,
        "card_h": None,
        "preset": "composed",
        "composed": True,
        "method": "compose_primitives",
        "compiler": "create_design",
        "parts": [str(p.get("label") or _kind(p)) for p in parts],
        "path_count": metrics.get("path_count"),
        "assembly": assembly,
        "linear_motion": linear_motion,
        "nesting": nesting,
        "topology": topology,
        "manufacturing": manufacturing,
        "engraving_composition": list(parts[0].get('_engraving_reports') or []) if parts else [],
        "surface_content": surface_content,
        "design_contract": compare(intent_contract, parts),
        "scale": scale_info,
        "primitives": parts,
        "parameters": {
            **params,
            "burn": burn,
            "thickness": thickness,
            "joint_clearance_mm": clearance,
            "effective_burn": effective_burn,
        },
        "physical": physical,
        "note": (
            "This SVG is the parts you passed, compiled with Boxes.py. "
            "It is not a named windmill generator and not a catalog preset."
        ),
    }
