"""Parametric studio makers — NOT AI. Fixed CAD recipes the product already knows."""

from __future__ import annotations

import math
from typing import Any


MAKERS = {
    "name_ornament": {
        "id": "name_ornament",
        "label_tr": "İsim süsü",
        "label_en": "Name ornament",
        "ai": False,
        "note": "Asılı isim plakası — parametrik, AI yok.",
    },
    "birdhouse": {
        "id": "birdhouse",
        "label_tr": "Kuş evi",
        "label_en": "Birdhouse",
        "ai": False,
        "note": "Boxes.py BirdHouse — finger-joint, AI yok.",
    },
    "christmas": {
        "id": "christmas",
        "label_tr": "Christmas süs",
        "label_en": "Christmas ornament",
        "ai": False,
        "note": "Yıldız / daire ası süsü — parametrik, AI yok.",
    },
}


def list_makers() -> list[dict[str, Any]]:
    return [dict(row) for row in MAKERS.values()]


def _f(value: Any, default: float) -> float:
    if value is None or value == "":
        return float(default)
    return float(value)


def _star_points(spikes: int, outer: float, inner: float) -> list[list[float]]:
    n = max(3, min(12, int(spikes)))
    pts: list[list[float]] = []
    for i in range(n * 2):
        ang = -math.pi / 2 + i * math.pi / n
        r = outer if i % 2 == 0 else inner
        pts.append([round(r * math.cos(ang), 3), round(r * math.sin(ang), 3)])
    return pts


def build_name_ornament(payload: dict[str, Any]) -> dict[str, Any]:
    """Hanging name plate: rounded-ish rect via panel + hang hole + engrave text."""
    text = str(payload.get("text") or payload.get("name") or payload.get("label") or "LaserMCP").strip()
    if not text:
        raise ValueError("isim süsü için yazı gerekli")
    if len(text) > 40:
        raise ValueError("yazı en fazla 40 karakter")
    thickness = _f(payload.get("thickness"), 3)
    width = _f(payload.get("width") or payload.get("w") or payload.get("x"), max(80.0, 12 * len(text)))
    height = _f(payload.get("height") or payload.get("h") or payload.get("y"), 40)
    font_h = _f(payload.get("font_mm") or payload.get("fontsize"), min(14.0, height * 0.45))
    hole_d = _f(payload.get("hang_hole_mm"), max(3.5, thickness + 0.5))
    width = max(40.0, min(300.0, width))
    height = max(28.0, min(120.0, height))

    panel = {
        "type": "panel",
        "label": "name-ornament",
        "role": "decorative_part",
        "w": width,
        "h": height,
        "edges": "eeee",
        "holes": [{"x": width / 2, "y": height - max(6.0, hole_d), "d": hole_d, "purpose": "hang"}],
        "markings": [
            {
                "kind": "text",
                "value": text,
                "x": width / 2,
                "y": height / 2,
                "height": font_h,
                "align": "center",
                "operation": "engrave",
            }
        ],
    }
    parameters = {
        "thickness": thickness,
        "project": f"name-ornament-{text[:24]}",
        "what_you_see": f"hanging name ornament '{text}'",
        "material": payload.get("material") or "poplar_3mm",
        "machine": payload.get("machine") or "payas_workshop",
        "holding_nicks": False,
        "surface_texts": [],
    }
    if payload.get("burn") not in (None, ""):
        parameters["burn"] = _f(payload.get("burn"), 0.15)
    return {
        "mode": "primitives",
        "primitives": [panel],
        "parameters": parameters,
        "summary": {
            "maker": "name_ornament",
            "text": text,
            "width_mm": width,
            "height_mm": height,
            "thickness_mm": thickness,
            "hang_hole_mm": hole_d,
            "ai": False,
        },
    }


def build_birdhouse(payload: dict[str, Any]) -> dict[str, Any]:
    """Boxes.py BirdHouse — parametric, no AI."""
    thickness = _f(payload.get("thickness"), 3)
    x = _f(payload.get("x") or payload.get("width"), 120)
    y = _f(payload.get("y") or payload.get("depth"), 100)
    h = _f(payload.get("h") or payload.get("height"), 100)
    overhang = _f(payload.get("roof_overhang"), 0.4)
    x = max(60.0, min(400.0, x))
    y = max(60.0, min(400.0, y))
    h = max(40.0, min(400.0, h))
    overhang = max(0.1, min(1.0, overhang))
    parameters = {
        "thickness": thickness,
        "x": x,
        "y": y,
        "h": h,
        "roof_overhang": overhang,
        "material": payload.get("material") or "poplar_3mm",
        "machine": payload.get("machine") or "payas_workshop",
        "project": "birdhouse",
    }
    if payload.get("burn") not in (None, ""):
        parameters["burn"] = _f(payload.get("burn"), 0.15)
    return {
        "mode": "generator",
        "generator": "BirdHouse",
        "parameters": parameters,
        "summary": {
            "maker": "birdhouse",
            "x_mm": x,
            "y_mm": y,
            "h_mm": h,
            "roof_overhang": overhang,
            "thickness_mm": thickness,
            "ai": False,
        },
    }


