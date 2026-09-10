"""Arial (or Arial-metric fallback) text as laser-ready outline paths. No <text> elements."""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont
from shapely.affinity import affine_transform
from shapely.affinity import scale as shp_scale
from shapely.affinity import translate as shp_translate
from shapely.geometry import Polygon
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parent

# LaserCAD / Ruida palette. Gray #222222 is dropped on import; text must be black paths.
LASER_CUT = "#FF0000"
LASER_ETCH = "#000000"
LASER_SVG_MARK = "Y-up for LaserCAD"


def to_lasercad_y(geom, height_mm: float):
    """SVG Y-down → LaserCAD Y-up (y' = height - y). No mirrors on X."""
    if geom is None or getattr(geom, "is_empty", False):
        return geom
    return affine_transform(geom, [1.0, 0.0, 0.0, -1.0, 0.0, float(height_mm)])


def svg_document(width_mm: float, height_mm: float, cut_svg: str, etch_svg: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm:.2f}mm" height="{height_mm:.2f}mm" '
        f'viewBox="0 0 {width_mm:.3f} {height_mm:.3f}" fill="none">'
        f'<!-- Payas laser CAD: mm; cut {LASER_CUT}; etch {LASER_ETCH}; {LASER_SVG_MARK}; path outlines only -->'
        f'<g id="CUT">\n{cut_svg}\n</g>'
        f'<g id="ENGRAVE">\n{etch_svg}\n</g>'
        f"</svg>"
    )


def _cubic(p0, p1, p2, p3, t: float) -> tuple[float, float]:
    u = 1.0 - t
    return (
        u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0],
        u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1],
    )


class _ShapelyPen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.rings: list[list[tuple[float, float]]] = []
        self._pts: list[tuple[float, float]] = []

    def _moveTo(self, pt):
        self._flush()
        self._pts = [pt]

    def _lineTo(self, pt):
        self._pts.append(pt)

    def _curveToOne(self, p1, p2, p3):
        p0 = self._pts[-1]
        steps = 10
        for i in range(1, steps + 1):
            self._pts.append(_cubic(p0, p1, p2, p3, i / steps))

    def _closePath(self):
        self._flush(closed=True)

    def _endPath(self):
        self._flush(closed=False)

    def _flush(self, closed: bool = True):
        if len(self._pts) >= 3:
            ring = list(self._pts)
            if closed and ring[0] != ring[-1]:
                ring.append(ring[0])
            self.rings.append(ring)
        self._pts = []


def _rings_to_geom(rings: list[list[tuple[float, float]]]):
    polys = []
    for ring in rings:
        poly = Polygon(ring)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            continue
        if poly.geom_type == "MultiPolygon":
            polys.extend(p for p in poly.geoms if p.area > 0)
        elif poly.geom_type == "Polygon" and poly.area > 0:
            polys.append(poly)
    polys.sort(key=lambda p: p.area, reverse=True)
    out = []
    for poly in polys:
        nested = False
        for i, outer in enumerate(out):
            try:
                if outer.contains(poly.representative_point()):
                    out[i] = outer.difference(poly)
                    nested = True
                    break
            except Exception:
                continue
        if not nested:
            out.append(poly)
    if not out:
        return None
    return unary_union(out)


