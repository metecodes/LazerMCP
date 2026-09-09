"""Trace a reference photo into Payas STEM laser SVG (cut + etch)."""

from __future__ import annotations

import base64
import io
from typing import Any

import numpy as np
from PIL import Image, ImageFilter, ImageOps
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from boxes_adapter import PAYAS_DEFAULTS

# Marching-squares edge midpoints: top, right, bottom, left (cell 0..1).
_TOP, _RIGHT, _BOTTOM, _LEFT = (0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5)
_CASES: dict[int, tuple[tuple[tuple[float, float], tuple[float, float]], ...]] = {
    0: (),
    1: ((_LEFT, _BOTTOM),),
    2: ((_BOTTOM, _RIGHT),),
    3: ((_LEFT, _RIGHT),),
    4: ((_TOP, _RIGHT),),
    5: ((_LEFT, _TOP), (_BOTTOM, _RIGHT)),
    6: ((_TOP, _BOTTOM),),
    7: ((_LEFT, _TOP),),
    8: ((_LEFT, _TOP),),
    9: ((_TOP, _BOTTOM),),
    10: ((_LEFT, _BOTTOM), (_TOP, _RIGHT)),
    11: ((_TOP, _RIGHT),),
    12: ((_LEFT, _RIGHT),),
    13: ((_BOTTOM, _RIGHT),),
    14: ((_LEFT, _BOTTOM),),
    15: (),
}


def _decode_image(image_base64: str | None = None, image_bytes: bytes | None = None) -> Image.Image:
    data: bytes | None = None
    if image_bytes:
        data = image_bytes
    elif image_base64:
        raw = image_base64.strip().replace("\n", "").replace(" ", "")
        if "," in raw and raw.lower().startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            data = base64.b64decode(raw, validate=False)
        except Exception as exc:
            raise ValueError("image_base64 is not valid base64") from exc
    if not data:
        raise ValueError("A reference image is required (image_base64 or uploaded file).")
    if len(data) > 12_000_000:
        raise ValueError("Image is larger than 12 MB")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as exc:
        raise ValueError("Could not read image (use PNG, JPEG, or WebP)") from exc
    return img.convert("RGB")


def _binary_mask(img: Image.Image, invert: bool | None, threshold: int) -> np.ndarray:
    gray = ImageOps.grayscale(img.filter(ImageFilter.MedianFilter(size=3)))
    arr = np.asarray(gray, dtype=np.float32)
    if invert is None:
        invert = bool(arr.mean() > 127)
    if invert:
        arr = 255.0 - arr
    mask = (arr < float(threshold)).astype(np.uint8)
    return mask


def _marching_segments(mask: np.ndarray) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    padded = np.pad(mask, 1, mode="constant")
    h, w = padded.shape
    segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for y in range(h - 1):
        row = padded[y]
        row2 = padded[y + 1]
        for x in range(w - 1):
            idx = int(row[x]) * 8 + int(row[x + 1]) * 4 + int(row2[x + 1]) * 2 + int(row2[x])
            for a, b in _CASES.get(idx, ()):
                segs.append(((x + a[0] - 1.0, y + a[1] - 1.0), (x + b[0] - 1.0, y + b[1] - 1.0)))
    return segs


def _key(pt: tuple[float, float]) -> tuple[int, int]:
    return (round(pt[0] * 1000), round(pt[1] * 1000))


