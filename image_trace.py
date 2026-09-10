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
from text_path import svg_document, to_lasercad_y

CUT = "#FF0000"
ETCH = "#000000"
CUT_W = 0.35
ETCH_W = 0.28

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
    if img.mode in {"RGBA", "LA"}:
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
        return bg
    return img.convert("RGB")


def _otsu(arr: np.ndarray) -> int:
    hist, _ = np.histogram(arr.astype(np.uint8), 256, (0, 256))
    total = int(arr.size)
    sum1 = float(np.dot(np.arange(256), hist))
    sum_b = 0.0
    w_b = 0
    best = 0.0
    thresh = 127
    for i in range(256):
        w_b += int(hist[i])
        if w_b == 0:
            continue
        w_f = total - w_b
        if w_f == 0:
            break
        sum_b += i * float(hist[i])
        m_b = sum_b / w_b
        m_f = (sum1 - sum_b) / w_f
        between = w_b * w_f * (m_b - m_f) ** 2
        if between > best:
            best = between
            thresh = i
    return thresh


def _morph(mask: np.ndarray, radius: int, op: str) -> np.ndarray:
    if radius <= 0:
        return mask.astype(np.uint8)
    pad = np.pad(mask.astype(np.uint8), radius, mode="constant", constant_values=0 if op == "dilate" else 1)
    h, w = mask.shape
    acc = None
    r2 = radius * radius
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy > r2:
                continue
            window = pad[radius + dy : radius + dy + h, radius + dx : radius + dx + w]
            acc = window.copy() if acc is None else (np.maximum(acc, window) if op == "dilate" else np.minimum(acc, window))
    return acc.astype(np.uint8)


def _score_mask(mask: np.ndarray) -> float:
    frac = float(mask.mean())
    if frac < 0.002 or frac > 0.48:
        return -1.0
    # Prefer connected ink over speckle: dilate should not explode.
    grown = float(_morph(mask, 2, "dilate").mean())
    if grown > 0.7:
        return -1.0
    return 1.0 - abs(frac - 0.10) - max(0.0, grown - frac - 0.12)


def _keep_large(mask: np.ndarray, min_px: int = 40) -> np.ndarray:
    h, w = mask.shape
    ink = int(mask.sum())
    if ink == 0 or ink > 450_000:
        return mask
    seen = np.zeros_like(mask, dtype=np.uint8)
    out = np.zeros_like(mask, dtype=np.uint8)
    ys, xs = np.where(mask > 0)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if seen[y, x]:
            continue
        stack = [(y, x)]
        seen[y, x] = 1
        blob: list[tuple[int, int]] = []
        while stack:
            cy, cx = stack.pop()
            blob.append((cy, cx))
            for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                    seen[ny, nx] = 1
                    stack.append((ny, nx))
        if len(blob) >= min_px:
            for by, bx in blob:
                out[by, bx] = 1
    return out if int(out.sum()) >= min_px else mask


def _crop_mask(mask: np.ndarray, pad: int = 10) -> np.ndarray:
    ys, xs = np.where(mask > 0)
    if ys.size == 0:
        return mask
    y0, y1 = max(0, int(ys.min()) - pad), min(mask.shape[0], int(ys.max()) + pad + 1)
    x0, x1 = max(0, int(xs.min()) - pad), min(mask.shape[1], int(xs.max()) + pad + 1)
    return mask[y0:y1, x0:x1]


