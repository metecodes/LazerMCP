"""LaserCAD-oriented DXF R12 (mm). Cut = red layer, etch = black layer."""

from __future__ import annotations

from typing import Iterable

CUT_LAYER = "CUT"
ETCH_LAYER = "ENGRAVE"


def _pairs(coords) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in coords]
    if len(pts) >= 2 and abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6:
        return pts
    return pts


def _polyline(points: list[tuple[float, float]], layer: str, closed: bool) -> str:
    if len(points) < 2:
        return ""
    pts = list(points)
    if closed and (abs(pts[0][0] - pts[-1][0]) > 1e-6 or abs(pts[0][1] - pts[-1][1]) > 1e-6):
        pts.append(pts[0])
    flag = 1 if closed else 0
    chunks = [
        "0",
        "POLYLINE",
        "8",
        layer,
        "66",
        "1",
        "70",
        str(flag),
    ]
    for x, y in pts[:-1] if closed and abs(pts[0][0] - pts[-1][0]) < 1e-6 else pts:
        chunks.extend(["0", "VERTEX", "8", layer, "10", f"{x:.4f}", "20", f"{y:.4f}"])
    chunks.extend(["0", "SEQEND"])
    return "\n".join(chunks)


def _geom_entities(geom, layer: str) -> list[str]:
    if geom is None or getattr(geom, "is_empty", False):
        return []
    kind = geom.geom_type
    if kind == "LineString":
        pts = _pairs(geom.coords)
        closed = abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6
        body = _polyline(pts, layer, closed)
        return [body] if body else []
    if kind == "LinearRing":
        body = _polyline(_pairs(geom.coords), layer, True)
        return [body] if body else []
    if kind == "Polygon":
        out = _geom_entities(geom.exterior, layer)
        for ring in geom.interiors:
            out.extend(_geom_entities(ring, layer))
        return out
    if kind in {"MultiPolygon", "MultiLineString", "GeometryCollection"}:
        bits = []
        for part in geom.geoms:
            bits.extend(_geom_entities(part, layer))
        return bits
    return []


def geoms_to_dxf(cut_geoms: Iterable, etch_geoms: Iterable) -> bytes:
    entities: list[str] = []
    for g in cut_geoms or []:
        entities.extend(_geom_entities(g, CUT_LAYER))
    for g in etch_geoms or []:
        entities.extend(_geom_entities(g, ETCH_LAYER))
    body = "\n".join(e for e in entities if e)
    dxf = f"""0
SECTION
2
HEADER
9
$ACADVER
1
AC1009
9
$INSUNITS
70
4
9
$MEASUREMENT
70
1
0
ENDSEC
0
SECTION
2
TABLES
0
TABLE
2
LAYER
70
2
0
LAYER
2
{CUT_LAYER}
70
0
62
1
6
CONTINUOUS
0
LAYER
2
{ETCH_LAYER}
70
0
62
2
6
CONTINUOUS
0
ENDTAB
0
ENDSEC
0
SECTION
2
ENTITIES
{body}
0
ENDSEC
0
EOF
"""
    return dxf.encode("utf-8")


def _stroke_is_etch(stroke: str) -> bool:
    raw = (stroke or "").lower().replace(" ", "")
    if "00ff00" in raw or "rgb(0,255,0)" in raw:
        return True
    if "ff0000" in raw or "rgb(255,0,0)" in raw:
        return False
    if "rgb(0,0,0)" in raw or "#000000" in raw:
        return True
    return False


def svg_bytes_to_dxf(svg_bytes: bytes, step_mm: float = 0.6) -> bytes:
    """Preserve line vertices and disconnected subpaths; flatten curves per segment."""
    import math
    import re
    import numpy as np
    from xml.etree import ElementTree as ET
    from shapely.geometry import LineString
    from svgpathtools import parse_path, Line
    from svgpathtools.parser import parse_transform
    from svgpathtools.path import transform
    if not svg_bytes:
        return geoms_to_dxf([], [])
    root = ET.fromstring(svg_bytes)
    parents = {child: parent for parent in root.iter() for child in parent}
    def mm(value):
        match = re.fullmatch(r"\s*([0-9.eE+\-]+)\s*(mm|cm|in|px|pt)?\s*", value or "")
        if not match:
            return None
        return float(match[1]) * {None: 25.4/96, "px": 25.4/96, "mm": 1, "cm": 10, "in": 25.4, "pt": 25.4/72}[match[2]]
    vb = [float(v) for v in (root.get("viewBox") or "").replace(",", " ").split()]
    width, height = mm(root.get("width")), mm(root.get("height"))
    viewport = np.eye(3)
    if len(vb) == 4 and vb[2] > 0 and vb[3] > 0:
        sx, sy = (width or vb[2])/vb[2], (height or vb[3])/vb[3]
        if (root.get("preserveAspectRatio") or "xMidYMid meet") != "none":
            sx = sy = max(sx, sy) if "slice" in (root.get("preserveAspectRatio") or "") else min(sx, sy)
        viewport[0, 0], viewport[1, 1] = sx, sy
        align = root.get("preserveAspectRatio") or "xMidYMid meet"
        viewport[0, 2] = -vb[0]*sx + (0 if "xMin" in align or align == "none" else (width or vb[2])-vb[2]*sx) / (1 if "xMax" in align else 2)
        viewport[1, 2] = -vb[1]*sy + (0 if "YMin" in align or align == "none" else (height or vb[3])-vb[3]*sy) / (1 if "YMax" in align else 2)
    else:
        viewport[0, 0] = viewport[1, 1] = 25.4/96
    cuts, etches = [], []
    from manufacturing import classify_element
    for el in root.iter():
        if el.tag.split("}")[-1].lower() != "path" or not (el.get("d") or "").strip():
            continue
        op = classify_element(el, parents)[0]
        if op not in {"CUT", "ENGRAVE", "SCORE", "LABEL"}:
            continue
        chain, node = [], el
        while node is not None:
            chain.append(node)
            node = parents.get(node)
        matrix = viewport.copy()
        for node in reversed(chain):
            matrix = matrix @ parse_transform(node.get("transform") or "")
        path = transform(parse_path(el.get("d")), matrix)
        for subpath in path.continuous_subpaths():
            pts = []
            for segment in subpath:
                count = 1 if isinstance(segment, Line) else max(2, math.ceil(segment.length()/max(step_mm, .02)))
                if not pts:
                    pts.append(segment.start)
                pts.extend(segment.point(i/count) for i in range(1, count+1))
            if len(pts) >= 2:
                geom = LineString([(float(pt.real), (height or 0)-float(pt.imag)) for pt in pts])
                (cuts if op == "CUT" else etches).append(geom)
    return geoms_to_dxf(cuts, etches)
