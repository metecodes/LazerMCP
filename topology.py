"""Cut-path topology: open loops, duplicate segments, self-intersections. Report only — never raise."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

from shapely.geometry import Polygon
from shapely.validation import explain_validity
from svgpathtools import Line, parse_path

from holding_nicks import NICK_MM

_NICK_GAP = float(NICK_MM) + 0.8


def _is_cut(el: ET.Element) -> bool:
    from manufacturing import element_is_cut

    return element_is_cut(el)


def inspect_topology(svg_bytes: bytes | None) -> dict[str, Any]:
    """Inspect CUT paths. Holding nicks are closed cuts, not open loops."""
    open_cuts: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    self_intersections: list[dict[str, Any]] = []
    closed = 0
    nicked = 0
    empty = {
        "ok": True,
        "cut_paths": 0,
        "closed": 0,
        "nicked_closed": 0,
        "open_cuts": [],
        "duplicates": [],
        "self_intersections": [],
    }
    if not svg_bytes:
        return empty
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return empty
    seen: set[tuple] = set()
    index = 0
    for el in root.iter():
        if el.tag.split("}")[-1].lower() != "path":
            continue
        d = el.get("d") or ""
        if not d.strip() or not _is_cut(el):
            continue
        index += 1
        nicks = el.get("data-holding-nicks")
        moves = d.upper().count("M")
        if nicks or moves > 1:
            nicked += 1
            closed += 1
            continue
        try:
            path = parse_path(d)
        except Exception:
            continue
        subs = list(path.continuous_subpaths()) if path else []
        if not subs:
            continue
        contour = subs[0]
        gap = abs(contour.start - contour.end)
        if gap > _NICK_GAP:
            open_cuts.append(
                {
                    "path": index,
                    "gap_mm": round(float(gap), 3),
                    "note": "CUT loop does not close (not a holding nick).",
                }
            )
            continue
        if gap > 0.05:
            nicked += 1
        closed += 1
        points = [contour.start]
        for segment in contour:
            if abs(segment.start - segment.end) < 1e-9 and isinstance(segment, Line):
                continue
            forward = tuple(round(v, 5) for p in segment.bpoints() for v in (p.real, p.imag))
            backward = tuple(round(v, 5) for p in reversed(segment.bpoints()) for v in (p.real, p.imag))
            key = min(forward, backward)
            if key in seen:
                duplicates.append({"path": index, "note": "Duplicate CUT segment."})
            else:
                seen.add(key)
            n = 1 if isinstance(segment, Line) else 8
            points.extend(segment.point(i / n) for i in range(1, n + 1))
        if len(points) < 4:
            continue
        points[-1] = points[0]
        try:
            poly = Polygon([(p.real, p.imag) for p in points])
        except Exception:
            continue
        if poly.area <= 0.05:
            continue
        if not poly.is_valid:
            reason = explain_validity(poly)
            if "self-intersection" in reason.lower():
                self_intersections.append({"path": index, "note": reason})
    return {
        "ok": not open_cuts and not duplicates and not self_intersections,
        "cut_paths": index,
        "closed": closed,
        "nicked_closed": nicked,
        "open_cuts": open_cuts,
        "duplicates": duplicates,
        "self_intersections": self_intersections,
    }
