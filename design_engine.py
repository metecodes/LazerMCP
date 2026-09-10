"""One CAD compiler: presets + primitives. New products should not need a new MCP tool."""

from __future__ import annotations

import math
from typing import Any
from xml.etree import ElementTree as ET

from shapely.affinity import translate

from boxes_adapter import PAYAS_DEFAULTS
from number_match_puzzle import (
    CUT,
    ETCH,
    _dots,
    _emit,
    _number,
    _rounded_rect,
    build_jigsaw_sheet,
    build_number_match_svg,
)
from text_path import svg_document, to_lasercad_y

PRESETS = {
    "jigsaw_puzzle": {
        "title": "Klasik yapboz",
        "hint": "Interlocking picture-puzzle grid. parameters: width_mm, height_mm, rows, cols, seed. Not number-dot cards.",
    },
    "number_match_puzzle": {
        "title": "Sayı eşleme yapboz",
        "hint": "1–N number-to-dot matching cards only. parameters: count, card_w, card_h, columns",
    },
}

PRIMITIVE_TYPES = (
    "box",
    "panel",
    "disc",
    "triangle",
    "propeller",
    "contour",
    "polygon",
    "jigsaw_grid",
    "jigsaw_card",
    "token_grid",
    "rounded_rect",
    "circle",
    "number",
    "pips",
    "text",
)

_PRESET_ALIASES = {
    "classic_jigsaw": "jigsaw_puzzle",
    "picture_puzzle": "jigsaw_puzzle",
    "yapboz": "jigsaw_puzzle",
    "number_match": "number_match_puzzle",
    "sayi_esleme": "number_match_puzzle",
    "jigsaw_numbers": "number_match_puzzle",
    "matching_puzzle": "number_match_puzzle",
}


def list_design_api() -> dict[str, Any]:
    from toolbox import GRAMMAR

    return {
        "presets": PRESETS,
        "primitives": list(PRIMITIVE_TYPES),
        "grammar": GRAMMAR,
        "examples": {
            "photo_then_plan": "Look at the photo, call plan_laser_job, then execute next_tool.",
            "assembly_from_photo": {
                "primitives": [
                    {
                        "type": "box",
                        "x": 80,
                        "y": 80,
                        "h": 140,
                        "bottom": True,
                        "walls": {
                            "front": {
                                "holes": [{"x": 40, "y": 120, "d": 4}],
                                "slots": [{"x": 40, "y": 45, "w": 22, "h": 32}],
                            },
                            "back": {"holes": [{"x": 40, "y": 120, "d": 4}]},
                        },
                    },
                    {"type": "triangle", "w": 80, "h": 28, "count": 2, "label": "gable"},
                    {"type": "panel", "w": 90, "h": 86, "edges": "eeee", "count": 2, "label": "roof"},
                    {"type": "propeller", "blades": 4, "d": 50, "blade_w": 12, "hole": 4, "label": "propeller"},
                    {"type": "disc", "d": 12, "hole": 4, "count": 2, "label": "spacer"},
                ]
            },
            "jigsaw_puzzle": {
                "preset": "jigsaw_puzzle",
                "parameters": {"width_mm": 300, "height_mm": 300, "rows": 10, "cols": 10},
            },
            "preset": {"preset": "number_match_puzzle", "parameters": {"count": 10}},
            "jigsaw_grid": {
                "primitives": [{"type": "jigsaw_grid", "count": 8, "columns": 2}],
            },
            "token_grid": {
                "primitives": [{"type": "token_grid", "count": 10, "columns": 5, "w": 48, "h": 48}],
            },
            "text_card": {
                "primitives": [{"type": "text", "value": "PAYAS", "height": 24}],
            },
        },
        "font": "Outline paths (bundled Arimo). No SVG <text>.",
        "note": (
            "This server is a toolbox, not a catalog. Do not ask for a new kit tool. "
            "Look at the photo, call plan_laser_job, then create_design with Boxes.py primitives "
            "(box/panel/disc/triangle/propeller/contour) using millimetres you read from the photo. "
            "create_from_reference only 2D-traces artwork. Never hand-write SVG."
        ),
    }


