"""Teach the client AI how to cut the current request. No geometry here."""

from __future__ import annotations

import re
from typing import Any

from boxes_adapter import PAYAS_DEFAULTS
from toolbox import GRAMMAR

_KITS = (
    (("astronaut", "astronot"), "create_astronaut", "Astronot kiti"),
    (("trafik", "traffic_light", "traffic light"), "create_traffic_light", "Trafik lambası"),
    (("robot bank", "kumbara", "hayal kumbara", "payasrobot"), "create_robot_bank", "Robot kumbara"),
    (("ressam", "drawing robot", "cizim robot"), "create_drawing_robot", "Ressam robot"),
    (("yacht", "yat "), "create_yacht", "Yat"),
    (("urun kutusu", "product box", "abox"), "create_product_box", "Ürün kutusu"),
)

_MATCH_CARD = (
    "sayi esleme",
    "number match",
    "number-dot",
    "nokta esleme",
    "matching card",
    "esleme kart",
)

_ASSEMBLY = (
    "finger",
    "tab-slot",
    "tab slot",
    "degirmen",
    "yel degirmen",
    "windmill",
    "mill ",
    " mill",
    "pervane",
    "propeller",
    "egimli cati",
    "cati",
    "gable",
    "4 duvar",
    "dort duvar",
    "four wall",
    "duvar",
    "kanatli",
    "maket",
    "montaj",
    "birlestir",
    "3d",
    "3-d",
    "assemble",
    "assembly",
    "kule",
    "house",
    "barn",
    "cabin",
    "shed",
    "taban",
    "kaide",
)

_TRACE_ONLY = (
    "sadece cizim",
    "sadece 2d",
    "2d iz",
    "siluet",
    "silhouette",
    "trace only",
    "vektorize",
    "vectorize",
    "logo",
)

_JIGSAW = (
    "yapboz",
    "puzzle",
    "jigsaw",
    "birbirine gec",
    "interlock",
    "parca",
    "pieces",
)


def _wants_assembly(text: str) -> bool:
    return any(k in text for k in _ASSEMBLY)


def _wants_trace_only(text: str) -> bool:
    return any(k in text for k in _TRACE_ONLY)


def _blob(*parts: str) -> str:
    return " ".join(p or "" for p in parts).lower().replace("ı", "i").replace("ş", "s").replace("ğ", "g")


def _size_mm(text: str) -> tuple[float | None, float | None]:
    cm = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*cm\b", text, re.I)
    if cm:
        return float(cm.group(1)) * 10.0, float(cm.group(2)) * 10.0
    mm = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*mm\b", text, re.I)
    if mm:
        return float(mm.group(1)), float(mm.group(2))
    one_cm = re.search(r"(\d+(?:\.\d+)?)\s*cm\b", text, re.I)
    if one_cm:
        v = float(one_cm.group(1)) * 10.0
        return v, v
    one_mm = re.search(r"(\d+(?:\.\d+)?)\s*mm\b", text, re.I)
    if one_mm:
        v = float(one_mm.group(1))
        if v >= 40:
            return v, v
    return None, None


def _grid(text: str) -> tuple[int | None, int | None]:
    cleaned = re.sub(
        r"\d+(?:\.\d+)?\s*[x×]\s*\d+(?:\.\d+)?\s*(?:cm|mm)\b",
        " ",
        text,
        flags=re.I,
    )
    grid = re.search(
        r"(\d{1,2})\s*[x×]\s*(\d{1,2})\s*(?:duzen|düzen|grid|parca|parça|piece)?",
        cleaned,
        re.I,
    )
    if grid:
        rows, cols = int(grid.group(1)), int(grid.group(2))
        if 2 <= rows <= 40 and 2 <= cols <= 40 and rows * cols <= 400:
            if rows <= 25 or cols <= 25:
                return rows, cols
    pieces = re.search(r"(\d{2,3})\s*(?:parca|parça|piece|pieces)\b", text, re.I)
    if pieces:
        n = int(pieces.group(1))
        root = int(round(n**0.5))
        if root * root == n and 2 <= root <= 40:
            return root, root
    return None, None


def _kit(text: str) -> tuple[str, str] | None:
    for keys, tool, title in _KITS:
        if any(k in text for k in keys):
            return tool, title
    return None


def _wants_jigsaw(text: str) -> bool:
    if any(k in text for k in _MATCH_CARD):
        return False
    strong = ("yapboz", "puzzle", "jigsaw", "birbirine gec", "interlock")
    if any(k in text for k in strong):
        return True
    if ("parca" in text or "piece" in text) and _grid(text)[0]:
        return True
    return False


