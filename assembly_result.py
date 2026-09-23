"""Serializable hand-off from Automatic Assembly to assembled rendering.

Rendering consumes this result and never re-solves joint geometry.  The result
is evidence from a completed automatic assembly run, not a replacement for
physical dry-fit verification.
"""
from __future__ import annotations

import math
from copy import deepcopy
from typing import Any


def _rotation_degrees(u, v, n):
    """ZYX Euler angles for diagnostic display; the matrix remains authoritative."""
    pitch = math.asin(max(-1.0, min(1.0, -float(u[2]))))
    cosine = math.cos(pitch)
    if abs(cosine) > 1e-8:
        roll = math.atan2(float(v[2]), float(n[2]))
        yaw = math.atan2(float(u[1]), float(u[0]))
    else:
        roll = 0.0
        yaw = math.atan2(-float(v[0]), float(v[1]))
    return [round(math.degrees(angle), 6) for angle in (roll, pitch, yaw)]


def _transform(part: dict[str, Any]) -> dict[str, Any] | None:
    pose = part.get("placement") or {}
    try:
        origin = [float(value) for value in pose["origin"]]
        u = [float(value) for value in pose["u"]]
        v = [float(value) for value in pose["v"]]
        if any(len(row) != 3 for row in (origin, u, v)):
            return None
        n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]]
        if not all(math.isfinite(value) for value in origin + u + v + n):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "position": origin,
        "rotation": _rotation_degrees(u, v, n),
        "matrix": [[u[0], v[0], n[0], origin[0]], [u[1], v[1], n[1], origin[1]], [u[2], v[2], n[2], origin[2]], [0, 0, 0, 1]],
        "placement_source": part.get("placement_source") or pose.get("source") or "explicit",
    }


def _geometry_from_transform(row: dict[str, Any]) -> dict[str, Any] | None:
    """Build renderer input from the stored matrix, never stale nested coords."""
    geometry = row.get("geometry")
    matrix = (row.get("transform") or {}).get("matrix")
    if not isinstance(geometry, dict) or not isinstance(matrix, list) or len(matrix) != 4:
        return None
    try:
        if any(not isinstance(column, list) or len(column) != 4 for column in matrix):
            return None
        values = [float(value) for column in matrix for value in column]
        if not all(math.isfinite(value) for value in values):
            return None
        u = [matrix[0][0], matrix[1][0], matrix[2][0]]
        v = [matrix[0][1], matrix[1][1], matrix[2][1]]
        origin = [matrix[0][3], matrix[1][3], matrix[2][3]]
    except (TypeError, ValueError, IndexError):
        return None
    output = deepcopy(geometry)
    output["placement"] = {
        "origin": origin, "u": u, "v": v,
        "source": (row.get("transform") or {}).get("placement_source") or "automatic_assembly",
    }
    return output


