"""Fail-closed cut validation; no modifications to Boxes.py drawing helpers."""
from xml.etree import ElementTree as ET
from copy import deepcopy

from shapely.geometry import Polygon, LineString
from svgpathtools import CubicBezier, Line, Path, parse_path


def check_contours(paths, panels, features, tolerance, thickness, burn, tab_width, inverted=False,
                   sheet=None, gap=0., margin=0.):
    """Analytic closure, duplicate segments, sampled curve topology and nesting."""
    contours, seen = [], set()
    for path in paths:
        for contour in path.continuous_subpaths():
            if not contour or abs(contour.start-contour.end) > tolerance:
                raise ValueError("Open cut contour")
            points = [contour.start]
            for segment in contour:
                if abs(segment.start-segment.end) < 1e-9 and isinstance(segment, Line):
                    continue
                forward = tuple(round(v, 6) for p in segment.bpoints() for v in (p.real, p.imag))
                backward = tuple(round(v, 6) for p in reversed(segment.bpoints()) for v in (p.real, p.imag))
                key = min(forward, backward)
                if key in seen:
                    raise ValueError("Duplicate cutting segment")
                seen.add(key)
                n = 1 if isinstance(segment, Line) else 64
                points.extend(segment.point(i/n) for i in range(1, n+1))
            points[-1] = points[0]  # absorb only the closure tolerance checked above
            poly = Polygon([(p.real, p.imag) for p in points])
            if not poly.is_valid or poly.area <= tolerance*tolerance:
                from shapely.validation import explain_validity
                raise ValueError("Invalid contour: " + explain_validity(poly))
            contours.append(poly)
    for i, a in enumerate(contours):
        for b in contours[:i]:
            if a.boundary.intersects(b.boundary):
                raise ValueError("Overlapping/touching cut contours")
    outers = [p for p in contours if not any(q.contains(p) for q in contours if q is not p)]
    outers.sort(key=lambda p: p.bounds[1])
    if sheet is not None:
        for i, outer in enumerate(outers):
            x0, y0, x1, y1 = outer.bounds
            if x0 < margin-tolerance or y0 < margin-tolerance or x1 > sheet[0]-margin+tolerance or y1 > sheet[1]-margin+tolerance:
                raise ValueError("Part outside sheet margin")
            if any(outer.distance(other) < gap-tolerance for other in outers[:i]):
                raise ValueError("Insufficient spacing between parts")
    if len(outers) != len(panels) or len(contours) != len(panels)+len(features):
        raise ValueError(f"Unexpected contour counts: {len(outers)} panels, {len(contours)} contours")
    for outer, panel in zip(outers, panels):
        holes = [p for p in contours if p is not outer and outer.contains(p)]
        expected = [f for f in features if f["part"] == panel[0]]
        if len(holes) != len(expected):
            raise ValueError("Wrong opening count in " + panel[0])
        xmin, ymin, xmax, ymax = outer.bounds
        bottom_extra = thickness if panel[3][0] != "e" else 0
        if abs(xmax-xmin-panel[1]-2*thickness-2*burn) > .005 or abs(
                ymax-ymin-panel[2]-thickness-bottom_extra-2*burn) > .005:
            raise ValueError("Incorrect panel envelope: " + panel[0])
        origin_x = xmin+thickness+burn
        origin_y = (ymax-bottom_extra-burn) if inverted else (ymin+bottom_extra+burn)
        remaining = list(holes)
        for f in expected:
            ex, ey = origin_x+f["x"], origin_y+(-f["y"] if inverted else f["y"])
            matches = []
            for hole in remaining:
                left, bottom, right, top = hole.bounds
                if (abs((left+right)/2-ex) < .005 and abs((bottom+top)/2-ey) < .005
                        and abs(right-left-(f["w"]-2*burn)) < .005
                        and abs(top-bottom-(f["h"]-2*burn)) < .005):
                    matches.append(hole)
            if len(matches) != 1:
                raise ValueError("Opening position/size mismatch: " + panel[0]+" "+f["kind"])
            remaining.remove(matches[0])
        if panel[3][0] == "T":
            # Cut across actual tab: exactly one interval of compensated width.
            level = ymax-thickness/2 if inverted else ymin+thickness/2
            section = outer.intersection(LineString([(xmin-1, level), (xmax+1, level)]))
            if (section.geom_type != "LineString" or abs(section.length-tab_width-2*burn) > .005
                    or abs(section.centroid.x-(origin_x+panel[1]/2)) > .005):
                raise ValueError("Actual mounting tab profile mismatch")
    return dict(closed_contours=len(contours), panels=len(outers), holes=len(features),
                duplicate_segments=0, intersections=0, curve_samples=64)