def _wants_match_cards(text: str) -> bool:
    return any(k in text for k in _MATCH_CARD)


def _rules() -> list[str]:
    return [
        "Laser MCP is a toolbox, not a product catalog. Never ask for a new kit/tool.",
        "Never write SVG or DXF yourself. Never prepare files outside Laser MCP.",
        "Never flip, rotate, or mirror geometry.",
        "Cut #FF0000, etch #000000, LaserCAD Y-up, 3 mm poplar, kerf 0.15 mm.",
        "Notches and closed cuts get ~1 mm holding nicks. Do not omit them.",
        "Look at the photo, read millimetres from it, then compose primitives (box/panel/disc/triangle).",
        "create_from_reference only traces 2D artwork (logo, photo, jigsaw etch). Assembly = create_design primitives.",
        "number_match_puzzle is only for number-to-dot matching cards.",
        "Named create_* kits only when the plan names an existing Payas product.",
    ]


def _assembly_recipe(text: str, width: float | None, height: float | None) -> list[dict[str, Any]]:
    x = float(width or 80)
    y = float(height or width or 80)
    x = max(50.0, min(400.0, x))
    y = max(50.0, min(400.0, y))
    h = round(max(80.0, min(280.0, max(x, y) * 1.5)), 1)
    recipe: list[dict[str, Any]] = [
        {
            "type": "box",
            "x": round(x, 1),
            "y": round(y, 1),
            "h": h,
            "bottom": True,
            "walls": {"front": {"holes": [], "slots": []}},
        }
    ]
    millish = any(k in text for k in ("degirmen", "windmill", "pervane", "propeller", "cati", "gable"))
    if millish:
        shaft = 4.0
        prop = round(min(x, y) * 0.65, 1)
        recipe[0]["walls"] = {
            "front": {
                "holes": [{"x": round(x / 2, 1), "y": round(h * 0.82, 1), "d": shaft}],
                "slots": [{"x": round(x / 2, 1), "y": round(h * 0.32, 1), "w": round(x * 0.28, 1), "h": round(h * 0.28, 1)}],
            },
            "back": {"holes": [{"x": round(x / 2, 1), "y": round(h * 0.82, 1), "d": shaft}]},
        }
        recipe.extend(
            [
                {"type": "triangle", "w": round(x, 1), "h": round(max(18.0, y * 0.35), 1), "count": 2, "label": "gable"},
                {"type": "panel", "w": round(x + 10, 1), "h": round(y + 6, 1), "edges": "eeee", "count": 2, "label": "roof"},
                {"type": "disc", "d": prop, "hole": shaft, "label": "propeller"},
                {"type": "disc", "d": 14, "hole": shaft, "count": 2, "label": "spacer"},
            ]
        )
    return recipe


def _compose_plan(
    summary: str,
    width: float | None,
    height: float | None,
    fmt: str,
    look: str,
    text: str,
) -> dict[str, Any]:
    recipe = _assembly_recipe(text, width, height)
    return {
        "success": True,
        "method": "compose_primitives",
        "summary": summary,
        "next_tool": "create_design",
        "next_arguments": {"primitives": recipe, "parameters": {"format": fmt}},
        "look_again": look,
        "grammar": GRAMMAR,
        "cannot_do": [],
        "rules": _rules(),
        "defaults": dict(PAYAS_DEFAULTS),
    }


