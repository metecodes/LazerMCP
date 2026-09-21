"""Optional engrave/cut marks on a toolbox part. Drawn in the part callback so nesting moves them."""

from __future__ import annotations

import math
import re
from typing import Any

from shapely.affinity import rotate as shp_rotate
from shapely.affinity import scale as shp_scale
from shapely.affinity import translate as shp_translate
from shapely.geometry import LineString, MultiLineString

from text_path import layout_text, stroke_geom

MARKING_TYPES = frozenset(
    {
        "marking",
        "markings",
        "mark",
        "engrave",
        "etch",
        "engraving",
        "logo",
        "icon",
        "lineart",
        "line_art",
    }
)

_KIND_ALIAS = {
    "image": "image",
    "bitmap": "image",
    "text": "text",
    "label": "text",
    "caption": "text",
    "path": "path",
    "logo": "path",
    "vector": "path",
    "svg": "path",
    "icon": "icon",
    "symbol": "icon",
    "line": "line",
    "lines": "line",
    "lineart": "line",
    "line_art": "line",
    "polyline": "line",
}

_NUM = re.compile(r"[MmLlHhVvCcSsQqTtAaZz]|[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?")


def _num(value: Any, default: float = 0.0) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def _kind(mark: dict[str, Any]) -> str:
    raw = str(mark.get("kind") or mark.get("content") or mark.get("type") or "text").strip().lower()
    if raw in MARKING_TYPES and raw not in _KIND_ALIAS:
        if mark.get("value") or mark.get("text"):
            return "text"
        if mark.get("icon") or mark.get("name"):
            return "icon"
        if mark.get("d") or mark.get("path"):
            return "path"
        if mark.get("points") or mark.get("lines"):
            return "line"
        return "text"
    return _KIND_ALIAS.get(raw, "text")


def parse_align(raw: Any) -> tuple[str, str]:
    text = str(raw or "center").lower().replace(",", "|").replace(" ", "|")
    bits = [b for b in text.split("|") if b]
    h, v = "center", "center"
    for bit in bits:
        if bit in {"left", "start"}:
            h = "left"
        elif bit in {"right", "end"}:
            h = "right"
        elif bit in {"top", "hanging"}:
            v = "top"
        elif bit in {"bottom", "alphabetic", "baseline"}:
            v = "bottom"
        elif bit in {"center", "middle"}:
            if len(bits) == 1:
                h, v = "center", "center"
    return h, v


