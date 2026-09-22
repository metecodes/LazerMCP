"""Teach the client AI how to cut the current request. No geometry here."""

from __future__ import annotations

import re
from typing import Any

from boxes_adapter import PAYAS_DEFAULTS
from scale import MEASURE
from toolbox import GRAMMAR

_KITS = (
    (("astronaut", "astronot"), "create_astronaut", "Astronot kiti"),
    (("trafik", "traffic_light", "traffic light"), "create_traffic_light", "Trafik lambası"),
    (("robot bank", "kumbara", "hayal kumbara", "payasrobot"), "create_robot_bank", "Robot kumbara"),
    (("ressam", "drawing robot", "cizim robot"), "create_drawing_robot", "Ressam robot"),
    (("yacht", "yat ", "statik yat", "yat kiti"), "create_yacht", "Yat"),
    (("urun kutusu", "product box", "abox"), "create_product_box", "Ürün kutusu"),
)

_TR_FOLD = str.maketrans({
    "ı": "i", "İ": "i", "I": "i",
    "ş": "s", "Ş": "s",
    "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o",
    "ç": "c", "Ç": "c",
    "â": "a", "î": "i", "û": "u",
})

_MATCH_CARD = (
    "sayi esleme",
    "number match",
    "number-dot",
    "nokta esleme",
    "matching card",
    "esleme kart",
)

_ASSEMBLY = (
    "kalemlik",
    "pencil holder",
    "pencil-holder",
    "finger",
    "tab-slot",
    "tab slot",
    "degirmen",
    "yel degirmen",
    "windmill",
    "mill ",
    " mill",
    "pervane",
    "propeller",
    "egimli cati",
    "cati",
    "gable",
    "4 duvar",
    "dort duvar",
    "four wall",
    "duvar",
    "kanatli",
    "maket",
    "montaj",
    "birlestir",
    "3d",
    "3-d",
    "assemble",
    "assembly",
    "solar",
    "gunes",
    "kule",
    "house",
    "barn",
    "cabin",
    "shed",
    "taban",
    "kaide",
    "kutu",
    "box",
    "kapak",
    "govde",
    "panel",
)

_TRACE_ONLY = (
    "sadece cizim",
    "sadece 2d",
    "2d iz",
    "siluet",
    "silhouette",
    "trace only",
    "vektorize",
    "vectorize",
    "logo",
)

_JIGSAW = (
    "yapboz",
    "puzzle",
    "jigsaw",
    "birbirine gec",
    "interlock",
    "parca",
    "pieces",
)


def _wants_assembly(text: str) -> bool:
    return any(k in text for k in _ASSEMBLY)


def _wants_trace_only(text: str) -> bool:
    return any(k in text for k in _TRACE_ONLY)


def _blob(*parts: str) -> str:
    return " ".join(p or "" for p in parts).translate(_TR_FOLD).lower()


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


def _rules() -> list[str]:
    return [
        "Laser MCP is a toolbox, not a product catalog. Never ask for a new kit/tool.",
        "Never write SVG or DXF yourself. Never prepare files outside Laser MCP.",
        "Never flip, rotate, or mirror geometry.",
        "Cut #FF0000, text/logo engraving #000000, LaserCAD Y-up; use the stated material thickness and measured kerf.",
        "Ask whether the user wants holding nicks (small uncut bridges) and what extra text to engrave. Pass holding_nicks true/false and surface_texts; [] means no extra text. Never confuse holding nicks with assembly tabs.",
        "Look at the photo, pick ONE length (or count 3 mm plywood edges), then compose primitives (box/panel/disc/triangle/propeller/contour).",
        "create_design is Designer → Reviewer → Repair → Reviewer → Final Gate → SVG. Do not skip review. Do not invent a PASS.",
        "Paste speak as the status card. BLOCKED = no authorized SVG. PROTOTYPE READY = Prototype SVG only. Physical tests stay NOT VERIFIED. PRODUCTION EXPORT is always BLOCKED. Never say LAZER KESİME HAZIR.",
        "If the user stated a size, use it. Else pick ONE photo length and set parameters.reference = {feature, mm, drawn_mm}.",
        "create_design compiles your primitives (method=compose_primitives). That is the designer step, not a wrong generator.",
        "Door/window = slots on the front wall, not type=slot and not separate sliding parts.",
        "Optional part marks: part.markings or {type:marking, target_part, kind:text|path|icon|line, x,y, width or height, rotation, align, operation:engrave|cut}.",
        "Copy what_you_see into parameters.what_you_see. After a coupon cut, pass measured_bar_mm from the human — never invent it.",
        "Pass parameters.material and parameters.machine. MCP writes MATERIALS (MCP) / bom. Do not invent kerf or hardware.",
        "Optional parameters.project stores a named version in studio history.",
        "physical_assembly=verified and movement_test=verified only after a real dry-fit / spin. Production export stays BLOCKED until those human tests exist.",
        "create_from_reference traces flat artwork; for one-sheet assemblies pass explicit primitives plus reference_markings targeted to named panels. Mechanical joints always come from primitives, never pixels.",
        "generate_svg only if the plan names a Boxes.py class. Named create_* kits only when the plan names an existing Payas product.",
        "For assemblies, consult joint_library and search_joint_templates before changing joint geometry. Reuse Boxes.py edges with shared settings for both mating parts; indexed source is not proof of physical fit. Supplied SVG takes precedence over a loosely matching template.",
        "First uncalibrated laser: add {type:coupon} once. Do not bolt a coupon onto every mill.",
        "number_match_puzzle is only for number-to-dot matching cards.",
    ]


