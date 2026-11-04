"""Extrude laser SVG CUT contours to STL. Coordinates stay millimetres — never invent XY scale."""

from __future__ import annotations

import math
import struct
from typing import Any
from xml.etree import ElementTree as ET

from shapely.geometry import Polygon
from shapely.ops import unary_union
from svgpathtools import parse_path


def _is_cut(el: ET.Element) -> bool:
    try:
        from manufacturing import element_is_cut

        return bool(element_is_cut(el))
    except Exception:
        stroke = (el.get("stroke") or "").lower()
        cls = (el.get("class") or "").lower()
        op = (el.get("data-operation") or el.get("data-op") or "").upper()
        if op == "CUT":
            return True
        if "cut" in cls:
            return True
        return stroke in {"#ff0000", "#f00", "red", "#e10600", "rgb(255,0,0)"}


def _path_polygons(d: str) -> list[Polygon]:
    try:
        path = parse_path(d)
    except Exception:
        return []
    polys: list[Polygon] = []
    for sub in path.continuous_subpaths() if path else []:
        pts: list[tuple[float, float]] = []
        # Sample polyline approximation of curves
        steps = max(8, int(sub.length() / 0.8) if sub.length() else 8)
        for i in range(steps + 1):
            pt = sub.point(i / steps)
            pts.append((float(pt.real), float(pt.imag)))
        if len(pts) < 3:
            continue
        if pts[0] != pts[-1]:
            pts.append(pts[0])
        poly = Polygon(pts)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty or poly.area < 1e-4:
            continue
        if poly.geom_type == "MultiPolygon":
            polys.extend(p for p in poly.geoms if p.area > 1e-4)
        elif poly.geom_type == "Polygon":
            polys.append(poly)
    return polys


def extract_cut_polygons(svg_bytes: bytes) -> list[Polygon]:
    root = ET.fromstring(svg_bytes)
    polys: list[Polygon] = []
    for el in root.iter():
        tag = el.tag.split("}")[-1].lower()
        if tag != "path":
            continue
        if not _is_cut(el):
            continue
        d = el.get("d") or ""
        if not d.strip():
            continue
        polys.extend(_path_polygons(d))
    if not polys:
        raise ValueError("No CUT polygons found in SVG")
    # Nest holes: larger outlines contain smaller as holes when fully inside
    polys = sorted(polys, key=lambda p: p.area, reverse=True)
    used = [False] * len(polys)
    solids: list[Polygon] = []
    for i, outer in enumerate(polys):
        if used[i]:
            continue
        holes = []
        for j, inner in enumerate(polys):
            if j <= i or used[j]:
                continue
            if outer.contains(inner):
                holes.append(list(inner.exterior.coords))
                used[j] = True
        solid = Polygon(outer.exterior.coords, holes=holes)
        if not solid.is_valid:
            solid = solid.buffer(0)
        if solid.is_empty:
            continue
        if solid.geom_type == "MultiPolygon":
            solids.extend(list(solid.geoms))
        else:
            solids.append(solid)
        used[i] = True
    if not solids:
        raise ValueError("CUT paths could not form solid polygons")
    return solids