def collect_markings(part: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(part, dict):
        return []
    out: list[dict[str, Any]] = []
    for key in ("markings", "marks", "engraves", "etches"):
        raw = part.get(key)
        if isinstance(raw, dict):
            out.append(raw)
        elif isinstance(raw, list):
            out.extend(item for item in raw if isinstance(item, dict))
    return out


def _norm_name(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-").replace(" ", "-")


def _box_wall(target: str) -> tuple[str, str | None]:
    text = _norm_name(target)
    if "." in text:
        host, wall = text.split(".", 1)
        return host, wall
    if text in {"front", "back", "left", "right", "bottom", "lid", "top"}:
        return "box", "lid" if text == "top" else text
    return text, None


def attach_marking(parts: list[dict[str, Any]], mark: dict[str, Any]) -> None:
    if not parts:
        return
    item = dict(mark)
    kind = str(item.get("type") or "").strip().lower()
    if kind in MARKING_TYPES:
        item.setdefault("kind", "icon" if kind == "icon" else "path" if kind == "logo" else "text")
    target, wall = _box_wall(item.get("target_part") or item.get("target") or item.get("part") or "")
    if wall:
        box = next((p for p in parts if str(p.get("type") or "").strip().lower() == "box"), None)
        if box and (not target or target in {"box", "body", ""}):
            walls = box.setdefault("walls", {})
            if not isinstance(walls, dict):
                walls = {}
                box["walls"] = walls
            face = walls.setdefault(wall, {})
            if not isinstance(face, dict):
                face = {}
                walls[wall] = face
            face.setdefault("markings", []).append(item)
            return
    for part in parts:
        label = _norm_name(part.get("label"))
        pkind = str(part.get("type") or "").strip().lower()
        if target and target not in {label, pkind, _norm_name(pkind)}:
            continue
        if str(part.get("type") or "").strip().lower() == "box":
            face_name = wall or "front"
            walls = part.setdefault("walls", {})
            if not isinstance(walls, dict):
                walls = {}
                part["walls"] = walls
            face = walls.setdefault(face_name, {})
            if not isinstance(face, dict):
                face = {}
                walls[face_name] = face
            face.setdefault("markings", []).append(item)
            return
        part.setdefault("markings", []).append(item)
        return
    host = next((p for p in parts if str(p.get("type") or "").strip().lower() in {"panel", "wall", "rect"}), None)
    host = host or next((p for p in parts if str(p.get("type") or "").strip().lower() == "box"), None) or parts[0]
    if str(host.get("type") or "").strip().lower() == "box":
        walls = host.setdefault("walls", {})
        if not isinstance(walls, dict):
            walls = {}
            host["walls"] = walls
        face = walls.setdefault("front", {})
        if not isinstance(face, dict):
            face = {}
            walls["front"] = face
        face.setdefault("markings", []).append(item)
        return
    host.setdefault("markings", []).append(item)


def _circle(cx: float, cy: float, r: float, n: int = 24) -> list[tuple[float, float]]:
    return [
        (cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n))
        for i in range(n + 1)
    ]


def _star(n: int = 5) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(n * 2 + 1):
        ang = -math.pi / 2 + i * math.pi / n
        rad = 0.48 if i % 2 == 0 else 0.20
        pts.append((0.5 + rad * math.cos(ang), 0.5 + rad * math.sin(ang)))
    return pts


def _heart() -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for i in range(25):
        t = math.pi * 2 * i / 24
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((0.5 + x / 36.0, 0.48 + y / 36.0))
    return pts


ICONS: dict[str, list[list[tuple[float, float]]]] = {
    "plus": [[(0.5, 0.12), (0.5, 0.88)], [(0.12, 0.5), (0.88, 0.5)]],
    "cross": [[(0.5, 0.12), (0.5, 0.88)], [(0.12, 0.5), (0.88, 0.5)]],
    "x": [[(0.18, 0.18), (0.82, 0.82)], [(0.82, 0.18), (0.18, 0.82)]],
    "arrow": [[(0.12, 0.5), (0.82, 0.5)], [(0.58, 0.28), (0.82, 0.5), (0.58, 0.72)]],
    "circle": [_circle(0.5, 0.5, 0.38)],
    "square": [[(0.18, 0.18), (0.82, 0.18), (0.82, 0.82), (0.18, 0.82), (0.18, 0.18)]],
    "triangle": [[(0.5, 0.14), (0.86, 0.82), (0.14, 0.82), (0.5, 0.14)]],
    "star": [_star()],
    "heart": [_heart()],
}


def _as_polylines(raw: Any) -> list[list[tuple[float, float]]]:
    if not raw:
        return []
    if isinstance(raw, dict):
        raw = raw.get("points") or raw.get("lines") or []
    if isinstance(raw, str):
        return parse_svg_path(raw)
    if not isinstance(raw, list) or not raw:
        return []
    first = raw[0]
    if isinstance(first, (int, float)):
        nums = [float(x) for x in raw]
        return [[(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]] if len(nums) >= 4 else []
    if isinstance(first, (list, tuple)) and first and isinstance(first[0], (list, tuple, dict)):
        return [line for line in (_one_line(item) for item in raw) if len(line) >= 2]
    line = _one_line(raw)
    return [line] if len(line) >= 2 else []


def _one_line(raw: Any) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    if not isinstance(raw, list):
        return pts
    for item in raw:
        if isinstance(item, dict):
            pts.append((_num(item.get("x")), _num(item.get("y"))))
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            pts.append((float(item[0]), float(item[1])))
    return pts


def parse_svg_path(d: str) -> list[list[tuple[float, float]]]:
    tokens = _NUM.findall(str(d or ""))
    if not tokens:
        return []
    lines: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    x = y = 0.0
    sx = sy = 0.0
    i = 0
    cmd = "M"

    def take(n: int) -> list[float]:
        nonlocal i
        out: list[float] = []
        while len(out) < n and i < len(tokens):
            tok = tokens[i]
            i += 1
            if tok.isalpha():
                i -= 1
                break
            out.append(float(tok))
        return out

    def push(px: float, py: float) -> None:
        nonlocal x, y
        x, y = px, py
        cur.append((x, y))

    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            cmd = tok
            i += 1
            if cmd in "Zz":
                if cur:
                    cur.append((sx, sy))
                    lines.append(cur)
                    cur = []
                x, y = sx, sy
            continue
        if cmd in "Mm":
            nums = take(2)
            if len(nums) < 2:
                break
            nx, ny = nums
            if cur:
                lines.append(cur)
                cur = []
            if cmd == "m":
                nx, ny = x + nx, y + ny
            push(nx, ny)
            sx, sy = x, y
            cmd = "l" if cmd == "m" else "L"
        elif cmd in "Ll":
            nums = take(2)
            if len(nums) < 2:
                break
            nx, ny = nums
            if cmd == "l":
                nx, ny = x + nx, y + ny
            push(nx, ny)
        elif cmd in "Hh":
            nums = take(1)
            if not nums:
                break
            nx = x + nums[0] if cmd == "h" else nums[0]
            push(nx, y)
        elif cmd in "Vv":
            nums = take(1)
            if not nums:
                break
            ny = y + nums[0] if cmd == "v" else nums[0]
            push(x, ny)
        elif cmd in "Cc":
            nums = take(6)
            if len(nums) < 6:
                break
            if cmd == "c":
                nums = [x + nums[0], y + nums[1], x + nums[2], y + nums[3], x + nums[4], y + nums[5]]
            p0 = (x, y)
            p1, p2, p3 = (nums[0], nums[1]), (nums[2], nums[3]), (nums[4], nums[5])
            for step in range(1, 9):
                t = step / 8.0
                u = 1.0 - t
                px = u * u * u * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t * t * t * p3[0]
                py = u * u * u * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t * t * t * p3[1]
                push(px, py)
        elif cmd in "Qq":
            nums = take(4)
            if len(nums) < 4:
                break
            if cmd == "q":
                nums = [x + nums[0], y + nums[1], x + nums[2], y + nums[3]]
            p0 = (x, y)
            p1, p2 = (nums[0], nums[1]), (nums[2], nums[3])
            for step in range(1, 7):
                t = step / 6.0
                u = 1.0 - t
                push(u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0], u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])
        elif cmd in "SsTtAa":
            n = 4 if cmd in "Ss" else 2 if cmd in "Tt" else 7
            nums = take(n)
            if len(nums) < 2:
                break
            nx, ny = nums[-2], nums[-1]
            if cmd.islower():
                nx, ny = x + nx, y + ny
            push(nx, ny)
        else:
            i += 1
    if cur:
        lines.append(cur)
    return [line for line in lines if len(line) >= 2]


