"""Python-level Boxes.py adapter. No shell, no arbitrary code execution."""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent


def _resolve_boxes_path() -> str:
    env = os.environ.get("BOXES_PATH", "").strip()
    if env and Path(env).is_dir():
        return env
    for candidate in (
        Path(r"C:\Project\boxes-master"),
        ROOT / "vendor" / "boxes-master",
        ROOT / "boxes-master",
    ):
        if (candidate / "boxes" / "__init__.py").is_file():
            return str(candidate)
    return env or str(ROOT / "vendor" / "boxes-master")


def _resolve_output_dir() -> Path:
    if os.environ.get("VERCEL"):
        path = Path(os.environ.get("TMPDIR") or "/tmp") / "laser-mcp-output"
    else:
        path = ROOT / "output"
    path.mkdir(parents=True, exist_ok=True)
    return path


BOXES_PATH = _resolve_boxes_path()

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
    "cut_color": "#FF0000",
    "etch_color": "#000000",
    "holding_nick_mm": 1.0,
}

GENERATOR_ALIASES = {
    "simplebox": "ABox",
}

OUTPUT_DIR = _resolve_output_dir()

MCP_NAME = "Laser mcp"
LATEST_SVG = "latest.svg"
LATEST_DXF = "latest.dxf"
_SAFE_NAME = re.compile(r"^[\w][\w .+-]*$", re.UNICODE)
_SKIP_ARGS = {"help", "output", "format"}
_LATEST_ALIASES = {
    "laser mcp",
    "laser mcp.svg",
    "laser_mcp.svg",
    "lasermcp.svg",
    "latest",
    "latest.svg",
}


def _file_url(public_base_url: str, file_id: str) -> str:
    return f"{public_base_url.rstrip('/')}/files/{quote(file_id)}"


