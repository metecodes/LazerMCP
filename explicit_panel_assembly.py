"""Compile declared connections between explicitly placed rectangular panels."""
from __future__ import annotations

from copy import deepcopy
import math
from typing import Any

EDGE_NAMES = ("bottom", "right", "top", "left")


def _v3(value: Any) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("placement origin/u/v must contain three numbers")
    return [float(x) for x in value]


def _add(a, b, scale=1.0): return [a[i] + b[i] * scale for i in range(3)]
def _dist(a, b): return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def _edges(part: dict[str, Any]) -> list[dict[str, Any]]:
    pose = part.get("placement") or {}
    origin, u, v = _v3(pose.get("origin")), _v3(pose.get("u")), _v3(pose.get("v"))
    w = float(part.get("w") or part.get("x") or part.get("width") or 0)
    h = float(part.get("h") or part.get("y") or part.get("height") or 0)
    if w <= 0 or h <= 0:
        raise ValueError(f"{part.get('label')}: panel dimensions must be positive")
    p00, p10, p11, p01 = origin, _add(origin, u, w), _add(_add(origin, u, w), v, h), _add(origin, v, h)
    return [
        {"index": 0, "name": "bottom", "a": p00, "b": p10, "length_mm": w},
        {"index": 1, "name": "right", "a": p10, "b": p11, "length_mm": h},
        {"index": 2, "name": "top", "a": p01, "b": p11, "length_mm": w},
        {"index": 3, "name": "left", "a": p00, "b": p01, "length_mm": h},
    ]


def _edge_error(a: dict[str, Any], b: dict[str, Any]) -> float:
    return min(max(_dist(a["a"], b["a"]), _dist(a["b"], b["b"])),
               max(_dist(a["a"], b["b"]), _dist(a["b"], b["a"])))


def _part_name(row: dict[str, Any], side: str) -> str:
    aliases = (side, f"part_{side}", "male" if side == "a" else "female", "from" if side == "a" else "to")
    return str(next((row.get(key) for key in aliases if row.get(key)), ""))


def _port_keepouts(part: dict[str, Any], safety: float) -> list[dict[str, Any]]:
    from enclosure_features import normalize
    result = []
    for slot in normalize(part).get("slots") or []:
        if str(slot.get("semantic_role") or "") != "port_cutout":
            continue
        x, y = float(slot.get("x") or slot.get("cx") or 0), float(slot.get("y") or slot.get("cy") or 0)
        w, h = float(slot.get("w") or 0), float(slot.get("h") or 0)
        result.append({"id": str(slot.get("id") or "port"), "target_part": str(part.get("label")),
                       "bbox": [x-w/2-safety, y-h/2-safety, x+w/2+safety, y+h/2+safety]})
    return result


def _keepout_hits_edge(part: dict[str, Any], edge_index: int, keepout: dict[str, Any], thickness: float) -> bool:
    w = float(part.get("w") or part.get("x") or part.get("width") or 0)
    h = float(part.get("h") or part.get("y") or part.get("height") or 0)
    x0, y0, x1, y1 = keepout["bbox"]
    if edge_index == 0: return y0 <= thickness and x1 >= 0 and x0 <= w
    if edge_index == 2: return y1 >= h - thickness and x1 >= 0 and x0 <= w
    if edge_index == 3: return x0 <= thickness and y1 >= 0 and y0 <= h
    return x1 >= w - thickness and y1 >= 0 and y0 <= h