def _stitch(segments: list[tuple[tuple[float, float], tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    adj: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for a, b in segments:
        adj.setdefault(_key(a), []).append(b)
        adj.setdefault(_key(b), []).append(a)
    used: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    polylines: list[list[tuple[float, float]]] = []

    def take_edge(k0: tuple[int, int], pt1: tuple[float, float]) -> None:
        k1 = _key(pt1)
        edge = (k0, k1) if k0 <= k1 else (k1, k0)
        used.add(edge)

    for a, b in segments:
        start_k = _key(a)
        first_edge = (start_k, _key(b)) if start_k <= _key(b) else (_key(b), start_k)
        if first_edge in used:
            continue
        line = [a, b]
        take_edge(start_k, b)
        cur = b
        cur_k = _key(b)
        while True:
            nxt = None
            for cand in adj.get(cur_k, []):
                ck = _key(cand)
                edge = (cur_k, ck) if cur_k <= ck else (ck, cur_k)
                if edge not in used:
                    nxt = cand
                    take_edge(cur_k, cand)
                    break
            if nxt is None:
                break
            line.append(nxt)
            cur = nxt
            cur_k = _key(nxt)
            if _key(line[-1]) == _key(line[0]) and len(line) > 3:
                break
        if len(line) >= 8:
            polylines.append(line)
    return polylines


def _to_geometry(line: list[tuple[float, float]], px_to_mm: float, simplify_mm: float):
    coords = [(p[0] * px_to_mm, p[1] * px_to_mm) for p in line]
    closed = abs(coords[0][0] - coords[-1][0]) < 1e-6 and abs(coords[0][1] - coords[-1][1]) < 1e-6
    if closed and len(coords) >= 4:
        geom = Polygon(coords)
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty or geom.area < 0.4:
            return None
        geom = geom.simplify(simplify_mm, preserve_topology=True)
        return geom
    ls = LineString(coords)
    if ls.length < 1.0:
        return None
    return ls.simplify(simplify_mm)


def _path_d(coords) -> str:
    pts = list(coords)
    if len(pts) < 2:
        return ""
    parts = [f"M {pts[0][0]:.3f} {pts[0][1]:.3f}"]
    for x, y in pts[1:]:
        parts.append(f"L {x:.3f} {y:.3f}")
    if abs(pts[0][0] - pts[-1][0]) < 1e-6 and abs(pts[0][1] - pts[-1][1]) < 1e-6:
        parts.append("Z")
    return " ".join(parts)


def _svg_path(geom, stroke: str) -> str:
    d = ""
    if geom.geom_type == "Polygon":
        d = _path_d(geom.exterior.coords)
        extras = "".join(
            f'<path d="{_path_d(ring.coords)}" fill="none" stroke="{stroke}" stroke-width="0.15"/>'
            for ring in geom.interiors
        )
        return f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="0.15"/>' + extras
    if geom.geom_type == "LineString":
        d = _path_d(geom.coords)
        return f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="0.15"/>'
    if geom.geom_type in {"MultiPolygon", "MultiLineString", "GeometryCollection"}:
        return "".join(_svg_path(g, stroke) for g in geom.geoms)
    return ""


def trace_reference_svg(
    *,
    image_base64: str | None = None,
    image_bytes: bytes | None = None,
    width_mm: float = 200.0,
    style: str = "cut_and_etch",
    invert: bool | None = None,
    threshold: int = 140,
) -> dict[str, Any]:
    img = _decode_image(image_base64, image_bytes)
    longest = max(img.size)
    if longest > 1400:
        scale = 1400 / longest
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.Resampling.LANCZOS)
    mask = _binary_mask(img, invert, threshold)
    if int(mask.sum()) < 20:
        raise ValueError("No dark drawing found. Try invert=true or a different threshold.")
    px_w, px_h = mask.shape[1], mask.shape[0]
    width_mm = max(10.0, float(width_mm))
    px_to_mm = width_mm / px_w
    height_mm = px_h * px_to_mm
    bed_w = PAYAS_DEFAULTS["bed_width"]
    bed_h = PAYAS_DEFAULTS["bed_height"]
    if width_mm > bed_w or height_mm > bed_h:
        fit = min(bed_w / width_mm, bed_h / height_mm)
        width_mm *= fit
        height_mm *= fit
        px_to_mm *= fit

    geoms = []
    for line in _stitch(_marching_segments(mask)):
        geom = _to_geometry(line, px_to_mm, simplify_mm=max(0.12, px_to_mm * 1.2))
        if geom is not None and not geom.is_empty:
            geoms.append(geom)
    if not geoms:
        raise ValueError("Could not trace vector paths from this image.")

    style = (style or "cut_and_etch").strip().lower()
    if style not in {"cut", "etch", "cut_and_etch"}:
        style = "cut_and_etch"

    areas = []
    for g in geoms:
        area = g.area if g.geom_type in {"Polygon", "MultiPolygon"} else 0.0
        areas.append(area)
    outer_idx = int(np.argmax(areas)) if any(areas) else 0

    cut_geoms = []
    etch_geoms = []
    if style == "cut":
        cut_geoms = geoms
    elif style == "etch":
        etch_geoms = geoms
    else:
        for i, g in enumerate(geoms):
            if i == outer_idx and areas[i] > 0:
                cut_geoms.append(g)
            else:
                etch_geoms.append(g)
        if not cut_geoms:
            cut_geoms = [geoms[0]]
            etch_geoms = geoms[1:]

    burn = PAYAS_DEFAULTS["burn"]
    offset_cut = []
    for g in cut_geoms:
        if g.geom_type == "Polygon":
            inset = g.buffer(-burn / 2.0)
            offset_cut.append(inset if not inset.is_empty else g)
        else:
            offset_cut.append(g)

    cut_paths = "".join(_svg_path(g, "#000000") for g in offset_cut)
    etch_paths = "".join(_svg_path(g, "#0066ff") for g in etch_geoms)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm:.2f}mm" height="{height_mm:.2f}mm" '
        f'viewBox="0 0 {width_mm:.3f} {height_mm:.3f}">'
        f'<g id="cut">{cut_paths}</g>'
        f'<g id="etch">{etch_paths}</g>'
        f"</svg>"
    )
    merged = unary_union([g for g in offset_cut + etch_geoms if not g.is_empty])
    path_count = 0
    if merged.geom_type == "GeometryCollection":
        path_count = len(merged.geoms)
    else:
        path_count = 1
    return {
        "svg_bytes": svg.encode("utf-8"),
        "width_mm": width_mm,
        "height_mm": height_mm,
        "path_count": path_count,
        "cut_paths": len(offset_cut),
        "etch_paths": len(etch_geoms),
        "style": style,
    }
