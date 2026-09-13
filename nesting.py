"""Translation-only nesting of Boxes.py part groups onto the 1500×3000 bed."""

from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

from rectpack import newPacker
from svgpathtools import parse_path

from boxes_adapter import PAYAS_DEFAULTS

NS = "{http://www.w3.org/2000/svg}"


def _groups(root: ET.Element) -> list[ET.Element]:
    found = [g for g in root.findall(f"{NS}g") if any(p.tag.split("}")[-1].lower() == "path" and p.get("d") for p in g.iter())]
    if found:
        return found
    if any(el.tag.split("}")[-1].lower() == "path" and el.get("d") for el in root.iter()):
        return [root]
    return []


def _bbox(group: ET.Element) -> tuple[float, float, float, float] | None:
    xmin = ymin = None
    xmax = ymax = None
    for el in group.iter():
        if el.tag.split("}")[-1].lower() != "path":
            continue
        d = el.get("d") or ""
        if not d.strip():
            continue
        try:
            path = parse_path(d)
            x0, x1, y0, y1 = path.bbox()
        except Exception:
            continue
        xmin = x0 if xmin is None else min(xmin, x0)
        xmax = x1 if xmax is None else max(xmax, x1)
        ymin = y0 if ymin is None else min(ymin, y0)
        ymax = y1 if ymax is None else max(ymax, y1)
    if xmin is None:
        return None
    return float(xmin), float(ymin), float(xmax), float(ymax)


_OP_LAYERS = {"CUT", "ENGRAVE", "SCORE", "GUIDE", "LABEL", "ETCH"}


def _is_operation_layer(group: ET.Element) -> bool:
    ident = (group.get("id") or group.get("data-operation") or "").strip().upper()
    return ident in _OP_LAYERS


def _inspect_parts(root: ET.Element) -> list[tuple[str, tuple[float, float, float, float]]]:
    """One bbox per data-panel. Operation layers are not parts."""
    merged: dict[str, tuple[float, float, float, float]] = {}
    anonymous: list[tuple[str, tuple[float, float, float, float]]] = []
    for group in root.iter():
        if group.tag.split("}")[-1].lower() != "g":
            continue
        if _is_operation_layer(group):
            continue
        panel = group.get("data-panel")
        if not panel:
            continue
        box = _bbox(group)
        if not box:
            continue
        if panel in merged:
            a = merged[panel]
            merged[panel] = (min(a[0], box[0]), min(a[1], box[1]), max(a[2], box[2]), max(a[3], box[3]))
        else:
            merged[panel] = box
    if merged:
        return [(name, box) for name, box in merged.items()]
    for i, group in enumerate(_groups(root)):
        if _is_operation_layer(group):
            continue
        box = _bbox(group)
        if box:
            anonymous.append((group.get("id") or f"p-{i}", box))
    return anonymous