def _slug(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", name or "svg").strip("-")
    return (slug[:40] or "svg")


def _new_file_id(generator: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    nonce = secrets.token_hex(4)
    return f"{_slug(generator)}-{stamp}-{nonce}.svg"


def _normalize_filename(file_id: str) -> str:
    name = unquote(file_id or "").replace("\\", "/").split("/")[-1].strip()
    if name.lower() in {"latest.dxf", "latest dxf"}:
        return LATEST_DXF
    if name.lower() in _LATEST_ALIASES:
        return LATEST_SVG
    return name


def _write_svg(svg_bytes: bytes, generator: str) -> tuple[str, bytes]:
    original = svg_bytes
    try:
        from text_path import prepare_lasercad_svg

        prepared = prepare_lasercad_svg(svg_bytes)
        if prepared:
            svg_bytes = prepared
    except Exception:
        svg_bytes = original
    try:
        from holding_nicks import NICK_MM, nick_cut_svg

        nicked = nick_cut_svg(svg_bytes, float(PAYAS_DEFAULTS.get("holding_nick_mm") or NICK_MM))
        if nicked:
            svg_bytes = nicked
    except Exception:
        pass
    file_id = _new_file_id(generator)
    path = OUTPUT_DIR / file_id
    path.write_bytes(svg_bytes)
    (OUTPUT_DIR / LATEST_SVG).write_bytes(svg_bytes)
    return file_id, svg_bytes


def _public_result(
    file_id: str,
    public_base_url: str,
    svg_bytes: bytes,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "success": True,
        "file_id": file_id,
        "svg_url": _file_url(public_base_url, file_id),
        "bytes": len(svg_bytes),
        "applied_defaults": {
            "material": PAYAS_DEFAULTS["material"],
            "thickness": PAYAS_DEFAULTS["thickness"],
            "burn": PAYAS_DEFAULTS["burn"],
            "holding_nick_mm": PAYAS_DEFAULTS.get("holding_nick_mm", 1.0),
            "output": "svg",
        },
    }
    if extra:
        for key, value in extra.items():
            if key in {"output_path", "path", "local_path"}:
                continue
            result[key] = value
    return result


def _generators_by_name() -> dict[str, type]:
    all_generators = boxes.generators.getAllBoxGenerators()
    by_name: dict[str, type] = {}
    for cls in all_generators.values():
        if not getattr(cls, "webinterface", True):
            continue
        by_name[cls.__name__] = cls
    from hayal_kumbaram import HayalKumbaram
    by_name["HayalKumbaram"] = HayalKumbaram
    from payas_robot import PayasRobot
    by_name["PayasRobot"] = PayasRobot
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
        if dest == "burn":
            item["default"] = PAYAS_DEFAULTS["burn"]
            item["locked"] = True
            item["help"] = "Payas kerf/burn is locked at 0.15 mm."
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
    merged["burn"] = PAYAS_DEFAULTS["burn"]
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
        "has_viewbox": bool(view_box),
    }


def _safe_output_file(file_id: str) -> Path:
    name = _normalize_filename(file_id)
    if not name or name in {".", ".."} or "\0" in name or not _SAFE_NAME.match(name):
        raise ValueError("invalid file_id")
    path = (OUTPUT_DIR / name).resolve()
    if path.parent != OUTPUT_DIR.resolve():
        raise ValueError("invalid file_id")
    if not path.is_file() and not name.lower().endswith((".svg", ".dxf")):
        path = (OUTPUT_DIR / f"{name}.svg").resolve()
        if path.parent != OUTPUT_DIR.resolve():
            raise ValueError("invalid file_id")
        name = path.name
    if not path.is_file():
        raise FileNotFoundError(f"file not found: {name}")
    return path


def payas_defaults() -> dict[str, Any]:
    defaults = dict(PAYAS_DEFAULTS)
    try:
        from text_path import font_info

        defaults["font"] = font_info()
    except Exception as exc:
        defaults["font"] = {"error": str(exc), "outlines_available": False}
    font = defaults["font"]
    if font.get("outlines_available"):
        defaults["font_note"] = (
            "Numbers and labels are outline paths (bundled Arimo / Arial-metric). No SVG <text>."
        )
    else:
        defaults["font_note"] = (
            "Outline font unavailable; kits still generate. Labels may remain as SVG <text>."
        )
    defaults["holding_nicks"] = (
        "Closed cuts and notches keep ~1 mm uncut nicks so pieces do not fall through the bed. "
        "Snap them out after cutting. Tiny bolt holes stay fully cut."
    )
    return defaults


def health_status() -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    generator_count = 0
    boxes_ok = False
    path_ok = Path(BOXES_PATH).is_dir()
    if not path_ok:
        errors.append("BOXES_PATH is not a directory")
    try:
        generator_count = len(_generators_by_name())
        boxes_ok = True
    except Exception as exc:
        errors.append(f"Boxes.py import/catalog failed: {exc}")
    ok = boxes_ok and path_ok
    font = None
    try:
        from text_path import font_info

        font = font_info()
        if not font.get("outlines_available"):
            warnings.append(
                "Outline font missing; kits still generate. Labels may remain as SVG <text>."
            )
    except Exception as exc:
        warnings.append(f"Outline font unavailable: {exc}")
        font = {"error": str(exc), "outlines_available": False}
    return {
        "status": "ok" if ok else "degraded",
        "boxes": boxes_ok,
        "boxes_path_configured": bool(BOXES_PATH),
        "generator_count": generator_count,
        "font": font,
        "defaults": dict(PAYAS_DEFAULTS),
        "errors": errors,
        "warnings": warnings,
    }


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


def list_generator_names(group: str | None = None) -> dict[str, Any]:
    data = list_generators(group)
    return {
        "count": data["count"],
        "groups": data["groups"],
        "aliases": data["aliases"],
        "names": [item["name"] for item in data["generators"]],
        "note": "Use get_generator_schema then generate_svg. Prefer create_* for Payas products.",
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
    file_id, svg_bytes = _write_svg(svg_bytes, name)
    dimensions = {
        key: merged[key]
        for key in ("x", "y", "h", "thickness", "burn")
        if key in merged
    }
    return _public_result(
        file_id,
        public_base_url,
        svg_bytes,
        extra={
            "generator": name,
            "dimensions": dimensions,
            "applied_defaults": {
                "material": PAYAS_DEFAULTS["material"],
                "thickness": merged["thickness"],
                "burn": merged["burn"],
                "holding_nick_mm": PAYAS_DEFAULTS.get("holding_nick_mm", 1.0),
                "output": "svg",
            },
        },
    )


def validate_svg(file_id: str) -> dict[str, Any]:
    path = _safe_output_file(file_id)
    raw = path.read_bytes()
    bed_w = PAYAS_DEFAULTS["bed_width"]
    bed_h = PAYAS_DEFAULTS["bed_height"]
    errors: list[str] = []
    metrics: dict[str, Any] = {
        "width_mm": None,
        "height_mm": None,
        "viewBox": None,
        "path_count": 0,
        "has_viewbox": False,
        "bytes": len(raw),
    }
    if not raw:
        errors.append("SVG file is empty")
        return {
            "success": False,
            "file_id": path.name,
            "well_formed": False,
            "fits_bed": False,
            "bed": {"width": bed_w, "height": bed_h},
            "metrics": metrics,
            "look_again": errors,
        }
    try:
        svg_text = raw.decode("utf-8")
    except UnicodeDecodeError:
        errors.append("SVG is not valid UTF-8")
        return {
            "success": False,
            "file_id": path.name,
            "well_formed": False,
            "fits_bed": False,
            "bed": {"width": bed_w, "height": bed_h},
            "metrics": metrics,
            "look_again": errors,
        }
    try:
        metrics.update(_svg_metrics(svg_text))
        metrics["bytes"] = len(raw)
        well_formed = True
    except ET.ParseError as exc:
        errors.append(f"XML parse error: {exc}")
        return {
            "success": False,
            "file_id": path.name,
            "well_formed": False,
            "fits_bed": False,
            "bed": {"width": bed_w, "height": bed_h},
            "metrics": metrics,
            "look_again": errors,
        }
    except ValueError as exc:
        errors.append(str(exc))
        well_formed = False

    width = metrics["width_mm"]
    height = metrics["height_mm"]
    fits_bed = True
    if width is None or height is None:
        errors.append("SVG has no numeric width/height or viewBox")
        fits_bed = False
    elif width <= 0 or height <= 0:
        errors.append(f"SVG dimensions must be positive, got {width}×{height} mm")
        fits_bed = False
    elif width > bed_w + 0.01 or height > bed_h + 0.01:
        rotated = width <= bed_h + 0.01 and height <= bed_w + 0.01
        if not rotated:
            errors.append(
                f"Drawing {width:.1f}×{height:.1f} mm does not fit "
                f"{bed_w}×{bed_h} mm bed"
            )
            fits_bed = False
    if metrics["path_count"] < 1:
        errors.append("SVG contains no drawable cut geometry")
    if re.search(r"<text[\s>]", svg_text, re.I):
        errors.append("SVG still contains <text>; laser CAD needs Arial outline paths")
        metrics["has_live_text"] = True
    else:
        metrics["has_live_text"] = False
    nesting_geom: dict[str, Any] | None = None
    try:
        from nesting import inspect_nesting

        nesting_geom = inspect_nesting(raw)
        if nesting_geom.get("errors"):
            errors.extend(str(e) for e in nesting_geom["errors"])
    except Exception:
        nesting_geom = None
    topology: dict[str, Any] | None = None
    try:
        from topology import inspect_topology

        topology = inspect_topology(raw)
    except Exception:
        topology = None
    sidecar = None
    side_path = path.with_suffix(".json")
    if side_path.is_file():
        try:
            sidecar = json.loads(side_path.read_text(encoding="utf-8"))
        except Exception:
            sidecar = None
    result = {
        "success": True,
        "file_id": path.name,
        "well_formed": well_formed,
        "fits_bed": fits_bed,
        "bed": {"width": bed_w, "height": bed_h},
        "metrics": metrics,
        "look_again": errors,
        "nesting": nesting_geom,
        "topology": topology,
    }
    if sidecar:
        if sidecar.get("assembly"):
            result["assembly"] = sidecar["assembly"]
        if sidecar.get("nesting") and not result.get("nesting"):
            result["nesting"] = sidecar["nesting"]
    return result


def render_preview(file_id: str, public_base_url: str = "http://127.0.0.1:8000") -> dict[str, Any]:
    path = _safe_output_file(file_id)
    metrics = _svg_metrics(path.read_text(encoding="utf-8"))
    return {
        "success": True,
        "file_id": path.name,
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
    generator: str = "cad",
    dxf_bytes: bytes | None = None,
) -> dict[str, Any]:
    name = (extra or {}).get("generator") or (extra or {}).get("product") or generator
    file_id, svg_bytes = _write_svg(svg_bytes, str(name))
    extra = dict(extra or {})
    try:
        from topology import inspect_topology

        extra["topology"] = inspect_topology(svg_bytes)
        if extra.get("ready_to_cut") and not extra["topology"].get("ok", True):
            extra["ready_to_cut"] = False
    except Exception:
        extra.setdefault("topology", extra.get("topology"))
    result = _public_result(file_id, public_base_url, svg_bytes, extra)
    if extra.get("assembly") is not None or extra.get("nesting") is not None or extra.get("topology") is not None:
        side = file_id[:-4] + ".json" if file_id.lower().endswith(".svg") else f"{file_id}.json"
        payload = {
            "file_id": file_id,
            "assembly": extra.get("assembly"),
            "nesting": extra.get("nesting"),
            "topology": extra.get("topology"),
            "product": extra.get("product"),
        }
        (OUTPUT_DIR / side).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        result["report_id"] = side
    if dxf_bytes:
        dxf_id = file_id[:-4] + ".dxf" if file_id.lower().endswith(".svg") else f"{file_id}.dxf"
        (OUTPUT_DIR / dxf_id).write_bytes(dxf_bytes)
        (OUTPUT_DIR / LATEST_DXF).write_bytes(dxf_bytes)
        result["dxf_id"] = dxf_id
        result["dxf_url"] = _file_url(public_base_url, dxf_id)
        defaults = dict(result.get("applied_defaults") or {})
        defaults["output"] = "svg+dxf"
        result["applied_defaults"] = defaults
    return result


def dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
