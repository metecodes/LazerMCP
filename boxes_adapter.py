"""Python-level Boxes.py adapter. No shell, no arbitrary code execution."""

from __future__ import annotations

import json
import os
import re
import secrets
import sys
import time
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
    env = (os.environ.get("MCP_OUTPUT_DIR") or os.environ.get("LASER_OUTPUT_DIR") or "").strip()
    if env:
        path = Path(env)
    elif os.environ.get("VERCEL"):
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

MCP_NAME = "LaserMCP"
LATEST_SVG = "latest.svg"
LATEST_DXF = "latest.dxf"
_SAFE_NAME = re.compile(r"^[\w][\w .+-]*$", re.UNICODE)
_SKIP_ARGS = {"help", "output", "format"}
_STUDIO_ARGS = {
    "material",
    "material_id",
    "machine",
    "machine_id",
    "project",
    "project_name",
    "project_id",
    "what_you_see",
    "measured_bar_mm",
    "physical_assembly",
    "movement_test",
}
_LATEST_ALIASES = {
    "laser mcp",
    "laser mcp.svg",
    "laser_mcp.svg",
    "lasermcp.svg",
    "latest",
    "latest.svg",
}


def _file_url(public_base_url: str, file_id: str) -> str:
    name = quote(file_id)
    if str(file_id).lower().endswith(".svg"):
        return f"{public_base_url.rstrip('/')}/out/{name}"
    return f"{public_base_url.rstrip('/')}/files/{name}"


