"""Tell the client AI how Laser MCP will cut a job. Call this before generating."""

from __future__ import annotations

import re
from typing import Any

from boxes_adapter import PAYAS_DEFAULTS

_KITS = (
    (("astronot", "astronaut"), "create_astronaut", {}),
    (("ressam", "drawing robot", "drawing_robot"), "create_drawing_robot", {}),
    (("kumbara", "robot bank", "hayal kumbara", "payasrobot"), "create_robot_bank", {}),
    (("trafik", "traffic light"), "create_traffic_light", {}),
    (("yat ", "yacht", "tekne kit"), "create_yacht", {}),
    (("ürün kutusu", "urun kutusu", "product box", "abox"), "create_product_box", {"x": 220, "y": 160, "h": 50}),
)


def _norm(text: str) -> str:
    return (text or "").casefold().replace("ı", "i").replace("â", "a").replace("ş", "s").replace("ğ", "g")


def _size_mm(text: str) -> tuple[float | None, float | None]:
    cm = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*cm", text)
    if cm:
        return float(cm.group(1)) * 10.0, float(cm.group(2)) * 10.0
    mm = re.search(r"(\d+(?:\.\d+)?)\s*[x×]\s*(\d+(?:\.\d+)?)\s*mm", text)
    if mm:
        return float(mm.group(1)), float(mm.group(2))
    one_cm = re.search(r"(\d+(?:\.\d+)?)\s*cm", text)
    if one_cm:
        value = float(one_cm.group(1)) * 10.0
        return value, value
    one_mm = re.search(r"(\d+(?:\.\d+)?)\s*mm", text)
    if one_mm and float(one_mm.group(1)) >= 40:
        value = float(one_mm.group(1))
        return value, value
    return None, None


def _grid(text: str, pieces: int | None) -> tuple[int, int]:
    grid = re.search(r"(\d+)\s*[x×]\s*(\d+)", text)
    if grid:
        rows, cols = int(grid.group(1)), int(grid.group(2))
        if rows >= 2 and cols >= 2 and rows * cols <= 1600:
            return rows, cols
    if pieces:
        side = round(pieces ** 0.5)
        if side >= 2 and side * side == pieces:
            return side, side
        if pieces == 100:
            return 10, 10
    return 10, 10


def _pieces(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(parca|parça|piece|pcs)", text)
    if match:
        return int(match.group(1))
    return None


def _wants_dxf(text: str, output: str | None) -> str:
    fmt = (output or "svg").strip().lower()
    if fmt in {"dxf", "both", "svg+dxf"}:
        return "both" if fmt != "dxf" else "dxf"
    if "dxf" in text:
        return "both"
    return "svg"


def _number_match(text: str) -> bool:
    keys = (
        "sayi esleme",
        "sayı esleme",
        "number match",
        "number-match",
        "nokta esleme",
        "sayi-nokta",
        "sayı-nokta",
        "dot matching",
    )
    return any(key in text for key in keys)


def _classic_jigsaw(text: str) -> bool:
    if _number_match(text):
        return False
    keys = (
        "yapboz",
        "puzzle",
        "jigsaw",
        "birbirine gecmeli",
        "interlocking",
        "100 parca",
        "100 parça",
        "klasik puzzle",
        "klasik yapboz",
    )
    return any(key in text for key in keys)


def plan_cad(
    intent: str,
    has_image: bool = False,
    width_mm: float | None = None,
    height_mm: float | None = None,
    output: str = "svg",
) -> dict[str, Any]:
    raw = (intent or "").strip()
    if not raw:
        raise ValueError("intent is required. Describe the drawing the user wants.")
    text = _norm(raw)
    fmt = _wants_dxf(text, output)
    parsed_w, parsed_h = _size_mm(text)
    width_mm = float(width_mm) if width_mm else parsed_w
    height_mm = float(height_mm) if height_mm else parsed_h
    pieces = _pieces(text)
    rows, cols = _grid(text, pieces)

    for keys, tool, args in _KITS:
        if any(key in text for key in keys):
            return _ok(tool, dict(args), "Named Payas kit. Do not trace a photo for this.", fmt)

    if _number_match(text):
        params = {"count": pieces or 10, "card_w": 108, "card_h": 64, "columns": 2}
        return _ok(
            "create_design",
            {"preset": "number_match_puzzle", "parameters": params, "output": fmt},
            "Number-to-dot matching cards only. Not a classic 100-piece puzzle.",
            fmt,
        )

    if _classic_jigsaw(text):
        board_w = width_mm or 300.0
        board_h = height_mm or board_w
        if has_image:
            return _ok(
                "create_from_reference",
                {
                    "image_base64": "<user image>",
                    "width_mm": board_w,
                    "height_mm": board_h,
                    "layout": "jigsaw",
                    "rows": rows,
                    "cols": cols,
                    "style": "etch",
                    "output": fmt,
                },
                "Classic interlocking puzzle: photo is etch, 10×10-style knobs are cut. Not number-dot cards.",
                fmt,
            )
        return _ok(
            "create_design",
            {
                "preset": "jigsaw_puzzle",
                "parameters": {
                    "width_mm": board_w,
                    "height_mm": board_h,
                    "rows": rows,
                    "cols": cols,
                },
                "output": fmt,
            },
            "Blank interlocking jigsaw grid. Ask for the photo if the artwork should be on the pieces.",
            fmt,
        )

    if has_image or any(word in text for word in ("foto", "photo", "resim", "cizim", "çizim", "logo", "görsel", "gorsel")):
        args = {
            "image_base64": "<user image>",
            "width_mm": width_mm or 200.0,
            "style": "cut_and_etch",
            "output": fmt,
        }
        if height_mm:
            args["height_mm"] = height_mm
        need = None if has_image else "Ask the user for the image, then call create_from_reference with image_base64."
        return _ok(
            "create_from_reference",
            args,
            "Trace the submitted drawing. Do not substitute number-match cards.",
            fmt,
            need=need,
        )

    return {
        "success": True,
        "tool": "list_cad_tools",
        "arguments": {},
        "why": "Intent is not a photo, classic jigsaw, number-match card, or named kit.",
        "need": "Ask whether they have a photo, want a 10×10 interlocking puzzle, or a named Payas kit.",
        "protocol": _protocol(),
        "defaults": dict(PAYAS_DEFAULTS),
        "forbidden": _forbidden(),
    }


def _protocol() -> str:
    return (
        "1) Call plan_cad with the user intent and has_image. "
        "2) Call only the returned tool with those arguments. "
        "3) Pass the user photo as image_base64 when the tool is create_from_reference. "
        "4) Never hand-write SVG/DXF and never produce the file outside Laser MCP."
    )


def _forbidden() -> list[str]:
    return [
        "Do not use preset=number_match_puzzle unless plan_cad says so.",
        "Do not offer to draw the SVG yourself or outside this MCP.",
        "Do not flip, rotate, or mirror geometry.",
        "Do not invent a new MCP tool.",
    ]


def _ok(tool: str, arguments: dict[str, Any], why: str, output: str, need: str | None = None) -> dict[str, Any]:
    if "output" not in arguments and tool in {"create_from_reference", "create_design"}:
        arguments = {**arguments, "output": output}
    result = {
        "success": True,
        "tool": tool,
        "arguments": arguments,
        "why": why,
        "protocol": _protocol(),
        "defaults": dict(PAYAS_DEFAULTS),
        "forbidden": _forbidden(),
        "output": output,
    }
    if need:
        result["need"] = need
    return result