def compile_connections(primitives: list[Any], parameters: dict[str, Any] | None, thickness: float = 3.0, burn: float = .15) -> tuple[list[Any], dict[str, Any]]:
    parts = deepcopy(primitives or [])
    params = parameters or {}
    declared = [c for c in params.get("connections") or [] if isinstance(c, dict) and str(c.get("type") or "") == "finger_joint"]
    panels = {str(p.get("label") or p.get("id") or ""): p for p in parts if isinstance(p, dict) and str(p.get("type") or p.get("kind") or "").lower() in {"panel", "wall", "rect"}}
    report = {"active": bool(declared), "status": "N/A", "joints": [], "errors": [], "port_keepouts": [], "port_inventory": {}}
    if not declared:
        return parts, report
    safety = float(params.get("finger_port_safety_margin_mm") or 3.0)
    original_ports = {name: [str(p.get("id") or f"port-{i+1}") for i, p in enumerate(part.get("ports") or []) if isinstance(p, dict)] for name, part in panels.items()}
    report["port_inventory"] = deepcopy(original_ports)
    occupied: set[tuple[str, int]] = set()
    for number, connection in enumerate(declared, 1):
        a_name, b_name = _part_name(connection, "a"), _part_name(connection, "b")
        a, b = panels.get(a_name), panels.get(b_name)
        joint_id = str(connection.get("id") or f"C{number:02d}")
        if not a or not b:
            report["errors"].append(f"{joint_id}: missing explicit panel {a_name or '?'} or {b_name or '?'}")
            continue
        try:
            def normal(panel):
                u, v = panel["placement"]["u"], panel["placement"]["v"]
                n = [u[1]*v[2]-u[2]*v[1], u[2]*v[0]-u[0]*v[2], u[0]*v[1]-u[1]*v[0]]
                length = sum(x*x for x in n)**.5
                if length <= 1e-9:
                    raise ValueError("invalid placement normal")
                return [x/length for x in n]
            if abs(sum(x*y for x,y in zip(normal(a), normal(b)))) > .001:
                report["errors"].append(f"{joint_id}: FINGER_JOINT_ORIENTATION_INVALID: mating panels must be perpendicular")
                continue
            candidates = []
            for ea in _edges(a):
                for eb in _edges(b):
                    delta = abs(ea["length_mm"] - eb["length_mm"])
                    if delta <= .05 and (a_name, ea["index"]) not in occupied and (b_name, eb["index"]) not in occupied:
                        candidates.append((_edge_error(ea, eb), ea, eb))
            candidates.sort(key=lambda row: row[0])
            if not candidates or candidates[0][0] > float(thickness) + .35:
                report["errors"].append(f"{joint_id}: {a_name} and {b_name} have no contacting equal-length edges")
                continue
            error, ea, eb = candidates[0]
            occupied.update({(a_name, ea["index"]), (b_name, eb["index"])})
            a_edges, b_edges = list(str(a.get("edges") or "eeee")[:4].ljust(4, "e")), list(str(b.get("edges") or "eeee")[:4].ljust(4, "e"))
            a_edges[ea["index"]], b_edges[eb["index"]] = "f", "F"
            a["edges"], b["edges"] = "".join(a_edges), "".join(b_edges)
            keepouts_a, keepouts_b = _port_keepouts(a, safety), _port_keepouts(b, safety)
            report["port_keepouts"].extend(keepouts_a + keepouts_b)
            unsafe = [row for row in keepouts_a if _keepout_hits_edge(a, ea["index"], row, thickness)] + [row for row in keepouts_b if _keepout_hits_edge(b, eb["index"], row, thickness)]
            if unsafe:
                report["errors"].append(f"{joint_id}: port keep-out intersects the only mating edge: "+", ".join(row["id"] for row in unsafe))
                continue
            pitch = max(float(thickness) * 2.0, 6.0)
            count = max(1, int(ea["length_mm"] // pitch))
            if count % 2 == 0: count = max(1, count - 1)
            joint = {"id": joint_id, "part_a": a_name, "edge_a": ea["name"], "part_b": b_name, "edge_b": eb["name"],
                     "joint_type": "finger_joint", "male": a_name, "male_edge": ea["name"], "female": b_name,
                     "female_edge": eb["name"], "length_mm": ea["length_mm"], "finger_count": count,
                     "finger_pitch_mm": ea["length_mm"] / count, "finger_width_mm": ea["length_mm"] / (count * 2 + 1),
                     "finger_depth_mm": float(thickness), "material_thickness_mm": float(thickness),
                     "kerf_compensation_mm": float(burn), "world_edge_error_mm": error, "result": "MATCH",
                     "via": "declared connection + placement-derived equal-length contacting edges",
                     "keepout_strategy": "reduce_count_then_shift", "port_keepout_clear": not unsafe}
            report["joints"].append(joint)
        except (TypeError, ValueError) as exc:
            report["errors"].append(f"{joint_id}: {exc}")
    current_ports = {name: [str(p.get("id") or f"port-{i+1}") for i, p in enumerate(part.get("ports") or []) if isinstance(p, dict)] for name, part in panels.items()}
    if current_ports != original_ports:
        report["errors"].append("PORT_MIGRATION: slot target_part is immutable")
    report["status"] = "PASS" if len(report["joints"]) == len(declared) and not report["errors"] else "FAIL"
    if parts:
        first = next((p for p in parts if isinstance(p, dict)), None)
        if first is not None: first["_explicit_panel_assembly"] = report
    return parts, report
