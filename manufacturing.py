"""Manufacturing intent: feature → semantic_role → operation → validate → export.

CUT is never a generic fallback. UNKNOWN is internal-only and blocks final export.
Stroke color is presentation. The exporter does not decide semantics.
"""

from __future__ import annotations

from collections import Counter
from typing import Any
from xml.etree import ElementTree as ET

EXPORT_OPERATIONS = ("CUT", "ENGRAVE", "SCORE", "GUIDE", "LABEL")
OPERATIONS = (*EXPORT_OPERATIONS, "UNKNOWN")
ORIGINS = ("EXPLICIT", "SEMANTIC_DEFAULT", "INFERRED", "UNKNOWN")

CRITICAL_FAIL = "FAIL"
WARNING = "WARNING"
PASS = "PASS"

ROLE_DEFAULTS: dict[str, str] = {
    "outer_contour": "CUT",
    "inner_cutout": "CUT",
    "hole": "CUT",
    "slot": "CUT",
    "tab": "CUT",
    "finger_joint": "CUT",
    "pivot_hole": "CUT",
    "shaft_hole": "CUT",
    "text": "ENGRAVE",
    "logo": "ENGRAVE",
    "surface_decoration": "ENGRAVE",
    "facade_detail": "ENGRAVE",
    "roof_texture": "ENGRAVE",
    "ornament": "ENGRAVE",
    "engraved_line": "ENGRAVE",
    "texture": "ENGRAVE",
    "decorative_detail": "ENGRAVE",
    "score_line": "SCORE",
    "fold_line": "SCORE",
    "score": "SCORE",
    "construction_guide": "GUIDE",
    "alignment_guide": "GUIDE",
    "label": "LABEL",
    "custom": "UNKNOWN",
}

CUT_ROLES = frozenset(
    {
        "outer_contour",
        "inner_cutout",
        "hole",
        "slot",
        "tab",
        "finger_joint",
        "pivot_hole",
        "shaft_hole",
    }
)
SURFACE_ROLES = frozenset(
    {
        "text",
        "logo",
        "surface_decoration",
        "facade_detail",
        "roof_texture",
        "ornament",
        "engraved_line",
        "texture",
        "decorative_detail",
        "label",
    }
)
GUIDE_ROLES = frozenset({"construction_guide", "alignment_guide"})
ROLE_ALIASES = {
    "texture": "roof_texture",
    "decorative_detail": "surface_decoration",
    "score": "score_line",
}

TYPE_ROLES: dict[str, str] = {
    "text": "text",
    "number": "text",
    "pips": "surface_decoration",
    "box": "outer_contour",
    "panel": "outer_contour",
    "disc": "outer_contour",
    "triangle": "outer_contour",
    "propeller": "outer_contour",
    "contour": "outer_contour",
    "polygon": "outer_contour",
    "coupon": "outer_contour",
    "jigsaw_grid": "outer_contour",
    "jigsaw_card": "outer_contour",
    "token_grid": "outer_contour",
    "rounded_rect": "outer_contour",
    "circle": "outer_contour",
    "marking": "surface_decoration",
}

_ROLE_WORDS: dict[str, tuple[str, ...]] = {
    "text": ("text", "yazi", "yazı", "letter", "glyph", "number"),
    "logo": ("logo", "amblem", "emblem", "brand"),
    "roof_texture": ("texture", "hatch", "tile", "shingle", "kiremit", "pattern", "roof-tile"),
    "facade_detail": ("facade", "cephe"),
    "ornament": ("ornament", "sus", "floral"),
    "surface_decoration": ("decor", "decorative", "detail", "surface"),
    "engraved_line": ("engrave", "engraved", "etch-line"),
    "construction_guide": ("construction", "dim", "datum"),
    "alignment_guide": ("alignment", "axis", "guide"),
    "pivot_hole": ("pivot",),
    "shaft_hole": ("shaft",),
    "hole": ("hole", "delik", "bore"),
    "slot": ("slot", "kanal", "kerf-slot"),
    "finger_joint": ("finger", "parmak"),
    "tab": ("tab", "nick", "holding"),
    "score_line": ("score", "cizik"),
    "fold_line": ("fold", "crease"),
    "label": ("caption", "callout", "label"),
    "outer_contour": ("outer", "contour", "outline"),
    "inner_cutout": ("inner-cutout", "cutout"),
}