def _geom_from_lines(lines: list[list[tuple[float, float]]], closed: bool = False):
    geoms = []
    for line in lines:
        if len(line) < 2:
            continue
        pts = list(line)
        if closed and pts[0] != pts[-1]:
            pts.append(pts[0])
        geoms.append(LineString(pts))
    if not geoms:
        return None
    return geoms[0] if len(geoms) == 1 else MultiLineString(geoms)


def _place(geom, x: float, y: float, width: float | None, height: float | None, rotation: float, align: Any):
    if geom is None or geom.is_empty:
        return None
    minx, miny, maxx, maxy = geom.bounds
    bw = max(maxx - minx, 1e-6)
    bh = max(maxy - miny, 1e-6)
    if width and height:
        scale = min(float(width) / bw, float(height) / bh)
    elif width:
        scale = float(width) / bw
    elif height:
        scale = float(height) / bh
    else:
        scale = 1.0
    geom = shp_scale(geom, xfact=scale, yfact=scale, origin=(minx, miny))
    minx, miny, maxx, maxy = geom.bounds
    h_align, v_align = parse_align(align)
    if h_align == "left":
        xoff = x - minx
    elif h_align == "right":
        xoff = x - maxx
    else:
        xoff = x - (minx + maxx) / 2.0
    if v_align == "bottom":
        yoff = y - miny
    elif v_align == "top":
        yoff = y - maxy
    else:
        yoff = y - (miny + maxy) / 2.0
    geom = shp_translate(geom, xoff=xoff, yoff=yoff)
    if rotation:
        geom = shp_rotate(geom, float(rotation), origin=(x, y))
    return geom


