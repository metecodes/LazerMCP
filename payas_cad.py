"""Payas STEM product CAD. Named tools, not one generator per Boxes.py class."""

from __future__ import annotations

from typing import Any

import boxes_adapter as boxespy

CAD_PRODUCTS = [
    {
        "id": "number_match_puzzle",
        "tool": "create_design",
        "title": "Sayı eşleme yapboz",
        "description": "1–10 sayı-nokta jigsaw kartları. create_design preset=number_match_puzzle. Referans fotoğrafı izlemez.",
    },
    {
        "id": "from_reference",
        "tool": "create_from_reference",
        "title": "Referans görsel",
        "description": "Foto/logo izleme. Eğitim kartı/yapboz için create_design kullanın.",
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
            "New educational cards/puzzles = create_design (preset or primitives). "
            "Do not request a new MCP tool. Photos/logos = create_from_reference. "
            "Named create_* kit tools are only for those exact products. Never hand-write SVG."
        ),
        "design": _design_api(),
        "generic": [
            "create_design",
            "create_from_reference",
            "payas_defaults",
            "list_cad_tools",
            "get_generator_schema",
            "generate_svg",
            "validate_svg",
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


def _save_build(svg_bytes: bytes, product: str, title: str, public_base_url: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {"product": product, "title": title, "generator": product}
    if extra:
        payload.update(extra)
    return boxespy.save_generated_svg(svg_bytes, public_base_url=public_base_url, extra=payload)


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
    style: str = "cut_and_etch",
    invert: bool | None = None,
    threshold: int = 140,
    image_bytes: bytes | None = None,
    public_base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    from image_trace import trace_reference_svg

    traced = trace_reference_svg(
        image_base64=image_base64,
        image_bytes=image_bytes,
        width_mm=width_mm,
        style=style,
        invert=invert,
        threshold=threshold,
    )
    extra = {
        "product": "from_reference",
        "title": "Referans görsel",
        "generator": "create_from_reference",
        "style": traced["style"],
        "cut_paths": traced["cut_paths"],
        "etch_paths": traced["etch_paths"],
        "dimensions": {
            "width_mm": traced["width_mm"],
            "height_mm": traced["height_mm"],
            "thickness": boxespy.PAYAS_DEFAULTS["thickness"],
            "burn": boxespy.PAYAS_DEFAULTS["burn"],
        },
    }
    return _save_build(traced["svg_bytes"], "from_reference", "Referans görsel", public_base_url, extra)


def create_design(
    preset: str | None = None,
    primitives: list[Any] | None = None,
    parameters: dict[str, Any] | None = None,
    svg: str | None = None,
    public_base_url: str = "http://127.0.0.1:8000",
) -> dict[str, Any]:
    from design_engine import compile_design, import_svg_document

    if svg:
        built = import_svg_document(svg)
    else:
        built = compile_design(preset=preset, primitives=primitives, parameters=parameters)
    name = str(built.get("preset") or preset or "design")
    title = "İçe aktarılan SVG" if built.get("imported") else "Parametrik tasarım"
    if name in {"number_match_puzzle", "number_match"}:
        title = "Sayı eşleme yapboz"
    extra = {
        "product": name,
        "title": title,
        "generator": name,
        "preset": name,
        "count": built.get("count"),
        "imported": bool(built.get("imported")),
        "dimensions": {
            "width_mm": built.get("width_mm"),
            "height_mm": built.get("height_mm"),
            "card_w": built.get("card_w"),
            "card_h": built.get("card_h"),
            "thickness": boxespy.PAYAS_DEFAULTS["thickness"],
            "burn": boxespy.PAYAS_DEFAULTS["burn"],
        },
    }
    return _save_build(built["svg_bytes"], name, title, public_base_url, extra)


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
    "from_reference": ("image_base64", "width_mm", "style", "invert", "threshold"),
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
