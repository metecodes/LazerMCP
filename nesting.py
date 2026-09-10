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
    groups = _groups(root)
    boxes = []
    for i, group in enumerate(groups):
        box = _bbox(group)
        if not box:
            continue
        x0, y0, x1, y1 = box
        rec = {
            "index": i,
            "name": group.get("data-panel") or group.get("id") or f"p-{i}",
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

    packer = newPacker(rotation=False)
    for i, (x0, y0, x1, y1) in enumerate(bounds):
        packer.add_rect((x1 - x0) + gap, (y1 - y0) + gap, rid=i)
    packer.add_bin(max(1.0, bed_w - 2 * margin), max(1.0, bed_h - 2 * margin))
    packer.pack()
    placed = packer.rect_list()
    if len(placed) != len(live):
        info["errors"] = [f"rectpack placed {len(placed)}/{len(live)} parts; they do not fit the bed"]
        return svg_bytes, info

    right = margin
    bottom = margin
    placements = []
    for _bin, x, y, w, h, index in placed:
        group = live[index]
        x0, y0, x1, y1 = bounds[index]
        dx = margin + x - x0
        dy = margin + y - y0
        name = group.get("id") or f"p-{index}"
        group.set("data-panel", name)
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
                "x": round(margin + x, 2),
                "y": round(margin + y, 2),
                "w": round(w - gap, 2),
                "h": round(h - gap, 2),
            }
        )

    sheet_w = min(bed_w, round(right + margin, 2))
    sheet_h = min(bed_h, round(bottom + margin, 2))
    root.set("width", f"{sheet_w:.2f}mm")
    root.set("height", f"{sheet_h:.2f}mm")
    root.set("viewBox", f"0 0 {sheet_w:.3f} {sheet_h:.3f}")
    root.set("data-layout", "compact")
    root.set("data-gap", str(gap))
    root.set("data-margin", str(margin))
    ET.register_namespace("", "http://www.w3.org/2000/svg")
    out = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    area = sheet_w * sheet_h
    used = sum(p["w"] * p["h"] for p in placements)
    info.update(
        {
            "ok": True,
            "errors": [],
            "occupied_mm": [sheet_w, sheet_h],
            "utilization": round(used / area, 3) if area else 0,
            "part_count": len(placements),
            "placements": placements,
        }
    )
    geom = inspect_nesting(out, gap=gap)
    if not geom["ok"]:
        info["ok"] = False
        info["errors"] = geom["errors"]
    return out, info