def validate_surface(surface, panels, features, thickness, burn, tab_width):
    paths = []
    for part in surface.parts:
        for drawing in part.pathes:
            if tuple(drawing.params["rgb"]) not in ((0., 0., 0.), (0., 0., 1.)):
                if all(c[0] in ("M", "T") for c in drawing.path):
                    continue
                raise ValueError("Unexpected drawing layer")
            drawing = deepcopy(drawing)
            drawing.faster_edges("corner")
            path, start = Path(), None
            for command in drawing.path:
                kind, x, y = command[:3]
                end = complex(x, y)
                if kind == "M":
                    if path:
                        paths.append(path)
                    path = Path()
                elif kind == "L":
                    path.append(Line(start, end))
                elif kind == "C":
                    path.append(CubicBezier(start, complex(*command[3:5]), complex(*command[5:7]), end))
                elif kind == "T" and tuple(command[5]["rgb"]) == (1., 0., 0.):
                    continue  # Boxes.py ANNOTATIONS; never a cutting path
                else:
                    raise ValueError("Unexpected non-cut command")
                start = end
            if path:
                paths.append(path)
    return check_contours(paths, panels, features, 1e-4, thickness, burn, tab_width)


def validate_svg(data, panels, features, thickness, burn, tab_width):
    root = ET.fromstring(data)
    if not root.get("width", "").endswith("mm") or not root.get("height", "").endswith("mm"):
        raise ValueError("SVG physical units missing")
    paths = []
    for element in root.iter():
        kind = element.tag.rsplit("}", 1)[-1]
        if kind in ("rect", "circle", "ellipse", "line", "polyline", "polygon", "use"):
            raise ValueError("Unexpected SVG geometry element")
        if kind in ("g", "svg", "path") and element.get("transform"):
            raise ValueError("Unexpected cut transform")
        if kind == "path":
            if element.get("stroke") not in ("#000000", "#0000ff", "rgb(0,0,0)", "rgb(0,0,255)"):
                raise ValueError("Unexpected SVG path layer")
            paths.append(parse_path(element.get("d")))
    if root.get("data-layout") == "compact":
        groups = [g for g in root.findall("{http://www.w3.org/2000/svg}g")
                  if g.findall("{http://www.w3.org/2000/svg}path")]
        lookup = {p[0]: p for p in panels}
        if sorted(g.get("data-panel", "") for g in groups) != sorted(lookup):
            raise ValueError("Packed panel identities mismatch")
        ordered = []
        for g in groups:
            local = [parse_path(p.get("d")) for p in g.findall("{http://www.w3.org/2000/svg}path")]
            panel = lookup[g.get("data-panel")]
            check_contours(local, [panel], [f for f in features if f["part"] == panel[0]],
                           .002, thickness, burn, tab_width, True)
            ordered.append((min(p.bbox()[2] for p in local), panel))
        ordered.sort(key=lambda item: item[0])
        sheet = (float(root.get("width")[:-2]), float(root.get("height")[:-2]))
        if [float(v) for v in root.get("viewBox").split()] != [0., 0., *sheet]:
            raise ValueError("Sheet viewBox scale mismatch")
        return check_contours(paths, [p for _, p in ordered], features, .002, thickness, burn,
                              tab_width, True, sheet, float(root.get("data-gap")), float(root.get("data-margin")))
    return check_contours(paths, list(reversed(panels)), features, .002, thickness, burn, tab_width, True)