_OP_WORDS: dict[str, tuple[str, ...]] = {
    "ENGRAVE": ("engrave", "etch", "kazima", "kazıma"),
    "SCORE": ("score", "fold", "crease"),
    "GUIDE": ("guide", "construction"),
    "LABEL": ("label", "caption"),
    "CUT": ("cut", "kesim", "through"),
}

PRESENTATION = {
    "CUT": ("#FF0000", "0.18"),
    "ENGRAVE": ("#FFFF00", "0.15"),
    "SCORE": ("#0000FF", "0.12"),
    "GUIDE": ("#00AA00", "0.10"),
    "LABEL": ("#333333", "0.12"),
}

_DRAW = {"path", "line", "polyline", "polygon", "circle", "rect", "ellipse"}
_NS = "http://www.w3.org/2000/svg"


def _local(tag: str) -> str:
    return (tag or "").split("}")[-1].lower()


def _norm(text: str) -> str:
    return (
        str(text or "")
        .casefold()
        .replace("ı", "i")
        .replace("ş", "s")
        .replace("ğ", "g")
        .replace("ç", "c")
        .replace("ö", "o")
        .replace("ü", "u")
    )


def _tokens(*hints: Any) -> set[str]:
    blob = _norm(" ".join(str(h or "") for h in hints))
    return {part for part in "".join(ch if ch.isalnum() else " " for ch in blob).split() if part}


def _hint_blob(*hints: Any) -> str:
    return _norm(" ".join(str(h or "") for h in hints)).replace("_", "-")


def _word_hit(words: tuple[str, ...], tokens: set[str], blob: str) -> bool:
    for word in words:
        needle = _norm(word).replace("_", "-")
        if not needle:
            continue
        if "-" in needle or " " in needle:
            if needle in blob:
                return True
        elif needle in tokens:
            return True
    return False


def _canon_op(raw: Any) -> str:
    value = str(raw or "").strip().upper()
    if value == "ETCH":
        return "ENGRAVE"
    return value


def _canon_origin(raw: Any) -> str:
    value = str(raw or "").strip().upper().replace(" ", "_")
    aliases = {
        "EXPLICIT": "EXPLICIT",
        "DEFAULT": "SEMANTIC_DEFAULT",
        "SEMANTIC_DEFAULT": "SEMANTIC_DEFAULT",
        "INFERRED": "INFERRED",
        "MISSING": "UNKNOWN",
        "UNKNOWN": "UNKNOWN",
    }
    return aliases.get(value, "")


def _canon_role(raw: Any) -> str:
    role = str(raw or "").strip().lower()
    return ROLE_ALIASES.get(role, role)


def default_operation(role: str) -> str:
    return ROLE_DEFAULTS.get(_canon_role(role), "")


def infer_role(*hints: Any) -> str:
    tokens = _tokens(*hints)
    blob = _hint_blob(*hints)
    for role, words in _ROLE_WORDS.items():
        if _word_hit(words, tokens, blob):
            return role
    return ""


def infer_operation_words(*hints: Any) -> str:
    tokens = _tokens(*hints)
    blob = _hint_blob(*hints)
    for op, words in _OP_WORDS.items():
        if _word_hit(words, tokens, blob):
            return op
    return ""


def resolve_operation(
    *,
    semantic_role: str = "",
    operation: Any = None,
    origin: str = "",
) -> dict[str, str]:
    """Canonical resolver. Never assigns CUT unless the role or explicit op requires it."""
    role = _canon_role(semantic_role)
    explicit = _canon_op(operation)
    given_origin = _canon_origin(origin)
    if explicit in EXPORT_OPERATIONS and given_origin == "EXPLICIT":
        return {"semantic_role": role or "custom", "operation": explicit, "operation_origin": "EXPLICIT"}
    if explicit in EXPORT_OPERATIONS and operation not in (None, ""):
        return {
            "semantic_role": role or "custom",
            "operation": explicit,
            "operation_origin": given_origin or "EXPLICIT",
        }
    if explicit == "UNKNOWN":
        return {"semantic_role": role or "custom", "operation": "UNKNOWN", "operation_origin": "UNKNOWN"}
    if explicit and explicit not in OPERATIONS:
        return {"semantic_role": role or "custom", "operation": "UNKNOWN", "operation_origin": "UNKNOWN"}
    mapped = default_operation(role)
    if mapped in EXPORT_OPERATIONS:
        return {"semantic_role": role, "operation": mapped, "operation_origin": "SEMANTIC_DEFAULT"}
    return {"semantic_role": role or "custom", "operation": "UNKNOWN", "operation_origin": "UNKNOWN"}