def _earclip(ring: list[tuple[float, float]]) -> list[tuple[int, int, int]]:
    """Simple ear clipping for a simple ring (no holes). Returns index triples."""
    pts = list(ring)
    if len(pts) >= 2 and pts[0] == pts[-1]:
        pts = pts[:-1]
    n = len(pts)
    if n < 3:
        return []
    idxs = list(range(n))

    def area2(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def inside(p, a, b, c):
        # barycentric-ish orientation checks
        return (
            area2(a, b, p) >= -1e-9
            and area2(b, c, p) >= -1e-9
            and area2(c, a, p) >= -1e-9
        ) or (
            area2(a, b, p) <= 1e-9
            and area2(b, c, p) <= 1e-9
            and area2(c, a, p) <= 1e-9
        )

    # Ensure CCW
    s = 0.0
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    if s < 0:
        pts.reverse()
        idxs = list(range(n))

    tris: list[tuple[int, int, int]] = []
    guard = 0
    while len(idxs) > 3 and guard < 10000:
        guard += 1
        ear_found = False
        m = len(idxs)
        for i in range(m):
            i0, i1, i2 = idxs[(i - 1) % m], idxs[i], idxs[(i + 1) % m]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if area2(a, b, c) <= 1e-12:
                continue
            is_ear = True
            for j in idxs:
                if j in (i0, i1, i2):
                    continue
                if inside(pts[j], a, b, c):
                    is_ear = False
                    break
            if not is_ear:
                continue
            tris.append((i0, i1, i2))
            del idxs[i]
            ear_found = True
            break
        if not ear_found:
            break
    if len(idxs) == 3:
        tris.append((idxs[0], idxs[1], idxs[2]))
    return tris


def _triangulate_polygon(poly: Polygon) -> tuple[list[tuple[float, float]], list[tuple[int, int, int]]]:
    """Triangulate by ear-clipping exterior then subtracting holes via shapely tessellation fallback."""
    # Prefer shapely + manual for simple polys; for holes, fan from representative point after buffer explode.
    if not poly.interiors:
        ring = list(poly.exterior.coords)
        pts = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
        tris = _earclip(ring)
        return pts, tris

    from shapely.geometry import Point

    # Triangulate exterior, drop triangles whose centroid falls inside a hole.
    ring = list(poly.exterior.coords)
    pts = ring[:-1] if ring and ring[0] == ring[-1] else list(ring)
    tris = _earclip(ring)
    kept: list[tuple[int, int, int]] = []
    holes = [Polygon(h) for h in poly.interiors]
    for a, b, c in tris:
        cx = (pts[a][0] + pts[b][0] + pts[c][0]) / 3
        cy = (pts[a][1] + pts[b][1] + pts[c][1]) / 3
        pt = Point(cx, cy)
        if any(h.contains(pt) or h.covers(pt) for h in holes):
            continue
        kept.append((a, b, c))
    return pts, kept


def _normal(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    return (nx / length, ny / length, nz / length)


def mesh_from_polygons(polys: list[Polygon], height_mm: float) -> list[tuple]:
    """Return list of triangles as ((nx,ny,nz), (v1,v2,v3))."""
    h = float(height_mm)
    if h <= 0.05:
        raise ValueError("extrusion height_mm must be > 0.05")
    tris_out: list[tuple] = []
    for poly in polys:
        if poly.is_empty:
            continue
        geoms = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
        for g in geoms:
            pts2, faces = _triangulate_polygon(g)
            # Top (+z) and bottom (-z)
            for a, b, c in faces:
                v1 = (pts2[a][0], pts2[a][1], h)
                v2 = (pts2[b][0], pts2[b][1], h)
                v3 = (pts2[c][0], pts2[c][1], h)
                tris_out.append((_normal(v1, v2, v3), (v1, v2, v3)))
                b1 = (pts2[a][0], pts2[a][1], 0.0)
                b2 = (pts2[c][0], pts2[c][1], 0.0)
                b3 = (pts2[b][0], pts2[b][1], 0.0)
                tris_out.append((_normal(b1, b2, b3), (b1, b2, b3)))
            # Side walls from exterior + interiors
            rings = [list(g.exterior.coords)] + [list(r.coords) for r in g.interiors]
            for ring in rings:
                for i in range(len(ring) - 1):
                    x1, y1 = ring[i]
                    x2, y2 = ring[i + 1]
                    v1 = (x1, y1, 0.0)
                    v2 = (x2, y2, 0.0)
                    v3 = (x2, y2, h)
                    v4 = (x1, y1, h)
                    tris_out.append((_normal(v1, v2, v3), (v1, v2, v3)))
                    tris_out.append((_normal(v1, v3, v4), (v1, v3, v4)))
    if not tris_out:
        raise ValueError("No triangles produced from CUT geometry")
    return tris_out


def write_binary_stl(triangles: list[tuple], name: str = "LaserMCP") -> bytes:
    header = (name[:80].ljust(80)).encode("ascii", "replace")[:80]
    body = [header, struct.pack("<I", len(triangles))]
    for n, (v1, v2, v3) in triangles:
        body.append(
            struct.pack(
                "<12fH",
                float(n[0]),
                float(n[1]),
                float(n[2]),
                float(v1[0]),
                float(v1[1]),
                float(v1[2]),
                float(v2[0]),
                float(v2[1]),
                float(v2[2]),
                float(v3[0]),
                float(v3[1]),
                float(v3[2]),
                0,
            )
        )
    return b"".join(body)


def suggest_height_mm(ai_hint: str, default: float, bounds: tuple[float, float, float, float]) -> dict[str, Any]:
    """Heuristic 'AI' assist: parse height from hint; never alter XY from SVG bounds."""
    import re

    text = (ai_hint or "").lower()
    found = None
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*mm", text):
        found = float(match.group(1))
    if found is None:
        for key, val in (("ince", 1.5), ("thin", 1.5), ("kalın", 4.0), ("thick", 4.0), ("standart", default)):
            if key in text:
                found = float(val)
                break
    height = float(found) if found is not None else float(default)
    height = max(0.4, min(40.0, height))
    minx, miny, maxx, maxy = bounds
    return {
        "height_mm": height,
        "xy_from_svg_mm": True,
        "bbox_mm": {
            "min_x": round(minx, 3),
            "min_y": round(miny, 3),
            "max_x": round(maxx, 3),
            "max_y": round(maxy, 3),
            "width": round(maxx - minx, 3),
            "depth": round(maxy - miny, 3),
        },
        "note": "XY scale locked to SVG millimetres. Only extrusion height may follow the hint.",
        "source": "hint" if found is not None else "default_thickness",
    }


def svg_bytes_to_stl(
    svg_bytes: bytes,
    *,
    height_mm: float | None = None,
    ai_hint: str = "",
    default_thickness_mm: float = 3.0,
) -> dict[str, Any]:
    polys = extract_cut_polygons(svg_bytes)
    merged = unary_union(polys)
    bounds = merged.bounds
    ai = suggest_height_mm(ai_hint, height_mm or default_thickness_mm, bounds)
    h = float(height_mm) if height_mm not in (None, "") else float(ai["height_mm"])
    geoms = list(merged.geoms) if merged.geom_type == "MultiPolygon" else [merged]
    tris = mesh_from_polygons(geoms, h)
    raw = write_binary_stl(tris, name="LaserMCP_mm")
    return {
        "stl_bytes": raw,
        "height_mm": h,
        "part_count": len(geoms),
        "triangle_count": len(tris),
        "scale": {"units": "mm", "xy": "svg_native", "z": h},
        "ai": ai,
    }
