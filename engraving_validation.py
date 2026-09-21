"""Validation for surface engraving and CUT/ENGRAVE operation separation."""
from __future__ import annotations

from typing import Any
from xml.etree import ElementTree as ET

PASS, FAIL, NA = "PASS", "FAIL", "N/A"
_DRAW = {"path", "rect", "circle", "ellipse", "line", "polyline", "polygon"}


def validate(svg_bytes: bytes, edge_clearance_mm: float = 1.0) -> dict[str, list[dict[str, Any]]]:
    geometry: list[dict[str, Any]] = []
    separation: list[dict[str, Any]] = []
    if not svg_bytes:
        return {"geometry": [{"status": FAIL, "note": "no SVG to validate engraving"}],
                "separation": [{"status": FAIL, "note": "no SVG operation evidence"}]}
    root = ET.fromstring(svg_bytes)
    parents = {child: parent for parent in root.iter() for child in parent}

    def inherited(el: ET.Element, key: str) -> str:
        while el is not None:
            if el.get(key) is not None:
                return str(el.get(key))
            el = parents.get(el)
        return ""

    engrave = []
    cuts = []
    for el in root.iter():
        if el.tag.split("}")[-1] not in _DRAW:
            continue
        op = inherited(el, "data-operation").upper()
        (engrave if op == "ENGRAVE" else cuts if op == "CUT" else []).append(el)
    if not engrave:
        geometry.append({"status": NA, "note": "no engraving operations"})
    else:
        bad_color = [el for el in engrave if inherited(el, "stroke").upper() not in {"#FFFF00", "YELLOW"}]
        through = [el for el in engrave if inherited(el, "data-through-cut").lower() in {"1", "true", "yes"}]
        geometry.append({"status": FAIL if bad_color else PASS, "note": f"ENGRAVE yellow #FFFF00: {len(engrave)-len(bad_color)}/{len(engrave)}"})
        separation.append({"status": FAIL if through else PASS, "note": "ENGRAVE remains a non-through surface operation"})
        try:
            from semantic_cad import inspect_design
            doc = inspect_design(svg_bytes)
            parts = [p["_geom"] for p in doc.get("_parts") or []]
            marks = [o["_geom"] for o in doc.get("_objects") or [] if o.get("operation") == "ENGRAVE"]
            mark_rows = [o for o in doc.get("_objects") or [] if o.get("operation") == "ENGRAVE"]
            inside = bool(parts) and all(any(part.buffer(1e-6).covers(mark) for part in parts) for mark in marks)
            clearance = bool(parts) and all(any(part.buffer(1e-6).covers(mark) and part.boundary.distance(mark) + 1e-6 >= edge_clearance_mm for part in parts) for mark in marks)
            geometry.append({"status": PASS if inside else FAIL, "note": "engraving is inside an outer CUT contour" if inside else "engraving extends outside every outer CUT contour"})
            geometry.append({"status": PASS if clearance else FAIL, "note": f"engraving edge clearance ≥ {edge_clearance_mm:g} mm" if clearance else f"engraving violates {edge_clearance_mm:g} mm edge clearance"})
            overlaps = []
            for index, left in enumerate(mark_rows):
                for right in mark_rows[index + 1:]:
                    if left.get("id") != right.get("id") and left["_geom"].intersects(right["_geom"]):
                        overlaps.append((left.get("id"), right.get("id")))
            geometry.append({"status": FAIL if overlaps else PASS, "note": f"unintended engraving overlaps={len(overlaps)}"})
        except Exception as exc:
            geometry.append({"status": FAIL, "note": f"engraving containment could not be verified: {exc}"})
    bad_cut = [el for el in cuts if inherited(el, "stroke").upper() not in {"#FF0000", "RED"}]
    separation.append({"status": FAIL if bad_cut else PASS, "note": f"CUT red #FF0000: {len(cuts)-len(bad_cut)}/{len(cuts)}"})
    try:
        from dxf_export import svg_bytes_to_dxf
        dxf = svg_bytes_to_dxf(svg_bytes).decode("utf-8", errors="replace")
        aci2 = not engrave or ("\nENGRAVE\n" in dxf and "\n62\n2\n" in dxf)
        separation.append({"status": PASS if aci2 else FAIL, "note": "DXF ENGRAVE layer uses ACI 2" if aci2 else "DXF ENGRAVE ACI 2 missing"})
    except Exception as exc:
        separation.append({"status": FAIL, "note": f"DXF operation separation failed: {exc}"})
    return {"geometry": geometry, "separation": separation}