def _explicit_operation(node: dict[str, Any]) -> str:
    for key in ("operation", "op"):
        if key not in node or node.get(key) in (None, ""):
            continue
        op = _canon_op(node.get(key))
        if op in EXPORT_OPERATIONS:
            return op
        return "UNKNOWN" if op else ""
    return ""


def _apply_intent(node: dict[str, Any], role: str, *, explicit: str = "", inferred_op: str = "") -> dict[str, Any]:
    given_role = _canon_role(node.get("semantic_role") or role)
    if explicit:
        intent = resolve_operation(semantic_role=given_role, operation=explicit, origin="EXPLICIT")
    elif inferred_op in EXPORT_OPERATIONS:
        intent = {
            "semantic_role": given_role or "custom",
            "operation": inferred_op,
            "operation_origin": "INFERRED",
        }
    else:
        intent = resolve_operation(semantic_role=given_role, operation=node.get("operation"))
    node["semantic_role"] = intent["semantic_role"]
    node["operation"] = intent["operation"]
    node["operation_origin"] = intent["operation_origin"]
    node["operation_source"] = intent["operation_origin"].lower()
    node.setdefault("geometry_type", str(node.get("type") or node.get("kind") or "path"))
    return node


def annotate_feature(node: dict[str, Any], role: str) -> dict[str, Any]:
    if not isinstance(node, dict):
        return node
    return _apply_intent(node, role, explicit=_explicit_operation(node))


def _marking_role(mark: dict[str, Any]) -> str:
    given = _canon_role(mark.get("semantic_role"))
    if given:
        return given
    kind = str(mark.get("kind") or mark.get("content") or "").strip().lower()
    inferred = infer_role(kind, mark.get("value"), mark.get("label"), mark.get("icon"))
    if inferred:
        return inferred
    if kind == "text":
        return "text"
    if kind in {"logo", "icon", "image", "bitmap"}:
        return "logo" if kind == "logo" else "ornament"
    if kind in {"path", "line", "lines"}:
        return "engraved_line"
    return "surface_decoration"


