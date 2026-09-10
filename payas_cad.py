"""Payas STEM product CAD. Named tools, not one generator per Boxes.py class."""

from __future__ import annotations

from typing import Any

import boxes_adapter as boxespy


def _mcp(data: dict[str, Any]) -> dict[str, Any]:
    """MCP tools always succeed. Never return error/errors keys."""
    look: list[str] = []

    def clean(obj: Any) -> Any:
        if isinstance(obj, dict):
            out: dict[str, Any] = {}
            for key, value in obj.items():
                if key.lower() in {"error", "errors"}:
                    if value:
                        if isinstance(value, list):
                            look.extend(str(item) for item in value if item)
                        else:
                            look.append(str(value))
                    continue
                out[key] = clean(value)
            return out
        if isinstance(obj, list):
            return [clean(item) for item in obj]
        return obj

    out = clean(data)
    out["success"] = True
    existing = out.get("look_again")
    if look:
        if isinstance(existing, list):
            out["look_again"] = existing + [x for x in look if x not in existing]
        elif existing:
            out["look_again"] = [str(existing), *look]
        else:
            out["look_again"] = look
    return out

CAD_PRODUCTS = [
    {
        "id": "from_reference",
        "tool": "create_from_reference",
        "title": "Fotoğraftan çizim",
        "description": "2D iz: fotoğrafı vektörleştirir veya yapboza kazır. Duvar/çatı/pervane için create_design primitive.",
    },
    {
        "id": "jigsaw_puzzle",
        "tool": "create_design",
        "title": "Klasik yapboz",
        "description": "10×10 birbirine geçmeli yapboz (varsayılan 300×300 mm). Fotoğraflı iş için from_reference + layout=jigsaw. Sayı-nokta kartı değildir.",
    },
    {
        "id": "number_match_puzzle",
        "tool": "create_design",
        "title": "Sayı eşleme kartları",
        "description": "Yalnız 1–10 sayı-nokta eşleme kartları. Resimli yapboz için kullanma.",
    },
    {
        "id": "traffic_light",
        "tool": "create_traffic_light",
        "title": "Trafik lambası",
        "generator": "STEMTrafficLight",
        "description": "Payas STEM Dene Yap kule + kaide. LED ve şalter kesimleri.",
    },
    {
        "id": "robot_bank",
        "tool": "create_robot_bank",
        "title": "Robot kumbara",
        "generator": "PayasRobot",
        "description": "Hayal kumbara gövde, kollar, raylar, para kapağı (PayasRobot).",
    },
    {
        "id": "drawing_robot",
        "tool": "create_drawing_robot",
        "title": "Ressam robot",
        "module": "products.ressam_robot.generate",
        "description": "Tek kalemli dört çubuk çizim robotu.",
    },
    {
        "id": "product_box",
        "tool": "create_product_box",
        "title": "Ürün kutusu",
        "generator": "ABox",
        "description": "Basit ürün/ambalaj kutusu (ABox).",
    },
    {
        "id": "yacht",
        "tool": "create_yacht",
        "title": "Yat",
        "module": "products.yacht.generate",
        "description": "Statik sergi yat kiti, yüzmez.",
    },
    {
        "id": "astronaut",
        "tool": "create_astronaut",
        "title": "Astronot",
        "module": "products.astronaut_open.generate",
        "description": "Açık şase sabit astronot gösterim kiti.",
    },
]


def list_cad_tools() -> dict[str, Any]:
    return {
        "defaults": dict(boxespy.PAYAS_DEFAULTS),
        "count": len(CAD_PRODUCTS),
        "products": CAD_PRODUCTS,
        "policy": (
            "Toolbox, not a catalog. Look at the photo, call plan_laser_job, then create_design "
            "with box/panel/disc/triangle/propeller/contour primitives (Boxes.py). Do not ask for a new kit tool. "
            "Scale with parameters.reference={feature, mm, drawn_mm}. Coupon {type:coupon} only to calibrate. "
            "Optional marks: part.markings or {type:marking, target_part} "
            "(text/path/icon/line, x,y, width or height, rotation, align, engrave|cut). "
            "create_from_reference is 2D artwork only. Named create_* only for existing Payas products. "
            "generate_svg only if the plan names a Boxes.py class. Never write SVG yourself. Cuts keep ~1 mm holding nicks. "
            "create_design runs Designer → Reviewer → Repair → Reviewer → Final Gate inside the tool. "
            "Paste speak as the status card. final_status is BLOCKED | PROTOTYPE READY. "
            "Software never grants production: Physical Kerf/Assembly/Movement stay NOT VERIFIED, "
            "AUTHORIZED OUTPUT is Prototype SVG, PRODUCTION EXPORT is BLOCKED. "
            "Never say LAZER KESİME HAZIR or production-ready."
        ),
        "preferred": [
            "plan_laser_job",
            "create_design",
            "create_from_reference",
            "validate_assembly",
            "validate_svg",
            "payas_defaults",
        ],
        "avoid_unless_plan_says": ["generate_svg", "get_generator_schema"],
        "design": _design_api(),
        "generic": [
            "plan_laser_job",
            "create_from_reference",
            "create_design",
            "payas_defaults",
            "list_cad_tools",
            "get_generator_schema",
            "generate_svg",
            "validate_svg",
            "validate_assembly",
            "render_preview",
        ],
    }