def _assembly_recipe(text: str, width: float | None, height: float | None) -> list[dict[str, Any]]:
    if any(k in text for k in ("kalemlik", "pencil holder", "pencil-holder")) and any(k in text for k in ("ev", "house")):
        from house_holder import recipe
        return recipe(width=max(100.0, float(width or 130)))
    millish = any(
        k in text
        for k in (
            "degirmen",
            "windmill",
            "pervane",
            "propeller",
            "cati",
            "gable",
            "solar",
            "gunes",
            "güneş",
        )
    )
    x = float(width or (70 if millish else 80))
    y = float(height or width or (52 if millish else 80))
    x = max(50.0, min(400.0, x))
    y = max(45.0, min(400.0, y))
    if millish:
        y = min(y, max(45.0, round(x * 0.75, 1)))
        h = round(max(140.0, min(320.0, x * 2.5)), 1)
    else:
        h = round(max(80.0, min(280.0, max(x, y) * 1.5)), 1)
    recipe: list[dict[str, Any]] = [
        {
            "type": "box",
            "x": round(x, 1),
            "y": round(y, 1),
            "h": h,
            "bottom": True,
            "walls": {"front": {"holes": [], "slots": []}},
        }
    ]
    if millish:
        shaft = 4.0
        prop = round(min(x, y) * 0.7, 1)
        cx = round(x / 2, 1)
        recipe[0]["walls"] = {
            "front": {
                "holes": [{"x": cx, "y": round(h * 0.88, 1), "d": shaft}],
                "slots": [
                    {"x": cx, "y": round(h * 0.20, 1), "w": round(x * 0.34, 1), "h": round(h * 0.22, 1)},
                    {"x": cx, "y": round(h * 0.48, 1), "w": round(x * 0.36, 1), "h": round(h * 0.18, 1)},
                ],
            },
            "back": {"holes": [{"x": cx, "y": round(h * 0.88, 1), "d": shaft}]},
        }
        recipe.extend(
            [
                {"type": "triangle", "w": round(x, 1), "h": round(max(18.0, y * 0.42), 1), "count": 2, "label": "roof-support"},
                {"type": "panel", "w": round(x + 10, 1), "h": round(y + 6, 1), "edges": "eeee", "count": 2, "label": "roof"},
                {"type": "panel", "w": round(x + 8, 1), "h": round(max(28.0, y * 0.9), 1), "edges": "eeee", "label": "solar"},
                {
                    "type": "panel",
                    "w": round(max(28.0, x * 0.5), 1),
                    "h": round(max(28.0, y * 0.55), 1),
                    "edges": "eeee",
                    "holes": [
                        {"x": round(max(14.0, x * 0.25), 1), "y": round(max(14.0, y * 0.275), 1), "d": shaft},
                        {"x": 8, "y": 8, "d": 3},
                        {"x": round(max(20.0, x * 0.5) - 8, 1), "y": 8, "d": 3},
                    ],
                    "label": "motor-mount",
                },
                {"type": "propeller", "blades": 4, "d": prop, "blade_w": round(max(10.0, prop * 0.22), 1), "hole": shaft, "label": "propeller"},
                {"type": "disc", "d": 14, "hole": shaft, "count": 2, "label": "spacer"},
            ]
        )
    return recipe


def _wants_coupon(text: str) -> bool:
    return any(
        k in text
        for k in (
            "kupon",
            "coupon",
            "kerf",
            "kalibrasyon",
            "burn test",
            "burntest",
            "ilk kesim",
            "olcum cubugu",
            "ölçüm çubuğu",
        )
    )