def build(assembly: dict[str, Any] | None, *, file_id: str | None = None, project_id: str | None = None) -> dict[str, Any]:
    """Create the durable Automatic Assembly result from one completed run."""
    assembly = assembly or {}
    source = [deepcopy(part) for part in (assembly.get("_physical_primitives") or []) if isinstance(part, dict)]
    joints = [deepcopy(row) for row in (assembly.get("joints") or []) if isinstance(row, dict)]
    connections = []
    for index, joint in enumerate(joints, 1):
        first, second = str(joint.get("male") or ""), str(joint.get("female") or "")
        if not first or not second:
            continue
        connections.append({
            "connection_id": str(joint.get("id") or f"C{index:02d}"),
            "part_a": first, "part_b": second,
            "joint_type": joint.get("joint_type") or joint.get("kind") or "finger_joint",
            "mating_features": {"a": joint.get("feature_a") or joint.get("connector_ids"), "b": joint.get("feature_b")},
            "validation_state": "PASS" if str(joint.get("result") or "").upper() in {"MATCH", "PASS"} else "FAIL",
            "source": joint.get("source") or joint.get("via"),
        })
    linked = {name for row in connections if row["validation_state"] == "PASS" for name in (row["part_a"], row["part_b"])}
    parts = []
    missing = []
    for index, part in enumerate(source, 1):
        part_id = str(part.get("physical_part_id") or part.get("part_id") or part.get("label") or f"part-{index}")
        transform = _transform(part)
        if transform is None:
            missing.append(part_id)
        parts.append({
            "part_id": part_id,
            "parent_part_id": part.get("composite_parent"),
            "geometry": part,
            "geometry_reference": {"outer_cut": (part.get("_cut_geometry") or {}).get("outer_cut"), "physical_part_id": part.get("physical_part_id")},
            "transform": transform,
            "connected_part_ids": sorted({row["part_b"] if row["part_a"] == part_id else row["part_a"] for row in connections if part_id in {row["part_a"], row["part_b"]}}),
        })
    transform_validation = assembly.get("transform_validation") or {}
    constraint_conflict = str(transform_validation.get("status") or "").upper() == "FAIL"
    collisions = [deepcopy(row) for row in (assembly.get("illegal_collisions") or []) if isinstance(row, dict)]
    validated = bool(assembly.get("ok")) and bool(parts) and not missing and not constraint_conflict and not collisions
    unconnected = [row["part_id"] for row in parts if row["part_id"] not in linked and len(parts) > 1]
    debug = {"part_count": len(parts), "connected_parts": len(parts) - len(unconnected), "unconnected_parts": unconnected,
             "joint_count": len(connections), "matched_joint_count": sum(row["validation_state"] == "PASS" for row in connections),
             "transform_count": len(parts) - len(missing), "missing_transforms": missing,
             "constraint_conflict": constraint_conflict, "collision_count": len(collisions)}
    return {"file_id": file_id, "project_id": project_id, "validated": validated,
            "validation_state": "PASS" if validated else "FAIL", "parts": parts, "connections": connections,
            "assembly_order": list((assembly.get("canonical_mates") or {}).get("sequence", {}).get("order") or []) or [row["part_id"] for row in parts],
            "thickness": assembly.get("thickness"), "debug": debug, "source": "automatic_assembly"}


def render(result: dict[str, Any] | None, view: str = "assembled") -> dict[str, Any]:
    """Render persisted transforms only; never invoke the assembly solver here."""
    data = result or {}
    if not data:
        return {"success": False, "code": "ASSEMBLY_RESULT_NOT_FOUND", "debug": {"part_count": 0}}
    debug = dict(data.get("debug") or {})
    if debug.get("constraint_conflict"):
        return {"success": False, "code": "ASSEMBLY_CONSTRAINT_CONFLICT", "debug": debug}
    if int(debug.get("collision_count") or 0) > 0:
        return {"success": False, "code": "COLLISION_DETECTED", "debug": debug}
    if not data.get("validated"):
        return {"success": False, "code": "ASSEMBLY_RESULT_NOT_VALIDATED", "debug": debug}
    rows = data.get("parts") or []
    if not isinstance(rows, list) or not rows:
        return {"success": False, "code": "CONNECTION_GRAPH_INCOMPLETE", "debug": debug}
    geometries = [_geometry_from_transform(row) if isinstance(row, dict) else None for row in rows]
    missing = [str(row.get("part_id")) for row, geometry in zip(rows, geometries) if geometry is None]
    if missing:
        debug["missing_transforms"] = missing
        return {"success": False, "code": "PART_TRANSFORM_MISSING", "debug": debug}
    if len(rows) > 1 and debug.get("matched_joint_count", 0) == 0:
        return {"success": False, "code": "JOINT_PAIR_NOT_FOUND", "debug": debug}
    parts = geometries
    try:
        from assembled_view import exploded_preview, preview
        thickness = float((data.get("thickness") or 3))
        svg = exploded_preview(parts, thickness) if view == "exploded" else preview(parts, thickness, caption="Automatic Assembly preview")
    except Exception:
        return {"success": False, "code": "RENDER_FAILED", "debug": debug}
    if not svg:
        return {"success": False, "code": "RENDER_FAILED", "debug": debug}
    return {"success": True, "preview_kind": view, "svg": svg, "debug": debug,
            "note": "Preview uses the persisted Automatic Assembly transforms; physical dry-fit is not verified."}