def build_christmas(payload: dict[str, Any]) -> dict[str, Any]:
    """Hanging Christmas ornament: star or disc + optional engrave + hang hole."""
    shape = str(payload.get("shape") or "star").lower()
    text = str(payload.get("text") or payload.get("name") or "").strip()
    if len(text) > 24:
        raise ValueError("christmas yazı en fazla 24 karakter")
    thickness = _f(payload.get("thickness"), 3)
    size = _f(payload.get("size") or payload.get("diameter") or payload.get("d"), 80)
    size = max(40.0, min(200.0, size))
    hole_d = _f(payload.get("hang_hole_mm"), max(3.5, thickness + 0.5))
    font_h = _f(payload.get("font_mm") or payload.get("fontsize"), min(10.0, size * 0.18))

    if shape in {"circle", "disc", "bauble", "disk"}:
        part: dict[str, Any] = {
            "type": "disc",
            "label": "xmas-bauble",
            "role": "decorative_part",
            "d": size,
            "hole": 0,
            "holes": [{"x": 0, "y": size / 2 - max(5.0, hole_d), "d": hole_d, "purpose": "hang"}],
        }
        # disc holes are relative to center origin in toolbox callback with origin (-d/2,-d/2)
        # Use contour-friendly approach: polygon circle approx + hole in panel space
        # Safer: use panel square with circular outer via contour
        r = size / 2
        n = 48
        pts = [
            [round(r * math.cos(2 * math.pi * i / n), 3), round(r * math.sin(2 * math.pi * i / n), 3)]
            for i in range(n)
        ]
        # shift to positive bbox
        minx = min(p[0] for p in pts)
        miny = min(p[1] for p in pts)
        shifted = [[p[0] - minx, p[1] - miny] for p in pts]
        w = max(p[0] for p in shifted)
        h = max(p[1] for p in shifted)
        part = {
            "type": "contour",
            "label": "xmas-bauble",
            "role": "decorative_part",
            "points": shifted,
            "holes": [{"x": w / 2, "y": h - max(5.0, hole_d), "d": hole_d, "purpose": "hang"}],
            "markings": [],
        }
        if text:
            part["markings"].append(
                {
                    "kind": "text",
                    "value": text,
                    "x": w / 2,
                    "y": h / 2,
                    "height": font_h,
                    "align": "center",
                    "operation": "engrave",
                }
            )
    else:
        outer = size / 2
        inner = outer * _f(payload.get("inner_ratio"), 0.42)
        spikes = int(payload.get("spikes") or 5)
        raw = _star_points(spikes, outer, inner)
        minx = min(p[0] for p in raw)
        miny = min(p[1] for p in raw)
        shifted = [[p[0] - minx, p[1] - miny] for p in raw]
        w = max(p[0] for p in shifted)
        h = max(p[1] for p in shifted)
        # hang hole near top tip
        top_y = max(p[1] for p in shifted)
        top_pts = [p for p in shifted if abs(p[1] - top_y) < 0.2]
        hx = sum(p[0] for p in top_pts) / len(top_pts) if top_pts else w / 2
        part = {
            "type": "contour",
            "label": "xmas-star",
            "role": "decorative_part",
            "points": shifted,
            "holes": [{"x": hx, "y": min(h - 2, top_y - max(3.0, hole_d * 0.6)), "d": hole_d, "purpose": "hang"}],
            "markings": [],
        }
        if text:
            part["markings"].append(
                {
                    "kind": "text",
                    "value": text,
                    "x": w / 2,
                    "y": h / 2,
                    "height": font_h,
                    "align": "center",
                    "operation": "engrave",
                }
            )

    parameters = {
        "thickness": thickness,
        "project": f"christmas-{shape}-{text[:16] or 'ornament'}",
        "what_you_see": f"christmas {shape} hanging ornament",
        "material": payload.get("material") or "poplar_3mm",
        "machine": payload.get("machine") or "payas_workshop",
        "holding_nicks": False,
    }
    if payload.get("burn") not in (None, ""):
        parameters["burn"] = _f(payload.get("burn"), 0.15)
    return {
        "mode": "primitives",
        "primitives": [part],
        "parameters": parameters,
        "summary": {
            "maker": "christmas",
            "shape": shape if shape in {"circle", "disc", "bauble", "disk"} else "star",
            "text": text or None,
            "size_mm": size,
            "thickness_mm": thickness,
            "ai": False,
        },
    }


def build_maker(kind: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    key = str(kind or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "isim": "name_ornament",
        "isim_susu": "name_ornament",
        "name": "name_ornament",
        "nameplate": "name_ornament",
        "ornament_name": "name_ornament",
        "kus_evi": "birdhouse",
        "bird_house": "birdhouse",
        "xmas": "christmas",
        "noel": "christmas",
        "yildiz": "christmas",
    }
    key = aliases.get(key, key)
    if key not in MAKERS:
        raise ValueError(f"unknown maker {kind!r}; use name_ornament|birdhouse|christmas")
    body = payload or {}
    if key == "name_ornament":
        return build_name_ornament(body)
    if key == "birdhouse":
        return build_birdhouse(body)
    return build_christmas(body)