def _svg_sheet(cut_bits: list, etch_bits: list, sheet_w: float, sheet_h: float) -> dict[str, Any]:
    cut_bits = [to_lasercad_y(g, sheet_h) for g in cut_bits]
    etch_bits = [to_lasercad_y(g, sheet_h) for g in etch_bits]
    svg = svg_document(
        sheet_w,
        sheet_h,
        "".join(_emit(g, CUT, 0.18) for g in cut_bits),
        "".join(_emit(g, ETCH, 0.25) for g in etch_bits),
    )
    return {
        "svg_bytes": svg.encode("utf-8"),
        "width_mm": sheet_w,
        "height_mm": sheet_h,
        "count": len(cut_bits),
        "card_w": None,
        "card_h": None,
    }


def _fit_sheet(sheet_w: float, sheet_h: float) -> float:
    bed_w, bed_h = PAYAS_DEFAULTS["bed_width"], PAYAS_DEFAULTS["bed_height"]
    if sheet_w <= bed_w and sheet_h <= bed_h:
        return 1.0
    return min(bed_w / sheet_w, bed_h / sheet_h) * 0.98


def _preset(name: str, params: dict[str, Any]) -> dict[str, Any]:
    key = (name or "").strip().lower().replace(" ", "_")
    key = _PRESET_ALIASES.get(key, key)
    if key == "jigsaw_puzzle":
        from jigsaw_puzzle import build_jigsaw_puzzle

        width = float(params.get("width_mm") or params.get("size_mm") or 300)
        height = float(params.get("height_mm") or params.get("size_mm") or width)
        return build_jigsaw_puzzle(
            width_mm=width,
            height_mm=height,
            rows=int(params.get("rows") or params.get("count") or 10),
            cols=int(params.get("cols") or params.get("columns") or 10),
            seed=int(params.get("seed") or 1),
        )
    if key != "number_match_puzzle":
        known = ", ".join(PRESETS)
        raise ValueError(f"Unknown preset '{name}'. Known: {known}. Or pass primitives.")
    return build_number_match_svg(
        count=int(params.get("count") or 10),
        card_w=float(params.get("card_w") or 108),
        card_h=float(params.get("card_h") or 64),
        columns=int(params.get("columns") or 2),
    )


