"""Scale a toolbox recipe so one photo length becomes real millimetres."""

from __future__ import annotations

from typing import Any

_SKIP_KEYS = {
    "type",
    "kind",
    "label",
    "edges",
    "edge",
    "top",
    "bottom",
    "lid",
    "format",
    "preset",
    "count",
    "n",
    "blades",
    "n_blades",
    "rows",
    "cols",
    "seed",
    "columns",
    "operation",
    "align",
    "target_part",
    "target",
    "icon",
    "name",
    "value",
    "content",
    "d",
    "closed",
    "rotation",
    "angle",
    "what_you_see",
    "measured_bar_mm",
    "measured_100mm",
    "physical_assembly",
    "movement_test",
    "nominal_bar_mm",
}

_SKIP_SCALE = {"count", "n", "blades", "n_blades", "rows", "cols", "seed", "columns"}

MEASURE = {
    "plywood_thickness_mm": 3.0,
    "kerf_mm": 0.15,
    "steps": [
        "If the user stated a size (cm/mm), that is the footprint. Do not invent a different one.",
        "Otherwise pick ONE clear length in the photo (base width, overall height, or door).",
        "If the 3 mm plywood edge is visible, count how many thicknesses fit in that ONE length. Do not invent a second size.",
        "Set parameters.reference = {feature, mm, drawn_mm}. drawn_mm is the current recipe value for that feature. create_design scales the whole recipe.",
        "Pass parameters.what_you_see so the reviewer can check rotor/door/lettering against the recipe.",
        "First uncalibrated laser: {type:coupon}. After cutting, pass measured_bar_mm (the 100 mm bar as measured). Do not invent that number.",
        "physical_assembly=verified and movement_test=verified only after a human dry-fit / spin. Never invent those flags.",
    ],
}


def scale_factor(parameters: dict[str, Any] | None) -> float:
    params = parameters or {}
    if params.get("scale") not in (None, ""):
        factor = float(params["scale"])
        if 0.05 <= factor <= 20:
            return factor
    ref = params.get("reference")
    if isinstance(ref, dict):
        mm = ref.get("mm") or ref.get("real_mm") or ref.get("target_mm")
        drawn = ref.get("drawn_mm") or ref.get("recipe_mm") or ref.get("current_mm")
        if mm and drawn and float(drawn) > 0.2:
            factor = float(mm) / float(drawn)
            if 0.05 <= factor <= 20:
                return factor
    return 1.0


def _scale_num(key: str, value: Any, factor: float) -> Any:
    if key in _SKIP_SCALE or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value) * factor, 3)
    return value


def scale_obj(value: Any, factor: float, key: str = "") -> Any:
    if abs(factor - 1.0) < 1e-9:
        return value
    if isinstance(value, list):
        if value and all(isinstance(x, (int, float)) for x in value):
            if key in {"borders", "sides"}:
                return [
                    round(float(x) * factor, 3) if i % 2 == 0 else x
                    for i, x in enumerate(value)
                ]
            if key in {"points", "vertices", "coords"}:
                return [round(float(x) * factor, 3) for x in value]
        return [scale_obj(item, factor, key) for item in value]
    if isinstance(value, tuple):
        return tuple(scale_obj(item, factor, key) for item in value)
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            if k in _SKIP_KEYS:
                out[k] = v
            else:
                out[k] = scale_obj(v, factor, k)
        return out
    return _scale_num(key, value, factor)


_COUPON = {"coupon", "kerf_test", "burn_test", "kerf"}


def scale_primitives(primitives: list[Any] | None, parameters: dict[str, Any] | None) -> tuple[list[Any], dict[str, Any]]:
    factor = scale_factor(parameters)
    parts = list(primitives or [])
    info: dict[str, Any] = {
        "scale": round(factor, 5),
        "applied": abs(factor - 1.0) >= 1e-9,
        "reference": (parameters or {}).get("reference"),
    }
    if not info["applied"]:
        return parts, info
    out: list[Any] = []
    for part in parts:
        if isinstance(part, dict):
            kind = str(part.get("type") or part.get("kind") or "").strip().lower()
            if kind in _COUPON:
                out.append(part)
            else:
                out.append(scale_obj(part, factor))
        else:
            out.append(part)
    return out, info
