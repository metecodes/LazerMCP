"""Payas STEM product CAD. Named tools, not one generator per Boxes.py class."""

from __future__ import annotations

from typing import Any

import boxes_adapter as boxespy

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
            "create_from_reference is 2D artwork only. Named create_* only for existing Payas products. "
            "generate_svg only if the plan names a Boxes.py class. Never write SVG yourself. Cuts keep ~1 mm holding nicks. "
            "create_design returns assembly (finger/shaft/slot/gable seating) and nesting (translation-only pack). "
            "If assembly.ok is false, fix primitives and call create_design again — do not tell the user to cut."
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
        return {
            "success": False,
            "error": str(exc),
            "hint": (
                "Call plan_laser_job first. Pass a compressed JPEG around 1200px as image_base64. "
                "This traces 2D artwork. For walls/roofs/propellers use create_design primitives."
            ),
        }
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
        return {
            "success": False,
            "error": str(exc),
            "hint": HINT,
            "grammar": GRAMMAR,
        }
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
        "scale": built.get("scale"),
        "primitives": built.get("primitives"),
        "parts": built.get("parts"),
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
    asm = extra.get("assembly")
    nest = extra.get("nesting")
    extra["ready_to_cut"] = (not isinstance(asm, dict) or bool(asm.get("ok", True))) and (
        not isinstance(nest, dict) or bool(nest.get("ok", True))
    )
    return _save_build(built["svg_bytes"], name, title, public_base_url, extra, dxf_bytes=_dxf_from_built(built, fmt))


def validate_assembly(
    file_id: str | None = None,
    primitives: list[Any] | None = None,
) -> dict[str, Any]:
    """Mechanical fit from a recipe, or reload assembly + nesting from a generated file."""
    from assembly import check_assembly

    if primitives:
        report = check_assembly(primitives)
        return {
            "success": bool(report.get("ok")),
            "source": "primitives",
            "assembly": report,
            "ready_to_cut": bool(report.get("ok")),
        }
    if not file_id:
        return {
            "success": False,
            "error": "Pass primitives (before cut) or file_id (after create_design).",
        }
    svg_report = boxespy.validate_svg(file_id)
    return {
        "success": bool(svg_report.get("success")) and bool((svg_report.get("assembly") or {}).get("ok", True)),
        "source": "file",
        "file_id": svg_report.get("file_id"),
        "assembly": svg_report.get("assembly"),
        "nesting": svg_report.get("nesting"),
        "errors": svg_report.get("errors") or [],
        "ready_to_cut": bool(svg_report.get("success"))
        and bool((svg_report.get("assembly") or {}).get("ok", True))
        and bool((svg_report.get("nesting") or {}).get("ok", True)),
    }


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