def annotate_primitive(part: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(part, dict):
        return part
    kind = str(part.get("type") or part.get("kind") or "").strip().lower()
    label = str(part.get("label") or part.get("name") or "")
    role = _canon_role(part.get("semantic_role")) or TYPE_ROLES.get(kind, "") or infer_role(kind, label)
    if not role:
        role = "custom"
    explicit = _explicit_operation(part)
    word_op = "" if explicit else infer_operation_words(label)
    _apply_intent(part, role, explicit=explicit, inferred_op=word_op)
    part.setdefault("geometry_type", kind or "part")
    part.setdefault("part_id", str(part.get("label") or part.get("id") or kind or "part"))
    for hole in part.get("holes") or []:
        if isinstance(hole, dict):
            hole_role = infer_role(hole.get("label"), hole.get("kind")) or "hole"
            if hole_role not in {"pivot_hole", "shaft_hole", "hole"}:
                hole_role = "hole"
            annotate_feature(hole, hole_role)
    for slot in part.get("slots") or []:
        if isinstance(slot, dict):
            annotate_feature(slot, "slot")
    walls = part.get("walls")
    if isinstance(walls, dict):
        for wall in walls.values():
            if not isinstance(wall, dict):
                continue
            for hole in wall.get("holes") or []:
                if isinstance(hole, dict):
                    hole_role = infer_role(hole.get("label"), hole.get("kind")) or "hole"
                    if hole_role not in {"pivot_hole", "shaft_hole", "hole"}:
                        hole_role = "hole"
                    annotate_feature(hole, hole_role)
            for slot in wall.get("slots") or []:
                if isinstance(slot, dict):
                    annotate_feature(slot, "slot")
            for mark in wall.get("markings") or []:
                if isinstance(mark, dict):
                    annotate_feature(mark, _marking_role(mark))
    for mark in part.get("markings") or []:
        if isinstance(mark, dict):
            annotate_feature(mark, _marking_role(mark))
    return part


def annotate_primitives(parts: list[Any] | None) -> list[Any]:
    out: list[Any] = []
    for i, part in enumerate(parts or [], start=1):
        if isinstance(part, dict):
            part.setdefault("id", part.get("id") or f"P{i:02d}")
            out.append(annotate_primitive(part))
        else:
            out.append(part)
    return out


def feature(
    *,
    semantic_role: str,
    operation: str | None = None,
    geometry_type: str = "path",
    part_id: str = "",
    d: str = "",
    **extra: Any,
) -> dict[str, Any]:
    node = {
        "id": extra.pop("id", "") or "",
        "part_id": part_id,
        "geometry_type": geometry_type,
        "semantic_role": semantic_role,
        "d": d,
        **extra,
    }
    if operation:
        node["operation"] = operation
        return _apply_intent(node, semantic_role, explicit=_canon_op(operation))
    return _apply_intent(node, semantic_role)


def add_outer_contour(**kw: Any) -> dict[str, Any]:
    return feature(semantic_role="outer_contour", geometry_type=kw.pop("geometry_type", "contour"), **kw)


def add_hole(**kw: Any) -> dict[str, Any]:
    return feature(semantic_role="hole", geometry_type=kw.pop("geometry_type", "hole"), **kw)


def add_slot(**kw: Any) -> dict[str, Any]:
    return feature(semantic_role="slot", geometry_type=kw.pop("geometry_type", "slot"), **kw)


def add_cutout(**kw: Any) -> dict[str, Any]:
    role = kw.pop("semantic_role", "ornament")
    op = kw.pop("operation", None)
    return feature(semantic_role=role, operation=op, geometry_type=kw.pop("geometry_type", "cutout"), **kw)


def add_engraving(**kw: Any) -> dict[str, Any]:
    return feature(semantic_role=kw.pop("semantic_role", "surface_decoration"), **kw)


def add_text(**kw: Any) -> dict[str, Any]:
    return feature(semantic_role="text", geometry_type=kw.pop("geometry_type", "text"), **kw)


def add_logo(**kw: Any) -> dict[str, Any]:
    return feature(semantic_role="logo", geometry_type=kw.pop("geometry_type", "logo"), **kw)


def add_texture(**kw: Any) -> dict[str, Any]:
    return feature(semantic_role="roof_texture", geometry_type=kw.pop("geometry_type", "texture"), **kw)


def add_score_line(**kw: Any) -> dict[str, Any]:
    return feature(semantic_role="score_line", geometry_type=kw.pop("geometry_type", "line"), **kw)


def add_guide(**kw: Any) -> dict[str, Any]:
    return feature(semantic_role="construction_guide", geometry_type=kw.pop("geometry_type", "guide"), **kw)


def _parents(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in list(parent)}


def _ancestor_operation_group(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    cur = parents.get(el)
    while cur is not None:
        ident = _canon_op(cur.get("id") or cur.get("data-operation"))
        if ident in EXPORT_OPERATIONS:
            return ident
        label = (cur.get("{http://www.inkscape.org/namespaces/inkscape}label") or "").upper()
        if label == "ETCH":
            return "ENGRAVE"
        if label in EXPORT_OPERATIONS:
            return label
        cur = parents.get(cur)
    return ""


def _stroke_raw(el: ET.Element) -> str:
    raw = (el.get("stroke") or "").lower().replace(" ", "")
    style = el.get("style") or ""
    if "stroke:" in style.lower():
        for part in style.split(";"):
            if part.strip().lower().startswith("stroke:"):
                raw = part.split(":", 1)[1].strip().lower().replace(" ", "")
                break
    return raw


def boxes_layer_intent(el: ET.Element) -> tuple[str, str]:
    """Boxes.py Color layers only, before LaserCAD remap. Not presentation color."""
    raw = _stroke_raw(el)
    if "00ff00" in raw or "rgb(0,255,0)" in raw:
        return "ENGRAVE", "surface_decoration"
    if "00ffff" in raw or "rgb(0,255,255)" in raw:
        return "ENGRAVE", "surface_decoration"
    if "ffff00" in raw or "rgb(255,255,0)" in raw:
        return "SCORE", "score_line"
    if "0000ff" in raw or "rgb(0,0,255)" in raw:
        return "CUT", "inner_cutout"
    if raw in {"#000000", "#000", "black"} or "rgb(0,0,0)" in raw:
        return "CUT", "outer_contour"
    if "ff0000" in raw or "rgb(255,0,0)" in raw:
        return "GUIDE", "construction_guide"
    return "", ""


def _svg_has_boxes_layers(root: ET.Element) -> bool:
    for el in root.iter():
        if _local(el.tag) not in _DRAW:
            continue
        raw = _stroke_raw(el)
        if "rgb(0,255,0)" in raw or "rgb(0,0,255)" in raw or "rgb(0,0,0)" in raw:
            return True
        if raw in {"#00ff00", "#0000ff", "#00ffff"}:
            return True
    return False


def classify_element(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> tuple[str, str, str]:
    """Resolve intent. Never invent CUT. Color is not used after LaserCAD remap."""
    stamped = _canon_op(el.get("data-operation"))
    origin = _canon_origin(el.get("data-operation-origin") or el.get("data-operation-source"))
    role = _canon_role(el.get("data-semantic-role") or el.get("data-role"))
    hints = (
        el.get("id"),
        el.get("class"),
        el.get("data-role"),
        el.get("{http://www.inkscape.org/namespaces/inkscape}label"),
    )
    if not role:
        role = infer_role(*hints)
    if el.get("data-holding-nicks") or el.get("data-holding-bridges"):
        if stamped in EXPORT_OPERATIONS and stamped != "CUT" and origin == "EXPLICIT":
            return stamped, role or "tab", "EXPLICIT"
        return "CUT", role or "tab", "SEMANTIC_DEFAULT"
    if stamped in EXPORT_OPERATIONS and origin == "EXPLICIT":
        return stamped, role or "custom", "EXPLICIT"
    if stamped in EXPORT_OPERATIONS:
        return stamped, role or _canon_role(el.get("data-semantic-role")) or "custom", origin or "INFERRED"
    if stamped == "UNKNOWN":
        return "UNKNOWN", role or "custom", "UNKNOWN"
    if role:
        intent = resolve_operation(semantic_role=role)
        return intent["operation"], intent["semantic_role"], intent["operation_origin"]
    word_op = infer_operation_words(*hints)
    if word_op in EXPORT_OPERATIONS:
        return word_op, role or "custom", "INFERRED"
    group = _ancestor_operation_group(el, parents)
    if group:
        return group, role or "custom", "INFERRED"
    return "UNKNOWN", role or "custom", "UNKNOWN"


def classify_element_pre_remap(el: ET.Element, parents: dict[ET.Element, ET.Element], *, allow_boxes_layer: bool) -> tuple[str, str, str]:
    op, role, origin = classify_element(el, parents)
    if op != "UNKNOWN":
        return op, role, origin
    if allow_boxes_layer:
        layer_op, layer_role = boxes_layer_intent(el)
        if layer_op in EXPORT_OPERATIONS:
            return layer_op, role if role and role != "custom" else layer_role, "INFERRED"
    return "UNKNOWN", role or "custom", "UNKNOWN"


def _ensure_groups(root: ET.Element) -> dict[str, ET.Element]:
    groups: dict[str, ET.Element] = {}
    for child in list(root):
        if _local(child.tag) != "g":
            continue
        ident = _canon_op(child.get("id") or child.get("data-operation"))
        if ident in EXPORT_OPERATIONS:
            groups[ident] = child
            child.set("id", ident)
            child.set("data-operation", ident)
    tag = f"{{{_NS}}}g" if root.tag.startswith("{") else "g"
    for op in EXPORT_OPERATIONS:
        if op in groups:
            continue
        g = ET.SubElement(root, tag)
        g.set("id", op)
        g.set("data-operation", op)
        groups[op] = g
    return groups


def _stamp_attrs(el: ET.Element, op: str, role: str, origin: str) -> None:
    el.set("data-operation", op)
    if role:
        el.set("data-semantic-role", role)
    el.set("data-operation-origin", origin)
    el.set("data-operation-source", origin.lower())


def stamp_source_operations(svg_bytes: bytes) -> bytes:
    """Pre-export classifier. Boxes.py layers only while still in Boxes palette."""
    if not svg_bytes:
        return svg_bytes
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return svg_bytes
    parents = _parents(root)
    allow_boxes = _svg_has_boxes_layers(root)
    changed = False
    for el in root.iter():
        if _local(el.tag) not in _DRAW:
            continue
        if _canon_op(el.get("data-operation")) in OPERATIONS and _canon_origin(
            el.get("data-operation-origin") or el.get("data-operation-source")
        ):
            continue
        op, role, origin = classify_element_pre_remap(el, parents, allow_boxes_layer=allow_boxes)
        _stamp_attrs(el, op, role, origin)
        changed = True
    if not changed:
        return svg_bytes
    ET.register_namespace("", _NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _panel_context(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> tuple[str, str]:
    cur: ET.Element | None = el
    while cur is not None:
        panel = cur.get("data-panel") or ""
        if panel and _canon_op(cur.get("id") or cur.get("data-operation")) not in EXPORT_OPERATIONS:
            return panel, cur.get("data-sheet") or ""
        cur = parents.get(cur)
    return "", ""


def _panel_bucket(dest: ET.Element, panel: str, sheet: str, cache: dict[tuple[str, str, str], ET.Element]) -> ET.Element:
    if not panel:
        return dest
    key = (dest.get("id") or "", panel, sheet)
    hit = cache.get(key)
    if hit is not None:
        return hit
    child = ET.SubElement(dest, dest.tag)
    child.set("data-panel", panel)
    if sheet:
        child.set("data-sheet", sheet)
    cache[key] = child
    return child


def apply_manufacturing_svg(svg_bytes: bytes, primitives: list[Any] | None = None) -> bytes:
    """Group already-classified drawables. Does not invent CUT or repair UNKNOWN."""
    del primitives
    if not svg_bytes:
        return svg_bytes
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return svg_bytes
    parents = _parents(root)
    groups = _ensure_groups(root)
    parents.update({group: root for group in groups.values()})
    def matrix(node):
        import numpy as np
        from svgpathtools.parser import parse_transform
        chain = []
        while node is not None:
            chain.append(node)
            node = parents.get(node)
        result = np.eye(3)
        for ancestor in reversed(chain):
            result = result @ parse_transform(ancestor.get("transform") or "")
        return result
    buckets: dict[tuple[str, str, str], ET.Element] = {}
    for el in list(root.iter()):
        if _local(el.tag) not in _DRAW:
            continue
        op, role, origin = classify_element(el, parents)
        if op not in OPERATIONS:
            op, role, origin = "UNKNOWN", role or "custom", "UNKNOWN"
        _stamp_attrs(el, op, role, origin)
        if op not in EXPORT_OPERATIONS:
            continue
        color, width = PRESENTATION[op]
        el.set("stroke", color)
        if not el.get("stroke-width"):
            el.set("stroke-width", width)
        el.set("fill", el.get("fill") or "none")
        parent = parents.get(el)
        dest = _panel_bucket(groups[op], *_panel_context(el, parents), buckets)
        if parent is dest or parent is None:
            continue
        if dest not in parents:
            parents[dest] = groups[op]
        import numpy as np
        relative = np.linalg.inv(matrix(dest)) @ matrix(el)
        el.set("transform", "matrix(" + " ".join(format(float(v), ".15g") for v in (
            relative[0, 0], relative[1, 0], relative[0, 1], relative[1, 1], relative[0, 2], relative[1, 2]
        )) + ")")
        try:
            parent.remove(el)
        except ValueError:
            continue
        dest.append(el)
        parents[el] = dest
    ET.register_namespace("", _NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def iter_drawables(svg_bytes: bytes) -> list[dict[str, Any]]:
    if not svg_bytes:
        return []
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return []
    rows: list[dict[str, Any]] = []
    for el in root.iter():
        if _local(el.tag) not in _DRAW:
            continue
        rows.append(
            {
                "operation": _canon_op(el.get("data-operation")),
                "semantic_role": _canon_role(el.get("data-semantic-role")),
                "origin": _canon_origin(el.get("data-operation-origin") or el.get("data-operation-source"))
                or "UNKNOWN",
                "source": str(el.get("data-operation-source") or ""),
                "nicked": bool(el.get("data-holding-nicks") or el.get("data-holding-bridges")),
                "id": el.get("id") or "",
            }
        )
    return rows


def debug_report(svg_bytes: bytes | None = None, primitives: list[Any] | None = None) -> dict[str, Any]:
    rows = list(iter_drawables(svg_bytes or b""))
    for part in primitives or []:
        if not isinstance(part, dict):
            continue
        rows.append(
            {
                "operation": _canon_op(part.get("operation")),
                "semantic_role": _canon_role(part.get("semantic_role")),
                "origin": _canon_origin(part.get("operation_origin") or part.get("operation_source")) or "UNKNOWN",
                "id": str(part.get("id") or part.get("label") or part.get("type") or "part"),
            }
        )
        for nest in list(part.get("holes") or []) + list(part.get("slots") or []) + list(part.get("markings") or []):
            if isinstance(nest, dict):
                rows.append(
                    {
                        "operation": _canon_op(nest.get("operation")),
                        "semantic_role": _canon_role(nest.get("semantic_role")),
                        "origin": _canon_origin(nest.get("operation_origin") or nest.get("operation_source"))
                        or "UNKNOWN",
                        "id": str(nest.get("kind") or nest.get("semantic_role") or "feature"),
                    }
                )
    by_role = Counter(r.get("semantic_role") or "missing" for r in rows)
    by_op = Counter(r.get("operation") or "UNKNOWN" for r in rows)
    by_origin = Counter(r.get("origin") or "UNKNOWN" for r in rows)
    unknown = [r for r in rows if r.get("operation") not in EXPORT_OPERATIONS]
    explicit_cut = [
        r for r in rows if r.get("operation") == "CUT" and r.get("origin") == "EXPLICIT" and r.get("semantic_role") in SURFACE_ROLES
    ]
    return {
        "total_primitives": len(rows),
        "by_semantic_role": dict(by_role),
        "by_operation": {op: by_op.get(op, 0) for op in OPERATIONS},
        "by_operation_origin": {origin: by_origin.get(origin, 0) for origin in ORIGINS},
        "unknown_items": unknown,
        "explicit_cut_overrides": explicit_cut,
    }


def validate_primitives(parts: list[Any] | None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for part in parts or []:
        if isinstance(part, dict):
            checks.extend(_validate_node(part, path=str(part.get("label") or part.get("type") or "part")))
            for nest in list(part.get("holes") or []) + list(part.get("slots") or []) + list(part.get("markings") or []):
                if isinstance(nest, dict):
                    checks.extend(_validate_node(nest, path=str(nest.get("kind") or nest.get("semantic_role") or "feature")))
            walls = part.get("walls")
            if isinstance(walls, dict):
                for wall in walls.values():
                    if not isinstance(wall, dict):
                        continue
                    for nest in list(wall.get("holes") or []) + list(wall.get("slots") or []) + list(
                        wall.get("markings") or []
                    ):
                        if isinstance(nest, dict):
                            checks.extend(
                                _validate_node(
                                    nest, path=str(nest.get("semantic_role") or nest.get("kind") or "wall-feature")
                                )
                            )
    return _pack(checks)


def _validate_node(node: dict[str, Any], *, path: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    role = _canon_role(node.get("semantic_role"))
    op = _canon_op(node.get("operation"))
    origin = _canon_origin(node.get("operation_origin") or node.get("operation_source"))
    explicit = origin == "EXPLICIT"
    if not role:
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: missing semantic_role", "critical": True})
    if not op:
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: missing operation", "critical": True})
        return checks
    if op == "UNKNOWN":
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: operation UNKNOWN blocks export", "critical": True})
        return checks
    if op not in EXPORT_OPERATIONS:
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: malformed operation {op}", "critical": True})
        return checks
    if role in {"text", "label"} and op == "CUT":
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: {role} must remain ENGRAVE and cannot be CUT", "critical": True})
    if role in SURFACE_ROLES - {"text", "label"} and op == "CUT":
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: {role} must remain ENGRAVE and cannot be CUT", "critical": True})
    if role in GUIDE_ROLES and op == "CUT":
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: guide marked CUT", "critical": True})
    if role in CUT_ROLES and op != "CUT":
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: {role} must be CUT", "critical": True})
    if not checks:
        checks.append({"status": PASS, "note": f"{path}: {role or 'part'} → {op}", "critical": False})
    return checks


def _distribution_warnings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if not rows:
        return checks
    ops = [r.get("operation") for r in rows]
    cut_n = sum(1 for op in ops if op == "CUT")
    roles = {str(r.get("semantic_role") or "") for r in rows}
    if roles & SURFACE_ROLES and cut_n / len(rows) > 0.9:
        checks.append(
            {
                "status": WARNING,
                "note": "more than 90% of primitives resolve to CUT in a design with text/decoration/texture",
                "critical": False,
            }
        )
    if len(set(ops)) == 1 and len(rows) > 8 and "CUT" in ops:
        checks.append(
            {
                "status": WARNING,
                "note": "operation distribution is suspiciously uniform (all CUT)",
                "critical": False,
            }
        )
    inferred_cut_decor = [
        r
        for r in rows
        if r.get("operation") == "CUT" and r.get("origin") == "INFERRED" and r.get("semantic_role") in SURFACE_ROLES
    ]
    if inferred_cut_decor:
        checks.append(
            {
                "status": WARNING,
                "note": f"{len(inferred_cut_decor)} decorative-looking path(s) marked CUT through inference",
                "critical": False,
            }
        )
    return checks


def validate_svg_operations(svg_bytes: bytes | None, primitives: list[Any] | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.extend(validate_primitives(primitives).get("checks") or [])
    rows = iter_drawables(svg_bytes or b"")
    if svg_bytes and not rows:
        checks.append({"status": CRITICAL_FAIL, "note": "SVG has no drawable geometry with an operation", "critical": True})
    cut_n = 0
    nick_n = 0
    unknown_n = 0
    for i, row in enumerate(rows, start=1):
        op = _canon_op(row.get("operation"))
        role = _canon_role(row.get("semantic_role"))
        origin = _canon_origin(row.get("origin") or row.get("source"))
        path = f"svg[{i}]"
        if row.get("nicked"):
            nick_n += 1
            if op != "CUT":
                checks.append({"status": CRITICAL_FAIL, "note": f"{path}: holding nick must remain CUT", "critical": True})
            else:
                cut_n += 1
            continue
        if not role:
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: missing semantic_role", "critical": True})
        if not op:
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: missing operation", "critical": True})
            unknown_n += 1
            continue
        if op == "UNKNOWN":
            unknown_n += 1
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: operation UNKNOWN blocks export", "critical": True})
            continue
        if op not in EXPORT_OPERATIONS:
            unknown_n += 1
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: malformed operation {op}", "critical": True})
            continue
        if op == "CUT":
            cut_n += 1
        checks.extend(_validate_node({"semantic_role": role, "operation": op, "operation_origin": origin}, path=path))
    checks.extend(_distribution_warnings(rows))
    if rows and cut_n < 1 and unknown_n == 0:
        checks.append({"status": CRITICAL_FAIL, "note": "no CUT operation on the sheet", "critical": True})
    groups = _group_ids(svg_bytes or b"")
    missing_groups = [op for op in EXPORT_OPERATIONS if op not in groups]
    if missing_groups and rows and unknown_n == 0:
        checks.append({"status": CRITICAL_FAIL, "note": f"SVG missing operation groups: {', '.join(missing_groups)}", "critical": True})
    report = debug_report(svg_bytes, primitives)
    intent = {
        "semantic_roles_complete": not any("missing semantic_role" in str(c.get("note")) for c in checks),
        "operations_resolved": unknown_n == 0,
        "unknown_operations_zero": unknown_n == 0,
        "unknown_operations": unknown_n,
        "suspicious_defaulting_checked": True,
        "explicit_overrides_recorded": True,
        "exportable": unknown_n == 0 and not any(c.get("critical") and c.get("status") == CRITICAL_FAIL for c in checks),
    }
    return _pack(
        checks,
        extra={
            "cut_paths": cut_n,
            "nicked": nick_n,
            "drawables": len(rows),
            "groups": groups,
            "intent": intent,
            "debug": report,
        },
    )


def _group_ids(svg_bytes: bytes) -> list[str]:
    if not svg_bytes:
        return []
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return []
    found: list[str] = []
    for el in root.iter():
        if _local(el.tag) != "g":
            continue
        ident = _canon_op(el.get("id") or el.get("data-operation"))
        if ident in EXPORT_OPERATIONS and ident not in found:
            found.append(ident)
    return found


def _pack(checks: list[dict[str, Any]], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    critical = [c for c in checks if c.get("critical") and c.get("status") == CRITICAL_FAIL]
    warnings = [c for c in checks if c.get("status") == WARNING]
    payload = {
        "ok": not critical,
        "critical_fail": bool(critical),
        "checks": checks,
        "fail": [c["note"] for c in critical if c.get("note")],
        "warnings": [c["note"] for c in warnings if c.get("note")],
    }
    if extra:
        payload.update(extra)
    return payload


def finish_manufacturing_svg(svg_bytes: bytes, primitives: list[Any] | None = None) -> tuple[bytes, dict[str, Any]]:
    annotated = annotate_primitives(list(primitives or []))
    classified = stamp_source_operations(svg_bytes)
    stamped = apply_manufacturing_svg(classified, annotated)
    report = validate_svg_operations(stamped, annotated)
    if not (report.get("intent") or {}).get("exportable", report.get("ok")):
        report["exportable"] = False
        report["ok"] = False
        report["critical_fail"] = True
        return stamped, report
    report["exportable"] = True
    return stamped, report


def element_is_cut(el: ET.Element, parents: dict[ET.Element, ET.Element] | None = None) -> bool:
    op = _canon_op(el.get("data-operation"))
    if op:
        return op == "CUT"
    if parents:
        return _ancestor_operation_group(el, parents) == "CUT"
    return False
