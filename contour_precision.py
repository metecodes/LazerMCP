"""Conservative cleanup for tiny accidental CUT-contour deviations.

The same SVG is used for preview, validation and DXF export.  This module only
removes a point when it lies within a machining-insignificant tolerance of the
line between its two neighbours.  It never squares intentional slopes, rounds
corners, changes engraving, or bridges open contours.
"""

from __future__ import annotations

import json
import math
from statistics import median
from xml.etree import ElementTree as ET

from svgpathtools import Line, parse_path

_TOLERANCE_MM = 0.03
_AXIS_DRIFT_MM = 0.05
_COLLINEAR_COSINE = math.cos(math.radians(1.0))


def _distance_to_line(point: complex, start: complex, end: complex) -> float:
    vector = end - start
    length = abs(vector)
    if length < 1e-9:
        return abs(point - start)
    return abs((point - start).real * vector.imag - (point - start).imag * vector.real) / length


def _collinear_cleanup(points: list[complex], closed: bool) -> tuple[list[complex], int]:
    """Delete only forward, nearly-collinear vertices within 0.03 mm."""
    result = list(points)
    removed = 0
    minimum = 3 if closed else 2
    changed = True
    while changed and len(result) > minimum:
        changed = False
        first = 0 if closed else 1
        last = len(result) if closed else len(result) - 1
        for index in range(first, last):
            previous = result[(index - 1) % len(result)]
            current = result[index]
            following = result[(index + 1) % len(result)]
            before = current - previous
            after = following - current
            if abs(before) < 1e-9 or abs(after) < 1e-9:
                del result[index]
                removed += 1
                changed = True
                break
            # Do not erase a point that reverses direction or makes a real corner.
            alignment = (before.real * after.real + before.imag * after.imag) / (abs(before) * abs(after))
            if alignment < _COLLINEAR_COSINE:
                continue
            if _distance_to_line(current, previous, following) <= _TOLERANCE_MM:
                del result[index]
                removed += 1
                changed = True
                break
    return result, removed


def _snap_near_axis_runs(points: list[complex], closed: bool) -> tuple[list[complex], int]:
    """Remove sub-0.05 mm drift from a long nominally horizontal/vertical run."""
    result = list(points)
    changed = 0
    limit = len(result) - 1
    index = 0
    while index < limit:
        start = index
        dx = result[index + 1].real - result[index].real
        dy = result[index + 1].imag - result[index].imag
        horizontal = abs(dy) <= _TOLERANCE_MM and abs(dx) > abs(dy)
        vertical = abs(dx) <= _TOLERANCE_MM and abs(dy) > abs(dx)
        if not (horizontal or vertical):
            index += 1
            continue
        index += 1
        while index < limit:
            dx = result[index + 1].real - result[index].real
            dy = result[index + 1].imag - result[index].imag
            if horizontal and abs(dy) <= _TOLERANCE_MM and abs(dx) > abs(dy):
                index += 1
            elif vertical and abs(dx) <= _TOLERANCE_MM and abs(dy) > abs(dx):
                index += 1
            else:
                break
        run = result[start:index + 1]
        travelled = sum(abs(b - a) for a, b in zip(run, run[1:]))
        values = [p.imag for p in run] if horizontal else [p.real for p in run]
        if travelled >= 5 and max(values) - min(values) <= _AXIS_DRIFT_MM:
            target = median(values)
            for slot in range(start, index + 1):
                point = result[slot]
                snapped = complex(point.real, target) if horizontal else complex(target, point.imag)
                if abs(snapped - point) > 1e-12:
                    result[slot] = snapped
                    changed += 1
    return result, changed


def _render_subpath(points: list[complex], closed: bool) -> str:
    if len(points) < 2:
        return ""
    body = "M {:.6f} {:.6f}".format(points[0].real, points[0].imag)
    body += "".join(" L {:.6f} {:.6f}".format(point.real, point.imag) for point in points[1:])
    return body + (" Z" if closed else "")


def cleanup_cut_contours(svg_bytes: bytes) -> bytes:
    """Clean tiny linear CUT defects and record a deterministic quality report.

    Curves and non-millimetre coordinate systems are intentionally untouched:
    changing them without a source-space tolerance would be a geometry rewrite.
    """
    if not svg_bytes:
        return svg_bytes
    root = ET.fromstring(svg_bytes)
    viewbox = (root.get("viewBox") or "").replace(",", " ").split()
    if (not root.get("width", "").endswith("mm") or not root.get("height", "").endswith("mm")
            or len(viewbox) != 4):
        return svg_bytes
    try:
        width, height = float(root.get("width")[:-2]), float(root.get("height")[:-2])
        _, _, vb_width, vb_height = map(float, viewbox)
    except ValueError:
        return svg_bytes
    if abs(width - vb_width) > 1e-6 or abs(height - vb_height) > 1e-6:
        return svg_bytes

    from manufacturing import classify_element
    parents = {child: parent for parent in root.iter() for child in parent}
    report = {"tolerance_mm": _TOLERANCE_MM, "axis_drift_mm": _AXIS_DRIFT_MM,
              "scanned_cut_paths": 0, "removed_vertices": 0, "snapped_vertices": 0,
              "reverted_non_simple_contours": 0}
    changed = False
    for element in root.iter():
        if element.tag.split("}")[-1].lower() != "path" or classify_element(element, parents)[0] != "CUT":
            continue
        try:
            path = parse_path(element.get("d") or "")
            subpaths = path.continuous_subpaths()
        except Exception:
            continue
        if not subpaths or any(any(not isinstance(segment, Line) for segment in subpath) for subpath in subpaths):
            continue
        report["scanned_cut_paths"] += 1
        output = []
        path_removed = path_snapped = 0
        safe = True
        for subpath in subpaths:
            closed = subpath.isclosed()
            points = [subpath.start] + [segment.end for segment in subpath]
            if closed and abs(points[0] - points[-1]) < 1e-8:
                points.pop()
            points, removed = _collinear_cleanup(points, closed)
            points, snapped = _snap_near_axis_runs(points, closed)
            # Snapping a true axis run can expose redundant points; remove only
            # the now-exactly-collinear ones, never curve samples.
            points, removed_after_snap = _collinear_cleanup(points, closed)
            removed += removed_after_snap
            # A simplification must not turn a valid contour into a crossing
            # contour.  Keep this exact path unchanged when that would happen.
            if closed and (removed or snapped):
                from shapely.geometry import LineString
                ring = [(p.real, p.imag) for p in points + [points[0]]]
                if not LineString(ring).is_simple:
                    safe = False
            path_removed += removed
            path_snapped += snapped
            output.append(_render_subpath(points, closed))
        if safe and (path_removed or path_snapped):
            element.set("d", " ".join(bit for bit in output if bit))
            report["removed_vertices"] += path_removed
            report["snapped_vertices"] += path_snapped
            changed = True
        elif not safe:
            report["reverted_non_simple_contours"] += 1
    if not changed:
        return svg_bytes
    root.set("data-contour-precision", json.dumps(report, separators=(",", ":")))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
