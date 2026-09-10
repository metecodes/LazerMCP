"""Classic interlocking jigsaw: one cut per seam, outer frame once."""

from __future__ import annotations

import math
import random
from typing import Any

from shapely.geometry import LineString, box

from boxes_adapter import PAYAS_DEFAULTS
from number_match_puzzle import CUT, ETCH, _emit
from text_path import svg_document, to_lasercad_y

TWO_PI = math.tau


def _arc(cx: float, cy: float, r: float, a0: float, a1: float, steps: int = 14) -> list[tuple[float, float]]:
    delta = a1 - a0
    if abs(delta) < 1e-9:
        return []
    n = max(6, steps)
    return [
        (cx + r * math.cos(a0 + delta * i / n), cy + r * math.sin(a0 + delta * i / n))
        for i in range(n + 1)
    ]


def _tabbed_edge(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    sign: int,
    rng: random.Random,
) -> list[tuple[float, float]]:
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    ux, uy = dx / length, dy / length
    nx, ny = -uy * sign, ux * sign
    t = 0.5 + rng.uniform(-0.05, 0.05)
    mx, my = x0 + ux * length * t, y0 + uy * length * t
    radius = min(length * 0.17, 7.2)
    stem = radius * 0.58
    slx, sly = mx - ux * stem, my - uy * stem
    srx, sry = mx + ux * stem, my + uy * stem
    cx, cy = mx + nx * radius * 0.78, my + ny * radius * 0.78
    a_left = math.atan2(sly - cy, slx - cx)
    a_right = math.atan2(sry - cy, srx - cx)
    a_peak = math.atan2(ny, nx)
    ccw = (a_right - a_left) % TWO_PI
    via_ccw = (a_peak - a_left) % TWO_PI
    if via_ccw <= ccw + 1e-6:
        a1 = a_left + ccw
    else:
        a1 = a_left - ((a_left - a_right) % TWO_PI)
    return [(x0, y0), (slx, sly), *_arc(cx, cy, radius, a_left, a1), (srx, sry), (x1, y1)]


def jigsaw_cut_geoms(
    width_mm: float,
    height_mm: float,
    rows: int,
    cols: int,
    seed: int = 1,
) -> list:
    rows = max(2, min(40, int(rows)))
    cols = max(2, min(40, int(cols)))
    width_mm = max(20.0, float(width_mm))
    height_mm = max(20.0, float(height_mm))
    rng = random.Random(int(seed) or 1)
    cw, ch = width_mm / cols, height_mm / rows
    cuts: list = [LineString(box(0.0, 0.0, width_mm, height_mm).exterior.coords)]
    for r in range(rows - 1):
        y = (r + 1) * ch
        for c in range(cols):
            sign = 1 if rng.randrange(2) else -1
            pts = _tabbed_edge(c * cw, y, (c + 1) * cw, y, sign, rng)
            cuts.append(LineString(pts))
    for c in range(cols - 1):
        x = (c + 1) * cw
        for r in range(rows):
            sign = 1 if rng.randrange(2) else -1
            pts = _tabbed_edge(x, r * ch, x, (r + 1) * ch, sign, rng)
            cuts.append(LineString(pts))
    return cuts


def build_jigsaw_puzzle(
    *,
    width_mm: float = 300.0,
    height_mm: float = 300.0,
    rows: int = 10,
    cols: int = 10,
    seed: int = 1,
    etch_geoms: list | None = None,
) -> dict[str, Any]:
    cut_geoms = jigsaw_cut_geoms(width_mm, height_mm, rows, cols, seed)
    etch = list(etch_geoms or [])
    y_cut = [to_lasercad_y(g, height_mm) for g in cut_geoms]
    y_etch = [to_lasercad_y(g, height_mm) for g in etch]
    svg = svg_document(
        width_mm,
        height_mm,
        "".join(_emit(g, CUT, 0.18) for g in y_cut),
        "".join(_emit(g, ETCH, 0.22) for g in y_etch),
    )
    return {
        "svg_bytes": svg.encode("utf-8"),
        "cut_geoms": y_cut,
        "etch_geoms": y_etch,
        "width_mm": width_mm,
        "height_mm": height_mm,
        "rows": rows,
        "cols": cols,
        "count": int(rows) * int(cols),
        "card_w": width_mm / cols,
        "card_h": height_mm / rows,
        "burn": PAYAS_DEFAULTS["burn"],
    }
