"""Python-level Boxes.py adapter. No shell, no arbitrary code execution."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote
from xml.etree import ElementTree as ET

BOXES_PATH = os.environ.get("BOXES_PATH", r"C:\Project\boxes-master")

if BOXES_PATH not in sys.path:
    sys.path.insert(0, BOXES_PATH)

import boxes  # noqa: E402
import boxes.generators  # noqa: E402

PAYAS_DEFAULTS = {
    "material": "poplar_plywood",
    "thickness": 3.0,
    "burn": 0.15,
    "bed_width": 1500,
    "bed_height": 3000,
    "output": "svg",
}

GENERATOR_ALIASES = {
    "simplebox": "ABox",
}

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

MCP_NAME = "Laser mcp"
OUTPUT_BASENAME = "Laser mcp"
_SAFE_NAME = re.compile(r"^[\w][\w .+-]*$", re.UNICODE)
_SKIP_ARGS = {"help", "output", "format"}


def _file_url(public_base_url: str, file_id: str) -> str:
    return f"{public_base_url.rstrip('/')}/files/{quote(file_id)}"


def _normalize_filename(file_id: str) -> str:
    name = unquote(file_id or "").replace("\\", "/").split("/")[-1].strip()
    if name.lower() in {"laser mcp", "laser_mcp", "lasermcp"}:
        name = f"{OUTPUT_BASENAME}.svg"
    return name


def _generators_by_name() -> dict[str, type]:
    all_generators = boxes.generators.getAllBoxGenerators()
    by_name: dict[str, type] = {}
    for cls in all_generators.values():
        if not getattr(cls, "webinterface", True):
            continue
        by_name[cls.__name__] = cls
    from hayal_kumbaram import HayalKumbaram
    by_name['HayalKumbaram'] = HayalKumbaram
    from payas_robot import PayasRobot
    by_name['PayasRobot'] = PayasRobot
    return by_name


def _resolve_generator(name: str) -> tuple[str, type]:
    if not name or not isinstance(name, str):
        raise ValueError("generator name is required")
    requested = name.strip()
    aliases = GENERATOR_ALIASES
    canonical = aliases.get(requested.lower(), requested)
    catalog = _generators_by_name()
    exact = catalog.get(canonical)
    if exact:
        return canonical, exact
    lowered = {key.lower(): key for key in catalog}
    hit = lowered.get(canonical.lower())
    if hit:
        return hit, catalog[hit]
    available = ", ".join(sorted(catalog))
    raise ValueError(f"Unknown generator '{name}'. Available: {available}")


def _jsonable(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return str(value)


def _arg_type_name(action) -> str:
    arg_type = action.type
    if arg_type is None:
        if action.choices:
            return "string"
        return "string"
    if arg_type is bool or type(arg_type).__name__ == "BoolArg":
        return "boolean"
    if arg_type is int:
        return "integer"
    if arg_type is float:
        return "number"
    return "string"


def _schema_for_class(cls: type) -> dict[str, Any]:
    box = cls()
    parameters: list[dict[str, Any]] = []
    for action in box.argparser._actions:
        dest = getattr(action, "dest", None)
        if not dest or dest in _SKIP_ARGS:
            continue
        if not getattr(action, "option_strings", None):
            continue
        item = {
            "name": dest,
            "type": _arg_type_name(action),
            "default": _jsonable(action.default),
            "help": (action.help or "").split("[\U0001F6C8]")[0].strip(),
        }
        if action.choices:
            item["choices"] = [_jsonable(c) for c in action.choices]
        parameters.append(item)
    return {
        "name": cls.__name__,
        "description": (cls.__doc__ or "").strip(),
        "group": getattr(cls, "ui_group", "Misc"),
        "parameters": parameters,
    }


def _merge_parameters(user_params: dict[str, Any] | None) -> dict[str, Any]:
    merged = {
        "thickness": PAYAS_DEFAULTS["thickness"],
        "burn": PAYAS_DEFAULTS["burn"],
    }
    if user_params:
        if not isinstance(user_params, dict):
            raise ValueError("parameters must be an object")
        merged.update(user_params)
    merged["format"] = "svg"
    return merged


def _to_cli_args(params: dict[str, Any]) -> list[str]:
    args: list[str] = []
    for key, value in params.items():
        if key in ("format", "output"):
            continue
        if isinstance(value, bool):
            args.append(f"--{key}={'1' if value else '0'}")
        elif isinstance(value, (list, tuple)):
            args.append(f"--{key}={':'.join(str(v) for v in value)}")
        else:
            args.append(f"--{key}={value}")
    args.append("--format=svg")
    return args


def _known_dests(box) -> set[str]:
    return {
        action.dest
        for action in box.argparser._actions
        if getattr(action, "dest", None) and action.dest != "help"
    }


def _parse_length_mm(raw: str | None) -> float | None:
    if not raw:
        return None
    text = raw.strip().lower().replace("mm", "").replace("px", "")
    try:
        return float(text)
    except ValueError:
        return None


def _svg_metrics(svg_text: str) -> dict[str, Any]:
    root = ET.fromstring(svg_text)
    tag = root.tag.split("}")[-1].lower()
    if tag != "svg":
        raise ValueError(f"Root element is <{tag}>, not <svg>")
    width = _parse_length_mm(root.attrib.get("width"))
    height = _parse_length_mm(root.attrib.get("height"))
    view_box = root.attrib.get("viewBox")
    if (width is None or height is None) and view_box:
        parts = view_box.replace(",", " ").split()
        if len(parts) == 4:
            width = width if width is not None else float(parts[2])
            height = height if height is not None else float(parts[3])
    path_count = 0
    for node in root.iter():
        if node.tag.split("}")[-1].lower() in {"path", "line", "polyline", "polygon", "rect", "circle"}:
            path_count += 1
    return {
        "width_mm": width,
        "height_mm": height,
        "viewBox": view_box,
        "path_count": path_count,
    }


def _safe_output_file(file_id: str) -> Path:
    name = _normalize_filename(file_id)
    if not name or name in {".", ".."} or "\0" in name or not _SAFE_NAME.match(name):
        raise ValueError("invalid file_id")
    path = (OUTPUT_DIR / name).resolve()
    if path.parent != OUTPUT_DIR.resolve():
        raise ValueError("invalid file_id")
    if not path.is_file() and not name.lower().endswith(".svg"):
        path = (OUTPUT_DIR / f"{name}.svg").resolve()
        if path.parent != OUTPUT_DIR.resolve():
            raise ValueError("invalid file_id")
        name = path.name
    if not path.is_file():
        raise FileNotFoundError(f"file not found: {name}")
    return path


def payas_defaults() -> dict[str, Any]:
    return dict(PAYAS_DEFAULTS)


def list_generators(group: str | None = None) -> dict[str, Any]:
    catalog = _generators_by_name()
    items = []
    for name, cls in sorted(catalog.items(), key=lambda kv: kv[0].lower()):
        ui_group = getattr(cls, "ui_group", "Misc")
        if group and ui_group.lower() != group.lower():
            continue
        doc = (cls.__doc__ or "").strip().splitlines()
        items.append(
            {
                "name": name,
                "group": ui_group,
                "description": doc[0] if doc else "",
            }
        )
    aliases = {alias: target for alias, target in GENERATOR_ALIASES.items()}
    groups = sorted({item["group"] for item in items})
    return {
        "defaults": dict(PAYAS_DEFAULTS),
        "count": len(items),
        "aliases": aliases,
        "groups": groups,
        "generators": items,
    }


def get_generator_schema(generator: str) -> dict[str, Any]:
    name, cls = _resolve_generator(generator)
    schema = _schema_for_class(cls)
    schema["resolved_name"] = name
    schema["defaults"] = dict(PAYAS_DEFAULTS)
    return schema


def generate_svg(
    generator: str,
    parameters: dict[str, Any] | None = None,
    public_base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    name, cls = _resolve_generator(generator)
    merged = _merge_parameters(parameters)
    box = cls()
    known = _known_dests(box)
    unknown = [key for key in merged if key not in known]
    if unknown:
        raise ValueError(
            f"Unknown parameters for {name}: {unknown}. "
            f"Valid: {sorted(k for k in known if k not in _SKIP_ARGS)}"
        )
    box.parseArgs(_to_cli_args(merged))
    box.open()
    box.render()
    data = box.close()
    svg_bytes = data.getvalue() if hasattr(data, "getvalue") else data.read()
    file_id = f"{OUTPUT_BASENAME}.svg"
    path = OUTPUT_DIR / file_id
    path.write_bytes(svg_bytes)
    dimensions = {
        key: merged[key]
        for key in ("x", "y", "h", "thickness", "burn")
        if key in merged
    }
    return {
        "success": True,
        "generator": name,
        "dimensions": dimensions,
        "applied_defaults": {
            "material": PAYAS_DEFAULTS["material"],
            "thickness": merged["thickness"],
            "burn": merged["burn"],
            "output": "svg",
        },
        "file_id": file_id,
        "output_path": str(path),
        "svg_url": _file_url(public_base_url, file_id),
        "bytes": len(svg_bytes),
    }


def validate_svg(file_id: str) -> dict[str, Any]:
    path = _safe_output_file(file_id)
    svg_text = path.read_text(encoding="utf-8")
    metrics = _svg_metrics(svg_text)
    width = metrics["width_mm"]
    height = metrics["height_mm"]
    bed_w = PAYAS_DEFAULTS["bed_width"]
    bed_h = PAYAS_DEFAULTS["bed_height"]
    fits_bed = True
    errors: list[str] = []
    if width is None or height is None:
        errors.append("SVG has no numeric width/height or viewBox")
        fits_bed = False
    elif width > bed_w + 0.01 or height > bed_h + 0.01:
        # Allow 90° rotation on the 1500×3000 bed.
        rotated = width <= bed_h + 0.01 and height <= bed_w + 0.01
        if not rotated:
            errors.append(
                f"Drawing {width:.1f}×{height:.1f} mm does not fit "
                f"{bed_w}×{bed_h} mm bed"
            )
            fits_bed = False
    if metrics["path_count"] < 1:
        errors.append("SVG contains no drawable cut geometry")
    return {
        "success": not errors,
        "file_id": file_id,
        "well_formed": True,
        "fits_bed": fits_bed,
        "bed": {"width": bed_w, "height": bed_h},
        "metrics": metrics,
        "errors": errors,
    }


def render_preview(file_id: str, public_base_url: str = "http://127.0.0.1:8000") -> dict[str, Any]:
    path = _safe_output_file(file_id)
    metrics = _svg_metrics(path.read_text(encoding="utf-8"))
    return {
        "success": True,
        "file_id": file_id,
        "format": "svg",
        "preview_url": _file_url(public_base_url, path.name),
        "width_mm": metrics["width_mm"],
        "height_mm": metrics["height_mm"],
        "path_count": metrics["path_count"],
        "note": "Stage 1 preview is the generated SVG. PNG raster comes later.",
    }


def save_generated_svg(
    svg_bytes: bytes,
    public_base_url: str = "http://127.0.0.1:8000",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    file_id = f"{OUTPUT_BASENAME}.svg"
    path = OUTPUT_DIR / file_id
    path.write_bytes(svg_bytes)
    result = {
        "success": True,
        "file_id": file_id,
        "output_path": str(path),
        "svg_url": _file_url(public_base_url, file_id),
        "bytes": len(svg_bytes),
        "applied_defaults": {
            "material": PAYAS_DEFAULTS["material"],
            "thickness": PAYAS_DEFAULTS["thickness"],
            "burn": PAYAS_DEFAULTS["burn"],
            "output": "svg",
        },
    }
    if extra:
        result.update(extra)
    return result


def dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