def arial_candidates() -> list[Path]:
    env = (os.environ.get("ARIAL_TTF") or os.environ.get("PAYAS_FONT") or "").strip()
    windir = os.environ.get("WINDIR", r"C:\Windows")
    paths = []
    if env:
        paths.append(Path(env))
    paths.extend(
        [
            Path(windir) / "Fonts" / "arial.ttf",
            Path(windir) / "Fonts" / "Arial.ttf",
            Path("/usr/share/fonts/truetype/msttcorefonts/Arial.ttf"),
            Path("/usr/share/fonts/truetype/msttcorefonts/arial.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
            ROOT / "fonts" / "LiberationSans-Regular.ttf",
            ROOT / "fonts" / "Arimo-Regular.ttf",
        ]
    )
    return paths


def find_arial_font() -> Path:
    for path in arial_candidates():
        if path.is_file():
            return path
    known = ", ".join(str(p) for p in arial_candidates()[:4])
    raise FileNotFoundError(f"Arial TTF not found. Install Arial or set ARIAL_TTF. Tried: {known}")


@lru_cache(maxsize=2)
def _font(path: str = "") -> TTFont:
    return TTFont(path or str(find_arial_font()), lazy=True)


def layout_text(
    text: str,
    cx: float,
    cy: float,
    height_mm: float,
    *,
    font_path: str | None = None,
    y_up: bool = False,
    anchor: str = "center",
    baseline: str = "center",
):
    """Place Arial outlines at (cx, cy). height_mm is approximate cap height.

    Default is SVG Y-down, bbox-centered. Boxes.py part coords use y_up=True.
    """
    raw = str(text if text is not None else "").strip()
    if not raw:
        return None
    path = font_path or str(find_arial_font())
    font = _font(path)
    glyph_set = font.getGlyphSet()
    cmap = font.getBestCmap() or {}
    upem = float(font["head"].unitsPerEm)
    os2 = font["OS/2"] if "OS/2" in font else None
    cap = float(getattr(os2, "sCapHeight", 0) or 0) or upem * 0.72
    scale_mm = float(height_mm) / cap
    x = 0.0
    parts = []
    for ch in raw:
        name = cmap.get(ord(ch))
        if not name:
            x += upem * 0.4
            continue
        glyph = glyph_set[name]
        pen = _ShapelyPen(glyph_set)
        glyph.draw(pen)
        geom = _rings_to_geom(pen.rings)
        if geom is not None and not geom.is_empty:
            parts.append(shp_translate(geom, xoff=x, yoff=0.0))
        x += float(glyph.width)
    if not parts:
        return None
    blob = unary_union(parts)
    yfact = scale_mm if y_up else -scale_mm
    blob = shp_scale(blob, xfact=scale_mm, yfact=yfact, origin=(0, 0))
    minx, miny, maxx, maxy = blob.bounds
    ax = (anchor or "center").lower()
    if ax in {"end", "right"}:
        xoff = cx - maxx
    elif ax in {"start", "left"}:
        xoff = cx - minx
    else:
        xoff = cx - (minx + maxx) / 2.0
    by = (baseline or "center").lower()
    if by == "hanging":
        yoff = cy - (maxy if y_up else miny)
    elif by in {"alphabetic", "bottom"}:
        yoff = cy - (miny if y_up else maxy)
    else:
        yoff = cy - (miny + maxy) / 2.0
    blob = shp_translate(blob, xoff=xoff, yoff=yoff)
    return blob.simplify(0.04, preserve_topology=True)


def font_info() -> dict[str, str]:
    path = find_arial_font()
    return {"font_path": str(path), "font_name": path.stem}


def stroke_geom(ctx, geom) -> None:
    """Stroke glyph rings on a Boxes.py drawing context (closed laser paths)."""
    if geom is None or geom.is_empty:
        return
    if geom.geom_type == "Polygon":
        for ring in (geom.exterior, *geom.interiors):
            pts = list(ring.coords)
            if len(pts) < 2:
                continue
            ctx.move_to(pts[0][0], pts[0][1])
            for x, y in pts[1:]:
                ctx.line_to(x, y)
            ctx.stroke()
        return
    if geom.geom_type in {"MultiPolygon", "GeometryCollection"}:
        for part in geom.geoms:
            stroke_geom(ctx, part)


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


def geom_path_elements(geom, stroke: str, width: float, ns: str):
    from xml.etree import ElementTree as ET

    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        d = _path_d(geom.exterior.coords)
        for ring in geom.interiors:
            hole = _path_d(ring.coords)
            if hole:
                d = f"{d} {hole}"
        if not d:
            return []
        el = ET.Element(
            f"{ns}path",
            {
                "d": d,
                "fill": "none",
                "stroke": stroke,
                "stroke-width": f"{width:.2f}",
            },
        )
        el.tail = "\n  "
        return [el]
    if geom.geom_type in {"MultiPolygon", "GeometryCollection"}:
        out = []
        for part in geom.geoms:
            out.extend(geom_path_elements(part, stroke, width, ns))
        return out
    return []


def _parse_matrix(transform: str | None):
    if not transform:
        return None
    match = re.search(r"matrix\s*\(\s*([^)]+)\)", transform, re.I)
    if match:
        nums = [float(x) for x in re.split(r"[,\s]+", match.group(1).strip()) if x]
        if len(nums) == 6:
            a, b, c, d, e, f = nums
            return [a, c, b, d, e, f]
    match = re.search(r"translate\s*\(\s*([^)]+)\)", transform, re.I)
    if match:
        nums = [float(x) for x in re.split(r"[,\s]+", match.group(1).strip()) if x]
        tx = nums[0] if nums else 0.0
        ty = nums[1] if len(nums) > 1 else 0.0
        return [1.0, 0.0, 0.0, 1.0, tx, ty]
    return None


def _style_color(el) -> str:
    style = el.get("style") or ""
    match = re.search(r"(?:^|;)\s*fill:\s*([^;]+)", style, re.I)
    color = (match.group(1).strip() if match else "") or (el.get("fill") or "")
    color = color.strip()
    if not color or color.lower() in {"none", "transparent"}:
        return LASER_ETCH
    return canon_color(color)


def _font_size_mm(el) -> float:
    raw = el.get("font-size") or ""
    if not raw:
        style = el.get("style") or ""
        match = re.search(r"font-size:\s*([^;]+)", style, re.I)
        raw = match.group(1).strip() if match else "10"
    try:
        return float(re.sub(r"[a-zA-Z%]+", "", raw) or 10)
    except ValueError:
        return 10.0


def laserize_svg(svg_bytes: bytes) -> bytes:
    """Replace live <text> with Arial outline paths. Laser CAD ignores SVG text."""
    if not svg_bytes:
        return svg_bytes
    lowered = svg_bytes.lower()
    if b"<text" not in lowered:
        return svg_bytes
    from xml.etree import ElementTree as ET
    from shapely.affinity import affine_transform

    ns = "{http://www.w3.org/2000/svg}"
    root = ET.fromstring(svg_bytes)
    if "fill" not in root.attrib:
        root.set("fill", "none")
    texts = [el for el in root.iter() if el.tag.split("}")[-1].lower() == "text"]
    parents = {c: p for p in root.iter() for c in list(p)}
    for el in texts:
        content = "".join(el.itertext()).strip()
        if not content:
            parent = parents.get(el)
            if parent is not None:
                parent.remove(el)
            continue
        height = _font_size_mm(el)
        anchor = (el.get("text-anchor") or "start").lower()
        baseline = (el.get("dominant-baseline") or "hanging").lower()
        if baseline not in {"hanging", "center", "middle", "alphabetic"}:
            baseline = "hanging"
        if baseline == "middle":
            baseline = "center"
        geom = layout_text(
            content,
            0.0,
            0.0,
            height,
            anchor="center" if anchor in {"middle", "center"} else ("end" if anchor == "end" else "start"),
            baseline=baseline,
        )
        if geom is None:
            continue
        matrix = _parse_matrix(el.get("transform"))
        if matrix:
            geom = affine_transform(geom, matrix)
        parent = parents.get(el)
        if parent is None:
            continue
        idx = list(parent).index(el)
        parent.remove(el)
        nodes = geom_path_elements(geom, _style_color(el), 0.22, ns)
        for i, node in enumerate(nodes):
            parent.insert(idx + i, node)
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def canon_color(value: str | None) -> str:
    """Map Payas / CSS colors onto LaserCAD palette layers."""
    raw = (value or "").strip()
    if not raw:
        return LASER_ETCH
    lower = re.sub(r"\s+", "", raw.lower())
    if lower in {"none", "transparent"}:
        return "none"
    if lower in {"#222", "#222222", "#212121", "#1a1a1a", "#333", "#333333", "#444", "#444444"}:
        return LASER_ETCH
    if lower in {"#cc0000", "#c00", "#c45a10", "#ff5a1f", "#c00000"}:
        return LASER_CUT
    match = re.fullmatch(r"rgb\((\d+),(\d+),(\d+)\)", lower)
    if match:
        r, g, b = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
        if r < 55 and g < 55 and b < 55:
            return LASER_ETCH
        if r > 170 and g < 90 and b < 90:
            return LASER_CUT
        if r == 0 and g >= 200 and b == 0:
            return "#00FF00"
        return f"#{r:02X}{g:02X}{b:02X}"
    if lower.startswith("#") and len(lower) == 7:
        return raw.upper() if raw.startswith("#") else raw
    return raw


def _remap_style(style: str) -> str:
    parts = []
    for chunk in style.split(";"):
        if not chunk.strip():
            continue
        if ":" not in chunk:
            parts.append(chunk)
            continue
        key, val = chunk.split(":", 1)
        key_l = key.strip().lower()
        val = val.strip()
        if key_l in {"stroke", "fill", "color"}:
            mapped = canon_color(val)
            if key_l == "fill" and mapped not in {"none", "transparent"}:
                mapped = "none"
            parts.append(f"{key.strip()}: {mapped}")
        else:
            parts.append(chunk.strip())
    return "; ".join(parts)


def _indent(elem, level: int = 0) -> None:
    pad = "\n" + "  " * level
    children = list(elem)
    if children:
        if not (elem.text and elem.text.strip()):
            elem.text = pad + "  "
        for i, child in enumerate(children):
            _indent(child, level + 1)
            child.tail = pad + ("  " if i < len(children) - 1 else "")
        if not (children[-1].tail and children[-1].tail.strip()):
            children[-1].tail = pad
    elif level and not (elem.tail and elem.tail.strip()):
        elem.tail = pad


def prepare_lasercad_svg(svg_bytes: bytes) -> bytes:
    """Text → paths, LaserCAD palette colors, paths on separate lines."""
    if not svg_bytes:
        return svg_bytes
    svg_bytes = laserize_svg(svg_bytes)
    text = svg_bytes.decode("utf-8")
    text = re.sub(r"#cc0000", LASER_CUT, text, flags=re.I)
    text = re.sub(r"#222222", LASER_ETCH, text, flags=re.I)
    text = re.sub(r"rgb\(\s*34\s*,\s*34\s*,\s*34\s*\)", LASER_ETCH, text, flags=re.I)
    if "<path" in text and "\n<path" not in text:
        text = text.replace("<path", "\n<path")
        text = text.replace("</g>", "\n</g>")
        text = text.replace("</svg>", "\n</svg>")
    return text.encode("utf-8")
