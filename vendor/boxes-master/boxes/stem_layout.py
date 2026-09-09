"""Compact, translation-only sheet layout of already validated Boxes.py panels."""
from xml.etree import ElementTree as ET

from rectpack import newPacker
from svgpathtools import parse_path

NS = "{http://www.w3.org/2000/svg}"


def pack_sheet(data, panels, width, height, gap=3., margin=10., cluster_width=300.):
    root = ET.fromstring(data)
    groups = [g for g in root.findall(NS+"g") if g.findall(NS+"path")]
    if len(groups) != len(panels):
        raise ValueError("Panel group count mismatch")
    packer = newPacker(rotation=False)
    bounds = []
    for i, group in enumerate(groups):
        paths = [parse_path(p.get("d")) for p in group.findall(NS+"path")]
        box = (min(p.bbox()[0] for p in paths), min(p.bbox()[2] for p in paths),
               max(p.bbox()[1] for p in paths), max(p.bbox()[3] for p in paths))
        bounds.append(box)
        packer.add_rect(box[2]-box[0]+gap, box[3]-box[1]+gap, rid=i)
    packer.add_bin(min(cluster_width, width-2*margin)+gap, height-2*margin+gap)
    packer.pack()
    placements = packer.rect_list()
    if len(placements) != len(panels):
        raise ValueError("Panels do not fit compact sheet area")
    right, bottom = margin, margin
    for _, x, y, w, h, index in placements:
        group = groups[index]
        dx, dy = margin+x-bounds[index][0], margin+y-bounds[index][1]
        group.set("data-panel", panels[index][0])
        for path in group.findall(NS+"path"):
            path.set("d", parse_path(path.get("d")).translated(complex(dx, dy)).d())
        for label in group.findall(NS+"text"):
            label.set("transform", f"translate({dx},{dy}) "+label.get("transform", ""))
        right, bottom = max(right, margin+x+w-gap), max(bottom, margin+y+h-gap)
    root.set("width", f"{width:g}mm")
    root.set("height", f"{height:g}mm")
    root.set("viewBox", f"0 0 {width:g} {height:g}")
    root.set("data-layout", "compact")
    root.set("data-gap", str(gap))
    root.set("data-margin", str(margin))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), dict(
        sheet_mm=[width, height], occupied_mm=[round(right-margin, 3), round(bottom-margin, 3)],
        gap_mm=gap, margin_mm=margin, rotation=False, product_sets=1)