def _compose_plan(
    summary: str,
    width: float | None,
    height: float | None,
    fmt: str,
    look: str,
    text: str,
    what_you_see: str = "",
    reference_job: bool = False,
) -> dict[str, Any]:
    recipe = _assembly_recipe(text, width, height)
    from joint_library import plan_references
    references = plan_references(text)
    if _wants_coupon(text):
        recipe = [{"type": "coupon", "x": 40, "label": "kerf-coupon"}] + recipe
    params: dict[str, Any] = {"format": fmt, "material": "poplar_3mm", "machine": "payas_workshop"}
    if str(what_you_see or "").strip():
        params["what_you_see"] = str(what_you_see).strip()
    if reference_job:
        params["reference_job"] = True
        params["reference_mode"] = "structural"
        params["reference_parts"] = []
    if recipe and recipe[0].get("placement"):
        look = "Use these six structural panels as the body and the separate star as an adhesive ornament; do not add a box behind the house faces. Keep explicit slot.mate, tabs and placement together. Dimensions are nominal, not recovered exactly from a photo. Call render_preview(view=assembled) after create_design; physical dry-fit remains NOT VERIFIED."
    box = next((p for p in recipe if isinstance(p, dict) and p.get("type") == "box"), None)
    if width and box:
        params["reference"] = {
            "feature": "footprint_x",
            "mm": width,
            "drawn_mm": box.get("x"),
            "note": "Change mm if the photo/user length differs; drawn_mm is the current recipe x.",
        }
    return {
        "success": True,
        "method": "compose_primitives",
        "joint_library": references,
        "summary": summary,
        "next_tool": "create_design",
        "next_arguments": {"primitives": recipe, "parameters": params},
        "look_again": look,
        "grammar": GRAMMAR,
        "measure": MEASURE,
        "cannot_do": [],
        "rules": _rules(),
        "defaults": dict(PAYAS_DEFAULTS),
    }


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
    dxf = True
    fmt = "both"
    width, height = _size_mm(request + " " + seen)
    rows, cols = _grid(request + " " + seen)
    photo = bool(has_photo) or bool(seen.strip())
    rules = _rules()

    # A requested Boxes.py template should execute its own geometry code.
    if "boxes" in text and not photo:
        from joint_library import search_joint_templates
        library = search_joint_templates(request, 1)
        if library["matches"]:
            match = library["matches"][0]
            valid = {p["name"] for p in match["parameters"]}
            params = {key: value for key, value in {"x": width, "y": height}.items()
                      if key in valid and value is not None}
            return {"success": True, "method": "boxes_template", "summary": match["description"],
                    "next_tool": "generate_svg", "next_arguments": {"generator": match["name"], "parameters": params},
                    "joint_library": library, "rules": rules, "defaults": dict(PAYAS_DEFAULTS),
                    "look_again": "Use the supplied real schema to set material thickness, height and edge choices. This is a retrieved source template, not an exact reconstruction of a photo. Physical fit remains NOT VERIFIED."}

    if photo and _wants_match_cards(text):
        photo = False

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
            "grammar": GRAMMAR, "measure": MEASURE,
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
            "look_again": f"Call {tool}. Do not request a new tool. Do not draw SVG yourself.",
            "grammar": GRAMMAR, "measure": MEASURE,
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

    if _wants_jigsaw(text) and not _wants_assembly(text):
        width = width or 300.0
        height = height or width
        rows = rows or 10
        cols = cols or 10
        if photo:
            args: dict[str, Any] = {
                "width_mm": width,
                "height_mm": height,
                "style": "etch",
                "layout": "jigsaw",
                "rows": int(rows),
                "cols": int(cols),
                "format": fmt,
            }
            return {
                "success": True,
                "method": "photo_jigsaw",
                "summary": (
                    f"Photo as etch on a {int(rows)}×{int(cols)} interlocking jigsaw, "
                    f"{width:.0f}×{height:.0f} mm."
                ),
                "next_tool": "create_from_reference",
                "next_arguments": args,
                "look_again": (
                    "Compress the photo to ~1200px JPEG and call create_from_reference "
                    "with next_arguments, then validate_svg."
                ),
                "grammar": GRAMMAR, "measure": MEASURE,
                "rules": rules,
                "defaults": dict(PAYAS_DEFAULTS),
            }
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
            "look_again": "Call create_design with those arguments.",
            "grammar": GRAMMAR, "measure": MEASURE,
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

    if _wants_coupon(text) and not _wants_assembly(text) and not _wants_trace_only(text):
        return {
            "success": True,
            "method": "kerf_coupon",
            "summary": "Kerf/fit coupon: Boxes.py FingerJoint f/F pair plus a 100 mm reference bar.",
            "next_tool": "create_design",
            "next_arguments": {
                "primitives": [{"type": "coupon", "x": 40, "label": "kerf-coupon"}],
                "parameters": {"format": fmt},
            },
            "look_again": (
                "Call create_design. Dry-fit male f into female F. Measure the 100 mm bar; "
                "burn ≈ shrinkage/2. Keep Payas burn at 0.15 unless the bar says otherwise. "
                "Do not add this coupon to every later mill."
            ),
            "grammar": GRAMMAR,
            "measure": MEASURE,
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

    if _wants_assembly(text) and not _wants_trace_only(text):
        width = width or (130.0 if any(k in text for k in ("kalemlik", "pencil holder", "pencil-holder")) else 80.0)
        height = height or width
        look = (
            "LOOK at the photo again. Read millimetres from what you see "
            "(footprint, wall height, door/window, shaft, propeller diameter and blade count). "
            "If the user stated cm/mm, that is box x/y. Otherwise pick ONE length and set "
            "parameters.reference = {feature, mm, drawn_mm} so create_design scales the recipe. "
            "Edit next_arguments.primitives accordingly, then call create_design. "
            "A 4-blade rotor is type=propeller (not disc). An odd silhouette is type=contour with points:[[x,y],...] mm. "
            "Door and window are slots on the front wall, not type=slot and not extra sliding parts. "
            "Motor plate / solar carrier / roof brace = type=panel. "
            "Do not ask for a mill kit. Do not 2D-trace this as the assembly. "
            "Add type=coupon only if they asked to calibrate this laser/sheet."
        )
        if not photo:
            look = (
                "No photo: still compose with create_design primitives. "
                "If a photo exists, call plan_laser_job again with has_photo=true and what_you_see filled, "
                "then adjust millimetres from the picture."
            )
        return _compose_plan(
            "Compose the mill/house with create_design primitives (that call is the drawing). "
            "The draft recipe is a starting grammar — overwrite sizes from the photo.",
            width,
            height,
            fmt,
            look,
            text,
            seen,
            photo,
        )

    if photo and not _wants_trace_only(text):
        look = (
            "LOOK at the photo. Name walls, floor, lid, holes, rotors in what_you_see. "
            "Do not 2D-trace a thing to build. Call create_design with primitives."
        )
        if not seen.strip():
            return {
                "success": True,
                "method": "ask_or_compose",
                "summary": "Photo of a thing to build. Describe the parts first — do not trace it as 2D art.",
                "next_tool": "plan_laser_job",
                "next_arguments": {"has_photo": True},
                "look_again": look,
                "grammar": GRAMMAR,
                "measure": MEASURE,
                "rules": rules,
                "defaults": dict(PAYAS_DEFAULTS),
            }
        return _compose_plan(
            "Compose the photographed object with create_design primitives. Do not trace the photo.",
            width or 80.0,
            height or width or 80.0,
            fmt,
            look,
            text,
            seen,
            True,
        )

    if photo:
        width = width or 200.0
        return {
            "success": True,
            "method": "photo_trace",
            "summary": (
                f"Trace the photo into laser paths at width {width:.0f} mm "
                "(height follows the image). Outline = cut, interior = etch."
            ),
            "next_tool": "create_from_reference",
            "next_arguments": {
                "width_mm": width,
                "style": "cut_and_etch",
                "layout": "trace",
                "format": fmt,
            },
            "look_again": (
                "2D artwork only. If this is a box, mill, or kit, describe parts in what_you_see "
                "and call plan_laser_job again — then create_design."
            ),
            "grammar": GRAMMAR, "measure": MEASURE,
            "rules": rules,
            "defaults": dict(PAYAS_DEFAULTS),
        }

    return {
        "success": True,
        "method": "ask_or_compose",
        "summary": (
            "No named kit. If the user sent a photo of a thing to cut and assemble, "
            "look at it and call this planner again with has_photo=true and what_you_see. "
            "If it is flat artwork, use create_from_reference."
        ),
        "next_tool": "plan_laser_job",
        "next_arguments": {"has_photo": True},
        "look_again": (
            "Look at the photo. Describe walls, roofs, holes, discs in what_you_see. "
            "Then call plan_laser_job with has_photo=true. Do not ask us to add a new kit."
        ),
        "grammar": GRAMMAR, "measure": MEASURE,
        "rules": rules,
        "defaults": dict(PAYAS_DEFAULTS),
    }