def _binary_mask(img: Image.Image, invert: bool | None, threshold: int) -> np.ndarray:
    gray = ImageOps.autocontrast(ImageOps.grayscale(img.filter(ImageFilter.MedianFilter(size=3))), cutoff=1)
    arr = np.asarray(gray, dtype=np.float32)
    radius = max(5, min(arr.shape) // 32)
    local = np.asarray(gray.filter(ImageFilter.GaussianBlur(radius=radius)), dtype=np.float32)
    adaptive = (arr < (local - 14.0)).astype(np.uint8)
    otsu_t = _otsu(arr)
    global_m = (arr < float(otsu_t)).astype(np.uint8)

    candidates: list[np.ndarray] = [adaptive, 1 - adaptive, global_m, 1 - global_m]
    user_t = int(threshold or 0)
    if user_t not in {0, 140} and 1 <= user_t <= 255:
        user = (arr < float(user_t)).astype(np.uint8)
        candidates = [user, 1 - user] + candidates

    if invert is True:
        candidates = [1 - c for c in candidates[:2]] + candidates
    elif invert is False:
        candidates = [adaptive, global_m] + ([ (arr < float(user_t)).astype(np.uint8) ] if 1 <= user_t <= 255 else [])

    ranked = sorted((_score_mask(c), int(c.sum()), c) for c in candidates)
    best = ranked[-1]
    if best[0] < 0:
        raise ValueError("No usable drawing found. Try a higher-contrast photo or threshold=0 (auto).")
    mask = best[2]
    mask = _morph(_morph(mask, 2, "dilate"), 2, "erode")
    mask = _morph(_morph(mask, 1, "erode"), 1, "dilate")
    mask = _keep_large(mask, min_px=max(120, int(mask.size * 0.0005)))
    mask = _crop_mask(mask)
    if int(mask.sum()) < 40:
        raise ValueError("No dark drawing found. Try invert=true or a different threshold.")
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

    def extend(origin: tuple[float, float]) -> list[tuple[float, float]]:
        extra: list[tuple[float, float]] = []
        cur = origin
        cur_k = _key(origin)
        while True:
            nxt = None
            for cand in adj.get(cur_k, []):
                ck = _key(cand)
                edge = (cur_k, ck) if cur_k <= ck else (ck, cur_k)
                if edge not in used:
                    nxt = cand
                    used.add(edge)
                    break
            if nxt is None:
                break
            extra.append(nxt)
            cur = nxt
            cur_k = _key(nxt)
            if _key(extra[-1]) == _key(origin) and len(extra) > 2:
                break
        return extra

    for a, b in segments:
        start_k = _key(a)
        first_edge = (start_k, _key(b)) if start_k <= _key(b) else (_key(b), start_k)
        if first_edge in used:
            continue
        used.add(first_edge)
        tail = extend(b)
        head = extend(a)
        line = list(reversed(head)) + [a, b] + tail
        if len(line) >= 5:
            polylines.append(line)
    return polylines


def _to_geometry(line: list[tuple[float, float]], px_to_mm: float, simplify_mm: float):
    coords = [(p[0] * px_to_mm, p[1] * px_to_mm) for p in line]
    closed = abs(coords[0][0] - coords[-1][0]) < 1e-6 and abs(coords[0][1] - coords[-1][1]) < 1e-6
    if closed and len(coords) >= 4:
        geom = Polygon(coords)
        if not geom.is_valid:
            geom = geom.buffer(0)
        if geom.is_empty or geom.area < 1.6:
            return None
        return geom.simplify(simplify_mm, preserve_topology=True)
    ls = LineString(coords)
    if ls.length < 3.0:
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


def _svg_path(geom, stroke: str, width: float) -> str:
    attrs = f'fill="none" stroke="{stroke}" stroke-width="{width:.2f}" stroke-linejoin="round" stroke-linecap="round"'
    if geom.geom_type == "Polygon":
        extras = "".join(f'<path d="{_path_d(ring.coords)}" {attrs}/>' for ring in geom.interiors)
        return f'<path d="{_path_d(geom.exterior.coords)}" {attrs}/>' + extras
    if geom.geom_type == "LineString":
        return f'<path d="{_path_d(geom.coords)}" {attrs}/>'
    if geom.geom_type in {"MultiPolygon", "MultiLineString", "GeometryCollection"}:
        return "".join(_svg_path(g, stroke, width) for g in geom.geoms)
    return ""


def _fuse_geoms(geoms: list, gap_mm: float = 0.55, _pass: int = 0) -> list:
    parts = []
    for g in geoms:
        try:
            buffered = g.buffer(gap_mm)
            if buffered is not None and not buffered.is_empty:
                parts.append(buffered)
        except Exception:
            continue
    if not parts:
        return geoms
    blob = unary_union(parts)
    try:
        blob = blob.buffer(-gap_mm * 0.88)
        if hasattr(blob, "buffer"):
            blob = blob.buffer(0)
    except Exception:
        return geoms
    if blob.is_empty:
        return geoms
    fused = []
    items = list(blob.geoms) if blob.geom_type in {"MultiPolygon", "GeometryCollection"} else [blob]
    for g in items:
        if g.geom_type == "Polygon" and g.area >= 12.0:
            fused.append(g.simplify(0.16, preserve_topology=True))
        elif g.geom_type == "LineString" and g.length >= 6.0:
            fused.append(g.simplify(0.16))
    if _pass == 0 and len(fused) > 20:
        return _fuse_geoms(fused, gap_mm=1.2, _pass=1)
    return fused or geoms


def _cut_and_etch(geoms: list, style: str, sheet_w: float, sheet_h: float):
    if style == "cut":
        return geoms, []
    if style == "etch":
        return [], geoms
    cut = []
    etch = []
    for g in geoms:
        if g.geom_type == "Polygon":
            cut.append(Polygon(g.exterior))
            for ring in g.interiors:
                hole = Polygon(ring)
                if hole.area >= 3.0:
                    etch.append(hole)
        elif g.geom_type == "MultiPolygon":
            for part in g.geoms:
                c, e = _cut_and_etch([part], style, sheet_w, sheet_h)
                cut.extend(c)
                etch.extend(e)
        else:
            etch.append(g)
    if not cut:
        return [geoms[0]], geoms[1:]
    cut.sort(key=lambda g: g.area, reverse=True)
    if len(cut) > 1 and cut[0].area > 0.12 * sheet_w * sheet_h:
        etch = cut[1:] + etch
        cut = [cut[0]]
    elif len(cut) > 1:
        outline = unary_union(cut).buffer(1.4).buffer(-0.7)
        if not outline.is_empty:
            etch = cut + etch
            cut = [outline]
    return cut, etch


def trace_reference_svg(
    *,
    image_base64: str | None = None,
    image_bytes: bytes | None = None,
    width_mm: float = 200.0,
    style: str = "cut_and_etch",
    invert: bool | None = None,
    threshold: int = 0,
) -> dict[str, Any]:
    img = _decode_image(image_base64, image_bytes)
    longest = max(img.size)
    if longest > 1800:
        scale = 1800 / longest
        img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.Resampling.LANCZOS)
    mask = _binary_mask(img, invert, int(threshold or 0))
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
        geom = _to_geometry(line, px_to_mm, simplify_mm=max(0.08, px_to_mm * 0.7))
        if geom is not None and not geom.is_empty:
            geoms.append(geom)
    geoms = _fuse_geoms(geoms)
    if not geoms:
        raise ValueError("Could not trace vector paths from this image.")

    style = (style or "cut_and_etch").strip().lower()
    if style not in {"cut", "etch", "cut_and_etch"}:
        style = "cut_and_etch"
    cut_geoms, etch_geoms = _cut_and_etch(geoms, style, width_mm, height_mm)

    burn = PAYAS_DEFAULTS["burn"]
    offset_cut = []
    for g in cut_geoms:
        if g.geom_type in {"Polygon", "MultiPolygon"}:
            inset = g.buffer(-burn / 2.0)
            offset_cut.append(inset if not inset.is_empty else g)
        else:
            offset_cut.append(g)

    cut_paths = "".join(_svg_path(to_lasercad_y(g, height_mm), CUT, CUT_W) for g in offset_cut)
    etch_paths = "".join(_svg_path(to_lasercad_y(g, height_mm), ETCH, ETCH_W) for g in etch_geoms)
    svg = svg_document(width_mm, height_mm, cut_paths, etch_paths)
    return {
        "svg_bytes": svg.encode("utf-8"),
        "width_mm": width_mm,
        "height_mm": height_mm,
        "path_count": len(offset_cut) + len(etch_geoms),
        "cut_paths": len(offset_cut),
        "etch_paths": len(etch_geoms),
        "style": style,
    }