def marking_geom(mark: dict[str, Any]):
    kind = _kind(mark)
    x = _num(mark.get("x") or mark.get("cx"), 0.0)
    y = _num(mark.get("y") or mark.get("cy"), 0.0)
    width = mark.get("width") if mark.get("width") not in (None, "") else mark.get("w")
    height = mark.get("height") if mark.get("height") not in (None, "") else mark.get("h")
    width = float(width) if width not in (None, "") else None
    height = float(height) if height not in (None, "") else None
    rotation = _num(mark.get("rotation") if mark.get("rotation") not in (None, "") else mark.get("angle"), 0.0)
    align = mark.get("align") or "center"
    closed = bool(mark.get("closed"))

    if kind == "image":
        if str(mark.get('operation','engrave')).lower() not in {'engrave','etch'}:
            raise ValueError('Uploaded image markings are engraving only')
        if not width and not height:
            raise ValueError('Image marking requires width or height in mm')
        from image_engraving import image_geometry
        return _place(image_geometry(mark),x,y,width,height,rotation,align)

    if kind == "text":
        value = str(mark.get("value") or mark.get("text") or mark.get("label") or "").strip()
        if not value:
            return None
        size = height or 6.0
        geom = layout_text(value, 0.0, 0.0, size, y_up=True, anchor="left", baseline="bottom")
        # When both limits are supplied, fit inside both. This prevents short
        # labels such as "I" from becoming taller than a learning-card cell.
        return _place(geom, x, y, width, height or size, rotation, align)

    if kind == "icon":
        name = str(mark.get("icon") or mark.get("name") or mark.get("value") or "plus").strip().lower()
        if name not in ICONS:
            raise ValueError(f"Unknown icon '{name}': supply the actual vector logo path instead of a placeholder")
        strokes = ICONS[name]
        geom = _geom_from_lines(strokes, closed=name in {"circle", "square", "triangle", "star", "heart"})
        return _place(geom, x, y, width or height or 10.0, height or width or 10.0, rotation, align)

    lines = _as_polylines(mark.get("d") or mark.get("path") or mark.get("points") or mark.get("lines") or mark.get("line"))
    if not lines:
        return None
    geom = _geom_from_lines(lines, closed=closed)
    if width or height:
        return _place(geom, x, y, width, height, rotation, align)
    if rotation:
        geom = shp_rotate(geom, rotation, origin=(x, y))
    return geom


def draw_markings(box: Any, markings: list[Any], origin: tuple[float, float] = (0.0, 0.0)) -> None:
    from boxes import Color

    ox, oy = origin
    for raw in markings or []:
        if not isinstance(raw, dict):
            continue
        geom = marking_geom(raw)
        if geom is None or geom.is_empty:
            continue
        if ox or oy:
            geom = shp_translate(geom, xoff=ox, yoff=oy)
        from manufacturing import EXPORT_OPERATIONS, _marking_role, resolve_operation

        given = raw.get("operation") if raw.get("operation") not in (None, "") else raw.get("layer") or raw.get("op")
        intent = resolve_operation(
            semantic_role=_marking_role(raw),
            operation=given,
            origin="EXPLICIT" if given not in (None, "") else "",
        )
        op = intent["operation"]
        if op not in EXPORT_OPERATIONS:
            continue
        if op == "CUT":
            color = Color.INNER_CUT
        elif op == "SCORE":
            color = Color.YELLOW
        elif op == "GUIDE":
            color = Color.ANNOTATIONS
        else:
            color = Color.ETCHING
        with box.saved_context():
            box.set_source_color(color)
            stroke_geom(box.ctx, geom)
