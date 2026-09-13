"""Manufacturing operations: intent is explicit. Color is presentation only."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

OPERATIONS = ("CUT", "ENGRAVE", "SCORE", "GUIDE", "LABEL")
CRITICAL_FAIL = "FAIL"
WARNING = "WARNING"
PASS = "PASS"

ROLE_DEFAULTS: dict[str, str] = {
    "outer_contour": "CUT",
    "hole": "CUT",
    "slot": "CUT",
    "finger_joint": "CUT",
    "tab": "CUT",
    "text": "ENGRAVE",
    "logo": "ENGRAVE",
    "texture": "ENGRAVE",
    "decorative_detail": "ENGRAVE",
    "construction_guide": "GUIDE",
    "score": "SCORE",
    "label": "LABEL",
}

TYPE_ROLES: dict[str, str] = {
    "text": "text",
    "number": "text",
    "pips": "decorative_detail",
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
    "marking": "decorative_detail",
}

_ROLE_WORDS: dict[str, tuple[str, ...]] = {
    "text": ("text", "yazi", "yazı", "letter", "glyph", "number", "label-text"),
    "logo": ("logo", "amblem", "emblem", "brand"),
    "texture": ("texture", "hatch", "tile", "shingle", "kiremit", "pattern", "roof-tile"),
    "decorative_detail": ("decor", "decorative", "facade", "cephe", "ornament", "sus", "detail"),
    "construction_guide": ("guide", "construction", "dim", "datum", "axis"),
    "hole": ("hole", "delik", "bore", "pivot"),
    "slot": ("slot", "kanal", "kerf-slot"),
    "finger_joint": ("finger", "parmak"),
    "tab": ("tab", "nick", "holding"),
    "score": ("score", "fold", "crease", "cizik"),
    "label": ("caption", "callout"),
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
    "ENGRAVE": ("#000000", "0.15"),
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


def default_operation(role: str) -> str:
    return ROLE_DEFAULTS.get(str(role or "").strip().lower(), "")


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


def _explicit_operation(node: dict[str, Any]) -> str:
    for key in ("operation", "op"):
        op = _canon_op(node.get(key))
        if op in OPERATIONS:
            return op
    return ""


def annotate_feature(node: dict[str, Any], role: str) -> dict[str, Any]:
    if not isinstance(node, dict):
        return node
    given_role = str(node.get("semantic_role") or "").strip().lower()
    role = given_role or role
    explicit = _explicit_operation(node)
    if explicit:
        node["operation"] = explicit
        node["operation_source"] = "explicit"
    else:
        node["operation"] = default_operation(role) or "CUT"
        node["operation_source"] = "default"
    node["semantic_role"] = role
    return node


def annotate_primitive(part: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(part, dict):
        return part
    kind = str(part.get("type") or part.get("kind") or "").strip().lower()
    label = str(part.get("label") or part.get("name") or "")
    role = str(part.get("semantic_role") or "").strip().lower()
    role = role or TYPE_ROLES.get(kind, "") or infer_role(kind, label)
    if not role:
        role = "decorative_detail" if kind in {"marking"} else "outer_contour"
    explicit = _explicit_operation(part)
    word_op = infer_operation_words(label, part.get("operation"))
    if explicit:
        part["operation"] = explicit
        part["operation_source"] = "explicit"
    elif word_op:
        part["operation"] = word_op
        part["operation_source"] = "default"
    else:
        part["operation"] = default_operation(role) or "CUT"
        part["operation_source"] = "default"
    part["semantic_role"] = role
    for hole in part.get("holes") or []:
        if isinstance(hole, dict):
            annotate_feature(hole, "hole")
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
                    annotate_feature(hole, "hole")
            for slot in wall.get("slots") or []:
                if isinstance(slot, dict):
                    annotate_feature(slot, "slot")
            for mark in wall.get("markings") or []:
                if isinstance(mark, dict):
                    mrole = infer_role(mark.get("kind"), mark.get("value"), mark.get("label")) or (
                        "text" if str(mark.get("kind") or "") == "text" else "decorative_detail"
                    )
                    annotate_feature(mark, mrole)
    for mark in part.get("markings") or []:
        if isinstance(mark, dict):
            mrole = infer_role(mark.get("kind"), mark.get("value"), mark.get("label")) or (
                "text" if str(mark.get("kind") or "") == "text" else "decorative_detail"
            )
            annotate_feature(mark, mrole)
    return part


def annotate_primitives(parts: list[Any] | None) -> list[Any]:
    out: list[Any] = []
    for part in parts or []:
        out.append(annotate_primitive(part) if isinstance(part, dict) else part)
    return out


def _parents(root: ET.Element) -> dict[ET.Element, ET.Element]:
    return {child: parent for parent in root.iter() for child in list(parent)}


def _ancestor_hint(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> str:
    cur: ET.Element | None = el
    while cur is not None:
        for key in ("data-operation", "id"):
            op = _canon_op(cur.get(key))
            if op in OPERATIONS:
                return op
        label = (cur.get("{http://www.inkscape.org/namespaces/inkscape}label") or "").upper()
        if label in OPERATIONS or label == "ETCH":
            return "ENGRAVE" if label == "ETCH" else label
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


def _role_for_op(op: str) -> str:
    return {
        "CUT": "outer_contour",
        "ENGRAVE": "decorative_detail",
        "SCORE": "score",
        "GUIDE": "construction_guide",
        "LABEL": "label",
    }.get(op, "outer_contour")


def boxes_color_hint(el: ET.Element) -> str:
    """Boxes.py palette before LaserCAD remap. Color is a hint, not the authority."""
    raw = _stroke_raw(el)
    if "00ff00" in raw or "rgb(0,255,0)" in raw:
        return "ENGRAVE"
    if "00ffff" in raw or "rgb(0,255,255)" in raw:
        return "ENGRAVE"
    if "ffff00" in raw or "rgb(255,255,0)" in raw:
        return "SCORE"
    if "0000ff" in raw or "rgb(0,0,255)" in raw:
        return "CUT"
    if raw in {"#000000", "#000", "black", "rgb(0,0,0)"} or "rgb(0,0,0)" in raw:
        return "CUT"
    if "ff0000" in raw or "rgb(255,0,0)" in raw:
        return "GUIDE"
    return ""


def _color_hint(el: ET.Element) -> str:
    """LaserCAD presentation palette. Never the only classification signal."""
    raw = _stroke_raw(el)
    if "00ff00" in raw or "00aa00" in raw or "rgb(0,255,0)" in raw:
        return "GUIDE"
    if "0000ff" in raw or "rgb(0,0,255)" in raw:
        return "SCORE"
    if "ff0000" in raw or "rgb(255,0,0)" in raw or "e10600" in raw:
        return "CUT"
    if raw in {"#000000", "#000", "black", "rgb(0,0,0)", "#333333"}:
        return "ENGRAVE"
    return ""


def classify_element(
    el: ET.Element,
    parents: dict[ET.Element, ET.Element],
    *,
    palette: str = "presentation",
) -> tuple[str, str, str]:
    """Return (operation, role, source). Source explicit|default|inferred|missing."""
    stamped = _canon_op(el.get("data-operation"))
    source = str(el.get("data-operation-source") or "")
    role = str(el.get("data-semantic-role") or "").strip().lower()
    hints = (
        el.get("id"),
        el.get("class"),
        el.get("data-role"),
        el.get("{http://www.inkscape.org/namespaces/inkscape}label"),
    )
    if not role:
        role = infer_role(*hints)
    if el.get("data-holding-nicks") or el.get("data-holding-bridges"):
        role = role or "tab"
        if stamped in OPERATIONS and stamped != "CUT" and source == "explicit":
            return stamped, role, "explicit"
        return "CUT", role or "tab", "default"
    if stamped in OPERATIONS:
        if source == "explicit":
            return stamped, role or _role_for_op(stamped), "explicit"
        return stamped, role or _role_for_op(stamped), source or "inferred"
    if role and default_operation(role):
        return default_operation(role), role, "default"
    word_op = infer_operation_words(*hints)
    if word_op:
        return word_op, role or infer_role(*hints) or "decorative_detail", "inferred"
    group = _ancestor_hint(el, parents)
    if group:
        return group, role or _role_for_op(group), "inferred"
    color = boxes_color_hint(el) if palette == "boxes" else _color_hint(el)
    if color:
        return color, role or _role_for_op(color), "inferred"
    return "", role, "missing"


def _ensure_groups(root: ET.Element) -> dict[str, ET.Element]:
    groups: dict[str, ET.Element] = {}
    for child in list(root):
        if _local(child.tag) != "g":
            continue
        ident = _canon_op(child.get("id") or child.get("data-operation"))
        if ident in OPERATIONS:
            groups[ident] = child
            child.set("id", ident)
            child.set("data-operation", ident)
    tag = f"{{{_NS}}}g" if root.tag.startswith("{") else "g"
    for op in OPERATIONS:
        if op in groups:
            continue
        g = ET.SubElement(root, tag)
        g.set("id", op)
        g.set("data-operation", op)
        groups[op] = g
    return groups


def stamp_source_operations(svg_bytes: bytes) -> bytes:
    """Stamp operation from Boxes.py color, group, and keywords. Do not regroup or recolor."""
    if not svg_bytes:
        return svg_bytes
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return svg_bytes
    parents = _parents(root)
    palette = "presentation" if _svg_has_operation_groups(root) else "boxes"
    changed = False
    for el in root.iter():
        if _local(el.tag) not in _DRAW:
            continue
        if _canon_op(el.get("data-operation")) in OPERATIONS:
            continue
        op, role, source = classify_element(el, parents, palette=palette)
        if op not in OPERATIONS:
            continue
        el.set("data-operation", op)
        if role:
            el.set("data-semantic-role", role)
        el.set("data-operation-source", source)
        changed = True
    if not changed:
        return svg_bytes
    ET.register_namespace("", _NS)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _panel_context(el: ET.Element, parents: dict[ET.Element, ET.Element]) -> tuple[str, str]:
    cur: ET.Element | None = el
    while cur is not None:
        panel = cur.get("data-panel") or ""
        if panel and _canon_op(cur.get("id") or cur.get("data-operation")) not in OPERATIONS:
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
    tag = dest.tag
    child = ET.SubElement(dest, tag)
    child.set("data-panel", panel)
    if sheet:
        child.set("data-sheet", sheet)
    cache[key] = child
    return child


def apply_manufacturing_svg(svg_bytes: bytes, primitives: list[Any] | None = None) -> bytes:
    """Stamp operation/role on every drawable and group by operation. Color is presentation."""
    del primitives  # reserved: future path-to-primitive matching
    if not svg_bytes:
        return svg_bytes
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return svg_bytes
    parents = _parents(root)
    groups = _ensure_groups(root)
    buckets: dict[tuple[str, str, str], ET.Element] = {}
    for el in list(root.iter()):
        if _local(el.tag) not in _DRAW:
            continue
        op, role, source = classify_element(el, parents)
        if op not in OPERATIONS:
            op, role, source = "CUT", role or "outer_contour", "inferred"
        el.set("data-operation", op)
        if role:
            el.set("data-semantic-role", role)
        el.set("data-operation-source", source)
        color, width = PRESENTATION[op]
        el.set("stroke", color)
        if not el.get("stroke-width"):
            el.set("stroke-width", width)
        el.set("fill", el.get("fill") or "none")
        parent = parents.get(el)
        dest = _panel_bucket(groups[op], *_panel_context(el, parents), buckets)
        if parent is dest:
            continue
        if parent is not None:
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
    parents = _parents(root)
    rows: list[dict[str, Any]] = []
    for el in root.iter():
        if _local(el.tag) not in _DRAW:
            continue
        op = _canon_op(el.get("data-operation"))
        rows.append(
            {
                "operation": op,
                "semantic_role": str(el.get("data-semantic-role") or ""),
                "source": str(el.get("data-operation-source") or ""),
                "nicked": bool(el.get("data-holding-nicks") or el.get("data-holding-bridges")),
            }
        )
    return rows


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
                    for nest in list(wall.get("holes") or []) + list(wall.get("slots") or []) + list(wall.get("markings") or []):
                        if isinstance(nest, dict):
                            checks.extend(
                                _validate_node(nest, path=str(nest.get("semantic_role") or nest.get("kind") or "wall-feature"))
                            )
    return _pack(checks)


def _validate_node(node: dict[str, Any], *, path: str) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    role = str(node.get("semantic_role") or "").strip().lower()
    op = _canon_op(node.get("operation"))
    source = str(node.get("operation_source") or "")
    explicit = source == "explicit"
    if not op:
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: missing operation", "critical": True})
        return checks
    if op not in OPERATIONS:
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: unknown operation {op}", "critical": True})
        return checks
    if role == "text" and op == "CUT":
        if explicit:
            checks.append({"status": WARNING, "note": f"{path}: text CUT is explicit and auditable", "critical": False})
        else:
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: text marked CUT without explicit operation", "critical": True})
    if role in {"texture", "decorative_detail"} and op == "CUT":
        checks.append({"status": WARNING, "note": f"{path}: decorative/texture marked CUT", "critical": False})
    if role == "construction_guide" and op == "CUT":
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: guide marked CUT", "critical": True})
    if role == "outer_contour" and op != "CUT":
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: outer contour must be CUT", "critical": True})
    if role in {"slot", "hole"} and op != "CUT":
        checks.append({"status": CRITICAL_FAIL, "note": f"{path}: {role} must be CUT", "critical": True})
    if not checks:
        checks.append({"status": PASS, "note": f"{path}: {role or 'part'} → {op}", "critical": False})
    return checks


def validate_svg_operations(svg_bytes: bytes | None, primitives: list[Any] | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.extend(validate_primitives(primitives).get("checks") or [])
    rows = iter_drawables(svg_bytes or b"")
    if svg_bytes and not rows:
        checks.append({"status": CRITICAL_FAIL, "note": "SVG has no drawable geometry with an operation", "critical": True})
    cut_n = 0
    nick_n = 0
    for i, row in enumerate(rows, start=1):
        op = _canon_op(row.get("operation"))
        role = str(row.get("semantic_role") or "").strip().lower()
        source = str(row.get("source") or "")
        path = f"svg[{i}]"
        if row.get("nicked"):
            nick_n += 1
            if op != "CUT":
                checks.append({"status": CRITICAL_FAIL, "note": f"{path}: holding nick must remain CUT", "critical": True})
            else:
                cut_n += 1
            continue
        if not op:
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: missing operation", "critical": True})
            continue
        if op not in OPERATIONS:
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: unknown operation {op}", "critical": True})
            continue
        if op == "CUT":
            cut_n += 1
        if role == "text" and op == "CUT" and source != "explicit":
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: text marked CUT without explicit operation", "critical": True})
        elif role == "text" and op == "CUT":
            checks.append({"status": WARNING, "note": f"{path}: text CUT is explicit and auditable", "critical": False})
        if role in {"texture", "decorative_detail"} and op == "CUT":
            checks.append({"status": WARNING, "note": f"{path}: decorative/texture marked CUT", "critical": False})
        if role == "construction_guide" and op == "CUT":
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: guide marked CUT", "critical": True})
        if role == "outer_contour" and op != "CUT":
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: outer contour must be CUT", "critical": True})
        if role in {"slot", "hole"} and op != "CUT":
            checks.append({"status": CRITICAL_FAIL, "note": f"{path}: {role} must be CUT", "critical": True})
    if rows and cut_n < 1:
        checks.append({"status": CRITICAL_FAIL, "note": "no CUT operation on the sheet", "critical": True})
    groups = _group_ids(svg_bytes or b"")
    missing_groups = [op for op in OPERATIONS if op not in groups]
    if missing_groups and rows:
        checks.append({"status": CRITICAL_FAIL, "note": f"SVG missing operation groups: {', '.join(missing_groups)}", "critical": True})
    return _pack(checks, extra={"cut_paths": cut_n, "nicked": nick_n, "drawables": len(rows), "groups": groups})


def _svg_has_operation_groups(root: ET.Element) -> bool:
    for el in root.iter():
        if _local(el.tag) != "g":
            continue
        if _canon_op(el.get("id") or el.get("data-operation")) in OPERATIONS:
            return True
    return False


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
        if ident in OPERATIONS and ident not in found:
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
    stamped = apply_manufacturing_svg(svg_bytes, annotated)
    report = validate_svg_operations(stamped, annotated)
    return stamped, report


def element_is_cut(el: ET.Element, parents: dict[ET.Element, ET.Element] | None = None) -> bool:
    op = _canon_op(el.get("data-operation"))
    if op:
        return op == "CUT"
    if parents:
        hint = _ancestor_hint(el, parents)
        if hint:
            return hint == "CUT"
    return _color_hint(el) == "CUT" or not _color_hint(el)