def plan_laser_job(
    user_request: str,
    what_you_see: str = "",
    has_photo: bool = False,
    want_dxf: bool = False,
) -> dict[str, Any]:
    """Return the next MCP call. Client AI must not invent SVG."""
    request = user_request or ""
    seen = what_you_see or ""
    text = _blob(request, seen)
    dxf = bool(want_dxf) or "dxf" in text
    fmt = "both" if dxf else "svg"
    width, height = _size_mm(request + " " + seen)
    rows, cols = _grid(request + " " + seen)
    photo = bool(has_photo) or bool(seen.strip())
    rules = _rules()

    if photo and _wants_match_cards(text):
        photo = False

    if _wants_match_cards(text):
        return {
            "success": True,
            "method": "number_match_cards",
            "summary": "Number-to-dot matching cards (not a picture jigsaw).",
            "next_tool": "create_design",
            "next_arguments": {
                "preset": "number_match_puzzle",
                "parameters": {"count": 10},
            },
            "look_again": "No photo trace. Call create_design with those arguments.",
            "grammar": GRAMMAR,
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

    kit = _kit(text)
    if kit:
        tool, title = kit
        return {
            "success": True,
            "method": "named_kit",
            "summary": f"Named Payas kit: {title}.",
            "next_tool": tool,
            "next_arguments": {},
            "look_again": f"Call {tool}. Do not request a new tool. Do not draw SVG yourself.",
            "grammar": GRAMMAR,
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

    if _wants_jigsaw(text) and not _wants_assembly(text):
        width = width or 300.0
        height = height or width
        rows = rows or 10
        cols = cols or 10
        if photo:
            args: dict[str, Any] = {
                "width_mm": width,
                "height_mm": height,
                "style": "etch",
                "layout": "jigsaw",
                "rows": int(rows),
                "cols": int(cols),
                "format": fmt,
            }
            return {
                "success": True,
                "method": "photo_jigsaw",
                "summary": (
                    f"Photo as etch on a {int(rows)}×{int(cols)} interlocking jigsaw, "
                    f"{width:.0f}×{height:.0f} mm."
                ),
                "next_tool": "create_from_reference",
                "next_arguments": args,
                "look_again": (
                    "Compress the photo to ~1200px JPEG and call create_from_reference "
                    "with next_arguments, then validate_svg."
                ),
                "grammar": GRAMMAR,
                "rules": rules,
                "defaults": dict(PAYAS_DEFAULTS),
            }
        return {
            "success": True,
            "method": "blank_jigsaw",
            "summary": (
                f"Blank interlocking jigsaw {int(rows)}×{int(cols)}, "
                f"{width:.0f}×{height:.0f} mm, no photo artwork."
            ),
            "next_tool": "create_design",
            "next_arguments": {
                "preset": "jigsaw_puzzle",
                "parameters": {
                    "width_mm": width,
                    "height_mm": height,
                    "rows": int(rows),
                    "cols": int(cols),
                    "format": fmt,
                },
            },
            "look_again": "Call create_design with those arguments.",
            "grammar": GRAMMAR,
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

    if _wants_assembly(text) and not _wants_trace_only(text):
        width = width or 80.0
        height = height or width
        look = (
            "LOOK at the photo again. Read millimetres from what you see "
            "(footprint, wall height, door/window, shaft, propeller diameter). "
            "Edit next_arguments.primitives accordingly, then call create_design. "
            "Add holes/slots on the wall that has the door or windows. "
            "Do not ask for a mill kit. Do not 2D-trace this as the assembly. "
            "create_from_reference is only if they also want the drawing etched on a panel."
        )
        if not photo:
            look = (
                "No photo: still compose with create_design primitives. "
                "If a photo exists, call plan_laser_job again with has_photo=true and what_you_see filled, "
                "then adjust millimetres from the picture."
            )
        return _compose_plan(
            "Compose cut parts with the toolbox: finger-joint box + extra panels/discs. "
            "The draft recipe is a starting grammar — overwrite sizes from the photo.",
            width,
            height,
            fmt,
            look,
            text,
        )

    if photo:
        width = width or 200.0
        return {
            "success": True,
            "method": "photo_trace",
            "summary": (
                f"Trace the photo into laser paths at width {width:.0f} mm "
                "(height follows the image). Outline = cut, interior = etch."
            ),
            "next_tool": "create_from_reference",
            "next_arguments": {
                "width_mm": width,
                "style": "cut_and_etch",
                "layout": "trace",
                "format": fmt,
            },
            "look_again": (
                "If this is a thing to build (walls, roof, propeller, box), call plan_laser_job again "
                "and describe those parts in what_you_see — then compose with create_design. "
                "If it is 2D artwork, compress JPEG ~1200px and call create_from_reference."
            ),
            "grammar": GRAMMAR,
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

    return {
        "success": True,
        "method": "ask_or_compose",
        "summary": (
            "No named kit. If the user sent a photo of a thing to cut and assemble, "
            "look at it and call this planner again with has_photo=true and what_you_see. "
            "If it is flat artwork, use create_from_reference."
        ),
        "next_tool": "plan_laser_job",
        "next_arguments": {"has_photo": True},
        "look_again": (
            "Look at the photo. Describe walls, roofs, holes, discs in what_you_see. "
            "Then call plan_laser_job with has_photo=true. Do not ask us to add a new kit."
        ),
        "grammar": GRAMMAR,
        "rules": rules,
        "defaults": dict(PAYAS_DEFAULTS),
    }
