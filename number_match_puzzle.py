"""Parametric number-to-dot jigsaw cards. True vectors, kerf-aware, not image tracing."""

from __future__ import annotations

import math
from typing import Any

from shapely.affinity import translate
from shapely.geometry import LineString, Point, box
from shapely.ops import unary_union

from boxes_adapter import PAYAS_DEFAULTS

CUT = "#cc0000"
ETCH = "#222222"


def _rounded_rect(w: float, h: float, r: float):
    r = min(r, w / 2 - 0.2, h / 2 - 0.2)
    return box(r, r, w - r, h - r).buffer(r, resolution=64)


def _jigsaw_tab(mid_x: float, mid_y: float, side: float, radius: float, neck: float):
    neck_h = neck * 1.85
    stem = box(mid_x - 0.35, mid_y - neck_h / 2, mid_x + side * radius * 0.55, mid_y + neck_h / 2)
    bulb = Point(mid_x + side * radius * 0.95, mid_y).buffer(radius, resolution=64)
    return stem.union(bulb)


def _pair_pieces(w: float, h: float, r: float, burn: float):
    card = _rounded_rect(w, h, r)
    tab = _jigsaw_tab(w / 2, h / 2, 1.0, radius=min(6.4, h * 0.11), neck=min(3.6, h * 0.06))
    left_mask = box(-2, -2, w / 2, h + 2).union(tab)
    left = card.intersection(left_mask)
    right = card.difference(left)
    inset = max(0.04, burn / 2.0)
    left = left.buffer(-inset, join_style=1, resolution=32).simplify(0.05, preserve_topology=True)
    right = right.buffer(-inset, join_style=1, resolution=32).simplify(0.05, preserve_topology=True)
    if left.is_empty or right.is_empty:
        raise ValueError("Puzzle pieces collapsed; increase card size.")
    return left, right


def _stroke(points: list[tuple[float, float]], radius: float):
    if len(points) == 1:
        return Point(points[0]).buffer(radius, resolution=32)
    return LineString(points).buffer(radius, cap_style=1, join_style=1, resolution=32)


def _arc(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float, n: int = 28):
    pts = []
    for i in range(n + 1):
        t = a0 + (a1 - a0) * i / n
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts


def _digit(n: str, ox: float, oy: float, w: float, h: float, thick: float):
    """Draw a digit. Unit space is x→ right, y↑ up, origin at glyph bottom-left; mapped to SVG y-down."""
    t = thick

    def P(x: float, y: float) -> tuple[float, float]:
        return (ox + x * w, oy + (1.0 - y) * h)

    def S(pts: list[tuple[float, float]]):
        return [P(x, y) for x, y in pts]

    def A(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float):
        return [P(cx + rx * math.cos(t), cy + ry * math.sin(t)) for t in
                [a0 + (a1 - a0) * i / 28 for i in range(29)]]

    parts = []
    if n == "1":
        parts.append(_stroke(S([(0.52, 0.08), (0.52, 0.92)]), t))
        parts.append(_stroke(S([(0.28, 0.78), (0.52, 0.92)]), t))
        parts.append(_stroke(S([(0.30, 0.08), (0.74, 0.08)]), t))
    elif n == "2":
        parts.append(_stroke(A(0.50, 0.70, 0.32, 0.22, math.pi * 0.95, math.pi * -0.05), t))
        parts.append(_stroke(S([(0.82, 0.68), (0.22, 0.10)]), t))
        parts.append(_stroke(S([(0.22, 0.10), (0.82, 0.10)]), t))
    elif n == "3":
        parts.append(_stroke(A(0.48, 0.72, 0.30, 0.20, math.pi * 0.85, math.pi * -0.15), t))
        parts.append(_stroke(S([(0.42, 0.52), (0.62, 0.52)]), t * 0.9))
        parts.append(_stroke(A(0.48, 0.28, 0.32, 0.22, math.pi * 0.15, math.pi * 1.05), t))
    elif n == "4":
        parts.append(_stroke(S([(0.68, 0.08), (0.68, 0.92)]), t))
        parts.append(_stroke(S([(0.68, 0.92), (0.22, 0.38)]), t))
        parts.append(_stroke(S([(0.20, 0.38), (0.84, 0.38)]), t))
    elif n == "5":
        parts.append(_stroke(S([(0.78, 0.90), (0.28, 0.90), (0.26, 0.56), (0.55, 0.56)]), t))
        parts.append(_stroke(A(0.50, 0.32, 0.32, 0.24, math.pi * 0.15, math.pi * 1.05), t))
    elif n == "6":
        parts.append(_stroke(A(0.52, 0.32, 0.30, 0.24, 0, 2 * math.pi), t))
        parts.append(_stroke(S([(0.24, 0.40), (0.38, 0.90), (0.74, 0.90)]), t))
    elif n == "7":
        parts.append(_stroke(S([(0.20, 0.90), (0.82, 0.90), (0.38, 0.08)]), t))
    elif n == "8":
        parts.append(_stroke(A(0.50, 0.72, 0.28, 0.20, 0, 2 * math.pi), t))
        parts.append(_stroke(A(0.50, 0.28, 0.30, 0.22, 0, 2 * math.pi), t))
    elif n == "9":
        parts.append(_stroke(A(0.50, 0.70, 0.30, 0.22, 0, 2 * math.pi), t))
        parts.append(_stroke(S([(0.78, 0.68), (0.62, 0.10), (0.28, 0.12)]), t))
    elif n == "0":
        parts.append(_stroke(A(0.50, 0.50, 0.32, 0.42, 0, 2 * math.pi), t))
    else:
        return None
    return unary_union(parts)


