"""Teach the client AI how to cut the current request. No geometry here."""

from __future__ import annotations

import re
from typing import Any

from boxes_adapter import PAYAS_DEFAULTS

_KITS = (
    (("astronaut", "astronot"), "create_astronaut", "Astronot kiti"),
    (("trafik", "traffic_light", "traffic light"), "create_traffic_light", "Trafik lambası"),
    (("robot bank", "kumbara", "hayal kumbara", "payasrobot"), "create_robot_bank", "Robot kumbara"),
    (("ressam", "drawing robot", "çizim robot"), "create_drawing_robot", "Ressam robot"),
    (("yacht", "yat "), "create_yacht", "Yat"),
    (("ürün kutusu", "product box", "abox"), "create_product_box", "Ürün kutusu"),
)

_MATCH_CARD = (
    "sayı eşleme",
    "sayi esleme",
    "number match",
    "number-dot",
    "nokta eşleme",
    "matching card",
    "eşleme kart",
)

_JIGSAW = (
    "yapboz",
    "puzzle",
    "jigsaw",
    "birbirine geç",
    "interlock",
    "parça",
    "pieces",
)


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

    rules = [
        "Never write SVG or DXF yourself. Never prepare files outside Laser MCP.",
        "Never flip, rotate, or mirror geometry.",
        "Cut #FF0000, etch #000000, LaserCAD Y-up, 3 mm poplar, kerf 0.15 mm.",
        "Call the next_tool with next_arguments. If next_tool is create_from_reference, pass the user photo as image_base64.",
        "number_match_puzzle is only for number-to-dot matching cards, never for a picture puzzle.",
    ]

    if photo and _wants_match_cards(text):
        photo = False

    if photo:
        layout = "jigsaw" if _wants_jigsaw(text) else "trace"
        if layout == "jigsaw":
            width = width or 300.0
            height = height or width
            rows = rows or 10
            cols = cols or 10
            style = "etch"
            method = "photo_jigsaw"
            summary = (
                f"Photo as etch on a {int(rows)}×{int(cols)} interlocking jigsaw, "
                f"{width:.0f}×{height:.0f} mm. Pieces share single-cut seams."
            )
        else:
            width = width or 200.0
            style = "cut_and_etch"
            method = "photo_trace"
            summary = (
                f"Trace the photo into laser paths at width {width:.0f} mm "
                "(height follows the image). Outline = cut, interior = etch."
            )
        args: dict[str, Any] = {
            "width_mm": width,
            "style": style,
            "layout": layout,
            "format": fmt,
        }
        if height:
            args["height_mm"] = height
        if layout == "jigsaw":
            args["rows"] = int(rows)
            args["cols"] = int(cols)
        return {
            "success": True,
            "method": method,
            "summary": summary,
            "next_tool": "create_from_reference",
            "next_arguments": args,
            "look_again": (
                "Go back to the photo and call create_from_reference with that image "
                "plus next_arguments. Do not substitute number_match_puzzle. Do not draw SVG yourself."
            ),
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

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
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

    if _wants_jigsaw(text):
        width = width or 300.0
        height = height or width
        rows = rows or 10
        cols = cols or 10
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
            "look_again": "Call create_design with those arguments. If the user also sent a photo, you should have set has_photo=true.",
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
            "look_again": f"Call {tool}. Do not trace a photo unless the user wants that image as artwork.",
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

    return {
        "success": True,
        "method": "ask_or_trace",
        "summary": "No photo and no named kit. If the user has an image, call this planner again with has_photo=true and what_you_see filled.",
        "next_tool": "create_from_reference",
        "next_arguments": {"width_mm": 200.0, "layout": "trace", "style": "cut_and_etch", "format": fmt},
        "look_again": "If a photo exists, look at it, describe it in what_you_see, and call plan_laser_job again with has_photo=true. Then execute next_tool.",
        "rules": rules,
        "defaults": dict(PAYAS_DEFAULTS),
    }
