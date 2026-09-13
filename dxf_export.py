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
7
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
    """Best-effort path dump for toolbox SVG. Cut = red, etch = black/green."""
    from xml.etree import ElementTree as ET

    from shapely.geometry import LineString
    from svgpathtools import parse_path

    if not svg_bytes:
        return geoms_to_dxf([], [])
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return geoms_to_dxf([], [])
    cuts: list = []
    etches: list = []
    for el in root.iter():
        if el.tag.split("}")[-1].lower() != "path":
            continue
        d = el.get("d") or ""
        if not d.strip():
            continue
        try:
            path = parse_path(d)
            length = float(path.length())
        except Exception:
            continue
        if length < 0.4:
            continue
        n = max(8, min(240, int(length / max(step_mm, 0.2)) + 1))
        pts = []
        for i in range(n + 1):
            pt = path.point(i / n)
            pts.append((float(pt.real), float(pt.imag)))
        if len(pts) < 2:
            continue
        geom = LineString(pts)
        op = (el.get("data-operation") or "").upper()
        if op == "GUIDE":
            continue
        stroke = f"{el.get('stroke') or ''} {el.get('style') or ''}"
        ident = (el.get("id") or "").upper()
        if op in {"ENGRAVE", "SCORE", "LABEL"} or _stroke_is_etch(stroke) or ident in {"ENGRAVE", "ETCH"}:
            etches.append(geom)
        elif op == "CUT" or not op:
            cuts.append(geom)
    return geoms_to_dxf(cuts, etches)