def _number(value: int, cx: float, cy: float, height: float, thick: float):
    text = str(value)
    gw = height * 0.62
    gap = height * 0.08
    total = len(text) * gw + (len(text) - 1) * gap
    x0 = cx - total / 2
    y0 = cy - height / 2
    glyphs = []
    for i, ch in enumerate(text):
        g = _digit(ch, x0 + i * (gw + gap), y0, gw, height, thick)
        if g is not None:
            glyphs.append(g)
    return unary_union(glyphs) if glyphs else None


def _dot_pattern(n: int) -> list[tuple[float, float]]:
    return {
        1: [(0, 0)],
        2: [(0, -0.72), (0, 0.72)],
        3: [(0, -0.78), (0, 0), (0, 0.78)],
        4: [(-0.58, -0.58), (0.58, -0.58), (-0.58, 0.58), (0.58, 0.58)],
        5: [(-0.62, -0.62), (0.62, -0.62), (0, 0), (-0.62, 0.62), (0.62, 0.62)],
        6: [(-0.55, -0.78), (-0.55, 0), (-0.55, 0.78), (0.55, -0.78), (0.55, 0), (0.55, 0.78)],
        7: [(-0.62, -0.78), (0.62, -0.78), (-0.78, 0), (0, 0), (0.78, 0), (-0.62, 0.78), (0.62, 0.78)],
        8: [
            (-0.55, -0.84), (-0.55, -0.28), (-0.55, 0.28), (-0.55, 0.84),
            (0.55, -0.84), (0.55, -0.28), (0.55, 0.28), (0.55, 0.84),
        ],
        9: [(x, y) for y in (-0.78, 0, 0.78) for x in (-0.78, 0, 0.78)],
        10: [(-0.55, y) for y in (-0.88, -0.44, 0.0, 0.44, 0.88)]
        + [(0.55, y) for y in (-0.88, -0.44, 0.0, 0.44, 0.88)],
    }[n]


def _dots(n: int, cx: float, cy: float, span: float, radius: float):
    sy = span * (0.42 if n < 10 else 0.38)
    sx = span * 0.42
    return [Point(cx + x * sx, cy + y * sy).buffer(radius, resolution=48) for x, y in _dot_pattern(n)]


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


def _emit(geom, stroke: str, width: float) -> str:
    if geom is None or geom.is_empty:
        return ""
    if geom.geom_type == "Polygon":
        d = _path_d(geom.exterior.coords)
        holes = "".join(
            f'<path d="{_path_d(r.coords)}" fill="none" stroke="{stroke}" stroke-width="{width}" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            for r in geom.interiors
        )
        return (
            f'<path d="{d}" fill="none" stroke="{stroke}" stroke-width="{width}" '
            f'stroke-linejoin="round" stroke-linecap="round"/>' + holes
        )
    if geom.geom_type in {"MultiPolygon", "GeometryCollection", "MultiLineString"}:
        return "".join(_emit(g, stroke, width) for g in geom.geoms)
    if geom.geom_type == "LineString":
        return (
            f'<path d="{_path_d(geom.coords)}" fill="none" stroke="{stroke}" '
            f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'
        )
    return ""