def inspect_nesting(svg_bytes: bytes, gap: float = 3.0) -> dict[str, Any]:
    """Geometry check on an already nested (or stacked) SVG. No rotation."""
    errors: list[str] = []
    parts: list[dict[str, Any]] = []
    if not svg_bytes:
        return {"ok": False, "errors": ["empty svg"], "parts": []}
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError as exc:
        return {"ok": False, "errors": [f"xml: {exc}"], "parts": []}
    boxes = []
    for i, (name, box) in enumerate(_inspect_parts(root)):
        x0, y0, x1, y1 = box
        rec = {
            "index": i,
            "name": name,
            "bbox": [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
            "w": round(x1 - x0, 2),
            "h": round(y1 - y0, 2),
        }
        parts.append(rec)
        boxes.append((x0, y0, x1, y1))
    for i, a in enumerate(boxes):
        for j, b in enumerate(boxes[:i]):
            overlap_x = min(a[2], b[2]) - max(a[0], b[0])
            overlap_y = min(a[3], b[3]) - max(a[1], b[1])
            if overlap_x > -gap + 0.2 and overlap_y > -gap + 0.2:
                errors.append(
                    f"parts {parts[j]['name']} and {parts[i]['name']} closer than {gap} mm (overlap {overlap_x:.1f}×{overlap_y:.1f})"
                )
    bed_w = PAYAS_DEFAULTS["bed_width"]
    bed_h = PAYAS_DEFAULTS["bed_height"]
    if boxes:
        x1 = max(b[2] for b in boxes)
        y1 = max(b[3] for b in boxes)
        if x1 > bed_w + 0.05 or y1 > bed_h + 0.05:
            errors.append(f"nested envelope {x1:.1f}×{y1:.1f} mm exceeds {bed_w}×{bed_h} mm bed")
    return {
        "ok": not errors,
        "errors": errors,
        "parts": parts,
        "part_count": len(parts),
        "gap_mm": gap,
        "rotation": False,
    }


def nest_svg(
    svg_bytes: bytes,
    bed_width: float | None = None,
    bed_height: float | None = None,
    gap: float = 3.0,
    margin: float = 10.0,
    panel_names: list[str] | None = None,
) -> tuple[bytes, dict[str, Any]]:
    """Pack part groups by translation only (no rotate/mirror). Shrink sheet to occupied size."""
    bed_w = float(bed_width or PAYAS_DEFAULTS["bed_width"])
    bed_h = float(bed_height or PAYAS_DEFAULTS["bed_height"])
    info: dict[str, Any] = {
        "ok": False,
        "method": "rectpack",
        "rotation": False,
        "gap_mm": gap,
        "margin_mm": margin,
        "bed_mm": [bed_w, bed_h],
    }
    if not svg_bytes:
        info["errors"] = ["empty svg"]
        return svg_bytes, info
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError as exc:
        info["errors"] = [str(exc)]
        return svg_bytes, info
    groups = _groups(root)
    bounds = []
    live = []
    for group in groups:
        box = _bbox(group)
        if not box:
            continue
        live.append(group)
        bounds.append(box)
    if len(live) < 1:
        info["errors"] = ["no path groups to nest"]
        return svg_bytes, info

    bin_w = max(1.0, bed_w - 2 * margin)
    bin_h = max(1.0, bed_h - 2 * margin)
    for i, (x0, y0, x1, y1) in enumerate(bounds):
        if (x1 - x0) + gap > bin_w + 0.05 or (y1 - y0) + gap > bin_h + 0.05:
            info["errors"] = [
                f"part {i} {(x1 - x0):.1f}×{(y1 - y0):.1f} mm does not fit the {bed_w:.0f}×{bed_h:.0f} mm bed (no rotate/mirror)"
            ]
            return svg_bytes, info

    placed: list = []
    n_bins = 1
    while n_bins <= 12:
        packer = newPacker(rotation=False)
        order = sorted(
            range(len(bounds)),
            key=lambda i: -((bounds[i][2] - bounds[i][0]) * (bounds[i][3] - bounds[i][1])),
        )
        for i in order:
            x0, y0, x1, y1 = bounds[i]
            packer.add_rect((x1 - x0) + gap, (y1 - y0) + gap, rid=i)
        for _ in range(n_bins):
            packer.add_bin(bin_w, bin_h)
        packer.pack()
        placed = packer.rect_list()
        if len(placed) == len(live):
            break
        n_bins += 1
    if len(placed) != len(live):
        info["errors"] = [f"rectpack placed {len(placed)}/{len(live)} parts; they do not fit {n_bins - 1} sheets"]
        info["sheets"] = n_bins - 1
        return svg_bytes, info

    by_bin: dict[int, list] = {}
    for bin_id, x, y, w, h, index in placed:
        by_bin.setdefault(int(bin_id), []).append((index, x, y, w, h))
    sheet_svgs: list[bytes] = []
    sheet_meta: list[dict[str, Any]] = []
    first_placements: list[dict[str, Any]] = []
    first_out = svg_bytes
    first_occ = [bed_w, bed_h]
    for sheet_i, bin_id in enumerate(sorted(by_bin)):
        items = by_bin[bin_id]
        out, placements, occupied = _render_sheet(
            svg_bytes, bounds, items, gap, margin, panel_names, bed_w, bed_h, sheet_i
        )
        sheet_svgs.append(out)
        sheet_meta.append({"n": sheet_i + 1, "occupied_mm": occupied, "part_count": len(placements), "placements": placements})
        if sheet_i == 0:
            first_placements = placements
            first_out = out
            first_occ = occupied

    occ = first_occ
    area = occ[0] * occ[1]
    used = sum(p["w"] * p["h"] for p in first_placements)
    info.update(
        {
            "ok": True,
            "errors": [],
            "occupied_mm": occ,
            "utilization": round(used / area, 3) if area else 0,
            "part_count": len(live),
            "placements": first_placements,
            "sheets": len(sheet_svgs),
            "sheet_meta": sheet_meta,
            "_sheet_svgs": sheet_svgs,
        }
    )
    geom = inspect_nesting(first_out, gap=gap)
    if not geom["ok"]:
        info["ok"] = False
        info["errors"] = geom["errors"]
    return first_out, info


def _render_sheet(
    src_bytes: bytes,
    bounds: list[tuple[float, float, float, float]],
    items: list[tuple[Any, ...]],
    gap: float,
    margin: float,
    panel_names: list[str] | None,
    bed_w: float,
    bed_h: float,
    sheet_i: int,
) -> tuple[bytes, list[dict[str, Any]], list[float]]:
    root_in = ET.fromstring(src_bytes)
    groups = _groups(root_in)
    live: list[ET.Element] = []
    for group in groups:
        if _bbox(group):
            live.append(group)
    ns = "http://www.w3.org/2000/svg"
    ET.register_namespace("", ns)
    out_root = ET.Element(f"{{{ns}}}svg")
    placements: list[dict[str, Any]] = []
    right = margin
    bottom = margin
    for index, x, y, w, h in items:
        group = live[int(index)]
        x0, y0, _x1, _y1 = bounds[int(index)]
        dx = margin + x - x0
        dy = margin + y - y0
        fallback = group.get("id") or f"p-{index}"
        name = ""
        if panel_names and 0 <= int(index) < len(panel_names) and panel_names[int(index)]:
            name = str(panel_names[int(index)])
        name = name or fallback
        group.set("id", fallback)
        group.set("data-panel", name)
        group.set("data-sheet", str(sheet_i + 1))
        for el in list(group.iter()):
            if el.tag.split("}")[-1].lower() != "path":
                continue
            d = el.get("d") or ""
            if not d.strip():
                continue
            try:
                el.set("d", parse_path(d).translated(complex(dx, dy)).d())
            except Exception:
                continue
        right = max(right, margin + x + w - gap)
        bottom = max(bottom, margin + y + h - gap)
        placements.append(
            {
                "name": name,
                "sheet": sheet_i + 1,
                "x": round(margin + x, 2),
                "y": round(margin + y, 2),
                "w": round(w - gap, 2),
                "h": round(h - gap, 2),
            }
        )
        out_root.append(group)
    sheet_w = min(bed_w, round(right + margin, 2))
    sheet_h = min(bed_h, round(bottom + margin, 2))
    out_root.set("width", f"{sheet_w:.2f}mm")
    out_root.set("height", f"{sheet_h:.2f}mm")
    out_root.set("viewBox", f"0 0 {sheet_w:.3f} {sheet_h:.3f}")
    out_root.set("data-layout", "compact")
    out_root.set("data-sheet", str(sheet_i + 1))
    out_root.set("data-gap", str(gap))
    out_root.set("data-margin", str(margin))
    ET.register_namespace("", ns)
    out = ET.tostring(out_root, encoding="utf-8", xml_declaration=True)
    return out, placements, [sheet_w, sheet_h]
