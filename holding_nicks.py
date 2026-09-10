"""Tiny uncut nicks on cut paths so notches and pieces stay on the bed."""

from __future__ import annotations

from xml.etree import ElementTree as ET

from svgpathtools import Path, parse_path

# Uncut tab width. Kerf ~0.15 mm leaves about 0.85 mm of 3 mm plywood.
NICK_MM = 1.0
MIN_LOOP_MM = 14.0
MIN_OPEN_MM = 22.0


def _is_engrave(stroke: str) -> bool:
    raw = (stroke or "").lower().replace(" ", "")
    if "00ff00" in raw or "rgb(0,255,0)" in raw:
        return True
    if "ff0000" in raw or "rgb(255,0,0)" in raw:
        return False
    if "rgb(0,0,0)" in raw or "#000000" in raw:
        return True
    return False


def _nick_count(length: float, closed: bool) -> int:
    if closed:
        if length < MIN_LOOP_MM:
            return 0
        return 2 if length >= 36.0 else 1
    if length < MIN_OPEN_MM:
        return 0
    return 2 if length >= 80.0 else 1


def _crop(path: Path, start_mm: float, end_mm: float) -> Path | None:
    total = path.length()
    if end_mm - start_mm < 0.25 or total <= 0:
        return None
    t0 = 0.0 if start_mm <= 0.02 else float(path.ilength(start_mm))
    t1 = 1.0 if end_mm >= total - 0.02 else float(path.ilength(end_mm))
    if t1 <= t0:
        return None
    try:
        piece = path.cropped(t0, t1)
    except Exception:
        return None
    return piece if piece and piece.length() >= 0.25 else None


def _closed(path: Path) -> bool:
    try:
        return bool(path.iscontinuous() and path.isclosed())
    except Exception:
        return False


def _subpaths(path: Path) -> list[Path]:
    try:
        parts = list(path.continuous_subpaths())
        return parts or [path]
    except Exception:
        return [path]


def _nick_one(path: Path, nick_mm: float) -> tuple[str, int]:
    length = float(path.length())
    nicks = _nick_count(length, _closed(path))
    if nicks < 1:
        return path.d(), 0
    gap = min(float(nick_mm), max(0.6, length / (nicks * 8.0)))
    gaps = []
    for i in range(nicks):
        center = (i + 0.5) / nicks * length
        gaps.append((center - gap / 2.0, center + gap / 2.0))
    keep: list[tuple[float, float]] = []
    cursor = 0.0
    for a, b in gaps:
        a = max(0.0, a)
        b = min(length, b)
        if a > cursor + 0.25:
            keep.append((cursor, a))
        cursor = max(cursor, b)
    if length - cursor > 0.25:
        keep.append((cursor, length))
    if len(keep) < 2:
        return path.d(), 0
    pieces = [_crop(path, a, b) for a, b in keep]
    parts = [p.d() for p in pieces if p is not None]
    if len(parts) < 2:
        return path.d(), 0
    return " ".join(parts), nicks


def nick_path_d(d: str, nick_mm: float = NICK_MM) -> tuple[str, int]:
    raw = (d or "").strip()
    if not raw:
        return d, 0
    try:
        path = parse_path(raw)
        chunks: list[str] = []
        total = 0
        for sub in _subpaths(path):
            piece, nicks = _nick_one(sub, nick_mm)
            chunks.append(piece)
            total += nicks
        if total and chunks:
            return " ".join(chunks), total
        return d, 0
    except Exception:
        return d, 0


def nick_cut_svg(svg_bytes: bytes, nick_mm: float = NICK_MM) -> bytes:
    """Leave holding nicks on CUT / red paths. Skip etch and already-bridged kits."""
    if not svg_bytes:
        return svg_bytes
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return svg_bytes
    parents = {c: p for p in root.iter() for c in list(p)}

    def _in_engrave(node) -> bool:
        cur = node
        while cur is not None:
            ident = (cur.get("id") or "").upper()
            label = (cur.get("{http://www.inkscape.org/namespaces/inkscape}label") or "").upper()
            if ident in {"ENGRAVE", "ETCH"} or "ENGRAVE" in label:
                return True
            cur = parents.get(cur)
        return False

    changed = 0
    for el in root.iter():
        tag = el.tag.split("}")[-1].lower()
        if tag != "path":
            continue
        if el.get("data-holding-bridges") or el.get("data-holding-nicks"):
            continue
        if _in_engrave(el):
            continue
        stroke = f"{el.get('stroke') or ''} {el.get('style') or ''}"
        if _is_engrave(stroke):
            continue
        d = el.get("d")
        if not d:
            continue
        new_d, nicks = nick_path_d(d, nick_mm)
        if nicks and new_d != d:
            el.set("d", new_d)
            el.set("data-holding-nicks", str(nicks))
            changed += 1
    if not changed:
        return svg_bytes
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