def build_jigsaw_sheet(
    items: list[dict[str, Any]],
    *,
    card_w: float = 108.0,
    card_h: float = 64.0,
    columns: int = 2,
) -> dict[str, Any]:
    """Place jigsaw pairs. Each item: {left: int|str, right_pips: int}."""
    count = len(items)
    if count < 1:
        raise ValueError("jigsaw_sheet needs at least one card")
    columns = 2 if int(columns) != 1 else 1
    burn = PAYAS_DEFAULTS["burn"]
    rows = math.ceil(count / columns)
    gap = 7.0
    margin = 10.0
    pair_gap = 2.4
    left0, right0 = _pair_pieces(card_w, card_h, r=min(9.0, card_h * 0.14), burn=burn)
    piece_w = max(left0.bounds[2] - left0.bounds[0], right0.bounds[2] - right0.bounds[0]) + 0.4
    pair_w = piece_w * 2 + pair_gap
    sheet_w = margin * 2 + columns * pair_w + (columns - 1) * gap
    sheet_h = margin * 2 + rows * card_h + (rows - 1) * gap
    bed_w, bed_h = PAYAS_DEFAULTS["bed_width"], PAYAS_DEFAULTS["bed_height"]
    if sheet_w > bed_w or sheet_h > bed_h:
        fit = min(bed_w / sheet_w, bed_h / sheet_h) * 0.98
        return build_jigsaw_sheet(items, card_w=card_w * fit, card_h=card_h * fit, columns=columns)

    cut_bits = []
    etch_bits = []
    for i, item in enumerate(items):
        n_right = int(item.get("right_pips") or item.get("n") or i + 1)
        left_val = item.get("left", i + 1)
        col, row = i % columns, i // columns
        origin_x = margin + col * (pair_w + gap)
        origin_y = margin + row * (card_h + gap)
        left, right = _pair_pieces(card_w, card_h, r=min(9.0, card_h * 0.14), burn=burn)
        lx, ly = left.bounds[0], left.bounds[1]
        rx, ry = right.bounds[0], right.bounds[1]
        left_t = translate(left, origin_x - lx, origin_y - ly)
        right_t = translate(right, origin_x + piece_w + pair_gap - rx, origin_y - ry)
        cut_bits.extend([left_t, right_t])
        lb, rb = left_t.bounds, right_t.bounds
        lcx, lcy = (lb[0] + lb[2]) / 2, (lb[1] + lb[3]) / 2
        rcx, rcy = (rb[0] + rb[2]) / 2, (rb[1] + rb[3]) / 2
        try:
            num = int(str(left_val))
        except ValueError:
            num = n_right
        glyph = _number(num, lcx, lcy, card_h * 0.46, thick=card_h * 0.028)
        if glyph is not None:
            etch_bits.append(glyph.boundary)
        pips = max(1, min(10, n_right))
        for dot in _dots(pips, rcx, rcy, span=min(rb[2] - rb[0], rb[3] - rb[1]) * 0.72, radius=card_h * 0.042):
            etch_bits.append(dot.boundary)

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{sheet_w:.2f}mm" height="{sheet_h:.2f}mm" '
        f'viewBox="0 0 {sheet_w:.3f} {sheet_h:.3f}">'
        f'<g id="cut" fill="none">{"".join(_emit(g, CUT, 0.18) for g in cut_bits)}</g>'
        f'<g id="etch" fill="none">{"".join(_emit(g, ETCH, 0.22) for g in etch_bits)}</g>'
        f"</svg>"
    )
    return {
        "svg_bytes": svg.encode("utf-8"),
        "width_mm": sheet_w,
        "height_mm": sheet_h,
        "count": count,
        "card_w": card_w,
        "card_h": card_h,
    }


def build_number_match_svg(
    *,
    count: int = 10,
    card_w: float = 108.0,
    card_h: float = 64.0,
    columns: int = 2,
) -> dict[str, Any]:
    count = max(1, min(20, int(count)))
    items = [{"left": i, "right_pips": i} for i in range(1, count + 1)]
    return build_jigsaw_sheet(items, card_w=card_w, card_h=card_h, columns=columns)
