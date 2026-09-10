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