def _blob_url(file_id: str, data: bytes, content_type: str = "image/svg+xml") -> str | None:
    # Generated files use one managed backend so copies cannot outlive the TTL.
    from persist.env import uses_supabase_app_db
    if uses_supabase_app_db():
        return None
    token = (
        os.environ.get("BLOB_READ_WRITE_TOKEN")
        or os.environ.get("VERCEL_BLOB_READ_WRITE_TOKEN")
        or ""
    ).strip()
    if not token:
        return None
    try:
        import urllib.request

        req = urllib.request.Request(
            f"https://blob.vercel-storage.com/{quote(file_id)}",
            data=data,
            method="PUT",
            headers={
                "Authorization": f"Bearer {token}",
                "x-api-version": "7",
                "x-content-type": content_type,
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("url") or payload.get("downloadUrl")
    except Exception:
        return None


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


def _write_svg(
    svg_bytes: bytes,
    generator: str,
    primitives: list[Any] | None = None,
    preserve_source_geometry: bool = False,
    operation_settings: dict[str, Any] | None = None,
    project_parameters: dict[str, Any] | None = None,
) -> tuple[str, bytes, dict[str, Any] | None]:
    from project_options import apply_holding_nicks
    if (project_parameters or {}).get('holding_nicks') is False:
        svg_bytes=apply_holding_nicks(svg_bytes,project_parameters,preserve_source_geometry)
    original = svg_bytes
    manufacturing = None
    try:
        from text_path import prepare_lasercad_svg

        prepared = prepare_lasercad_svg(svg_bytes)
        if prepared:
            svg_bytes = prepared
    except Exception:
        svg_bytes = original
    try:
        from manufacturing import finish_manufacturing_svg

        stamped, manufacturing = finish_manufacturing_svg(svg_bytes, primitives)
        if stamped:
            svg_bytes = stamped
    except Exception:
        manufacturing = None
    if operation_settings:
        from laser_settings import stamp_operation_settings
        svg_bytes=stamp_operation_settings(svg_bytes,operation_settings)
    from project_options import apply_holding_nicks
    svg_bytes = apply_holding_nicks(svg_bytes, project_parameters, preserve_source_geometry)
    file_id = _new_file_id(generator)
    path = OUTPUT_DIR / file_id
    path.write_bytes(svg_bytes)
    (OUTPUT_DIR / LATEST_SVG).write_bytes(svg_bytes)
    return file_id, svg_bytes, manufacturing


def attach_elapsed(result: dict[str, Any], started_at: float | None) -> dict[str, Any]:
    """MCP speed note. Color/geometry unchanged."""
    if started_at is None:
        return result
    sec = max(0.0, time.perf_counter() - float(started_at))
    minutes = sec / 60.0
    result["elapsed_s"] = round(sec, 3)
    result["elapsed_min"] = round(minutes, 3)
    if sec < 60:
        result["speed_note"] = f"{sec:.1f} saniyede çıkarılmıştır ({minutes:.2f} dk)"
    else:
        result["speed_note"] = f"{minutes:.1f} dk'da çıkarılmıştır ({sec:.0f} s)"
    return result


def _public_result(
    file_id: str,
    public_base_url: str,
    svg_bytes: bytes,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    blob = _blob_url(file_id, svg_bytes)
    result: dict[str, Any] = {
        "success": True,
        "file_id": file_id,
        "svg_url": blob or _file_url(public_base_url, file_id),
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
            if key in {"output_path", "path", "local_path", "svg_bytes"}:
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
            item["help"] = "Kerf from material profile or coupon. Do not invent."
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
    if user_params is not None and not isinstance(user_params, dict):
        raise ValueError("parameters must be an object")
    incoming = dict(user_params or {})
    try:
        from studio import prepare_parameters

        prepared = prepare_parameters(incoming)
    except Exception:
        prepared = {
            "thickness": PAYAS_DEFAULTS["thickness"],
            "burn": PAYAS_DEFAULTS["burn"],
            **incoming,
        }
    merged = {key: value for key, value in prepared.items() if not str(key).startswith("_")}
    merged.setdefault("thickness", PAYAS_DEFAULTS["thickness"])
    merged.setdefault("burn", PAYAS_DEFAULTS["burn"])
    merged["format"] = "svg"
    return merged


def _to_cli_args(params: dict[str, Any]) -> list[str]:
    args: list[str] = []
    for key, value in params.items():
        if key in ("format", "output") or key in _STUDIO_ARGS or str(key).startswith("_"):
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
    try:
        from profiles import list_profiles

        defaults["profiles"] = list_profiles()
    except Exception:
        pass
    defaults["studio"] = (
        "Pass parameters.material and parameters.machine. "
        "MCP writes the material list (bom / MATERIALS (MCP)). "
        "Do not invent kerf or hardware. After a coupon, pass measured_bar_mm."
    )
    try:
        from plans import public_plans

        defaults["plans"] = public_plans()
    except Exception:
        pass
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
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    name, cls = _resolve_generator(generator)
    merged = _merge_parameters(parameters)
    box = cls()
    known = _known_dests(box)
    unknown = [key for key in merged if key not in known and key not in _SKIP_ARGS and key not in _STUDIO_ARGS and not str(key).startswith("_")]
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
    dimensions = {
        key: merged[key]
        for key in ("x", "y", "h", "thickness", "burn")
        if key in merged
    }
    payload = {
        "_started_at": started_at,
        "generator": name,
        "product": (extra or {}).get("product") or name,
        "title": (extra or {}).get("title"),
        "parameters": parameters,
        "dimensions": dimensions,
        "applied_defaults": {
            "material": merged.get("material") or PAYAS_DEFAULTS["material"],
            "thickness": merged["thickness"],
            "burn": merged["burn"],
            "holding_nick_mm": PAYAS_DEFAULTS.get("holding_nick_mm", 1.0),
            "output": "svg+dxf",
        },
    }
    if extra:
        payload.update(extra)
        payload.setdefault("generator", name)
    return save_generated_svg(svg_bytes, public_base_url=public_base_url, extra=payload, generator=name)


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
        if sidecar.get("topology") and not result.get("topology"):
            result["topology"] = sidecar["topology"]
        for key in (
            "review",
            "pipeline",
            "design_map",
            "connections",
            "final_status",
            "speak",
            "scorecard",
            "authorized_output",
            "production_export",
            "production_summary",
        ):
            if sidecar.get(key) is not None:
                result[key] = sidecar[key]
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
        "note": "Preview is the generated SVG. A nest PNG is attached when available.",
    }


def save_generated_svg(
    svg_bytes: bytes,
    public_base_url: str = "http://127.0.0.1:8000",
    extra: dict[str, Any] | None = None,
    generator: str = "cad",
    dxf_bytes: bytes | None = None,
) -> dict[str, Any]:
    try:
        from persist.cleanup import cleanup_expired
        from persist.env import uses_supabase_app_db
        # Hosted storage is cleaned by the scheduled database job, never by CAD requests.
        if not uses_supabase_app_db():
            cleanup_expired()
    except Exception:
        pass
        
    name = (extra or {}).get("generator") or (extra or {}).get("product") or generator
    extra = dict(extra or {})
    started_at = extra.pop("_started_at", None)
    from laser_settings import resolve_operation_settings
    laser_profile=resolve_operation_settings(extra.get('parameters') or {})
    extra['operation_settings']=laser_profile
    file_id, svg_bytes, manufacturing = _write_svg(
        svg_bytes,
        str(name),
        extra.get("primitives") if isinstance(extra.get("primitives"), list) else None,
        preserve_source_geometry=bool(extra.get("preserve_source_geometry")),
        operation_settings=laser_profile,
        project_parameters=extra.get('parameters') or {},
    )
    # Rebuild every requested DXF from the finalized SVG. Manufacturing normalization,
    # holding nicks and operation repair happen in _write_svg and must not leave the
    # companion DXF describing an older geometry revision.
    if dxf_bytes is not None:
        from dxf_export import svg_bytes_to_dxf
        dxf_bytes = svg_bytes_to_dxf(svg_bytes)
    if manufacturing:
        extra["manufacturing"] = manufacturing
    elif extra.get("manufacturing") is None:
        try:
            from manufacturing import validate_svg_operations

            extra["manufacturing"] = validate_svg_operations(svg_bytes, extra.get("primitives"))
        except Exception:
            pass
    try:
        from topology import inspect_topology

        extra["topology"] = inspect_topology(svg_bytes)
    except Exception:
        extra.setdefault("topology", extra.get("topology"))
    if extra.get("nesting") is None:
        try:
            from nesting import inspect_nesting

            extra["nesting"] = inspect_nesting(svg_bytes)
        except Exception:
            extra["nesting"] = extra.get("nesting")
    try:
        from pipeline import review_only

        gated = review_only({**extra, "svg_bytes": svg_bytes})
        extra["review"] = gated.get("review")
        extra["pipeline"] = extra.get("pipeline") or gated.get("pipeline")
        extra["design_map"] = gated.get("design_map")
        extra["connections"] = gated.get("connections")
        extra["final_status"] = gated.get("final_status")
        extra["speak"] = gated.get("speak")
        extra["scorecard"] = gated.get("scorecard")
        extra["gate_levels"] = gated.get("gate_levels")
        extra["reference_comparison"] = gated.get("reference_comparison")
        extra["authorized_output"] = gated.get("authorized_output")
        extra["production_export"] = gated.get("production_export") or "BLOCKED"
        extra["production_summary"] = gated.get("production_summary")
        extra["physical"] = gated.get("physical")
        extra["assembly_sheet"] = gated.get("assembly_sheet")
        extra["ready_to_cut"] = gated.get("final_status") == "PRODUCTION READY"
        if gated.get("look_again"):
            extra["look_again"] = gated["look_again"]
    except Exception:
        extra["final_status"] = "BLOCKED"
        extra["production_export"] = "BLOCKED"
        extra["validation_error"] = "POST_SAVE_REVIEW_FAILED"
        extra["authorized_output"] = "None"
        extra["look_again"] = ["POST_SAVE_REVIEW_FAILED: finalized SVG could not be verified"]
    extra["ready_to_cut"] = extra.get("final_status") == "PRODUCTION READY"
    extra["production_export"] = extra.get("production_export") or "BLOCKED"
    extra.setdefault(
        "authorized_output",
        "Production SVG"
        if extra.get("final_status") == "PRODUCTION READY"
        else ("Prototype SVG" if extra.get("final_status") == "PROTOTYPE READY" else "None"),
    )
    nest = extra.get("nesting") if isinstance(extra.get("nesting"), dict) else {}
    extra_sheets = list(nest.pop("_sheet_svgs", None) or [])
    try:
        from studio import attach

        extra = attach(extra, svg_bytes, extra.get("primitives"))
    except Exception:
        pass
    from plans import entitled

    if not dxf_bytes and entitled("dxf"):
        try:
            from dxf_export import svg_bytes_to_dxf

            dxf_bytes = svg_bytes_to_dxf(svg_bytes)
        except Exception:
            dxf_bytes = None
    if not entitled("dxf"):
        dxf_bytes = None
    if extra_sheets and not entitled("advanced_nesting"):
        extra_sheets = extra_sheets[:1]
    preview_id = None
    preview_bytes = None
    try:
        from preview_sheet import nest_preview_png

        preview_bytes = nest_preview_png(extra.get("nesting"))
    except Exception:
        preview_bytes = None
    stem = file_id[:-4] if file_id.lower().endswith(".svg") else file_id
    result = _public_result(file_id, public_base_url, svg_bytes, extra)
    result["preview_url"] = result.get("svg_url")
    if preview_bytes:
        preview_id = f"{stem}-preview.png"
        (OUTPUT_DIR / preview_id).write_bytes(preview_bytes)
        preview_blob = _blob_url(preview_id, preview_bytes, "image/png")
        result["preview_url"] = preview_blob or _file_url(public_base_url, preview_id)
        result["preview_id"] = preview_id
        extra["preview_url"] = result["preview_url"]
    if extra_sheets:
        sheet_ids = [file_id]
        for i, raw in enumerate(extra_sheets[1:], start=2):
            sid = f"{stem}-sheet{i}.svg"
            (OUTPUT_DIR / sid).write_bytes(raw)
            sheet_ids.append(sid)
        result["sheet_ids"] = sheet_ids
        result["sheets"] = len(extra_sheets)
    try:
        from assembly_steps import build_assembly_steps
        assembly_plan=build_assembly_steps(extra.get("primitives"),extra.get("assembly"),extra.get("parameters"))
    except Exception as exc:
        assembly_plan={"status":"BLOCKED","reason":str(exc),"steps":[]}
    step_rows=[]
    for row in assembly_plan.pop("steps",[]):
        step_id=f"{stem}-assembly-step-{int(row['step']):02d}.svg"
        raw=row.pop("svg_bytes")
        (OUTPUT_DIR / step_id).write_bytes(raw)
        step_rows.append({**row,"file_id":step_id,"url":_blob_url(step_id,raw,"image/svg+xml") or _file_url(public_base_url,step_id)})
    assembly_plan["steps"]=step_rows
    extra["assembly_steps"]=assembly_plan
    result["assembly_steps"]=assembly_plan
    result["assembly_step_ids"]=[row["file_id"] for row in step_rows]
    try:
        from assembly_result import build as build_assembly_result
        assembly_result = build_assembly_result(extra.get("assembly"), file_id=file_id)
    except Exception:
        assembly_result = None
    if assembly_result:
        extra["assembly_result"] = assembly_result
        result["assembly_result"] = assembly_result
    side = f"{stem}.json"
    payload = {
        "file_id": file_id,
        "product": extra.get("product"),
        "final_status": extra.get("final_status"),
        "ready_to_cut": extra.get("ready_to_cut"),
        "physical": extra.get("physical"),
        "assembly_sheet": extra.get("assembly_sheet"),
        "assembly_steps": extra.get("assembly_steps"),
        "speak": extra.get("speak"),
        "scorecard": extra.get("scorecard"),
        "gate_levels": extra.get("gate_levels"),
        "reference_comparison": extra.get("reference_comparison"),
        "authorized_output": extra.get("authorized_output"),
        "production_export": extra.get("production_export") or "BLOCKED",
        "assembly": extra.get("assembly"),
        "assembly_result": extra.get("assembly_result"),
        "nesting": extra.get("nesting"),
        "topology": extra.get("topology"),
        "review": extra.get("review"),
        "pipeline": extra.get("pipeline"),
        "design_map": extra.get("design_map"),
        "connections": extra.get("connections"),
        "production_summary": extra.get("production_summary"),
        "primitives": extra.get("primitives"),
        "bom": extra.get("bom"),
        "project": extra.get("project"),
        "profiles": extra.get("profiles"),
        "preview_url": result.get("preview_url"),
        "calibration": extra.get("calibration"),
        "operation_settings": extra.get("operation_settings"),
    }
    (OUTPUT_DIR / side).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result["report_id"] = side
    summary = extra.get("production_summary")
    if summary:
        md_id = f"{stem}-production.md"
        (OUTPUT_DIR / md_id).write_text(str(summary), encoding="utf-8")
        result["production_report_id"] = md_id
    sheet = extra.get("assembly_sheet")
    if sheet:
        sheet_id = f"{stem}-assembly.txt"
        (OUTPUT_DIR / sheet_id).write_text(str(sheet), encoding="utf-8")
        result["assembly_sheet_id"] = sheet_id
    bom_speak = extra.get("materials_speak") or (extra.get("bom") or {}).get("speak")
    if bom_speak:
        bom_id = f"{stem}-bom.txt"
        (OUTPUT_DIR / bom_id).write_text(str(bom_speak), encoding="utf-8")
        result["bom_id"] = bom_id
    if dxf_bytes:
        dxf_id = f"{stem}.dxf"
        (OUTPUT_DIR / dxf_id).write_bytes(dxf_bytes)
        (OUTPUT_DIR / LATEST_DXF).write_bytes(dxf_bytes)
        result["dxf_id"] = dxf_id
        result["dxf_url"] = _blob_url(dxf_id, dxf_bytes, "image/vnd.dxf") or _file_url(public_base_url, dxf_id)
        defaults = dict(result.get("applied_defaults") or {})
        defaults["output"] = "svg+dxf"
        result["applied_defaults"] = defaults
    try:
        from studio import finish_result

        result = finish_result(result, extra)
        if extra.get("project"):
            payload["project"] = extra.get("project")
            (OUTPUT_DIR / side).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        result["project_persistence"] = "PROJECT_PERSISTENCE_FAILED"
        looks = result.get("look_again")
        if not isinstance(looks, list):
            looks = [str(looks)] if looks else []
        result["look_again"] = looks + ["Project history could not be saved. Do not treat this as a stored project."]
    try:
        from persist.job import attach_durable_artifacts

        result = attach_durable_artifacts(result, extra)
    except Exception:
        result["durable_persistence"] = False
        result["artifact_persistence"] = "ARTIFACT_PERSISTENCE_FAILED"
        result["artifact_persistence"] = "ARTIFACT_PERSISTENCE_FAILED"
    return attach_elapsed(result, started_at)


def dump_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