def _design_api() -> dict[str, Any]:
    from design_engine import list_design_api

    return list_design_api()


def _traffic_params(
    thickness: float = 3.0,
    burn: float = 0.15,
    led: float | None = None,
    base_width: float | None = None,
    base_depth: float | None = None,
    base_height: float | None = None,
    tower_width: float | None = None,
    tower_depth: float | None = None,
    tower_height: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "thickness": thickness,
        "burn": burn,
        "labels": False,
        "reference": 0,
        "tabs": 0,
        "qr_code": False,
        "debug": False,
        "inner_corners": "corner",
        "sheet_width": boxespy.PAYAS_DEFAULTS["bed_width"],
        "sheet_height": boxespy.PAYAS_DEFAULTS["bed_height"],
    }
    if led is not None:
        params["led_dia"] = led
    for key, value in {
        "base_width": base_width,
        "base_depth": base_depth,
        "base_height": base_height,
        "tower_width": tower_width,
        "tower_depth": tower_depth,
        "tower_height": tower_height,
    }.items():
        if value is not None:
            params[key] = value
    if extra:
        params.update(extra)
    return params


def create_traffic_light(
    thickness: float = 3.0,
    burn: float = 0.15,
    led: float | None = None,
    base_width: float | None = None,
    base_depth: float | None = None,
    base_height: float | None = None,
    tower_width: float | None = None,
    tower_depth: float | None = None,
    tower_height: float | None = None,
    parameters: dict[str, Any] | None = None,
    public_base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    params = _traffic_params(
        thickness, burn, led, base_width, base_depth, base_height,
        tower_width, tower_depth, tower_height, parameters,
    )
    result = boxespy.generate_svg("STEMTrafficLight", params, public_base_url=public_base_url)
    result["product"] = "traffic_light"
    result["title"] = "Trafik lambası"
    return result


def create_product_box(
    x: float = 220,
    y: float = 160,
    h: float = 50,
    thickness: float = 3.0,
    burn: float = 0.15,
    outside: bool = True,
    public_base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    result = boxespy.generate_svg(
        "ABox",
        {"x": x, "y": y, "h": h, "thickness": thickness, "burn": burn, "outside": outside},
        public_base_url=public_base_url,
    )
    result["product"] = "product_box"
    result["title"] = "Ürün kutusu"
    return result


def _save_build(
    svg_bytes: bytes,
    product: str,
    title: str,
    public_base_url: str,
    extra: dict[str, Any] | None = None,
    dxf_bytes: bytes | None = None,
) -> dict[str, Any]:
    payload = {"product": product, "title": title, "generator": product}
    if extra:
        payload.update(extra)
    return boxespy.save_generated_svg(
        svg_bytes,
        public_base_url=public_base_url,
        extra=payload,
        dxf_bytes=dxf_bytes,
    )


def _dxf_from_built(built: dict[str, Any], fmt: str | None) -> bytes | None:
    if (fmt or "svg").strip().lower() not in {"dxf", "both"}:
        return None
    from dxf_export import geoms_to_dxf, svg_bytes_to_dxf

    cuts = built.get("cut_geoms") or []
    etches = built.get("etch_geoms") or []
    if cuts or etches:
        return geoms_to_dxf(cuts, etches)
    svg_bytes = built.get("svg_bytes")
    if svg_bytes:
        return svg_bytes_to_dxf(svg_bytes)
    return None


def create_robot_bank(public_base_url: str = "http://127.0.0.1:8000") -> dict[str, Any]:
    result = boxespy.generate_svg(
        "PayasRobot",
        {
            "x": 120,
            "y": 100,
            "h": 180,
            "thickness": 3.0,
            "burn": 0.15,
            "labels": False,
        },
        public_base_url=public_base_url,
    )
    result["product"] = "robot_bank"
    result["title"] = "Robot kumbara"
    result["generator"] = "PayasRobot"
    return result


def create_drawing_robot(public_base_url: str = "http://127.0.0.1:8000") -> dict[str, Any]:
    from products.ressam_robot.generate import (
        RessamRobot,
        add_bridges,
        motion_check,
        pack_sheet,
        validate_closed,
        validate_final,
        validate_joints,
    )

    robot = RessamRobot()
    motion = motion_check()
    robot.open()
    robot.render()
    joints = validate_joints(robot)
    raw = robot.close().getvalue()
    validate_closed(raw, robot)
    packed, layout = pack_sheet(raw, [(p["name"],) for p in robot.specs], 1500, 3000, cluster_width=360)
    validate_closed(packed, robot, True)
    final, bridges = add_bridges(packed)
    geometry = validate_final(final, bridges, robot)
    extra = {"status": "GEOMETRY_VALIDATED_PHYSICAL_PROTOTYPE_REQUIRED", "layout": layout, "geometry": geometry, "joints": joints, "motion": motion}
    return _save_build(final, "drawing_robot", "Ressam robot", public_base_url, extra)


def create_yacht(public_base_url: str = "http://127.0.0.1:8000") -> dict[str, Any]:
    from products.yacht.generate import build

    svg_bytes, report, _box = build()
    extra = {"status": report.get("status"), "layout": report.get("layout")}
    return _save_build(svg_bytes, "yacht", "Yat", public_base_url, extra)


def create_astronaut(public_base_url: str = "http://127.0.0.1:8000") -> dict[str, Any]:
    from products.astronaut_open.generate import build

    svg_bytes, report, _box = build()
    extra = {"status": report.get("status"), "layout": report.get("layout")}
    return _save_build(svg_bytes, "astronaut", "Astronot", public_base_url, extra)


def create_from_reference(
    image_base64: str | None = None,
    width_mm: float = 200.0,
    height_mm: float | None = None,
    style: str = "cut_and_etch",
    invert: bool | None = None,
    threshold: int = 0,
    layout: str = "trace",
    rows: int = 10,
    cols: int = 10,
    seed: int = 1,
    format: str = "svg",
    image_bytes: bytes | None = None,
    public_base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    from image_trace import produce_photo_job

    try:
        built = produce_photo_job(
            image_base64=image_base64,
            image_bytes=image_bytes,
            width_mm=width_mm,
            height_mm=height_mm,
            style=style,
            invert=invert,
            threshold=threshold,
            layout=layout,
            rows=rows,
            cols=cols,
            seed=seed,
        )
    except Exception as exc:
        return _mcp(
            {
                "ready_to_cut": False,
                "hint": (
                    "Pass a compressed JPEG around 1200px as image_base64. "
                    "This traces 2D artwork. For walls/roofs/propellers use create_design primitives."
                ),
                "look_again": [str(exc)],
            }
        )
    extra = {
        "product": built.get("layout") or "from_reference",
        "title": "Klasik yapboz" if built.get("layout") == "jigsaw" else "Fotoğraftan çizim",
        "generator": "create_from_reference",
        "style": built.get("style"),
        "layout": built.get("layout"),
        "cut_paths": built.get("cut_paths"),
        "etch_paths": built.get("etch_paths"),
        "count": built.get("count"),
        "dimensions": {
            "width_mm": built.get("width_mm"),
            "height_mm": built.get("height_mm"),
            "thickness": boxespy.PAYAS_DEFAULTS["thickness"],
            "burn": boxespy.PAYAS_DEFAULTS["burn"],
        },
    }
    return _save_build(
        built["svg_bytes"],
        extra["product"],
        extra["title"],
        public_base_url,
        extra,
        dxf_bytes=_dxf_from_built(built, format),
    )


def create_design(
    preset: str | None = None,
    primitives: list[Any] | None = None,
    parameters: dict[str, Any] | None = None,
    svg: str | None = None,
    public_base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    from design_engine import compile_design, import_svg_document
    from toolbox import GRAMMAR, HINT

    try:
        if svg:
            built = import_svg_document(svg)
        else:
            built = compile_design(preset=preset, primitives=primitives, parameters=parameters)
    except Exception as exc:
        from toolbox import GRAMMAR, HINT

        return _mcp(
            {
                "ready_to_cut": False,
                "hint": HINT,
                "grammar": GRAMMAR,
                "look_again": [str(exc), "Call create_design with box/panel/propeller primitives from the mill grammar."],
            }
        )
    name = str(built.get("preset") or preset or "design")
    title = "İçe aktarılan SVG" if built.get("imported") else "Bestelenmiş kesim"
    if name in {"number_match_puzzle", "number_match"}:
        title = "Sayı eşleme kartları"
    if name in {"jigsaw_puzzle", "classic_jigsaw"}:
        title = "Klasik yapboz"
    composed = bool(built.get("composed")) or name in {"toolbox", "composed", "box", "panel", "disc"}
    if composed and name not in {"number_match_puzzle", "number_match", "jigsaw_puzzle", "classic_jigsaw"}:
        name = "composed"
        title = "Bestelenmiş kesim"
    extra = {
        "product": name,
        "title": title,
        "generator": "create_design" if composed else name,
        "preset": None if composed else name,
        "method": built.get("method") or ("compose_primitives" if composed else "preset"),
        "compiler": built.get("compiler") or ("create_design" if composed else name),
        "note": built.get("note")
        or (
            "This SVG is YOUR primitives compiled with Boxes.py. "
            "It is not a Boxes.py catalog generator and not a missed windmill kit."
            if composed
            else None
        ),
        "count": built.get("count"),
        "imported": bool(built.get("imported")),
        "assembly": built.get("assembly"),
        "nesting": built.get("nesting"),
        "topology": built.get("topology"),
        "scale": built.get("scale"),
        "primitives": built.get("primitives"),
        "parts": built.get("parts"),
        "pipeline": built.get("pipeline"),
        "review": built.get("review"),
        "design_map": built.get("design_map"),
        "connections": built.get("connections"),
        "final_status": built.get("final_status"),
        "speak": built.get("speak"),
        "scorecard": built.get("scorecard"),
        "authorized_output": built.get("authorized_output"),
        "production_export": built.get("production_export") or "BLOCKED",
        "production_summary": built.get("production_summary"),
        "dimensions": {
            "width_mm": built.get("width_mm"),
            "height_mm": built.get("height_mm"),
            "card_w": built.get("card_w"),
            "card_h": built.get("card_h"),
            "thickness": boxespy.PAYAS_DEFAULTS["thickness"],
            "burn": boxespy.PAYAS_DEFAULTS["burn"],
        },
    }
    fmt = str((parameters or {}).get("format") or "svg")
    if extra.get("review") is None:
        from nesting import inspect_nesting
        from pipeline import review_only
        from topology import inspect_topology

        extra["topology"] = extra.get("topology") or inspect_topology(built.get("svg_bytes"))
        extra["nesting"] = extra.get("nesting") or inspect_nesting(built.get("svg_bytes"))
        gated = review_only({**built, **extra, "svg_bytes": built.get("svg_bytes")})
        extra["review"] = gated.get("review")
        extra["pipeline"] = gated.get("pipeline")
        extra["design_map"] = gated.get("design_map")
        extra["connections"] = gated.get("connections")
        extra["final_status"] = gated.get("final_status")
        extra["speak"] = gated.get("speak")
        extra["scorecard"] = gated.get("scorecard")
        extra["authorized_output"] = gated.get("authorized_output")
        extra["production_export"] = gated.get("production_export") or "BLOCKED"
        extra["production_summary"] = gated.get("production_summary")
        extra["look_again"] = gated.get("look_again") or extra.get("look_again")
    extra["ready_to_cut"] = False
    extra["production_export"] = extra.get("production_export") or "BLOCKED"
    extra.setdefault(
        "authorized_output",
        "Prototype SVG" if extra.get("final_status") == "PROTOTYPE READY" else "None",
    )
    return _mcp(_save_build(built["svg_bytes"], name, title, public_base_url, extra, dxf_bytes=_dxf_from_built(built, fmt)))


def validate_assembly(
    file_id: str | None = None,
    primitives: list[Any] | None = None,
) -> dict[str, Any]:
    """Mechanical fit from a recipe, or reload assembly + nesting from a generated file."""
    from assembly import apply_roof_lock, check_assembly

    if primitives:
        from pipeline import run_pipeline

        built = run_pipeline(primitives, {})
        report = built.get("assembly") or check_assembly(apply_roof_lock(primitives)[0])
        return _mcp(
            {
                "source": "primitives",
                "assembly": report,
                "pipeline": built.get("pipeline"),
                "review": built.get("review"),
                "design_map": built.get("design_map"),
                "connections": built.get("connections"),
                "final_status": built.get("final_status"),
                "speak": built.get("speak"),
                "scorecard": built.get("scorecard"),
                "authorized_output": built.get("authorized_output"),
                "production_export": built.get("production_export") or "BLOCKED",
                "ready_to_cut": False,
                "look_again": built.get("look_again") or report.get("look_again") or [],
            }
        )
    if not file_id:
        return _mcp(
            {
                "ready_to_cut": False,
                "look_again": ["Pass primitives or file_id from create_design."],
            }
        )
    svg_report = boxespy.validate_svg(file_id)
    sidecar = svg_report.get("review") or {}
    status = svg_report.get("final_status") or sidecar.get("final_status")
    return _mcp(
        {
            "source": "file",
            "file_id": svg_report.get("file_id"),
            "assembly": svg_report.get("assembly"),
            "nesting": svg_report.get("nesting"),
            "topology": svg_report.get("topology"),
            "review": svg_report.get("review") or sidecar,
            "pipeline": svg_report.get("pipeline"),
            "design_map": svg_report.get("design_map"),
            "connections": svg_report.get("connections"),
            "final_status": status,
            "speak": svg_report.get("speak"),
            "scorecard": svg_report.get("scorecard") or sidecar.get("scorecard"),
            "authorized_output": svg_report.get("authorized_output") or sidecar.get("authorized_output"),
            "production_export": svg_report.get("production_export") or sidecar.get("production_export") or "BLOCKED",
            "look_again": svg_report.get("look_again") or svg_report.get("errors") or [],
            "ready_to_cut": False,
        }
    )


def create_number_match_puzzle(
    count: int = 10,
    card_w: float = 108.0,
    card_h: float = 64.0,
    columns: int = 2,
    public_base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    return create_design(
        preset="number_match_puzzle",
        parameters={"count": count, "card_w": card_w, "card_h": card_h, "columns": columns},
        public_base_url=public_base_url,
    )


CREATE = {
    "traffic_light": lambda params, url: create_traffic_light(public_base_url=url, **params),
    "robot_bank": lambda params, url: create_robot_bank(public_base_url=url),
    "drawing_robot": lambda params, url: create_drawing_robot(public_base_url=url),
    "product_box": lambda params, url: create_product_box(public_base_url=url, **params),
    "yacht": lambda params, url: create_yacht(public_base_url=url),
    "astronaut": lambda params, url: create_astronaut(public_base_url=url),
    "from_reference": lambda params, url: create_from_reference(public_base_url=url, **params),
    "jigsaw_puzzle": lambda params, url: create_design(preset="jigsaw_puzzle", parameters=params, public_base_url=url),
    "number_match_puzzle": lambda params, url: create_number_match_puzzle(public_base_url=url, **params),
}

CREATE_KEYS = {
    "traffic_light": (
        "thickness", "burn", "led", "base_width", "base_depth", "base_height",
        "tower_width", "tower_depth", "tower_height",
    ),
    "product_box": ("x", "y", "h", "thickness", "burn", "outside"),
    "robot_bank": (),
    "drawing_robot": (),
    "yacht": (),
    "astronaut": (),
    "from_reference": (
        "image_base64", "width_mm", "height_mm", "style", "invert", "threshold",
        "layout", "rows", "cols", "seed", "format",
    ),
    "jigsaw_puzzle": ("width_mm", "height_mm", "rows", "cols", "seed", "format", "size_mm"),
    "number_match_puzzle": ("count", "card_w", "card_h", "columns"),
}


def create_product(product_id: str, parameters: dict[str, Any] | None = None, public_base_url: str = "http://127.0.0.1:8000") -> dict[str, Any]:
    handler = CREATE.get(product_id)
    if handler is None:
        known = ", ".join(CREATE)
        raise ValueError(f"Unknown CAD product '{product_id}'. Known: {known}")
    allowed = CREATE_KEYS.get(product_id, ())
    raw = parameters or {}
    params = {key: raw[key] for key in allowed if key in raw}
    return handler(params, public_base_url)
