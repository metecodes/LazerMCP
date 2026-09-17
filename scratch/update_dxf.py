import re

with open('c:/Project/boxes-mcp/dxf_export.py', 'r', encoding='utf-8') as f:
    text = f.read()

replacement = '''def svg_bytes_to_dxf(svg_bytes: bytes, step_mm: float = 0.6) -> bytes:
    """Best-effort path dump for toolbox SVG. Cut = red, etch = black/green."""
    from xml.etree import ElementTree as ET

    from shapely.geometry import LineString
    from svgpathtools import parse_path

    if not svg_bytes:
        return geoms_to_dxf([], [])
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError:
        return geoms_to_dxf([], [])
        
    try:
        height_str = root.attrib.get("height", "0")
        import re
        height_str = re.sub(r"[a-zA-Z]+", "", height_str).strip()
        doc_height = float(height_str)
    except Exception:
        doc_height = 0.0

    cuts: list = []
    etches: list = []
    for el in root.iter():
        if el.tag.split("}")[-1].lower() != "path":
            continue
        d = el.get("d") or ""
        if not d.strip():
            continue
        try:
            path = parse_path(d)
            length = float(path.length())
        except Exception:
            continue
        if length < 0.4:
            continue
        n = max(8, min(240, int(length / max(step_mm, 0.2)) + 1))
        pts = []
        for i in range(n + 1):
            pt = path.point(i / n)
            # Transform SVG (Y-down) to DXF (Y-up) without mirroring the geometry itself.
            # Y_dxf = doc_height - Y_svg
            y_svg = float(pt.imag)
            y_dxf = (doc_height - y_svg) if doc_height > 0 else -y_svg
            pts.append((float(pt.real), y_dxf))
        if len(pts) < 2:
            continue
        geom = LineString(pts)
        op = (el.get("data-operation") or "").upper()
        if op in {"GUIDE", "UNKNOWN"}:
            continue
        stroke = f"{el.get('stroke') or ''} {el.get('style') or ''}"
        ident = (el.get("id") or "").upper()
        if op in {"ENGRAVE", "SCORE", "LABEL"} or _stroke_is_etch(stroke) or ident in {"ENGRAVE", "ETCH"}:
            etches.append(geom)
        elif op == "CUT":
            cuts.append(geom)
    return geoms_to_dxf(cuts, etches)'''

# Do a regex replace of the function
text = re.sub(
    r'def svg_bytes_to_dxf.*?return geoms_to_dxf\(cuts, etches\)',
    replacement,
    text,
    flags=re.DOTALL
)

with open('c:/Project/boxes-mcp/dxf_export.py', 'w', encoding='utf-8') as f:
    f.write(text)