def _compile_jigsaw(first: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    count = int(first.get("count") or params.get("count") or 10)
    items = first.get("items")
    if not items:
        items = [{"left": i, "right_pips": i} for i in range(1, count + 1)]
    return build_jigsaw_sheet(
        items,
        card_w=float(first.get("card_w") or first.get("w") or params.get("card_w") or 108),
        card_h=float(first.get("card_h") or first.get("h") or params.get("card_h") or 64),
        columns=int(first.get("columns") or params.get("columns") or 2),
    )


def _compile_token_grid(first: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    count = max(1, min(40, int(first.get("count") or params.get("count") or 10)))
    w = float(first.get("w") or first.get("card_w") or 48)
    h = float(first.get("h") or first.get("card_h") or 48)
    columns = max(1, int(first.get("columns") or params.get("columns") or min(5, count)))
    rows = math.ceil(count / columns)
    gap = float(first.get("gap") or 6)
    margin = float(first.get("margin") or 10)
    r = min(8.0, min(w, h) * 0.14)
    sheet_w = margin * 2 + columns * w + (columns - 1) * gap
    sheet_h = margin * 2 + rows * h + (rows - 1) * gap
    fit = _fit_sheet(sheet_w, sheet_h)
    if fit < 1:
        return _compile_token_grid(
            {**first, "w": w * fit, "h": h * fit, "count": count, "columns": columns},
            params,
        )
    burn = PAYAS_DEFAULTS["burn"]
    cut_bits = []
    etch_bits = []
    for i in range(count):
        n = i + 1
        col, row = i % columns, i // columns
        x = margin + col * (w + gap)
        y = margin + row * (h + gap)
        token = translate(_rounded_rect(w, h, r).buffer(-burn), x, y)
        cut_bits.append(token)
        cx, cy = x + w / 2, y + h / 2
        glyph = _number(n, cx, cy, h * 0.46)
        if glyph is not None:
            etch_bits.append(glyph)
        if first.get("pips"):
            for dot in _dots(min(n, 10), cx, cy - h * 0.02, span=min(w, h) * 0.55, radius=h * 0.04):
                etch_bits.append(dot.boundary)
    built = _svg_sheet(cut_bits, etch_bits, sheet_w, sheet_h)
    built["count"] = count
    built["card_w"] = w
    built["card_h"] = h
    return built


def _compile_primitives(primitives: list[Any], parameters: dict[str, Any] | None) -> dict[str, Any]:
    if not primitives:
        raise ValueError("primitives is empty")
    params = parameters or {}
    from toolbox import is_assembly, compile_toolbox

    if is_assembly(primitives):
        return compile_toolbox(primitives, params)
    first = primitives[0] if isinstance(primitives[0], dict) else {}
    kind = (first.get("type") or first.get("kind") or "").lower()
    if kind in {"jigsaw_grid", "jigsaw_sheet", "number_match_puzzle"}:
        return _compile_jigsaw(first, params)
    if kind == "jigsaw_card":
        return build_jigsaw_sheet(
            [{"left": first.get("left", 1), "right_pips": first.get("right_pips") or first.get("n") or 1}],
            card_w=float(first.get("w") or first.get("card_w") or 108),
            card_h=float(first.get("h") or first.get("card_h") or 64),
            columns=1,
        )
    if kind in {"token_grid", "rounded_rect"}:
        return _compile_token_grid(first, params)
    if kind in {"text", "label", "number"}:
        return _compile_text(first, params)
    raise ValueError(
        "Pass assembly primitives (box, panel, disc, triangle, propeller, contour) or type=jigsaw_grid / token_grid / text. "
        f"Got type={kind!r}. Primitive types: {', '.join(PRIMITIVE_TYPES)}"
    )


def _compile_text(first: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    from text_path import layout_text

    value = str(first.get("value") or first.get("text") or params.get("text") or "")
    height = float(first.get("height") or first.get("h") or params.get("height") or 24)
    glyph = layout_text(value, 0.0, 0.0, height)
    if glyph is None:
        raise ValueError("text is empty or has no drawable glyphs")
    minx, miny, maxx, maxy = glyph.bounds
    margin = float(first.get("margin") or 10)
    sheet_w = (maxx - minx) + margin * 2
    sheet_h = (maxy - miny) + margin * 2
    placed = translate(glyph, margin - minx, margin - miny)
    return _svg_sheet([], [placed], sheet_w, sheet_h)


def compile_design(
    preset: str | None = None,
    primitives: list[Any] | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params = parameters or {}
    if preset:
        built = _preset(preset, params)
        built["preset"] = (preset or "").strip().lower().replace(" ", "_")
        return built
    if primitives:
        built = _compile_primitives(primitives, params)
        from toolbox import is_assembly

        built["preset"] = "toolbox" if is_assembly(primitives) else (
            primitives[0].get("type") if isinstance(primitives[0], dict) else "primitives"
        )
        return built
    raise ValueError(
        "Pass primitives (box/panel/disc/triangle/propeller/contour from the photo) or a preset "
        "(jigsaw_puzzle, number_match_puzzle). For a photo: plan_laser_job then next_tool. "
        "Do not ask for a new kit tool."
    )


def _mm_size(value: str | None) -> float | None:
    if not value:
        return None
    text = value.strip().lower().replace("mm", "").replace("px", "")
    try:
        return float(text)
    except ValueError:
        return None


def import_svg_document(svg_text: str) -> dict[str, Any]:
    """Keep incoming SVG, stamp Payas size if missing; do not invent geometry."""
    raw = (svg_text or "").strip()
    if not raw:
        raise ValueError("svg is empty")
    if "<svg" not in raw.lower():
        raise ValueError("svg must contain an <svg> root")
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid SVG: {exc}") from exc
    width = _mm_size(root.attrib.get("width"))
    height = _mm_size(root.attrib.get("height"))
    if width is None or height is None:
        vb = (root.attrib.get("viewBox") or "").replace(",", " ").split()
        if len(vb) == 4:
            width = width or float(vb[2])
            height = height or float(vb[3])
            root.set("width", f"{width:.2f}mm")
            root.set("height", f"{height:.2f}mm")
            raw = ET.tostring(root, encoding="unicode")
    return {
        "svg_bytes": raw.encode("utf-8"),
        "width_mm": width,
        "height_mm": height,
        "count": None,
        "card_w": None,
        "card_h": None,
        "preset": "import_svg",
        "imported": True,
    }
